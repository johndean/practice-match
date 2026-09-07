import pytest

from tests.perf.gate import gate_p95, p95_of


async def _measure_seq(runs):
    it = iter(runs)

    async def measure():
        return next(it)
    return measure


async def test_passes_first_time_without_a_second_measurement(capsys):
    calls = []

    async def measure():
        calls.append(1); return [5.0] * 50
    assert await gate_p95(measure, 100, label="x") == 5.0
    assert calls == [1]


async def test_a_stalled_first_run_is_re_measured_once_and_passes(capsys):
    measure = await _measure_seq([[7.0] * 45 + [150.0, 112.0, 120.0, 116.0, 53.0], [7.0] * 50])
    got = await gate_p95(measure, 100, label="/api/interest")
    assert got == 7.0
    out = capsys.readouterr().out
    assert "first p95" in out and "re-measured" in out and "150" in out


async def test_a_regression_fails_twice_with_both_sample_sets(capsys):
    measure = await _measure_seq([[130.0] * 50, [128.0] * 50])
    with pytest.raises(AssertionError) as e:
        await gate_p95(measure, 100, label="/api/interest")
    assert "re-measured: p95 128.0 ms" in str(e.value) and "first p95 130.0" in str(e.value)


def test_p95_of_is_the_95th_percentile_by_rank():
    # Deviation from the brief (Task 15): the brief's own draft was `ordered[round(0.95*n) - 1]`,
    # which gives 95.0 here. The function this module actually moves verbatim is the one
    # `test_api_latency.py` already shipped — `statistics.quantiles(samples, n=20,
    # method="inclusive")[18]` — which the brief itself says to keep if it differs. It does: on
    # 1..100 it returns 95.05, not 95.0 (verified against `statistics.quantiles` directly).
    assert p95_of([float(i) for i in range(1, 101)]) == 95.05
