"""Wait until a deployed service runs a given commit, then check that it is healthy.

    python scripts/smoke_test.py https://my-service.onrender.com --sha <commit> --timeout 900

Why this exists: "the deploy hook returned 200" only means a deploy was queued. This script
polls /version until the running service reports the commit we pushed, so the pipeline goes
green only when the new code is live. While a deploy is in progress the old version keeps
answering (or the service is briefly unreachable); both count as "not ready yet", not as failure.
Exit code 0 = live and healthy, 1 = timed out.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float = 15):
    """The parsed JSON body, or None when the service is unreachable or answers badly."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, ValueError):
        return None


def wait_for_commit(
    base_url: str,
    expected_sha: str,
    timeout: float = 900,
    interval: float = 10,
    sleep=time.sleep,
    clock=time.monotonic,
    log=print,
) -> bool:
    base = base_url.rstrip("/")
    deadline = clock() + timeout
    attempt = 0
    while True:
        attempt += 1
        info = fetch_json(f"{base}/version")
        running = info.get("commit") if isinstance(info, dict) else None
        if running == expected_sha:
            health = fetch_json(f"{base}/health")
            if isinstance(health, dict) and health.get("status") == "ok":
                log(f"attempt {attempt}: commit {expected_sha[:7]} is live and healthy")
                return True
            log(f"attempt {attempt}: commit {expected_sha[:7]} is live but /health is not ok yet")
        elif running is None:
            log(f"attempt {attempt}: service not reachable yet")
        else:
            log(f"attempt {attempt}: still running {str(running)[:7]}, waiting for {expected_sha[:7]}")
        if clock() + interval > deadline:
            return False
        sleep(interval)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url")
    parser.add_argument("--sha", required=True, help="the commit that must be running")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--interval", type=float, default=10)
    args = parser.parse_args(argv)
    if wait_for_commit(args.base_url, args.sha, args.timeout, args.interval):
        return 0
    print(f"::error::{args.base_url} did not report commit {args.sha[:7]} within {args.timeout:.0f}s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
