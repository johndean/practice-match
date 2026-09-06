# Local amendments to the V3 Rev 2 design (spec D15)

`Practice Match V3.dc.html` = `Practice Match V3.rev2.dc.html` (pristine, never edited) + the entries below, applied by `frontend/tests/design-amendments.ts` and proved byte-for-byte by `frontend/tests/design-amendments.test.ts`. They retire when a re-issued bundle carries them.

| Id | Date | John's ruling | What changes |
|---|---|---|---|
| A1 | 2026-09-07 | "keep the V2 header and do not restyle header or fonts" | 24 template elements: every display-size heading paired with V2 (by tag, text and size) takes V2's `text-transform`/`letter-spacing` values in place; the key-fact values `{{ m.v }}` and the 28 px mobile asking price return to V2's uppercase `.005em`; `{{ resultHeadline }}` is untouched (V3's only occurrence, in the mobile list, already equals V2's). No script, no `_ds/**`, no site header (byte-identical V2↔V3 already). |
| A2 | 2026-09-07 | "resolve this" — the mobile practice card opens the detail (spec D17) | One line of the design's script: the mobile results card's `open` handler. Root cause: it set `browseSel`, which C13 left nothing to read once it removed the peek card that used to display it, so the tap was a no-op; `open` now navigates straight to the detail screen, the same way V2's card and C13's own second-pin-tap already do. |
