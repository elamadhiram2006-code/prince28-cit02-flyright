"""CLI for the polite, resumable source downloader."""

import argparse
import asyncio
from pathlib import Path

from flyright.ingest.fetch import fetch_all, read_sources

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch approved source documents politely and resumably."
    )
    parser.add_argument(
        "command",
        choices=["urls"],
        help="Read URLs from data/sources.csv and fetch eligible sources.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum number of simultaneous downloads (default: 4).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Minimum delay between requests to the same host (default: 0.5).",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=4,
        help="Maximum attempts for retryable failures (default: 4).",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if args.concurrency < 1 or args.delay < 0 or args.attempts < 1:
        print("Concurrency and attempts must be positive; delay cannot be negative.")
        return 2

    try:
        sources = read_sources(SOURCES)
    except (OSError, ValueError) as exc:
        print(f"Could not read source list: {exc}")
        return 1

    print(f"sources={len(sources)}")
    counts = await fetch_all(
        sources,
        root=ROOT,
        max_concurrency=args.concurrency,
        per_host_delay=args.delay,
        max_attempts=args.attempts,
        on_result=lambda record: print(f"{record['status']}: {record['source']} — {record['url']}"),
    )
    print(" ".join(f"{key}={value}" for key, value in counts.items()))
    return 1 if counts["failed"] else 0


def main() -> None:
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        print("\nDownload interrupted.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
