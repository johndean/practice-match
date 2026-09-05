import statistics
import time

import pytest

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
