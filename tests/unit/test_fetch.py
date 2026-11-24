"""Offline unit tests for the polite, resumable downloader."""

import asyncio
import hashlib

import httpx
import pytest

from flyright.ingest.fetch import (
    HostGate,
    Manifest,
    Robots,
    Source,
    _download,
    backoff_delay,
    fetch_all,
    fetch_one,
    file_stem,
    make_client,
    pick_ext,
    read_sources,
    retry_after_seconds,
    slug,
)


def test_slug_is_safe():
    assert slug("DGCA Passenger Rules 2026") == "dgca-passenger-rules-2026"
    assert slug("!!!") == "file"


def test_file_stem_is_stable():
    url = "https://example.com/docs/passenger-rules.pdf"
    assert file_stem(url) == file_stem(url)
    assert file_stem(url).startswith("passenger-rules-")


def test_pick_ext():
    assert pick_ext("https://example.com/file.pdf", "") == ".pdf"
    assert pick_ext("https://example.com/file", "application/pdf") == ".pdf"
    assert pick_ext("https://example.com/file", "unknown/type") == ".bin"


def test_retry_helpers():
    assert 0 <= backoff_delay(2) <= 4
    assert retry_after_seconds("5") == 5.0
    assert retry_after_seconds("invalid") is None
    assert retry_after_seconds(None) is None


def test_read_sources_ignores_comments_and_duplicates(tmp_path):
    path = tmp_path / "sources.csv"
    path.write_text(
        "# reviewed sources\n"
        "url,source,licence,title\n"
        "https://example.com/a.pdf,DGCA,review pending,Rules\n"
        "https://example.com/a.pdf,DGCA,review pending,Rules\n",
        encoding="utf-8",
    )

    sources = read_sources(path)

    assert len(sources) == 1
    assert sources[0].title == "Rules"


def test_read_sources_rejects_invalid_rows(tmp_path):
    path = tmp_path / "sources.csv"
    path.write_text(
        "url,source,licence,title\nfile:///private/file,DGCA,review pending,Invalid\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="http"):
        read_sources(path)


def test_manifest_records_and_resumes(tmp_path):
    path = tmp_path / "data" / "manifest.jsonl"
    root = tmp_path
    downloaded = root / "data" / "raw" / "dgca" / "rules.pdf"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"sample")

    manifest = Manifest(path)
    record = {
        "url": "https://example.com/rules.pdf",
        "status": "downloaded",
        "path": "data/raw/dgca/rules.pdf",
    }
    manifest.add(record)

    reloaded = Manifest(path)

    assert reloaded.done(record["url"], root)
    assert not reloaded.done("https://example.com/other.pdf", root)


@pytest.mark.asyncio
async def test_robots_allows_and_blocks_paths():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: examate-student-bot\nDisallow: /private\n",
            )
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = Robots(client)

        allowed, _ = await robots.check("https://example.com/public/file.pdf")
        blocked, _ = await robots.check("https://example.com/private/file.pdf")

    assert allowed
    assert not blocked


@pytest.mark.asyncio
async def test_robots_fails_closed_on_network_error():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = Robots(client)
        allowed, _ = await robots.check("https://example.com/file.pdf")

    assert not allowed


@pytest.mark.asyncio
async def test_host_gate_applies_delay():
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    gate = HostGate(0.5, fake_sleep)

    await gate.wait("example.com")
    await gate.wait("example.com")

    assert len(waits) == 1
    assert waits[0] > 0


