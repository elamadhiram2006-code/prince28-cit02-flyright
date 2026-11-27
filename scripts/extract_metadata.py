"""Extract structured metadata from stored FlyRight documents."""

import argparse
import asyncio
import logging

from flyright.config import get_settings
from flyright.db.llm_calls import make_recorder
from flyright.db.session import make_engine, make_sessionmaker
from flyright.llm.extract import run as run_extraction
from flyright.llm.gateway import build_gateway


async def run(
    limit: int,
    rpm: int,
    chars: int,
    retry_failed: bool,
    schema: bool,
) -> None:
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    try:
        gateway = build_gateway(
            settings,
            recorder=make_recorder(session_factory),
        )

        async with session_factory() as session:
            summary = await run_extraction(
                session,
                gateway,
                limit=limit,
                rpm=rpm,
                chars=chars,
                retry_failed=retry_failed,
                schema=schema,
            )

        print("\nExtraction summary")
        print("------------------")
        print(f"Pending: {summary['pending']}")
        print(f"Successful: {summary['ok']}")
        print(f"Repaired: {summary['repaired']}")
        print(f"Failed: {summary['failed']}")
        print(f"Skipped: {summary['skipped']}")
        print(f"Input tokens: {summary['tokens_in']}")
        print(f"Output tokens: {summary['tokens_out']}")
        print(f"Cost (INR): ₹{summary['micro_inr'] / 1_000_000:.6f}")
        print(f"Stopped: {summary['stopped']}")

        for item in summary["results"]:
            print(f"Document {item.document_id}: {item.status} (attempts: {item.attempts})")
            if item.error:
                print(f"  Error: {item.error}")

    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured metadata from FlyRight documents."
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rpm", type=int, default=12)
    parser.add_argument("--chars", type=int, default=6000)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--schema", action="store_true")

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit cannot be negative")
    if args.rpm < 1:
        parser.error("--rpm must be at least 1")
    if args.chars < 1:
        parser.error("--chars must be at least 1")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        run(
            args.limit,
            args.rpm,
            args.chars,
            args.retry_failed,
            args.schema,
        )
    )


if __name__ == "__main__":
    main()
