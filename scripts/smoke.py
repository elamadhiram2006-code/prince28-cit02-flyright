import os
import sys

import httpx


def main():
    base_url = os.environ.get("LIVE_URL")

    if not base_url:
        print("ERROR: LIVE_URL is not set")
        sys.exit(1)

    try:
        response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=30)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "ok":
            print("ERROR: Health check failed:", data)
            sys.exit(1)

        print("FlyRight is healthy:", data)

    except Exception as exc:
        print("ERROR: Smoke test failed:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
