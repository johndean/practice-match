import sys,re,base64
SP=sys.argv[1]
def img(name, alt):
    b=base64.b64encode(open(f"{SP}/shots/{name}.jpg","rb").read()).decode()
    return f'<figure style="margin:0"><img src="data:image/jpeg;base64,{b}" alt="{alt}" style="width:100%;border:1px solid var(--rule);border-radius:6px"><figcaption style="font-size:12.5px;color:var(--ink-muted);margin-top:6px">{alt}</figcaption></figure>'
def m(s): return f'<span class="mono">{s}</span>'
STAGES=["Brief","Built","Reviewed","Merged","CI green","QA","Production"]
def row(tid,name,done,state,label,now=None):
    dots=[]
    for i,s in enumerate(STAGES):
        cls="past" if i<done else ("now" if (now is not None and i==now) else "")
        klass=("bdot "+cls).strip()
        dots.append('<span class="%s" title="%s"></span>' % (klass, s))
    fill=int(done/len(STAGES)*100)
    return ('<li class="brow %s"><span class="tid">%s</span><span class="bname">%s</span>'
            '<span class="bdots" aria-hidden="true"><i class="bfill" style="width:%d%%"></i>%s</span>'
            '<span class="blabel">%s</span></li>') % (state, tid, name, min(fill,100), "".join(dots), label)
board="\n".join([
 row("0.1.22","SNAP — the snapshot strip has AREA and LOCATION modes and says which is on; the false “$99K metro median” card is gone",7,"done","Live on QA + production since 01:45 UTC"),
 row("0.1.22","Metro switch asks once · panel closes on metro change · listings geocode on publish · cache drops guarded · CI-timing split",7,"done","Live on QA + production"),
 row("0.1.23","SCREEN-LABELS — panel index “+19% vs US · approximate”; tooltip counts the bands it spans; six drawer sub-lines name their geography",7,"done","Live on QA + production since 06:45 UTC"),
 row("0.1.23","ESRI-ZOOM — zoom to 20, never the “Map data not yet available” tile; Satellite credits Esri’s current text",7,"done","Live on QA + production"),
 row("0.1.23","ADMIN-GATE — a buyer never reaches the Admin screen; admin data loads on arrival",7,"done","Live on QA + production · hiding the doors is held for your ruling"),
 row("0.1.23","HOUSEKEEPING-B — the ledger proves its own integrity; the documented gate is CI’s",7,"done","Live (docs, tests, tooling)"),
 row("0.1.24","ONE-VOCABULARY — every one of the 47 figures names its statistic, geography and basis; three tests keep it so",1,"live","Implementing now (started 06:45 UTC)",now=1),
 row("0.1.24","SNAP-METRO — the Census’s published metro figure as the AREA headline where one exists",1,"next","Briefed · starts when ONE-VOCABULARY merges"),
 row("0.1.24","HOUSEKEEPING-C — citation re-mapper, live sign-in check, eleven small items",1,"next","Briefed"),
 row("0.1.24","VINTAGE-STRINGS — “(2023)” and “Jan 2025” read from the served vintages",1,"next","Briefed"),
 row("admin","Users · Data Sources · Listings · Requests tabs — real rows, every action wired (A36–A39)",0,"wait","WAITING ON YOU: compose from V3’s elements, or a new design export"),
])
STATE_LABEL={"done":"Live","active":"In progress","blocked":"Waiting on John"}
def rnode(ver,state,frac,blurb,letter):
    return ('<div class="rnode %s"><span class="rdot" aria-hidden="true" style="display:flex;align-items:center;justify-content:center">%s</span>'
            '<span class="rtext"><span class="rstate">%s</span><span class="rfrac">%s · %s</span><span class="rblurb">%s</span></span></div>') % (state, letter, STATE_LABEL[state], ver, frac, blurb)
rail=('<div style="display:flex;justify-content:space-between;gap:6px;padding:8px 0 4px">'
 + rnode("0.1.21","done","4 / 4","Six real Census layers on the map","✓")
 + rnode("0.1.22","done","7 / 7","Snapshot AREA/LOCATION; metro switch; geocode on publish","✓")
 + rnode("0.1.23","done","4 / 4","Honest labels; zoom to 20; admin gate; ledger guard","✓")
 + rnode("0.1.24","active","1 / 4","Caption sweep (running); published metro figure; housekeeping","4")
 + rnode("admin","blocked","0 / 4","Users · Data Sources · Listings · Requests","?")
 + '</div>')
