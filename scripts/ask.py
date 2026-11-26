"""Ask the FlyRight API and measure the time to the first answer.

Examples:
    uv run python scripts/ask.py "What happens if my flight is cancelled?"
    uv run python scripts/ask.py "Explain denied boarding" --json
    uv run python scripts/ask.py "What are my rights?" --url http://localhost:8000
"""

import argparse
import json
import sys
import time

import httpx


def show_problem(response: httpx.Response) -> int:
    """Display an API error response."""
    try:
        body = json.loads(response.read())
        detail = body.get("detail") or body
    except ValueError:
        detail = response.text[:300]

    print(f"HTTP {response.status_code}: {detail}")
    return 1


def show_summary(info: dict, first: float | None, total: float) -> None:
    """Display model usage and response timing."""
    waited = f"first words after {first:.2f} s, " if first is not None else ""

    print(f"\n--- {info['provider']} / {info['model']}: {waited}total {total:.2f} s")
    print(
        f"    tokens in={info['tokens_in']} out={info['tokens_out']}  "
        f"cost Rs {info['cost_inr']:.6f}  attempts={info['attempts']}  "
        f"fallback={'YES' if info['fallback_used'] else 'no'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="where your API runs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="request one JSON response without streaming",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    url = args.url.rstrip("/") + "/v1/chat"
    payload = {
        "message": args.message,
        "stream": not args.json,
    }

    started = time.perf_counter()
    first = None

    try:
        with httpx.stream(
            "POST",
            url,
            json=payload,
            timeout=120,
        ) as response:
            if response.status_code != 200:
                return show_problem(response)

            if args.json:
                body = json.loads(response.read())
                print(body.pop("answer"))
                show_summary(
                    body,
                    None,
                    time.perf_counter() - started,
                )
                return 0

            event = ""

            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()

                elif line.startswith("data:"):
                    data = json.loads(line[5:])

                    if event == "done":
                        show_summary(
                            data,
                            first,
                            time.perf_counter() - started,
                        )

                    elif event == "error":
                        print(f"\n--- the answer stopped: {data.get('detail')}")
                        return 1

                    else:
                        if first is None:
                            first = time.perf_counter() - started

                        print(data["delta"], end="", flush=True)

                elif not line:
                    event = ""

    except httpx.TransportError as exc:
        print(f"{type(exc).__name__}: is the API running at {args.url}?")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
