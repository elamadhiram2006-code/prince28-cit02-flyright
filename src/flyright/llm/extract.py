"""Extract structured metadata from stored FlyRight documents."""

import asyncio
import logging

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


async def extract_metadata(
    session: AsyncSession,
    gateway: LLMGateway,
    document_id: int,
    *,
    prompt_version: str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """Extract, validate, and save metadata for one document."""

    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")

    document = await session.get(Document, document_id)
    if document is None:
        raise ValueError(f"Document {document_id} does not exist")

    pages_result = await session.execute(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_no)
    )
    pages = list(pages_result.scalars().all())

    if not pages:
        return {
            "document_id": document_id,
            "status": "skipped",
            "attempts": 0,
            "error": "Document has no parsed pages",
        }

    document_text = "\n\n".join(f"[Page {page.page_no}]\n{page.text}" for page in pages)[
        :MAX_DOCUMENT_CHARS
    ]

    version = prompt_version or latest_version("extract")
    prompt = load_prompt("extract", version).replace(
        "{document_text}",
        document_text,
    )

    metadata = dict(document.metadata_ or {})
    metadata["extract_status"] = "pending"
    metadata["extract_prompt_version"] = version
    metadata["extract_attempts"] = 0
    metadata.pop("extract_error", None)
    document.metadata_ = metadata
    await session.commit()

    messages = [
        {
            "role": "system",
            "content": (
                "Extract factual metadata from the source document. "
                "Return only valid JSON matching the requested schema."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    last_error = ""
    attempt = 0

    for attempt in range(1, max_attempts + 1):
        result = None

        try:
            result = await gateway.generate(
                messages,
                purpose="extract",
                prompt_version=version,
                temperature=0,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
            )

            extracted = DocMeta.model_validate_json(result.text.strip())

            extracted_data = extracted.model_dump(mode="json")
            metadata = dict(document.metadata_ or {})
            metadata["extract"] = extracted_data
            metadata["doc_kind"] = extracted.doc_kind
            metadata["extract_status"] = "success"
            metadata["extract_prompt_version"] = version
            metadata["extract_attempts"] = attempt
            metadata.pop("extract_error", None)
            document.metadata_ = metadata
            await session.commit()

            return {
                "document_id": document_id,
                "status": "success",
                "attempts": attempt,
                "metadata": extracted_data,
            }

        except (ValueError, TypeError) as exc:
            last_error = str(exc)

        except LLMUnavailable as exc:
            last_error = str(exc)
            break

        if attempt < max_attempts and result is not None:
            messages.extend(
                [
                    {"role": "assistant", "content": result.text},
                    {
                        "role": "user",
                        "content": (
                            "Correct your previous response. Return only valid "
                            "JSON matching the schema. Error: "
                            f"{last_error[:1000]}"
                        ),
                    },
                ]
            )

    metadata = dict(document.metadata_ or {})
    metadata["extract_status"] = "failed"
    metadata["extract_prompt_version"] = version
    metadata["extract_attempts"] = attempt
    metadata["extract_error"] = last_error[:1000]
    document.metadata_ = metadata
    await session.commit()

    return {
        "document_id": document_id,
        "status": "failed",
        "attempts": attempt,
        "error": last_error,
    }


async def extract_pending(
    session: AsyncSession,
    gateway: LLMGateway,
    *,
    limit: int | None = None,
    delay_seconds: float = 1.0,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """Extract metadata from documents that have parsed pages."""

    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    has_pages = select(Page.id).where(Page.document_id == Document.id).exists()
    statement = select(Document).where(has_pages).order_by(Document.id)

    result = await session.execute(statement)
    documents = list(result.scalars().all())

    summary = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "results": [],
    }

    for document in documents:
        if limit is not None and summary["total"] >= limit:
            break

        if (document.metadata_ or {}).get("extract_status") == "success":
            summary["skipped"] += 1
            continue

        if summary["total"] and delay_seconds:
            await asyncio.sleep(delay_seconds)

        outcome = await extract_metadata(
            session,
            gateway,
            document.id,
            max_attempts=max_attempts,
        )

        summary["total"] += 1
        summary[outcome["status"]] += 1
        summary["results"].append(outcome)

    return summary