tile=lambda title,big,sub: ('<div style="border:1px solid var(--rule);border-radius:8px;padding:12px 14px"><div class="rstate" style="color:var(--ok)">%s</div>'
                            '<div style="font-size:26px;font-weight:700;color:var(--ink-strong)">%s</div><div class="blabel">%s</div></div>') % (title,big,sub)
v8 = '<section class="status" data-doc="status">\n<div class="card hero">\n<div class="card-h"><span class="eyebrow">Live status &middot; measured 2026-09-13 06:45 UTC (14:45 WITA) from both ' + m("/api/healthz") + ', the CI runs and a signed-in browser on QA</span><h2>Live now: <b>0.1.23</b> on QA and on production.</h2>\n'
v8 += '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px">' \
    + tile("QA &middot; qa.foundation.vin","0.1.23", m("3ee9a59")+" &middot; app mode &middot; db + redis ok") \
    + tile("Production &middot; foundation.vin","0.1.23", m("3ee9a59")+" &middot; coming-soon mode &middot; db + redis ok") \
    + tile("CI on the release commit","4 / 4","backend &middot; frontend &middot; coming-soon &middot; gitleaks &mdash; read before each deploy") \
    + '</div>' + rail + '</div></div>\n\n'
v8 += '<div class="card"><div class="card-h"><span class="eyebrow">Check these on QA &middot; Browse &rarr; Austin, TX metro &rarr; click DEF Veterinary Hospital</span><h2>What is live to check.</h2></div>\n<ol class="plain" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 22px;list-style:none;padding:0;margin:0">\n'
v8 += '<li><b>1 &middot; Snapshot strip, practice selected</b> &mdash; heading <b>LOCATION &middot; DEF Veterinary Hospital</b>; income <b>$94K &middot; Within about 5 miles of the practice &middot; approximate</b>; growth <b>+3.4% &middot; Austin</b>; payroll <b>$755K &middot; surrounding county</b>. Deselect: heading <b>AREA &middot; Austin, TX metro</b>, income <b>$95K &middot; median of 541 Census tracts</b>. The words &ldquo;metro median&rdquo; appear nowhere.<br>' + img("qa-0122-strip-location-def","LOCATION mode on QA — each card names its own geography") + '</li>\n'
v8 += '<li><b>2 &middot; Practice Detail panel</b> &mdash; Median Income <b>$94K &middot; +19% vs US &middot; approximate</b> (was a hard-coded +25%). Same $94K as the strip: the two agree on purpose.<br>' + img("qa-0123-panel-def","The docked panel’s Median Income tile on QA 0.1.23") + '</li>\n'
v8 += '<li><b>3 &middot; Zoom all the way in</b> &mdash; press + until it stops (zoom 20). Soft streets under sharp tract outlines; never &ldquo;Map data not yet available&rdquo;. Labels hide above 18 by ruling. Satellite at 20 shows real imagery and credits &ldquo;Source: Esri, Vantor, &hellip;&rdquo;.<br>' + img("qa-0123-zoom-20-no-placeholder","Zoom 20 on QA 0.1.23 — no placeholder tile") + '</li>\n'
v8 += '<li><b>4 &middot; Admin gate</b> &mdash; as the buyer persona, the header&rsquo;s Admin button and ' + m("/admin") + ' both land on &ldquo;This page is not available to your account&rdquo;. As the staff persona, Listings loads real rows on sign-in with no page reload. (The two doors a buyer cannot open are still SHOWN &mdash; hiding them is your decision, below.)<br>' + img("qa-0123-admin-buyer-header-gate","The buyer persona refused at the gate on QA 0.1.23") + '</li>\n'
v8 += '<li><b>5 &middot; Tooltip</b> &mdash; hover a tract: the margin caveat counts the bands it spans (&ldquo;three&rdquo; on Tract 4.01, &ldquo;two&rdquo; on Tract 300, none on Tract 307).</li>\n'
v8 += '<li><b>6 &middot; Layers drawer</b> &mdash; six sub-lines each read &ldquo;&lt;statistic&gt; by &lt;geography&gt; &middot; &lt;dataset&gt;&rdquo;, e.g. &ldquo;Household income by Census tract &middot; ACS 5-year&rdquo;.</li>\n</ol></div>\n\n'
v8 += '<div class="card"><div class="card-h"><span class="eyebrow">Every task, stage by stage &middot; dots read Brief &middot; Built &middot; Reviewed &middot; Merged &middot; CI green &middot; QA &middot; Production &middot; a pulsing dot is in progress now</span><h2>Where each one really is.</h2></div>\n<ol class="board" aria-label="Task board">\n' + board + '\n</ol></div>\n\n'
v8 += '<div class="card"><div class="card-h"><span class="eyebrow">Two decisions only you can make &middot; everything else is decided and moving</span><h2>Waiting on you.</h2></div>\n<ul class="plain">\n'
v8 += '<li><b>Admin screens (Users, Data Sources, Listings, Requests; permissions, settings, drill-down).</b> The backend has them; the V3 design never drew them. <b>Compose them from V3&rsquo;s own elements under your approval</b> (how the eight account screens were built) <b>or export a new design revision</b>. Composing starts as soon as you say; an export blocks until it lands.</li>\n'
v8 += '<li><b>Hide the doors a buyer cannot open?</b> Doing it re-pins 7 of the 13 frozen design screens and adds a ninth prototype prop so the reference design can render a buyer&rsquo;s two doors. Recommendation: yes &mdash; a door that refuses is a fake affordance under your D-C53.</li>\n</ul></div>\n\n'
rows=[
 ("Three &ldquo;median household income&rdquo; figures on one screen &mdash; $84K (one tract, published), $94K (the practice&rsquo;s 5-mile ring), $99K labelled &ldquo;metro median&rdquo; but really GHI&rsquo;s ring figure","ok","Fixed in 0.1.22 &mdash; the false card is gone; every LOCATION card names its own geography"),
 ("Panel &ldquo;+25% vs US&rdquo; from a hard-coded US figure; tooltip &ldquo;two bands&rdquo; where it spans three; drawer &ldquo;by community&rdquo; on tract layers","ok","Fixed in 0.1.23"),
 ("&ldquo;Map data not yet available&rdquo; basemap tiles when zoomed in","ok","Fixed in 0.1.23 &mdash; tiles requested only where Esri has them; zoom to 20"),
 ("A buyer could reach the Admin screen; Users/Requests/Data Sources tabs showed the design&rsquo;s sample rows to anyone","ok","Gate fixed in 0.1.23; the four tabs&rsquo; real data is the admin work waiting on your decision"),
 ("0.1.21 had shipped with CI red (a coverage threshold; every test passed) because the documented local gate skipped coverage","ok","Fixed &mdash; the local gate is CI&rsquo;s step; no deploy without the workflow green on the pushed commit"),
 ("Remaining caption collisions across the other 44 figures (payroll&rsquo;s &ldquo;market level&rdquo;, Compare rows, the panel&rsquo;s Households tile, both footnotes)","accent","Fixing now &mdash; ONE-VOCABULARY, 0.1.24"),
 ("The AREA card&rsquo;s &ldquo;median of 541 Census tracts&rdquo; ($95K) differs from the Census&rsquo;s published metro median ($98K)","accent","Scheduled &mdash; SNAP-METRO, 0.1.24: the published figure becomes the headline"),
 ("Hard-coded &ldquo;(2023)&rdquo; / &ldquo;Jan 2025&rdquo; caption strings; a buyer cannot apply to sell anywhere; Listings badge reads &ldquo;3&rdquo; over 30 rows","accent","Scheduled &mdash; VINTAGE-STRINGS; the admin spec; A39 Listings"),
]
v8 += '<div class="card"><div class="card-h"><span class="eyebrow">Found today &middot; each with what happened to it</span><h2>Issues, and their state.</h2></div>\n<div class="table-wrap"><table><thead><tr><th>Found</th><th>State</th></tr></thead><tbody>\n'
for found,color,state in rows:
    v8 += '<tr><td>%s</td><td><b style="color:var(--%s)">%s</b></td></tr>\n' % (found,color,state)
v8 += '</tbody></table></div></div>\n</section>'
open(f"{SP}/status-v8.html","w").write(v8)
art=open('/tmp/pm-artifact-v4.html').read()
pat=re.compile(r'<section class="status" data-doc="status">.*?</section>', re.S)
assert len(pat.findall(art))==1
new=pat.sub(lambda _: v8, art); open('/tmp/pm-artifact-v4.html','w').write(new)
print("v8 bytes:",len(v8),"| artifact bytes:",len(new))
