"""Download, parse, and extract one ingestion item."""

import asyncio
import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from arq import Retry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.db.models import Document, IngestItem, Page
from flyright.ingest.fetch import (
    RETRYABLE,
    HostGate,
    Robots,
    Source,
    fetch_one,
)
from flyright.ingest.parse import ParseError, parse_file
from flyright.ingest.store import document_id, save_document, save_failure
from flyright.llm.extract import extract
from flyright.llm.prompts import latest_version


class Permanent(Exception):
    """An error that should not be retried."""


def plan(
    records: list[dict],
    done_ids: set[str],
    *,
    source: str = "",
    limit: int = 0,
) -> list[dict]:
    """Select downloaded records not already known, deduplicated by content."""
    if limit < 0:
        raise ValueError("limit cannot be negative")

    selected: list[dict] = []
    seen = set(done_ids)

    for record in records:
        if record.get("status") != "downloaded":
            continue
        if source and record.get("source") != source:
            continue

        digest = record.get("sha256")
        if not digest:
            continue

        identifier = document_id(digest)
        if identifier in seen:
            continue

        seen.add(identifier)
        selected.append(record)

        if limit and len(selected) >= limit:
            break

    return selected


GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+/[^/]+)/blob/[^/]+/(.+)$")


def raw_url(record: dict) -> str:
    """Convert an approved GitHub blob URL to its raw commit URL."""
    url = record.get("url", "")

    if record.get("via") != "git" or not record.get("commit"):
        return url

    match = GITHUB_BLOB.match(url)
    if not match:
        return url

    repository, path = match.groups()
    commit = str(record["commit"])

    return f"https://raw.githubusercontent.com/{repository}/{commit}/{path}"


