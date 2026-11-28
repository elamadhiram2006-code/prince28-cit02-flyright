import hashlib

import pytest

from flyright.workers.ingest import Pace, plan, raw_url, sha256_of


def test_plan_selects_downloaded_records():
    records = [
        {"status": "downloaded", "sha256": "a" * 64},
        {"status": "failed", "sha256": "b" * 64},
        {"status": "downloaded", "sha256": "c" * 64},
    ]
    result = plan(records, set())
    assert len(result) == 2
    assert result[0]["sha256"] == "a" * 64


def test_plan_skips_duplicates_and_known_ids():
    records = [
        {"status": "downloaded", "sha256": "a" * 64},
        {"status": "downloaded", "sha256": "a" * 64},
        {"status": "downloaded", "sha256": "b" * 64},
    ]
    result = plan(records, {"f-" + "b" * 20})
    assert len(result) == 1
    assert result[0]["sha256"] == "a" * 64


def test_plan_filters_source_and_limit():
    records = [
        {"status": "downloaded", "source": "one", "sha256": "a" * 64},
        {"status": "downloaded", "source": "two", "sha256": "b" * 64},
        {"status": "downloaded", "source": "one", "sha256": "c" * 64},
    ]
    result = plan(records, set(), source="one", limit=1)
    assert len(result) == 1
    assert result[0]["sha256"] == "a" * 64


def test_plan_rejects_negative_limit():
    with pytest.raises(ValueError):
        plan([], set(), limit=-1)


def test_raw_url_converts_github_blob_to_raw_commit():
    record = {
        "url": "https://github.com/example/project/blob/main/docs/guide.pdf",
        "via": "git",
        "commit": "abc123",
    }
    assert raw_url(record) == (
        "https://raw.githubusercontent.com/example/project/abc123/docs/guide.pdf"
    )


def test_raw_url_keeps_original_url_without_git_commit():
    record = {"url": "https://example.com/file.pdf"}
    assert raw_url(record) == "https://example.com/file.pdf"


def test_sha256_of_file(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("hello", encoding="utf-8")
    expected = hashlib.sha256(b"hello").hexdigest()
    assert sha256_of(path) == expected


@pytest.mark.asyncio
async def test_pace_waits_between_requests():
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    pace = Pace(12, clock=clock, sleep=sleep)
    await pace.wait()
    await pace.wait()
    await pace.wait()
    assert sleeps == [5.0, 5.0]


def test_pace_rejects_zero_rate():
    with pytest.raises(ValueError):
        Pace(0)
