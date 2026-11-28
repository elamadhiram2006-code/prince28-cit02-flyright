import httpx
import pytest

from flyright.workers.ingest import Permanent, get_file


@pytest.mark.asyncio
async def test_get_file_returns_existing_local_file(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    path = folder / "sample.pdf"
    path.write_bytes(b"sample")

    async with httpx.AsyncClient() as client:
        result = await get_file(
            {"path": "sample.pdf", "via": "manual"},
            folder,
            client,
        )

    assert result == path


@pytest.mark.asyncio
async def test_get_file_missing_manual_file_is_permanent(tmp_path):
    async with httpx.AsyncClient() as client:
        with pytest.raises(Permanent, match="Manual file is missing"):
            await get_file(
                {"path": "missing.pdf", "via": "manual"},
                tmp_path,
                client,
            )


@pytest.mark.asyncio
async def test_get_file_successful_download(tmp_path, monkeypatch):
    downloaded = tmp_path / "data" / "raw" / "source" / "sample.pdf"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"downloaded content")

    async def fake_fetch_one(*args, **kwargs):
        return {
            "status": "downloaded",
            "path": "data/raw/source/sample.pdf",
        }

    monkeypatch.setattr("flyright.workers.ingest.fetch_one", fake_fetch_one)

    async with httpx.AsyncClient() as client:
        result = await get_file(
            {
                "url": "https://example.com/sample.pdf",
                "source": "source",
                "licence": "public",
            },
            tmp_path,
            client,
        )

    assert result == downloaded
    assert result.read_bytes() == b"downloaded content"


@pytest.mark.asyncio
async def test_get_file_blocked_source_is_permanent(tmp_path, monkeypatch):
    async def fake_fetch_one(*args, **kwargs):
        return {
            "status": "blocked",
            "error": "robots.txt",
        }

    monkeypatch.setattr("flyright.workers.ingest.fetch_one", fake_fetch_one)

    async with httpx.AsyncClient() as client:
        with pytest.raises(Permanent, match="robots.txt"):
            await get_file(
                {
                    "url": "https://example.com/sample.pdf",
                    "source": "source",
                    "licence": "public",
                },
                tmp_path,
                client,
            )


@pytest.mark.asyncio
async def test_get_file_http_404_is_permanent(tmp_path, monkeypatch):
    async def fake_fetch_one(*args, **kwargs):
        return {
            "status": "failed",
            "http_status": 404,
            "error": "HTTP 404",
        }

    monkeypatch.setattr("flyright.workers.ingest.fetch_one", fake_fetch_one)

    async with httpx.AsyncClient() as client:
        with pytest.raises(Permanent, match="HTTP 404"):
            await get_file(
                {
                    "url": "https://example.com/sample.pdf",
                    "source": "source",
                    "licence": "public",
                },
                tmp_path,
                client,
            )


@pytest.mark.asyncio
async def test_get_file_http_503_is_retryable(tmp_path, monkeypatch):
    async def fake_fetch_one(*args, **kwargs):
        return {
            "status": "failed",
            "http_status": 503,
            "error": "HTTP 503",
        }

    monkeypatch.setattr("flyright.workers.ingest.fetch_one", fake_fetch_one)

    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="HTTP 503"):
            await get_file(
                {
                    "url": "https://example.com/sample.pdf",
                    "source": "source",
                    "licence": "public",
                },
                tmp_path,
                client,
            )
