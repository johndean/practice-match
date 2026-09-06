import statistics
import time
import uuid

import psycopg2
import pytest

from app.config import settings

BUDGET_MS = {"/api/healthz": 20, "/": 15}   # Census B5 and Map engines M3/M4 extend this dict in their tasks


async def p95(client, path: str, n: int = 50) -> float:
    await client.get(path)  # warm-up
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = await client.get(path)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code < 500, path
    return statistics.quantiles(samples, n=20)[18]


@pytest.mark.parametrize("path, budget", sorted(BUDGET_MS.items()))
async def test_p95_within_budget(client, path, budget):
    assert await p95(client, path) <= budget, f"{path} p95 over {budget} ms"


# POST budgets live here as their own tests; BUDGET_MS (GET) is what Census B5 / Map M3-M4 extend (M7 ruling).
async def test_interest_stored_path_p95_within_budget(client, db_ready):
    """Spec 2026-09-06 §3: the full path — validation, three Redis counters, one INSERT — at p95 ≤ 100 ms.
    Every request carries a fresh client IP and a fresh address so no rate limit trips; rows are removed after."""
    tag = uuid.uuid4().hex[:8]
    samples: list[float] = []
    try:
        warm_ip = "10." + ".".join(str((uuid.uuid4().int >> s) & 255) for s in (16, 8, 0))
        await client.post("/api/interest", json={"email": f"perf-{tag}-warm@example.org"}, headers={"x-forwarded-for": warm_ip})  # warm-up (M6, N8: fresh address)
        for i in range(50):
            n = uuid.uuid4().int
            ip = "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))
            t0 = time.perf_counter()
            r = await client.post("/api/interest", json={"email": f"perf-{tag}-{i}@example.org"}, headers={"x-forwarded-for": ip})
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 202, r.text
        assert statistics.quantiles(samples, n=20)[18] <= 100, "/api/interest p95 over 100 ms"
    finally:
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"perf-{tag}-%",))
