"""Polite, resumable downloader for your corpus.

Downloads only sources with explicit download approval.
Checks robots.txt before requesting source documents.
Preserves partial downloads so interrupted downloads can resume.
"""

import asyncio
import csv
import hashlib
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from protego import Protego

CONTACT = "https://github.com/elamadhiram2006-code/prince28-cit02-flyright"
ROBOTS_TOKEN = "examate-student-bot"
USER_AGENT = f"{ROBOTS_TOKEN}/0.1 (student project; +{CONTACT})"

RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
MAX_WAIT = 120.0
MAX_BYTES = 200 * 1024 * 1024
ATTEMPT_TIMEOUT = 300.0

KNOWN_EXT = {
    ".pdf",
    ".html",
    ".htm",
    ".json",
    ".txt",
    ".md",
    ".mdx",
    ".rst",
    ".adoc",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".zip",
    ".docx",
    ".xlsx",
    ".xls",
}

EXT_BY_TYPE = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/zip": ".zip",
    "application/yaml": ".yaml",
}

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Source:
    url: str
    source: str
    licence: str
    title: str = ""
    download_approved: bool = False


class DownloadError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def slug(text: str, limit: int = 60) -> str:
    """Create a safe filename or directory name."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit] or "file"


def file_stem(url: str) -> str:
    """Create a stable filename from a URL."""
    parts = urlsplit(url)
    last = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1]) or parts.netloc
    name = last.rsplit(".", 1)[0] if "." in last else last
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"{slug(name)}-{digest}"


def pick_ext(url: str, content_type: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in KNOWN_EXT:
        return suffix
    return EXT_BY_TYPE.get(content_type.split(";")[0].strip().lower(), ".bin")


def backoff_delay(
    attempt: int,
    *,
    base: float = 1.0,
    cap: float = 60.0,
) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0, min(cap, base * 2**attempt))


def retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After as seconds or an HTTP date."""
    if not value:
        return None

    value = value.strip()
    if value.isdigit():
        return float(value)

    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)

    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def read_sources(path: Path) -> list[Source]:
    """Read sources.csv. Lines starting with # are notes."""
    sources: list[Source] = []
    seen: set[str] = set()

    with path.open(encoding="utf-8-sig", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.lstrip().startswith("#"))

        for number, row in enumerate(csv.DictReader(lines), start=1):
            url = (row.get("url") or "").strip()
            name = (row.get("source") or "").strip()
            licence = (row.get("licence") or "").strip()

            approved_text = (row.get("download_approved") or "false").strip().lower()

            if approved_text not in {"true", "false"}:
                raise ValueError(f"sources row {number}: download_approved must be true or false")

            download_approved = approved_text == "true"

            if urlsplit(url).scheme not in {"http", "https"}:
                raise ValueError(f"sources row {number}: not an http(s) URL: {url!r}")

            if not name or not licence:
                raise ValueError(f"sources row {number}: source and licence are required: {url}")

            if url not in seen:
                seen.add(url)
                sources.append(
                    Source(
                        url,
                        name,
                        licence,
                        (row.get("title") or "").strip(),
                        download_approved,
                    )
                )

    return sources


