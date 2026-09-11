"""I3 (whole-branch review, 2026-09-11) — the 8 000 m band is ONE number in four places.

`BANDS["drive_10"]` is the radius the pipeline actually buffers at (`app/census/catchment.py`),
and three other files state the same distance in their own vocabulary:

  * `app/census/serve.py`'s `BAND_LABEL` — the sentence the Community Context card shows a buyer,
    "Within about 5 miles of the practice" (D-C39: the band is described by DISTANCE, not time);
  * `frontend/src/components/MarketMapView.vue` — the ring the app draws on Browse;
  * `docs/design-reference/.../MarketMapV3.jsx` — the ring the DESIGN draws, moved to 8 000 m by
    amendment A28.1 under ruling D-C44, which exists precisely because that file had drifted to
    16 000 m and a buyer was reading one distance and shown a circle twice its size.

Before this module, changing `BANDS["drive_10"]` to 16 000 left EVERY gate green while the card
went on naming five miles and the maps went on drawing eight kilometres — the exact drift D-C44
was raised to fix, re-armed one layer down. There is no import path between the Python that
decides the radius and a design bundle that must stay a verbatim port, so the link is this file:
one authority, three derivations, and a failure the moment any of them moves alone.
"""
from __future__ import annotations

from pathlib import Path

from app.census.catchment import BANDS
from app.census.serve import BAND_LABEL

ROOT = Path(__file__).resolve().parents[2]

# The international mile. The label rounds to whole miles because it says "about".
METRES_PER_MILE = 1609.344


def _miles() -> int:
    return round(BANDS["drive_10"] / METRES_PER_MILE)


def test_the_card_s_sentence_names_the_distance_the_pipeline_buffers_at():
    """8 000 m is 4.97 miles, which "about 5 miles" is. The sentence's wording is ruled (D-C39)
    and stays a literal in `serve.py`; what is checked here is its NUMBER, against the only
    place that decides it."""
    assert BAND_LABEL == f"Within about {_miles()} miles of the practice", (
        f"BAND_LABEL says {BAND_LABEL!r} while BANDS['drive_10'] is {BANDS['drive_10']} m "
        f"(~{_miles()} miles). The card would name a distance the catchment is not measured at."
    )


def test_the_app_draws_the_ring_at_the_band_radius():
    """`MarketMapView.vue`'s C7 ring. Matched on the whole call so a bare `8000` elsewhere in the
    file cannot satisfy it."""
    vue = (ROOT / "frontend" / "src" / "components" / "MarketMapView.vue").read_text()
    call = f"engine.ring(props.driveCenter, {BANDS['drive_10']},"
    assert call in vue, (
        f"frontend/src/components/MarketMapView.vue does not draw the C7 ring at "
        f"{BANDS['drive_10']} m — expected a call beginning {call!r}"
    )


def test_the_design_draws_the_ring_at_the_band_radius():
    """The AMENDED bundle (`MarketMapV3.jsx`), which is A28.1's output — the pristine
    `MarketMapV3.rev2.jsx` still carries the 16 000 m mash-up D-C44 corrected and is never
    edited. Both are read, so this cannot pass against a file that lost the declaration."""
    amended = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3"
               / "MarketMapV3.jsx").read_text()
    pristine = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3"
                / "MarketMapV3.rev2.jsx").read_text()
    assert "radius: 16000, color:" in pristine, (
        "the pristine bundle no longer carries the 16 000 m ring A28.1 corrects; this test's "
        "other half would then be asserting against a file that never had a radius"
    )
    assert f"radius: {BANDS['drive_10']}, color:" in amended, (
        f"the amended MarketMapV3.jsx does not draw the ring at {BANDS['drive_10']} m — "
        "amendment A28.1's replacement and app/census/catchment.py's BANDS have diverged"
    )


def test_the_far_band_is_the_one_no_map_draws_and_no_card_names():
    """`drive_20` exists in the pipeline (catchments are built for it) and is drawn by nothing and
    named by nothing: D-C44 ruled AGAINST restoring V2's second ring, and `community_rows` reads
    only `place` and `drive_10`. Pinned so that a later change cannot quietly make the near band
    the far one and leave every assertion above satisfied by the wrong number."""
    assert BANDS["drive_20"] == 2 * BANDS["drive_10"]
    amended = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3"
               / "MarketMapV3.jsx").read_text()
    vue = (ROOT / "frontend" / "src" / "components" / "MarketMapView.vue").read_text()
    for name, text in (("MarketMapV3.jsx", amended), ("MarketMapView.vue", vue)):
        assert str(BANDS["drive_20"]) not in text, f"{name} draws something at the drive_20 radius"
