"""Extract, validate, cache, and persist structured document metadata."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.db.models import Document, Page
from flyright.llm.doc_meta import DocMeta
from flyright.llm.gateway import LLMGateway, LLMUnavailable
from flyright.llm.prompts import latest_version, load_prompt

logger = logging.getLogger("flyright.llm.extract")

MAX_ATTEMPTS = 3
MAX_DOCUMENT_CHARS = 6000
MAX_COMPLETION_TOKENS = 4096


@dataclass
class Extraction:
    """Result of one metadata extraction."""

    document_id: int
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    repaired: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    cost_inr: float = 0.0
    error: str = ""


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, including one wrapped in Markdown fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def explain(error: Exception | str) -> str:
    """Return a concise explanation of an extraction error."""
    return str(error).strip()[:1000]


async def save(
    session: AsyncSession,
    document: Document,
    extraction: Extraction,
    prompt_version: str,
) -> None:
    """Persist extraction results without overwriting source metadata."""
    metadata = dict(document.metadata_ or {})

    metadata["extract_status"] = extraction.status
    metadata["extract_prompt_version"] = prompt_version
    metadata["extract_attempts"] = extraction.attempts

    if extraction.status == "success":
        metadata["extract"] = extraction.metadata
        metadata["doc_kind"] = extraction.metadata["doc_kind"]
        metadata.pop("extract_error", None)

        cache = dict(metadata.get("extract_cache", {}))
        cache[prompt_version] = extraction.metadata
        metadata["extract_cache"] = cache
    else:
        metadata["extract_error"] = extraction.error[:1000]

    document.metadata_ = metadata
    await session.commit()


async def extract(
    session: AsyncSession,
    gateway: LLMGateway,
    document_id: int,
    *,
    prompt_version: str | None = None,
    chars: int = MAX_DOCUMENT_CHARS,
    max_attempts: int = MAX_ATTEMPTS,
    schema: bool = False,
) -> Extraction:
    """Extract and validate metadata for one document."""
    if chars < 1:
        raise ValueError("chars must be at least 1")
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")

    document = await session.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} does not exist")

    version = prompt_version or latest_version("extract")
    metadata = dict(document.metadata_ or {})

    cached = metadata.get("extract_cache", {}).get(version)
    if cached:
        return Extraction(
            document_id=document_id,
            status="success",
            metadata=cached,
        )

    pages_result = await session.execute(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_no)
    )
    pages = list(pages_result.scalars().all())

    if not pages:
        return Extraction(
            document_id=document_id,
            status="skipped",
            error="Document has no parsed pages",
        )

    document_text = "\n\n".join(f"[Page {page.page_no}]\n{page.text}" for page in pages)[:chars]

    prompt = load_prompt("extract", version)
    if schema:
        prompt += "\n\nRequired JSON schema:\n"
        prompt += json.dumps(DocMeta.model_json_schema(), ensure_ascii=False)

    prompt = prompt.replace("{document_text}", document_text)

    messages = [
        {
            "role": "system",
            "content": (
                "Extract factual metadata from the source document. "
                "Return only a valid JSON object. Never invent facts."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    total_in = 0
    total_out = 0
    total_cost = 0.0
    last_error = ""
    repaired = False

    metadata["extract_status"] = "pending"
    metadata["extract_prompt_version"] = version
    metadata.pop("extract_error", None)
    document.metadata_ = metadata
    await session.commit()

    for attempt in range(1, max_attempts + 1):
        try:
            result = await gateway.generate(
                messages,
                purpose="extract",
                prompt_version=version,
                temperature=0,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
            )

            total_in += result.tokens_in
            total_out += result.tokens_out
            total_cost += result.cost_inr

            try:
                extracted = DocMeta.model_validate(parse_json(result.text))
            except (ValueError, TypeError) as exc:
                last_error = explain(exc)
                if attempt == max_attempts:
                    break

                repaired = True
                messages.extend(
                    [
                        {"role": "assistant", "content": result.text},
                        {
                            "role": "user",
                            "content": (
                                "Repair the previous response. Return only a "
                                "valid JSON object matching the required schema. "
                                f"Validation error: {last_error}"
                            ),
                        },
                    ]
                )
                continue

            extraction = Extraction(
                document_id=document_id,
                status="success",
                metadata=extracted.model_dump(mode="json"),
                attempts=attempt,
                repaired=repaired,
                tokens_in=total_in,
                tokens_out=total_out,
                cost_inr=total_cost,
            )
            await save(session, document, extraction, version)
            return extraction

        except LLMUnavailable as exc:
            last_error = explain(exc)
            break

    extraction = Extraction(
        document_id=document_id,
        status="failed",
        attempts=attempt,
        repaired=repaired,
        tokens_in=total_in,
        tokens_out=total_out,
        cost_inr=total_cost,
        error=last_error,
    )
    await save(session, document, extraction, version)
    return extraction


async def pending(
    session: AsyncSession,
    *,
    retry_failed: bool = False,
) -> list[Document]:
    """Find documents that still need extraction."""
    has_pages = select(Page.id).where(Page.document_id == Document.id).exists()
    statement = select(Document).where(has_pages).order_by(Document.id)

    result = await session.execute(statement)
    documents = list(result.scalars().all())

    return [
        document
        for document in documents
        if (document.metadata_ or {}).get("extract_status") != "success"
        and (retry_failed or (document.metadata_ or {}).get("extract_status") != "failed")
    ]


async def run(
    session: AsyncSession,
    gateway: LLMGateway,
    *,
    limit: int = 0,
    rpm: int = 12,
    chars: int = MAX_DOCUMENT_CHARS,
    retry_failed: bool = False,
    schema: bool = False,
) -> dict[str, Any]:
    """Run extraction at a controlled request rate."""
    if limit < 0:
        raise ValueError("limit cannot be negative")
    if rpm < 1:
        raise ValueError("rpm must be at least 1")

    documents = await pending(session, retry_failed=retry_failed)
    if limit:
        documents = documents[:limit]

    summary = {
        "pending": len(documents),
        "ok": 0,
        "repaired": 0,
        "failed": 0,
        "skipped": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "micro_inr": 0.0,
        "stopped": False,
        "results": [],
    }

    delay = 60.0 / rpm
    consecutive_unavailable = 0

    for index, document in enumerate(documents):
        if index:
            await asyncio.sleep(delay)

        result = await extract(
            session,
            gateway,
            document.id,
            chars=chars,
            schema=schema,
        )

        summary["results"].append(result)
        summary["tokens_in"] += result.tokens_in
        summary["tokens_out"] += result.tokens_out
        summary["micro_inr"] += result.cost_inr * 1_000_000

        if result.status == "success":
            summary["ok"] += 1
            if result.repaired:
                summary["repaired"] += 1
            consecutive_unavailable = 0
        elif result.status == "skipped":
            summary["skipped"] += 1
            consecutive_unavailable = 0
        else:
            summary["failed"] += 1
            if "provider" in result.error.lower() or "unavailable" in result.error.lower():
                consecutive_unavailable += 1
            else:
                consecutive_unavailable = 0

        if consecutive_unavailable >= 2:
            summary["stopped"] = True
            break

    summary["micro_inr"] = round(summary["micro_inr"], 2)
    return summary


# Backward-compatible interface used by existing tests and integrations.


async def extract_metadata(
    session: AsyncSession,
    gateway: LLMGateway,
    document_id: int,
    *,
    prompt_version: str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """Compatibility wrapper for extract()."""
    result = await extract(
        session,
        gateway,
        document_id,
        prompt_version=prompt_version,
        max_attempts=max_attempts,
    )
    return {
        "document_id": result.document_id,
        "status": result.status,
        "attempts": result.attempts,
        "metadata": result.metadata,
        "error": result.error,
    }


async def extract_pending(
    session: AsyncSession,
    gateway: LLMGateway,
    *,
    limit: int | None = None,
    delay_seconds: float = 1.0,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """Compatibility wrapper for the previous batch interface."""
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    query = await session.scalars(select(Document).join(Page).distinct())
    all_documents = query.all()

    skipped = sum(
        1
        for document in all_documents
        if (document.metadata_ or {}).get("extract_status") == "success"
    )

    documents = await pending(session, retry_failed=True)
    summary = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": skipped,
        "results": [],
    }

    for document in documents:
        if limit is not None and summary["total"] >= limit:
            break
        if summary["total"] and delay_seconds:
            await asyncio.sleep(delay_seconds)

        result = await extract(
            session,
            gateway,
            document.id,
            max_attempts=max_attempts,
        )
        item = {
            "document_id": result.document_id,
            "status": result.status,
            "attempts": result.attempts,
            "error": result.error,
            "metadata": result.metadata,
        }
        summary["total"] += 1
        summary[result.status] += 1
        summary["results"].append(item)

    return summary