class Manifest:
    """Append-only log: newest record for a URL wins."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: dict[str, dict] = {}

        if path.exists():
            text = path.read_text(encoding="utf-8")

            for line in text.splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                self.records[record["url"]] = record

            if text and not text.endswith("\n"):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n")

    def done(self, url: str, root: Path) -> bool:
        record = self.records.get(url)
        return bool(
            record and record["status"] == "downloaded" and (root / record["path"]).is_file()
        )

    def add(self, record: dict) -> None:
        self.records[record["url"]] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class Robots:
    """Fetch robots.txt once per origin and apply its rules."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._rules: dict[str, Protego | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _load(self, origin: str) -> Protego | None:
        try:
            response = await self._client.get(origin + "/robots.txt")
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        return Protego.parse(response.text)

    async def check(self, url: str) -> tuple[bool, float]:
        """Return whether the URL is allowed and its crawl delay."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"

        async with self._locks.setdefault(origin, asyncio.Lock()):
            if origin not in self._rules:
                self._rules[origin] = await self._load(origin)

        rules = self._rules[origin]

        if rules is None:
            return False, 0.0

        return (
            rules.can_fetch(url, ROBOTS_TOKEN),
            float(rules.crawl_delay(ROBOTS_TOKEN) or 0.0),
        )


class HostGate:
    """Leave a gap between requests to the same host."""

    def __init__(self, delay: float, sleep: Sleep) -> None:
        self._delay = delay
        self._sleep = sleep
        self._next_ok: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str, crawl_delay: float = 0.0) -> None:
        async with self._locks.setdefault(host, asyncio.Lock()):
            pause = self._next_ok.get(host, 0.0) - time.monotonic()

            if pause > 0:
                await self._sleep(pause)

            self._next_ok[host] = time.monotonic() + max(
                self._delay,
                crawl_delay,
            )


def make_client(max_concurrency: int = 4) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=max_concurrency),
        follow_redirects=True,
    )


async def _download(
    client: httpx.AsyncClient,
    src: Source,
    root: Path,
    raw_dir: Path,
) -> dict:
    """Download a file and resume an existing partial download."""
    stem = file_stem(src.url)

    url_suffix = Path(urlsplit(src.url).path).suffix.lower()
    part_ext = url_suffix if url_suffix in KNOWN_EXT else ".bin"

    folder = raw_dir / slug(src.source)
    folder.mkdir(parents=True, exist_ok=True)

    part = folder / f"{stem}{part_ext}.part"
    offset = part.stat().st_size if part.exists() else 0

    if offset > MAX_BYTES:
        part.unlink(missing_ok=True)
        raise DownloadError(f"larger than {MAX_BYTES // 2**20} MB")

    headers = {"Accept-Encoding": "identity"}

    if offset:
        headers["Range"] = f"bytes={offset}-"

    async with client.stream(
        "GET",
        src.url,
        headers=headers,
    ) as response:
        status = response.status_code

        if status not in {200, 206}:
            raise DownloadError(
                f"HTTP {status}",
                code=status,
                retry_after=retry_after_seconds(response.headers.get("Retry-After")),
            )

        content_type = response.headers.get("Content-Type", "")
        extension = pick_ext(src.url, content_type)
        name = stem + extension
        target = folder / name

        append = False
        expected_chunk_size: int | None = None

        if status == 206:
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)",
                content_range.strip(),
            )

            if not match:
                raise DownloadError("Invalid or missing Content-Range header")

            range_start, range_end, total = map(int, match.groups())

            if (
                range_start != offset
                or range_end < range_start
                or range_end != total - 1
                or total > MAX_BYTES
            ):
                raise DownloadError("Invalid Content-Range values")

            expected_chunk_size = range_end - range_start + 1
            append = offset > 0

        # If the server ignores Range and returns 200, restart from zero.
        mode = "ab" if append else "wb"

        digest = hashlib.sha256()
        size = 0

        if append:
            with part.open("rb") as existing:
                while chunk := existing.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)

        try:
            with part.open(mode) as handle:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)

                    if size > MAX_BYTES:
                        raise DownloadError(f"larger than {MAX_BYTES // 2**20} MB")

                    digest.update(chunk)
                    handle.write(chunk)

            downloaded_chunk_size = size - (offset if append else 0)

            if expected_chunk_size is not None and downloaded_chunk_size != expected_chunk_size:
                raise DownloadError("Incomplete response body; partial file preserved")

            part.replace(target)

        except DownloadError as exc:
            if "larger than" in str(exc):
                part.unlink(missing_ok=True)
            raise

    return {
        "path": target.relative_to(root).as_posix(),
        "bytes": size,
        "sha256": digest.hexdigest(),
        "content_type": content_type.split(";")[0].strip(),
        "http_status": status,
    }


async def fetch_one(
    client: httpx.AsyncClient,
    src: Source,
    *,
    root: Path,
    raw_dir: Path,
    robots: Robots,
    gate: HostGate,
    slots: asyncio.Semaphore,
    max_attempts: int,
    sleep: Sleep,
) -> dict:
    """Download one approved source with retries."""
    record = {
        "url": src.url,
        "source": src.source,
        "licence": src.licence,
        "title": src.title,
        "download_approved": src.download_approved,
        "via": "http",
    }

    # Permission check happens before any robots or document request.
    if not src.download_approved:
        return record | {
            "status": "blocked",
            "error": "download permission not approved",
            "fetched_at": now_iso(),
        }

    allowed, crawl_delay = await robots.check(src.url)

    if not allowed:
        return record | {
            "status": "blocked",
            "error": "robots.txt",
            "fetched_at": now_iso(),
        }

    host = urlsplit(src.url).netloc
    error, code, attempt = "", None, 0

    for attempt in range(1, max_attempts + 1):
        wait = backoff_delay(attempt - 1)

        async with slots:
            await gate.wait(host, crawl_delay)

            try:
                async with asyncio.timeout(ATTEMPT_TIMEOUT):
                    fields = await _download(client, src, root, raw_dir)

                done = {
                    "status": "downloaded",
                    "attempts": attempt,
                    "fetched_at": now_iso(),
                }

                return record | fields | done

            except DownloadError as exc:
                error, code = str(exc), exc.code

                if code not in RETRYABLE:
                    break

                if exc.retry_after is not None:
                    if exc.retry_after > MAX_WAIT:
                        error = f"{error}: asked to wait {exc.retry_after:.0f} s, run again later"
                        break

                    wait = max(wait, exc.retry_after)

            except (httpx.TransportError, TimeoutError) as exc:
                error, code = type(exc).__name__, None

            except httpx.HTTPError as exc:
                error, code = type(exc).__name__, None
                break

        if attempt < max_attempts:
            await sleep(min(wait, MAX_WAIT))

    failed = {
        "status": "failed",
        "http_status": code,
        "error": error,
        "attempts": attempt,
    }

    return record | failed | {"fetched_at": now_iso()}


async def fetch_all(
    sources: list[Source],
    *,
    root: Path = Path("."),
    max_concurrency: int = 4,
    per_host_delay: float = 0.5,
    max_attempts: int = 4,
    client: httpx.AsyncClient | None = None,
    sleep: Sleep = asyncio.sleep,
    on_result: Callable[[dict], None] | None = None,
) -> dict[str, int]:
    """Download approved sources that are not already downloaded."""
    raw_dir = root / "data" / "raw"
    manifest = Manifest(root / "data" / "manifest.jsonl")

    todo = [src for src in sources if not manifest.done(src.url, root)]

    counts = {
        "downloaded": 0,
        "skipped": len(sources) - len(todo),
        "blocked": 0,
        "failed": 0,
    }

    own_client = client is None
    client = client or make_client(max_concurrency)

    robots = Robots(client)
    gate = HostGate(per_host_delay, sleep)
    slots = asyncio.Semaphore(max_concurrency)

    try:
        tasks = [
            asyncio.create_task(
                fetch_one(
                    client,
                    src,
                    root=root,
                    raw_dir=raw_dir,
                    robots=robots,
                    gate=gate,
                    slots=slots,
                    max_attempts=max_attempts,
                    sleep=sleep,
                )
            )
            for src in todo
        ]

        for finished in asyncio.as_completed(tasks):
            record = await finished
            counts[record["status"]] += 1

            before = manifest.records.get(record["url"], {})

            same_problem = (
                before.get("status"),
                before.get("error"),
            ) == (
                record["status"],
                record.get("error"),
            )

            if record["status"] == "downloaded" or not same_problem:
                manifest.add(record)

            if on_result:
                on_result(record)

    finally:
        if own_client:
            await client.aclose()

    return counts
