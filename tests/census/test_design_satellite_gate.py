"""The satellite basemap is unreachable from the design while its licence is unresolved (A49).

Task SATELLITE-GATE, controller ruling 2026-09-15. The approved Census & Market Data Source
Specification says it twice, and both sentences are the ruling this file enforces:

    §2  "Rows marked Unresolved or Blocked must not ship. The satellite basemap and any
         commercial pet-ownership incidence rate require a signed license before the layer is
         enabled; until then the UI shows the street basemap..."
    §15 "Which satellite imagery vendor, and is the license budgeted?
         Until answered, the Satellite toggle ships disabled."

`dataset_registry`'s `imagery` row is `unresolved` (migration 017), and its own note has said
since that migration that the toggle "stays behind a feature flag until a written licence names
commercial web display" -- a flag that existed nowhere in the running code until this amendment.

WHY THIS IS NOT A ROLE GATE, which is the finding that produced the ruling. `layer.satellite` is
declared in `app.auth.permissions.MATRIX` and holds `{buyer, seller, staff, admin}` -- the SAME
set `page.browse` holds, so every account that can reach the Browse map holds it and gating the
control on it would have hidden the control from NOBODY. The identity spec designs it as one
conjunct of two ("satellite toggle (∧ cleared imagery/engine row)"): it is the POST-clearance role
gate, and it is left in the matrix untouched, waiting for its second conjunct. The matrix could
not express the answer in any case -- ruling D-C54 unions every row with `admin`, so "nobody until
a licence is signed" is not writable as a matrix row at all.

WHAT IS PINNED HERE, and why it is a source test rather than a behavioural one. The amendment
removed the control from the DESIGN (A6's launch-removal mechanism), so the reference and the app
lose it together and every visual gate keeps holding. `frontend/src/logic.test.ts` pins the
RENDER VALUES -- no `md.setBasemap`, no `mob.basemaps`, `md.basemap === "map"`. What only the
source can say is that `mdBasemap` has no WRITER left anywhere: a render value can be absent while
some other line still sets the key, and it is the absence of every writer that makes an imagery
tile unrequestable rather than merely unclicked.

REVERSIBILITY is pinned too, deliberately. `MarketMapV3.jsx` keeps its own `onBasemap &&` guard
and `BASEMAPS.satellite` keeps its A35 entries, so re-instating the control the day the VIN
Foundation clears the row is restoring two mounts and two declarations -- not rebuilding a
feature. A test that let those rot would turn a reversible gate into a demolition.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE = _ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3"
DESIGN = _BUNDLE / "Practice Match V3.dc.html"
MAP_COMPONENT = _BUNDLE / "MarketMapV3.jsx"


def _design() -> str:
    return DESIGN.read_text(encoding="utf-8")


def test_no_mount_hands_the_map_a_basemap_callback() -> None:
    """The desktop mount's `on-basemap` is what `MarketMapView`'s `v-if="props.onBasemap"` reads.

    Both `x-import` mounts of `MarketMapV3` are checked at once rather than the desktop one by
    name: the phone's mount has never passed it (C13), and naming only the desktop one would let
    the control come back through the other door.
    """
    assert "on-basemap" not in _design(), (
        "a MarketMapV3 mount passes `on-basemap` again -- that prop is the whole of the desktop "
        "Satellite control, and the imagery licence is still unresolved (spec §15)"
    )


def test_the_phone_sheet_has_no_basemap_section() -> None:
    """`mob.basemaps` was the phone frame's own control -- the sheet's "Basemap" section."""
    design = _design()
    assert "mob.basemaps" not in design, "the phone sheet renders a Basemap section again (spec §15)"
    assert not re.search(r"^\s*basemaps:", design, re.MULTILINE), (
        "the design declares a `basemaps:` render value again -- the phone sheet's own "
        "Map | Satellite pair (spec §15)"
    )


def test_mdbasemap_has_no_writer_left_so_the_map_can_only_be_the_gray_canvas() -> None:
    """The real gate: no writer, so no imagery tile can ever be requested.

    `mdBasemap` survives as a READ (`basemap: s.mdBasemap || "map"`) because the map still has to
    be told which basemap to draw, and that read is what makes re-instatement one line. Every
    occurrence must be a read: a `setState` naming the key is a writer by definition, whatever
    reaches it.
    """
    design = _design()
    occurrences = [m.group(0) for m in re.finditer(r"[^\n]*mdBasemap[^\n]*", design)]
    assert occurrences, "the design no longer mentions `mdBasemap` at all -- has the map lost its basemap?"
    writers = [line for line in occurrences if "setState" in line]
    assert writers == [], (
        "`mdBasemap` has a writer again, so the satellite basemap is reachable: "
        f"{writers} -- the imagery licence is still unresolved (spec §2, §15)"
    )
    reads = [line for line in occurrences if 's.mdBasemap || "map"' in line]
    assert len(reads) == 1, (
        f"expected exactly one `mdBasemap` read (the map's own basemap), found {len(reads)}: {occurrences}"
    )


def test_the_control_is_gated_not_demolished_so_the_licence_can_restore_it() -> None:
    """Reversibility, pinned. The component keeps the ability; nothing hands it the callback.

    `MarketMapV3.jsx` is untouched by A49 -- its `onBasemap &&` guard is the DESIGN'S OWN off
    switch (the phone mount has always used it), which is why this amendment needed no edit to
    that file and no interaction with A35's seven entries.
    """
    component = MAP_COMPONENT.read_text(encoding="utf-8")
    assert "onBasemap && React.createElement" in component, (
        "MarketMapV3 lost the guarded control block -- A49 gates the Satellite toggle, it does "
        "not delete the component's ability to render one when the licence lands"
    )
    assert "satellite:" in component, (
        "MarketMapV3 lost its `BASEMAPS.satellite` entry -- A35 pins its maxNativeZoom and "
        "attribution, and re-instatement needs it"
    )


def test_the_imagery_row_is_still_unresolved_which_is_why_the_gate_is_on(conn) -> None:
    """The precondition, stated so the ruling's own trigger is visible from the gate.

    This is the test to revisit the day the VIN Foundation clears the row: when `imagery` reads
    `cleared`, the four assertions above are the ones that describe behaviour nobody ruled for any
    more, and `layer.satellite` -- untouched in the matrix throughout -- becomes live as the
    identity spec's second conjunct always intended.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT license_status, notes FROM dataset_registry WHERE dataset_key = 'imagery'")
        row = cur.fetchone()
    assert row is not None, "the `imagery` dataset_registry row is gone -- migration 017 seeds it"
    status, notes = row
    assert status != "cleared", (
        "the imagery basemap is licence-CLEARED now. A49 gated the Satellite control on the "
        "strength of this row being unresolved; revisit this file, the A49 amendment entries and "
        "`layer.satellite`'s second conjunct together rather than deleting any one of them"
    )
    assert "feature flag" in (notes or ""), (
        "the imagery row's own note no longer says a flag protects it -- that note is what A49 "
        "finally made true"
    )