@pytest.mark.asyncio
async def test_download_writes_file_and_hash(tmp_path):
    body = b"sample PDF content"

    def handler(request):
        return httpx.Response(
            200,
            content=body,
            headers={"Content-Type": "application/pdf"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _download(
            client,
            Source(
                "https://example.com/rules.pdf",
                "DGCA",
                "review pending",
            ),
            tmp_path,
            tmp_path / "data" / "raw",
        )

    saved = tmp_path / result["path"]

    assert saved.read_bytes() == body
    assert result["bytes"] == len(body)
    assert result["sha256"] == hashlib.sha256(body).hexdigest()
    assert not saved.with_name(saved.name + ".part").exists()


@pytest.mark.asyncio
async def test_download_rejects_oversized_file(tmp_path, monkeypatch):
    import flyright.ingest.fetch as fetch_module

    monkeypatch.setattr(fetch_module, "MAX_BYTES", 4)

    def handler(request):
        return httpx.Response(200, content=b"12345")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception, match="larger than"):
            await _download(
                client,
                Source(
                    "https://example.com/file.txt",
                    "DGCA",
                    "review pending",
                ),
                tmp_path,
                tmp_path / "data" / "raw",
            )


@pytest.mark.asyncio
async def test_fetch_one_records_robots_block(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /\n",
        )

    async def no_sleep(seconds):
        pytest.fail("A blocked URL must not be retried")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await fetch_one(
            client,
            Source(
                "https://example.com/file.pdf",
                "DGCA",
                "review pending",
                download_approved=True,
            ),
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=Robots(client),
            gate=HostGate(0, no_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=2,
            sleep=no_sleep,
        )

    assert record["status"] == "blocked"
    assert record["error"] == "robots.txt"


@pytest.mark.asyncio
async def test_fetch_one_retries_server_error(tmp_path):
    requests = {"file": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nAllow: /\n",
            )

        requests["file"] += 1

        if requests["file"] == 1:
            return httpx.Response(503)

        return httpx.Response(200, content=b"document")

    async def no_sleep(seconds):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await fetch_one(
            client,
            Source(
                "https://example.com/file.txt",
                "DGCA",
                "review pending",
                download_approved=True,
            ),
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=Robots(client),
            gate=HostGate(0, no_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=2,
            sleep=no_sleep,
        )

    assert record["status"] == "downloaded"
    assert record["attempts"] == 2
    assert requests["file"] == 2


@pytest.mark.asyncio
async def test_fetch_one_does_not_retry_permanent_error(tmp_path):
    requests = {"file": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nAllow: /\n",
            )

        requests["file"] += 1
        return httpx.Response(404)

    async def no_sleep(seconds):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await fetch_one(
            client,
            Source(
                "https://example.com/missing.pdf",
                "DGCA",
                "review pending",
                download_approved=True,
            ),
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=Robots(client),
            gate=HostGate(0, no_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=4,
            sleep=no_sleep,
        )

    assert record["status"] == "failed"
    assert record["http_status"] == 404
    assert requests["file"] == 1


@pytest.mark.asyncio
async def test_fetch_all_skips_existing_download(tmp_path):
    source = Source(
        "https://example.com/existing.pdf",
        "DGCA",
        "review pending",
    )

    saved = tmp_path / "data" / "raw" / "dgca" / "existing.pdf"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"already downloaded")

    manifest = Manifest(tmp_path / "data" / "manifest.jsonl")
    manifest.add(
        {
            "url": source.url,
            "status": "downloaded",
            "path": saved.relative_to(tmp_path).as_posix(),
        }
    )

    def handler(request):
        pytest.fail("A completed download must not make another request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        counts = await fetch_all(
            [source],
            root=tmp_path,
            client=client,
        )

    assert counts["skipped"] == 1
    assert counts["downloaded"] == 0


@pytest.mark.asyncio
async def test_fetch_all_downloads_and_writes_manifest(tmp_path):
    source = Source(
        "https://example.com/new.pdf",
        "DGCA",
        "review pending",
        "New document",
        download_approved=True,
    )

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nAllow: /\n",
            )

        return httpx.Response(200, content=b"new document")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        counts = await fetch_all(
            [source],
            root=tmp_path,
            client=client,
            per_host_delay=0,
        )

    assert counts["downloaded"] == 1
    assert counts["failed"] == 0

    manifest = Manifest(tmp_path / "data" / "manifest.jsonl")
    assert manifest.records[source.url]["status"] == "downloaded"


@pytest.mark.asyncio
async def test_fetch_all_counts_blocked_sources(tmp_path):
    source = Source(
        "https://example.com/private.pdf",
        "DGCA",
        "review pending",
    )

    def handler(request):
        return httpx.Response(
            200,
            text="User-agent: *\nDisallow: /\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        counts = await fetch_all(
            [source],
            root=tmp_path,
            client=client,
        )

    assert counts["blocked"] == 1
    assert counts["downloaded"] == 0


def test_make_client_sets_user_agent_and_limits():
    async def check():
        client = make_client(max_concurrency=2)

        try:
            assert "User-Agent" in client.headers
            assert client.timeout.connect == 10.0
        finally:
            await client.aclose()

    asyncio.run(check())


@pytest.mark.parametrize("status_code", [403, 404, 503])
@pytest.mark.asyncio
async def test_robots_fails_closed_on_http_error(status_code):
    def handler(request):
        return httpx.Response(status_code)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = Robots(client)
        allowed, _ = await robots.check("https://example.com/file.pdf")

    assert not allowed


@pytest.mark.asyncio
async def test_fetch_one_blocks_unapproved_source(tmp_path):
    def handler(request):
        pytest.fail("Unapproved sources must not make network requests")

    async def no_sleep(seconds):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await fetch_one(
            client,
            Source(
                "https://example.com/unapproved.pdf",
                "DGCA",
                "review pending",
            ),
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=Robots(client),
            gate=HostGate(0, no_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=2,
            sleep=no_sleep,
        )

    assert record["status"] == "blocked"
    assert record["error"] == "download permission not approved"
    assert record["download_approved"] is False
