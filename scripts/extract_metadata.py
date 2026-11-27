"""Extract structured metadata from stored FlyRight documents."""

import argparse
import asyncio
import logging

from flyright.config import get_settings
from flyright.db.llm_calls import make_recorder
from flyright.db.session import make_engine, make_sessionmaker
from flyright.llm.extract import extract_pending
from flyright.llm.gateway import build_gateway


async def run(limit: int, delay: float) -> None:
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    try:
        gateway = build_gateway(
            settings,
            recorder=make_recorder(session_factory),
        )

        async with session_factory() as session:
            summary = await extract_pending(
                session,
                gateway,
                limit=limit,
                delay_seconds=delay,
            )

        print("\nExtraction summary")
        print("------------------")
        print(f"Processed: {summary['total']}")
        print(f"Successful: {summary['success']}")
        print(f"Failed: {summary['failed']}")
        print(f"Skipped: {summary['skipped']}")

        for item in summary["results"]:
            print(
                f"Document {item['document_id']}: {item['status']} (attempts: {item['attempts']})"
            )
            if item["status"] == "failed":
                print(f"  Error: {item.get('error', 'Unknown error')}")

    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured metadata from FlyRight documents."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum documents to inspect (default: 5).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between documents (default: 1).",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.delay < 0:
        parser.error("--delay cannot be negative")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.limit, args.delay))


if __name__ == "__main__":
    main()
