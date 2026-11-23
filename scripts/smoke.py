import os
import sys

import httpx


def main():
    base_url = os.environ.get("LIVE_URL")
    expected_sha = os.environ.get("EXPECTED_SHA")

    if not base_url:
        print("ERROR: LIVE_URL is not set")
        sys.exit(1)

    if not expected_sha:
        print("ERROR: EXPECTED_SHA is not set")
        sys.exit(1)

    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/health",
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "ok":
            print("ERROR: Health check failed:", data)
            sys.exit(1)

        actual_sha = data.get("version")

        if actual_sha != expected_sha:
            print(f"ERROR: Version mismatch. Expected {expected_sha}, got {actual_sha}")
            sys.exit(1)

        print("SUCCESS: Correct FlyRight version is live:", data)

    except Exception as exc:
        print("ERROR: Smoke test failed:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
