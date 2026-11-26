"""Compare versioned classification prompts against a labelled test set."""

import argparse
import asyncio
import json
from pathlib import Path

from flyright.config import get_settings
from flyright.llm.classify import accuracy, classify, find_leaks
from flyright.llm.gateway import build_gateway
from flyright.llm.prompts import list_versions, load_prompt

ROOT = Path(__file__).resolve().parents[1]
TESTSET = ROOT / "eval" / "prompt_testset.jsonl"
CACHE_DIR = ROOT / "eval" / "cache"


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file."""
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write rows as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_cache(path: Path) -> dict[str, dict]:
    """Load cached predictions, keyed by question."""
    if not path.exists():
        return {}
    return {row["question"]: row for row in read_jsonl(path)}


async def close_gateway(gateway) -> None:
    """Close provider HTTP clients owned by the gateway."""
    for provider in gateway.providers:
        client = getattr(provider, "_client", None)
        if client is not None:
            await client.aclose()


async def compare_version(
    gateway,
    version: str,
    questions: list[dict],
    cache_dir: Path,
) -> tuple[list[dict], int]:
    """Evaluate one prompt version and count failed calls."""
    prompt = load_prompt("classify", version)
    cache_path = cache_dir / f"classify_{version}.jsonl"
    cached = load_cache(cache_path)
    results = []
    failures = 0

    for index, row in enumerate(questions, start=1):
        question = row["question"]
        expected = row["label"]

        previous = cached.get(question)

        if previous and previous.get("label") == expected:
            result = previous
            print(f"[{version}] {index}/{len(questions)} CACHED")
        else:
            print(f"[{version}] {index}/{len(questions)} Calling LLM...")

            try:
                got, llm_result = await classify(
                    gateway,
                    prompt,
                    version,
                    question,
                )
            except Exception as exc:
                failures += 1
                print(f"  FAILED: {type(exc).__name__}: {exc}")
                continue

            result = {
                "question": question,
                "label": expected,
                "got": got,
                "provider": llm_result.provider,
                "model": llm_result.model,
                "tokens_in": llm_result.tokens_in,
                "tokens_out": llm_result.tokens_out,
                "latency_ms": llm_result.latency_ms,
                "fallback_used": llm_result.fallback_used,
                "cost_inr": llm_result.cost_inr,
            }

            cached[question] = result
            write_jsonl(cache_path, list(cached.values()))

        results.append(result)

    if results:
        correct = sum(r["got"] == r["label"] for r in results)
        print(f"\n{version}: {correct}/{len(results)} correct ({accuracy(results) * 100:.1f}%)")
        print(f"  Evaluated: {len(results)}/{len(questions)}")
        print(f"  Provider/model: {results[-1]['provider']} / {results[-1]['model']}")
        print(f"  Tokens: {sum(r['tokens_in'] + r['tokens_out'] for r in results)}")
        print(f"  Cost: Rs {sum(r['cost_inr'] for r in results):.6f}")
        print(f"  Average latency: {sum(r['latency_ms'] for r in results) / len(results):.0f} ms")
        print(f"  Fallbacks: {sum(r['fallback_used'] for r in results)}")
    else:
        print(f"\n{version}: No questions were successfully evaluated.")

    if failures:
        print(f"  Failed calls: {failures}")

    return results, failures


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="evaluate only one version, for example v4",
    )
    parser.add_argument(
        "--testset",
        type=Path,
        default=TESTSET,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE_DIR,
    )
    args = parser.parse_args()

    questions = read_jsonl(args.testset)

    if not questions:
        raise SystemExit("The evaluation test set is empty.")

    for index, row in enumerate(questions, start=1):
        if not isinstance(row.get("question"), str) or not row["question"].strip():
            raise SystemExit(f"Invalid question in test-set row {index}.")
        if row.get("label") not in ("docs", "personal", "off_topic"):
            raise SystemExit(f"Invalid label in test-set row {index}.")

    versions = [args.version] if args.version else list_versions("classify")

    if not versions:
        raise SystemExit("No classification prompt versions found.")

    available = list_versions("classify")
    for version in versions:
        if version not in available:
            raise SystemExit(f"Prompt version {version} does not exist.")

    print(f"Questions: {len(questions)}")
    print(f"Versions: {', '.join(versions)}")
    print(f"Cache: {args.cache_dir}\n")

    settings = get_settings()
    gateway = build_gateway(settings)
    total_failures = 0

    try:
        for version in versions:
            prompt = load_prompt("classify", version)
            leaks = find_leaks(
                prompt,
                [row["question"] for row in questions],
            )

            print("=" * 60)
            print(f"Evaluating {version}")
            print(f"Test-set leakage: {'FOUND' if leaks else 'NONE'}")

            if leaks:
                for question in leaks:
                    print(f"  LEAK: {question}")

            _, failures = await compare_version(
                gateway,
                version,
                questions,
                args.cache_dir,
            )
            total_failures += failures
            print()

    finally:
        await close_gateway(gateway)

    if total_failures:
        print(f"Evaluation incomplete: {total_failures} LLM calls failed.")
        return 1

    print("Prompt comparison finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
