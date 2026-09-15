"""Re-derive the admin Data Sources tab's two layout caps in a real browser (A38, review F11).

`app.census.registry.SOURCE_SUBLINE_CAP` and `DATASET_SUBLINE_CAP` are MEASURED numbers, and
`tests/census/test_registry.py` holds every `dataset_registry` row to them: the tab prints `notes`,
`license_name`, `refresh_cadence` and the vintages verbatim into the approved design's own table,
by ruling, because it is the platform's legal gate and hidden text on it is not an option.

A number measured once and then written down goes stale the day the admin table's grid, its
padding, the design's 12.5 px/1.5 sub-line type or the card's own max-width moves -- so this is the
committed re-derivation, in the shape `scripts/measure_area_breaks.py` established for
`AREA_LAYERS`. It runs the probe that produced the numbers (`frontend/tests/smoke.spec.ts`,
"A38 -- the measured sub-line caps", three cases in real Chromium at the design's own 1440 x 940)
and compares what the probe prints with the two constants. A cap that no longer buys two lines, or
a design row that is no longer 94 px tall in a 258/376 px pair of columns, exits non-zero.

    poetry run python scripts/measure_source_subline_cap.py

It needs the same local preconditions the Playwright suite does -- `docker compose -f
docker-compose.dev.yml up -d`, and `DATABASE_URL`/`REDIS_URL` pointing at that stack -- because the
probe drives the real app against the real API. Nothing here writes to the repository: the caps are
reported, never rewritten, so moving one stays a ruled act.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from app.census.registry import DATASET_SUBLINE_CAP, SOURCE_SUBLINE_CAP

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
GREP = "measured sub-line caps"

# What the design itself is, re-asserted by the probe's third case: its tallest fixture row and the
# two column widths every character count below is a count OF.
DESIGN_TALLEST_PX = 94
DATASET_COLUMN_PX = 258
SOURCE_COLUMN_PX = 376


def run_probe() -> str:
    """The Playwright case's stdout. Not captured through a JSON file on purpose: the probe is a
    test first, so it stays runnable and readable on its own."""
    cmd = ["npx", "playwright", "test", "--config=tests/playwright.config.ts", "--project=app", "smoke.spec.ts", "-g", GREP]
    proc = subprocess.run(cmd, cwd=FRONTEND, capture_output=True, text=True, check=False, env=os.environ.copy())
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"\nthe probe FAILED (exit {proc.returncode}) -- one of the caps no longer buys two lines")
        raise SystemExit(proc.returncode)
    return proc.stdout


def measured(out: str, name: str) -> dict[str, int]:
    line = re.search(rf"\[A38-CAPS\] {name}=(\d+) (.*)", out)
    if line is None:
        raise SystemExit(f"the probe printed no {name} measurement; did the case name change?")
    values = {"cap": int(line.group(1))}
    values.update({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line.group(2))})
    return values


def main() -> int:
    out = run_probe()
    source = measured(out, "SOURCE_SUBLINE_CAP")
    dataset = measured(out, "DATASET_SUBLINE_CAP")
    design = measured(out, "designTallestPx")

    print("\n--- measured against app/census/registry.py ---")
    bad = []
    for name, probe, constant in (("SOURCE_SUBLINE_CAP", source["cap"], SOURCE_SUBLINE_CAP),
                                  ("DATASET_SUBLINE_CAP", dataset["cap"], DATASET_SUBLINE_CAP)):
        mark = "ok " if probe == constant else "OUT"
        print(f"  {mark} {name}: probe {probe}, constant {constant}")
        if probe != constant:
            bad.append(f"{name}: the probe measures {probe} and the constant says {constant}")

    for name, got, want in (("the design's tallest fixture row", design["cap"], DESIGN_TALLEST_PX),
                            ("the Dataset column", design["datasetPx"], DATASET_COLUMN_PX),
                            ("the Source column", design["sourcePx"], SOURCE_COLUMN_PX)):
        mark = "ok " if got == want else "OUT"
        print(f"  {mark} {name}: {got} px (recorded {want} px)")
        if got != want:
            bad.append(f"{name} is {got} px, not the {want} px both caps were cut to")

    if bad:
        print("\nthe caps no longer describe the design:")
        for line in bad:
            print(f"  - {line}")
        print("\nRe-take them and say so in app/census/registry.py -- a cap is a ruled number, not a default.")
        return 1
    print("\nboth caps still hold: every character count buys two lines of the design's own row.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
