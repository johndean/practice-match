"""Regenerate the artifact's task board (the three ol.board groups) and the stamp from a state file.
Usage: compose_board_v14.py <board-state-json> <artifact-html-path>
State: {"stamp": "...", "groups": [{"title": "...", "rows": [{"tid","name","done"(0-7),"now"(int|null),"state","label"}]}]}
Row state: done | live | next | wait. Replaces ONLY the board card's groups; every other card is untouched."""
import sys, json, re, html
STATE, ART = sys.argv[1], sys.argv[2]
d = json.load(open(STATE))
def esc(s): return html.escape(str(s if s is not None else ""), quote=False)
STAGES = ["Brief", "Built", "Reviewed", "Merged", "CI green", "QA", "Production"]
def row(r):
    done, now = int(r.get("done", 0)), r.get("now")
    assert now is None or now >= done, f"a pulsing dot must be the next one, not a past one: {r['tid']}"
    dots = "".join('<span class="%s" title="%s"></span>' % (("bdot past" if i < done else ("bdot now" if now is not None and i == now else "bdot")), s) for i, s in enumerate(STAGES))
    return ('<li class="brow %s"><span class="tid">%s</span><span class="bname">%s</span>'
            '<span class="bdots" aria-hidden="true"><i class="bfill" style="width:%d%%"></i>%s</span>'
            '<span class="blabel">%s</span></li>' % (esc(r["state"]), esc(r["tid"]), r["name"], int(done / 7 * 100), dots, r["label"]))
blocks = []
for g in d["groups"]:
    blocks.append('<div class="rstate" style="margin:%s">%s</div>\n<ol class="board" aria-label="%s">\n%s\n</ol>'
                  % ("6px 0 4px" if g is d["groups"][0] else "14px 0 4px", esc(g["title"]), esc(g["title"]), "\n".join(row(r) for r in g["rows"])))
art = open(ART).read()
sec = re.search(r'<section class="status" data-doc="status">.*?</section>', art, re.S)
s = sec.group(0)
i = s.find('<h2>Where each one really is.</h2>'); assert i > 0, "board card not found"
hdr_end = s.find('</div>\n', i) + len('</div>\n')          # end of the card-h
j = s.find('<div class="card"', i); assert j > i, "next card not found"
body_end = s.rfind('</div>', hdr_end, j)                    # the board card's own closing div
new_card_body = "\n".join(blocks) + "\n"
s2 = s[:hdr_end] + new_card_body + s[body_end:]
new = art[:sec.start()] + s2 + art[sec.end():]
new, n = re.subn(r'updated 2026-09-1\d [0-9:]+ WITA', 'updated ' + d["stamp"], new)
open(ART, "w").write(new)
rows = sum(len(g["rows"]) for g in d["groups"])
print("board rows:", rows, "| groups:", len(d["groups"]), "| stamp replaced:", n, "| artifact bytes:", len(new))
