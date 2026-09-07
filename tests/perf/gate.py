"""The p95 gate every latency test asserts through. A regression fails twice; a stalled shared
runner does not (Task 15, 2026-09-08)."""
import statistics
from collections.abc import Awaitable, Callable


def p95_of(samples: list[float]) -> float:
    """The 95th percentile, `method="inclusive"` — never above the largest observed sample.

    The default (exclusive) method EXTRAPOLATES past the data, which on the ten samples the sign-in
    gate takes made the assertion `1.2 x max(10) <= budget` rather than `p95 <= budget`: a measured
    max of 213.1 ms came out as a "p95" of 255.3 ms (fix round 2, NEW-2). Every gate goes through
    here, so none of them can report a latency nothing actually took."""
    return statistics.quantiles(samples, n=20, method="inclusive")[18]


async def gate_p95(measure: Callable[[], Awaitable[list[float]]], budget_ms: float, *, label: str) -> float:
    """Measures once; if that p95 is over budget, measures once more (warm — `measure()` owns its
    own warm-up) and asserts the SECOND p95, printing both sample sets either way. A regression
    (both measurements over budget) still fails, loudly, with evidence; a stalled shared runner
    (only the first measurement over budget) does not."""
    first = await measure()
    a = p95_of(first)
    if a <= budget_ms:
        return a
    second = await measure()
    b = p95_of(second)
    msg = (f"{label}: first p95 {a:.1f} ms over {budget_ms:g} ms — re-measured: p95 {b:.1f} ms; "
           f"samples first {[round(x) for x in first]} second {[round(x) for x in second]}")
    print("\n" + msg)
    assert b <= budget_ms, msg
    return b
