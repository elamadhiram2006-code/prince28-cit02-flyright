"""Parse downloaded corpus files into pages in Postgres.

Examples:
    uv run python scripts/parse_corpus.py
    uv run python scripts/parse_corpus.py --limit 20
    uv run python scripts/parse_corpus.py --retry-failed
    uv run python scripts/parse_corpus.py --retry-failed --ocr eng
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

from flyright.config import get_settings
from flyright.db.session import make_engine, make_sessionmaker
from flyright.ingest.parse import (
    ParsedDoc,
    ParseError,
    parse_file,
    parse_pdf_ocr,
)
from flyright.ingest.store import (
    document_id,
    failed_paths,
    parsed_ids,
    save_document,
    save_failure,
)

MANIFEST = Path("data/manifest.jsonl")


def load_records() -> list[dict]:
    """Load the newest manifest record per URL for files on disk."""
    latest: dict[str, dict] = {}

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        latest[record["url"]] = record

    return [
        record
        for record in latest.values()
        if record["status"] == "downloaded" and Path(record["path"]).is_file()
    ]


def parse_one(path: Path, ocr_language: str) -> ParsedDoc:
    """Parse normally, using OCR if requested for a scanned PDF."""
    try:
        return parse_file(path)
    except ParseError as error:
        if error.reason != "no_text_layer" or not ocr_language:
            raise

        return parse_pdf_ocr(path, ocr_language)


async def run(args: argparse.Namespace) -> int:
    records = load_records()
    engine = make_engine(get_settings())

    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    pages = 0
    started = time.perf_counter()

    try:
        async with make_sessionmaker(engine)() as session:
            done = await parsed_ids(session)
            failed = await failed_paths(session)
            todo = []

            for record in records:
                doc_id = document_id(record["sha256"])

                if doc_id in done:
                    counts["already_parsed"] += 1
                elif record["path"] in failed and not args.retry_failed:
                    counts["failed_before"] += 1
                else:
                    # Different URLs can point to identical file contents.
                    if doc_id not in done:
                        done.add(doc_id)
                        todo.append(record)

            selected = todo[: args.limit or None]

            for number, record in enumerate(selected, start=1):
                try:
                    parsed = await asyncio.to_thread(
                        parse_one,
                        Path(record["path"]),
                        args.ocr,
                    )

                    await save_document(session, record, parsed)

                    counts["parsed"] += 1
                    pages += len(parsed.pages)

                except ParseError as error:
                    await session.rollback()
                    await save_failure(session, record, error)

                    counts["failed"] += 1
                    reasons[error.reason] += 1

                    print(
                        f"failed  {error.reason:<16} {record['path']}",
                        flush=True,
                    )

                if number % 50 == 0:
                    print(
                        f"... {number} of {len(selected)} files",
                        flush=True,
                    )

    finally:
        await engine.dispose()

    took = time.perf_counter() - started
    summary = " ".join(f"{name}={count}" for name, count in sorted(counts.items()))

    print(f"files={len(records)} {summary} pages={pages} seconds={took:.1f}")

    if reasons:
        print(
            "failure reasons: "
            + ", ".join(f"{reason}={count}" for reason, count in reasons.most_common())
        )

    return 0


def main() -> int:
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="parse at most N new files",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="retry files that failed",
    )
    parser.add_argument(
        "--ocr",
        default="",
        metavar="LANG",
        help="OCR scanned PDFs, e.g. eng",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be zero or a positive number")

    if not MANIFEST.exists():
        print("data/manifest.jsonl not found: collect your corpus first (Day 6)")
        return 1

    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
