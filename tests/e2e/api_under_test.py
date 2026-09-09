"""The api web server the Playwright `app` project starts — TEST ONLY (controller amendment A-SL28,
on the round-4 NEEDS_CONTEXT).

`frontend/tests/listing-flows.spec.ts` proves the seller wizard against the real API with no stub
armed, and its photograph half needs a real upload route: `app/api/seller_listings.py`'s
`store_for_request` refuses every write with `503 STORAGE_UNAVAILABLE` until all four `S3_*`
settings are present, and no local or CI environment has a bucket. `moto[s3]` — pytest's own S3
double — is already a dev dependency, so this launcher gives the api under test the same bucket
pytest gives the upload routes: `mock_aws()` started IN THIS PROCESS, the bucket named by
`S3_BUCKET` created in it, then uvicorn run exactly as `frontend/tests/targets.ts`'s bare command
used to run it (`uvicorn app.main:app --port N` — same module string, same loopback default, same
single process, so the mock is live for every request the app serves). `targets.ts` supplies the
four settings as dummies (an AWS-shaped endpoint, a bucket that exists nowhere, made-up keys) under
its "process env wins" rule; nothing about a live target (`PW_APP_URL`) changes, because Playwright
does not start this entry there.

Never shipped: it lives under `tests/`, it imports a dev dependency, and it refuses to start unless
`ENVIRONMENT` is exactly `test` — a launcher whose only safety is where it happens to be invoked
from is one edit away from running somewhere else (`scripts/reset_rate_limits.py`'s rule). Two more
refusals guard the mock itself: every one of the four settings must be present (an unconfigured
store is the very 503 this exists to remove), and the endpoint must be an AWS-shaped host, because
moto intercepts by request URL and a Railway-shaped one would escape to the network with the dummy
credentials (A-SL16 M4 — the first time that fixture was written, it did). Each refusal is a
non-zero exit and ONE line on stderr that never repeats a value from the environment.

    ENVIRONMENT=test S3_ENDPOINT_URL=https://s3.amazonaws.com S3_BUCKET=pm-e2e \\
    S3_ACCESS_KEY_ID=x S3_SECRET_ACCESS_KEY=y poetry run python -m tests.e2e.api_under_test --port 8017

`tests/e2e/test_api_under_test.py` pins every branch with `uvicorn.run` recorded, never run.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

import boto3
import uvicorn
from moto import mock_aws

#: The only environment this may run in, compared exactly.
ALLOWED_ENVIRONMENT = "test"
#: `ObjectStore.from_settings` enables the store only when all four are present.
S3_SETTINGS = ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
#: The host suffix moto's interceptor matches (A-SL16 M4).
INTERCEPTED_SUFFIX = ".amazonaws.com"
#: What `frontend/tests/targets.ts`'s bare command served, unchanged.
APP = "app.main:app"


def refuse(message: str) -> int:
    print(f"[api_under_test] refusing to start: {message}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Playwright app project's api web server, with an in-process moto bucket (test only).")
    parser.add_argument("--port", type=int, required=True, help="the port uvicorn binds, as `targets.ts` passes it")
    args = parser.parse_args(argv)

    if os.environ.get("ENVIRONMENT") != ALLOWED_ENVIRONMENT:
        return refuse(f"ENVIRONMENT must be exactly {ALLOWED_ENVIRONMENT!r}; this launcher is the Playwright suite's and nothing else's")
    missing = [name for name in S3_SETTINGS if not os.environ.get(name)]
    if missing:
        return refuse(f"{', '.join(missing)} must be set; the moto bucket has nothing to answer for without them")
    endpoint = os.environ["S3_ENDPOINT_URL"]
    if not endpoint.rstrip("/").split("://", 1)[-1].split("/", 1)[0].endswith(INTERCEPTED_SUFFIX):
        return refuse(f"S3_ENDPOINT_URL must be an AWS-shaped host (*{INTERCEPTED_SUFFIX}) for moto to intercept it; anything else would reach the network")

    bucket = os.environ["S3_BUCKET"]
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        print(f"[api_under_test] moto bucket {bucket} ready; serving {APP} on port {args.port}", file=sys.stderr)
        uvicorn.run(APP, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