def sha256_of(path: Path) -> str:
    """Calculate a file's SHA-256 digest without loading it all into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


class Pace:
    """Space requests evenly to respect a configured requests-per-minute rate."""

    def __init__(
        self,
        per_minute: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        if per_minute <= 0:
            raise ValueError("per_minute must be greater than zero")

        self.interval = 60.0 / per_minute
        self.clock = clock
        self.sleep = sleep
        self.next_ok = 0.0

    async def wait(self) -> None:
        now = self.clock()
        delay = max(0.0, self.next_ok - now)

        if delay:
            await self.sleep(delay)

        self.next_ok = max(now, self.next_ok) + self.interval


async def get_file(
    record: dict,
    folder: Path,
    client: httpx.AsyncClient,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> Path:
    """Find a local file or download an approved HTTP source."""
    folder = Path(folder)
    original_path = Path(record.get("path", ""))
    local_path = original_path if original_path.is_absolute() else folder / original_path

    if original_path and local_path.is_file():
        return local_path

    if record.get("via") == "manual":
        raise Permanent(f"Manual file is missing: {record.get('path', '')}")

    url = raw_url(record)
    if not url or urlsplit(url).scheme not in {"http", "https"}:
        raise Permanent("Record does not contain a valid HTTP(S) URL")

    source = Source(
        url=url,
        source=record.get("source") or "unknown",
        licence=record.get("licence") or "unknown",
        title=record.get("title") or "",
        download_approved=True,
    )

    result = await fetch_one(
        client,
        source,
        root=folder,
        raw_dir=folder / "data" / "raw",
        robots=Robots(client),
        gate=HostGate(0.5, sleep),
        slots=asyncio.Semaphore(1),
        max_attempts=3,
        sleep=sleep,
    )

    if result["status"] == "downloaded":
        return folder / result["path"]

    error = result.get("error") or "Download failed"
    status_code = result.get("http_status")

    if result["status"] == "blocked":
        raise Permanent(error)

    if status_code is not None and status_code not in RETRYABLE:
        raise Permanent(f"HTTP {status_code}: {error}")

    if result["status"] == "failed":
        raise RuntimeError(error)

    raise Permanent(error)


async def process(
    ctx: dict,
    session: AsyncSession,
    item: IngestItem,
) -> tuple[str, int]:
    """Process one item idempotently and return its status and page count."""
    record = item.record

    if not isinstance(record, dict):
        raise Permanent("Ingestion item has no valid record")

    settings = ctx["settings"]
    manifest_path = Path(settings.manifest_file)

    root = (
        manifest_path.parent.parent if manifest_path.parent.name == "data" else manifest_path.parent
    )

    path = await get_file(record, root, ctx["http"])
    digest = sha256_of(path)
    identifier = document_id(digest)

    document = await session.scalar(select(Document).where(Document.external_id == identifier))

    if document is None:
        stored_record = dict(record)
        stored_record["sha256"] = digest

        try:
            stored_record["path"] = path.relative_to(root).as_posix()
        except ValueError:
            stored_record["path"] = str(path)

        stored_record.setdefault("url", record.get("url", ""))
        stored_record.setdefault("source", "unknown")
        stored_record.setdefault("licence", "unknown")

        try:
            parsed = parse_file(path)
        except ParseError as exc:
            await save_failure(session, stored_record, exc)
            raise Permanent(f"Parsing failed: {exc.reason}") from exc

        await save_document(session, stored_record, parsed)

        document = await session.scalar(select(Document).where(Document.external_id == identifier))

        if document is None:
            raise RuntimeError("Parsed document was not saved")

    pages = await session.scalar(select(func.count(Page.id)).where(Page.document_id == document.id))
    page_count = pages or 0

    extraction_settings = ctx.get("extract") or {}
    version = extraction_settings.get("version") or latest_version("extract", settings.prompts_dir)

    metadata = document.metadata_ or {}
    already_extracted = (
        metadata.get("extract_status") == "success"
        and metadata.get("extract_prompt_version") == version
    )

    if already_extracted:
        return "done", page_count

    if page_count == 0:
        return "skipped", 0

    pace = ctx.get("pace")
    if pace is not None:
        await pace.wait()

    result = await extract(
        session,
        ctx["gateway"],
        document.id,
        prompt_version=version,
        chars=int(extraction_settings.get("chars", 6000)),
        max_attempts=3,
        schema=bool(extraction_settings.get("schema", False)),
    )

    if result.status == "failed":
        raise RuntimeError(result.error or "Metadata extraction failed")

    if result.status == "skipped":
        return "skipped", page_count

    return "done", page_count


async def ingest_document(ctx: dict, item_id: int) -> str:
    """Run one queued item, retry transient failures, and dead-letter final failures."""
    settings = ctx["settings"]
    sessionmaker = ctx["sessionmaker"]
    max_tries = settings.ingest_max_tries

    async with sessionmaker() as session:
        item = await session.get(IngestItem, item_id)

        if item is None:
            return "ignored"

        if item.status not in {"queued", "running"}:
            return "ignored"

        if item.attempts >= max_tries:
            item.status = "failed"
            item.error = "Maximum attempts reached"
            await session.commit()
            return "failed"

        item.attempts += 1
        attempt = item.attempts
        item.status = "running"
        item.error = ""
        await session.commit()

        try:
            status, pages = await process(ctx, session, item)

        except Permanent as exc:
            await session.rollback()
            item = await session.get(IngestItem, item_id)

            if item is None:
                return "ignored"

            item.status = "failed"
            item.error = str(exc)[:2000]
            await session.commit()
            return "failed"

        except Exception as exc:
            await session.rollback()
            item = await session.get(IngestItem, item_id)

            if item is None:
                return "ignored"

            item.error = str(exc)[:2000]

            if attempt >= max_tries:
                item.status = "failed"
                await session.commit()
                return "failed"

            item.status = "queued"
            await session.commit()
            raise Retry(defer=attempt * 30) from exc

        item = await session.get(IngestItem, item_id)

        if item is None:
            return "ignored"

        item.status = status
        item.pages = pages
        item.error = ""
        await session.commit()

        return status
