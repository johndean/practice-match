# What a seller can actually hide — and what we propose to change

**For John's ruling. 2026-09-25.**
Measured against the code at commit `6ca2d4c`, branch `fix/wizard-submit-truth`.
Ruling this responds to — **D-C68**, in your words: *"this applies to every view, address, pricing, images, etc."*

This is a proposal, not a change. No code was touched. No gates were run, because nothing runs
differently than it did yesterday.

---

## 1. The decision, in one page

A seller today gets five switches. They cover the practice **name**, the **street address and
telephone**, the **photographs**, the **revenue figure**, and the **floor plans and financial
packet**. Everything else a seller types into the listing wizard goes to every signed-in member of
the platform, with no switch and no way to ask for one.

"Every signed-in member" is worth saying plainly, because it is wider than it sounds: it means every
buyer, and it also means **every other seller** — a competing practice owner three miles away reads
the same page.

I measured every field the API sends and every screen that draws it. **Sixteen pieces of
seller-supplied information have no control of any kind.** Most of them should not have one, and I
say so below rather than proposing sixteen new switches. Three of them matter, and they are your
call:

| | The decision | What I recommend |
|---|---|---|
| **A** | **The three free-text boxes** — "Hours", "Services offered", "Facility description" — are published word-for-word to everyone. | **Gate them.** They join `IDENTITY`. No new capability. |
| **B** | **The asking price** has no control. The audit recorded this as deliberate. | **Leave it public — but fix the filter anyway.** |
| **C** | **The map route** answers the location question differently from the listing route. | **Fix it.** It is a consistency defect, and smaller than it first looks. |

Decision **A** is the one I would most like you to say yes to. On **B** I am recommending *against*
adding a control, which is the one place in this document where I am arguing for fewer switches
rather than more — the reasoning is in §3 and it deserves your scrutiny. **C** needs a nod, not a
debate.

**One thing to fix whatever you decide:** the Browse filter currently reveals hidden figures. It
does this to revenue **today**, on live listings, and it would do it to anything else we ever hide.
That is a small change and it does not depend on any of the three decisions. Details in §3.

---

## 2. Decision A — the three free-text boxes

### What they are

The wizard asks three open questions, and stores the answers exactly as typed:

- Step 4, **"Hours"** — placeholder *"Mon–Fri 7:30–6, Sat 8–1"*
- Step 4, **"Services offered"** — placeholder *"Wellness, dentistry, soft-tissue surgery, in-house lab, digital radiography"*
- Step 5, **"Facility description"** — placeholder *"Freestanding building on a 0.6-acre corner lot, remodeled 2019."*

Neither step says anything about privacy. Step 4's heading is *"The practical picture: who works
there and what you do."* Step 5's is *"Real estate is usually the second question a buyer asks."*
There is no switch on either step, and none on step 7, that covers them. **[E1]**

### Why this one is not a judgement call about risk

I am not asking you to take my word that free text is risky. **The product has already decided it
is, and acts on that decision every day.**

When a seller uploads a photograph, the redaction pipeline scrubs anything identifying off it —
signage, logos, the practice name on a door. To know what to scrub, it builds a list of words that
could identify this practice. That list is built from the practice name, the street, the city, the
ZIP, the telephone — **and from these same three boxes.** One line of code pools "Facility
description", "Services offered" and "Hours" into the identity-token pool, and the redactor then
masks any distinctive word from that pool off the photographs. **[E2]**

The code even distinguishes carefully between words that identify and words that do not: a list of
generic terms — *wellness, dentistry, surgery, boarding, grooming* — is excluded, with a comment
explaining that "a word that names what every practice does identifies none of them", so **only
distinctive words trigger redaction.** **[E3]**

So the position the platform holds today is:

> A distinctive word in "Services offered" can identify this practice, so we will remove it from
> the photographs — and then publish it in full, as text, on the same page.

That is not a risk assessment anyone needs to agree with. It is the product contradicting itself,
and the contradiction is visible in one file.

### What a seller expects

Step 7's switch says *"Keep practice name and address hidden until I approve a buyer"*, and
explains: *"Your listing shows the practice type, community and figures you released."* **[E4]**

A seller reads that sentence and reasonably concludes the prose they typed is covered — it is
neither a type, nor a community, nor a figure. It is not covered.

The concrete failure: a seller ticks "keep my name hidden", and then writes *"Freestanding building
on a 0.6-acre corner lot, remodeled 2019, adjacent to the Cedar Park farmers' market"* in a box with
no privacy label. We remove that phrase from their photographs and publish it as a sentence.

### Recommendation

**Gate all three on `IDENTITY`.** No new capability, no migration, no new vocabulary. `IDENTITY` is
already the switch a seller uses to say "not until I approve a buyer", and these three fields are
exactly that — free-text identity risk, already classified as such by our own redactor.

**What it costs — and I had this wrong in my first draft, so here is the measured version.** All
three appear on the **desktop detail screen and nowhere else at all.** Not the Browse card, not the
map, not the panel, not the phone — the phone's detail screen draws only the key-facts strip and
never this block. That is a small blast radius, which is the good news.

The less good news is that only one of the three currently degrades cleanly. "Services offered" is
already guarded — hide it and the paragraph simply is not drawn. **"Hours" and "Facility
description" are not guarded**: the code adds the "Hours" row unconditionally and marks the facility
paragraph as present without checking, so hiding them today would draw an empty row and an empty
paragraph rather than nothing. **[E15]**

That is a real cost, and it is small and bounded: the fix is the same "draw no row when there is no
value" pattern the product already uses for facility type on the very next line, and the same one
that shipped last week under D-C65 when two fabricated rows came out of this block. **Still no new
copy** — nothing has to be written or approved; two lines need a guard. I mention it only because I
would rather you heard the true cost than a tidier one.

**One honest caveat.** Gating them makes the anonymous listing thinner — a buyer browsing an
anonymous practice sees less about what it does. If you would rather keep "Services offered" public
because it is genuinely how a buyer shortlists, that is a legitimate answer and I would gate the
other two. I have not recommended it because the redactor's own judgement points the other way, but
the trade is real and it is yours.

### Two more that are served but that no seller can fill

Two further free-text fields — an internal **note** and a **staff** description — are sent to every
member and drawn on the detail screen, but **no wizard step writes either of them.** They carry
design fixture text today. They are not a live leak; they are an open pipe. Whichever way you rule
on the three above, these two should be gated the same way or dropped from the payload, before
anything starts writing to them. I do not think this needs a separate decision. **[E5]**

---

## 3. Decision B — the asking price

**My recommendation is that you do not gate it.** I am putting it to you because D-C68 names pricing
explicitly, so it needs an answer on the record rather than an omission.

### Why I recommend leaving it public

The seller is never told the price is private, and the product is built around it being public. Step
3 says *"Two numbers get a buyer to a decision"*, and offers a privacy control for **one** of them
— revenue, which can be shown as a range. The absence of a price control sits directly beside a
present revenue control, on the same step. That reads as a decision, not an oversight. **[E6]**

A price also identifies nobody. Every other uncovered field I am worried about is worrying because
it can point at a particular practice. "$1.45M" points at nothing.

### The brief said this would need new copy from you. It does not — I checked

The concern raised was that the Browse card and results rail are built around a price, the design
draws no treatment for a missing one, and gating it would need new copy from you.

**That turned out to be wrong, and I want to correct it rather than carry it forward.** All **eight**
places the code formats a price — seven of them live, one computed and never drawn — go through a
single shared helper, and that helper already returns an em dash, "—", for a missing value. It is
the same helper that draws revenue, so a withheld revenue already renders "— revenue" on the Browse
map pin today, on live listings. The treatment exists, it ships, and buyers already see it. **[E7]**

One real caveat, measured: on the **detail screen** the price sits in a large navy banner in 34-point
type, under a heading reading "Asking price" that is fixed in the template. A missing price there
draws a very large dash under a heading that still asks the question. Everywhere else it is
unremarkable. So the accurate statement is *"a treatment exists everywhere, and in one place it
looks bad"*, not *"there is no treatment"*.

### The leak — and this part matters whatever you decide about price

The Browse filter has a bug, and it is not limited to price.

The filter tests bands by dividing: *"is the revenue under $1M?"* is computed as `revenue ÷ 1000 <
1000`. When a figure is withheld the server sends an explicit "no value", and **in JavaScript that
value divides to zero.** So a listing whose revenue the seller has withheld computes as zero, zero
is under $1M, and the listing is returned inside the "Under $1M" band. A buyer filtering for the
cheapest practices is shown, in that result set, exactly the practices whose figures are hidden. I
ran this rather than reasoned about it. **[E8]**

**This is live today for revenue** — revenue is already a gated field, so the leak is real now, not
hypothetical.

And it is a class, not a single bug. I tested every band filter. The same shape applies to **price**
(a hidden price lands in "Under $500K"), to **square feet** (lands in "Under 3,000"), and to **year
established** (lands in "pre-1995"). The doctors filter fails the other way — a hidden doctor count
*excludes* the listing from every doctors filter, so the listing quietly vanishes instead of leaking.
**[E8]**

The consequence for planning: **any numeric field you ever decide to hide will announce itself
through this filter unless the filter is fixed first.** I recommend fixing it as its own small
change, independent of every decision on this page, because it is a live leak for revenue today.

### Sorting — the brief was stale, and this is good news

The brief warned that sort-by-price carries the same exposure. **It does not, because nothing
sorts.** The sort control exists in the page — a dropdown offering "Newest first", "Price: low to
high", "Revenue: high to low" — but it has no handler, no binding, and nothing anywhere in the
application sorts listings by anything. It is the inert control recorded as defect D-F1, which you
ruled on 2026-09-11 should be wired up as its own change. That change has not landed. **[E9]**

So sorting is not a current leak. It becomes one the day D-F1 is wired, and whoever does that work
needs the filter fixed first. Worth recording so it is not discovered twice.

---

## 4. Decision C — the map route disagrees with the listing route

There are two routes that will tell a caller where a practice is, and they do not use the same rule.

The listings route serves a deliberately blurred pin — rounded to about 1.1 km — to anyone without
an approved `EXACT_LOCATION` grant. That blurring is the whole point of the capability, and it was
reaffirmed as recently as last week. The market route re-derives the same decision from scratch,
reads only the seller's own visibility flag, ignores capabilities entirely, and hands back the
**exact** coordinate. **[E10]**

### How bad it actually is — narrower than it first appears, and I want to be straight about that

My first read was that this makes `EXACT_LOCATION` meaningless. Having traced it through, that
overstates it.

The exact coordinate is served only when the seller's visibility flag is **open**. But that same
flag is what publishes the street address and the practice name in the listings payload — the wizard
sets both from the single "Show only the community" toggle. So in every case where the map route
gives away the exact point, **the street address and the practice name are already public on the
same listing.** The coordinate discloses nothing the address did not. When the seller's flag is
shut, the map route correctly serves a place centroid, not the practice's point.

So this is **one question with two answers**, not an open door. It should still be fixed, for three
reasons:

1. It is exactly the defect D-C68 describes — one served answer, honoured by every surface.
2. There is one residual case that *is* a real disclosure: a listing whose flag is open but whose
   street column is empty. Those exist among older rows; a guard added last week stops a seller
   creating new ones.
3. It becomes a genuine leak the moment anyone changes what the open ceiling means — and this plan
   has changed location semantics twice in two weeks.

**Recommendation: fix it, as a small correctness change, not an emergency.** Route the market
endpoint through the same function the listings route uses. No ruling needed unless you disagree
with the framing.

**One thing to note about reach.** This route is guarded by `market.read`, which every member holds
— and which an *anonymous* visitor also holds whenever the `MARKET_DATA_PUBLIC` flag is on. That flag
defaults off, and the production deploy script refuses to ship with it on, so this is a QA-only
exposure and is already fenced. I mention it because it is the one place in this document where the
audience is potentially wider than "signed-in members", and I would rather you heard it from me.
**[E11]**

---

## 5. The ten I recommend leaving alone

These are uncovered, and I do not think any of them wants a switch. Listing them so the decision is
visible rather than silent:

**Practice type · market area · year established · ownership structure · doctor count · exam rooms ·
square feet · building status · facility type · listing age**

Two reasons. First, the seller is told these stay visible, in the sentence quoted above: *"Your
listing shows the practice type, community and figures you released."* Gating them would contradict
a promise we currently keep. Second, a buyer cannot shortlist without them — a marketplace where the
listings say nothing is not anonymised, it is empty.

**Two that turn out not to be questions at all.** The API also sends the **city** and the **state**,
and I had them on this list until I checked where they are drawn. They are drawn nowhere: the
frontend never copies either one out of the payload, and every "…, TX" on screen is parsed out of
the market name instead. They are sent and ignored. No decision needed; worth knowing they are two
fewer things to reason about. **[E16]**

**One caveat I will not paper over.** Enough of these together can narrow a practice to a short list
— a specialty practice, in a named small city, established 1998, five doctors, 4,200 square feet, is
plausibly one practice. That is a real property of anonymised marketplaces and **nobody has analysed
it for this product**; I searched and found no prior work on it. I am not proposing anything about it
here, because "how many public attributes identify a practice" is a research question and not a
switch. Flagging it as a known unknown rather than leaving it out.

**One engineering note that bears on any future decision to hide square feet.** Square footage is
formatted for display in six places without any check for a missing value, and the call used would
throw an error on a hidden value — taking the Browse rail and the phone list down with it, in the
manner of the null-coordinate crash fixed under A25. If square feet is ever gated, those six sites
must be guarded in the same change. Not a reason to avoid gating it; a reason not to do it casually.
**[E12]**

---

## 6. What a sixth capability would cost

None of my recommendations needs one — `IDENTITY` absorbs Decision A. Recording the price so the
question does not have to be re-derived if you want a new switch for something:

A sixth capability is **not** a one-line change. The five names live in six places that are pinned
against each other, deliberately, so that none can be changed alone: the Python vocabulary; two
database constraints, in separate migrations, each of which must be dropped and restated because
PostgreSQL cannot edit a constraint in place; the ordered list the seller's chooser is built from;
the labels a member reads; and a cross-language test added one task ago for exactly this reason.
Plus the buyer's request screen and the seller's chooser. **[E13]**

The test's own note explains why it exists, and it is a good argument against adding capabilities
lightly: if the list falls out of step, the seller's read-back of what a buyer currently holds
silently drops the new one — "a disclosure product may under-offer; it may not under-report."

---

## 7. What I measured

**Eleven buyer-facing surfaces** draw listing data: the Browse results rail, the Browse map pin and
its callout, the Browse docked panel, the Browse market-snapshot strip, the detail screen, the
interest modal, the photo lightbox, the phone list, the phone map, the phone detail, and the buyer's
"My Requests" list.

**Twenty-six pieces of seller-supplied data** reach them. Ten are gated by the five capabilities.
**Sixteen are not.** Two more are served and drawn but cannot currently be written by any seller.

The concentration is worth seeing, because it is why Decision A is cheap: **the detail screen draws
more of them than every other surface combined**, and six are drawn *only* there — ownership,
support team, the internal note, the facility description, services and hours appear on **no other
surface in the product**, not even the phone's own detail screen, which draws only the key-facts
strip. The Browse rail, by contrast, draws eight.

| Gated today | By which |
|---|---|
| Practice name, listing slug | `IDENTITY` |
| Street, ZIP, telephone, pin precision | `EXACT_LOCATION` |
| Revenue figure | `FINANCIALS` |
| Photographs, photo captions | `UNREDACTED_IMAGES` |
| Document filenames | `FINANCIALS` / `FLOOR_PLANS` |

| Ungated | Proposed |
|---|---|
| Hours, Services offered, Facility description | **Decision A** — recommend `IDENTITY` |
| Asking price | **Decision B** — recommend leaving public |
| Note, staff description *(no writer today)* | Follow Decision A |
| Type, area, market, established, ownership, doctors, rooms, square feet, building status, facility type | **Leave alone** (§5) |
| City, state | Sent but never drawn — nothing to decide (§5) |
| Listing age, status, geocode precision | Metadata — not seller content |

Census community figures (population, income, households and so on) are excluded throughout: they
describe the neighbourhood, not the practice, and no seller supplies them.

### Two corrections to the brief I was given

Recorded because they run the other way from the usual drift — both make the work *smaller*:

1. **"The design has no treatment for a missing price."** It has one, on all nine surfaces, and it
   already ships for revenue. No new copy needed. (§3)
2. **"Sort by price has the same exposure."** Nothing sorts; the control is inert. Not a current
   leak. (§3)

A third: the brief's list of ungated fields omitted six that are also ungated — the three free-text
boxes are in it, but `note`, `staff`, `facility`, `market`, `status` and geocode precision are not.
`facility` is the one that matters, and it is in Decision A.

---

## 7a. Four things I found on the way that are not decisions

Measuring every field across every screen turned these up. None needs a ruling; all are the same
family as the fabricated rows D-C65 removed last week, and I would rather log them here than let
them be found twice.

**The document list a buyer sees is not the seller's documents.** The "Photos and Documents" block
on the detail screen shows four rows — *exterior and interior photos, floor plan, three-year
financial summary, equipment list* — and those four rows are written into the page as fixed text.
They appear on **every listing**, identically, whatever the seller actually uploaded. The only live
part is the lock pill, which reflects the buyer's own approval status. Meanwhile the server does
build a real, correctly-gated document list — but it does so on a route **the application never
calls**, so no buyer has ever seen it. This is not a leak; it is the opposite — a promise the
product displays and does not keep.

It has one consequence worth noting for D-C68. Of the five capabilities, **`FLOOR_PLANS` currently
governs nothing a buyer can reach**: documents are the only thing it covers, and the real document
list never arrives. `FINANCIALS` is half in the same position — it genuinely gates the revenue
figure, which buyers do see, and it gates a financial packet they cannot. So when we say the five
capabilities cover ten pieces of data, one and a half of those five are covering a door that is not
yet connected. **[E14]**

**A buyer can be shown the wrong practice's figures.** Both the detail screen and the "My Requests"
list look up a listing by its identifier and, when they cannot find it, **fall back to the first
listing in the list** rather than showing nothing. A buyer whose request points at a practice
outside the currently loaded page therefore reads a different practice's asking price, doctor count
and square footage under their own request. This is a disclosure defect as much as a correctness
one — it discloses practice A's figures on a page about practice B. **[E17]**

**A missing building status is published as "Leased — assignable".** The code maps "Included" and
"Separate" to their own wording and sends *everything else*, a missing value included, down the
lease branch. It appears on four separate rows of the detail screen. That is a statement about a
lease that no seller made — precisely the class of thing D-C65 ruled out. **[E17]**

**A derived EBITDA is computed for every listing.** The Browse rail calculates a figure at 19 % of
revenue and puts it in the render values. Nothing currently draws it, so nothing leaks today — but
it is a derived financial number sitting one line of template away from a buyer's screen, computed
from the one figure sellers are actually offered a control over. It also would not degrade
gracefully: hidden revenue produces "$0K" rather than a dash. I would delete it. **[E17]**

---

## 8. Evidence

Every load-bearing claim above, with where to check it. Each was verified by trying to
*disprove* it, not by finding something that agreed.

| | Claim | How I tried to break it | What I found | Verdict |
|---|---|---|---|---|
| **E1** | Three free-text fields, no privacy control | Read every wizard step's fields and toggles | `logic.js:1754` (step 4), `:1755` (step 5), `:1758-1761` (step 7's four toggles) | Confirmed. No toggle names any of the three. |
| **E2** | The redactor treats these three as identity risk | Read the identity-term builder | `app/privacy/identity.py:266` pools `facility`, `services`, `hours` into the prose token pool | Confirmed, verbatim. |
| **E3** | Only *distinctive* words redact | Read the generic-word exclusion | `identity.py:74-84`, and `:203-208` on the two pools | Confirmed. The product has already separated identifying from non-identifying prose. |
| **E4** | The seller is promised name/address cover only | Read the step 7 help text | `logic.js:1758` — *"Your listing shows the practice type, community and figures you released."* | Confirmed. Prose is not named. |
| **E5** | `note` and `staff` served but unwritable | Searched the seller route and the step→field map | `frontend/src/listings/step-fields.json` lists no step writing either; both drawn by `detail()` | Confirmed. Served, drawn, no writer. |
| **E6** | Price public is deliberate | Read step 3 and its toggle | `logic.js:1753` — price and revenue together, `revBand` covers revenue only | Confirmed. A control for one, beside none for the other. |
| **E7** | Every price render degrades to "—" | Searched for a render bypassing the helper, incl. the Vue template | Eight sites, all `money()`: `logic.js:821, 1030, 1342, 1872, 1919, 2447, 2465, 2510` (`:2465` has no template reader); `money()` at `:436-440` returns `"—"` for null. Template check found only the static "Asking price" kicker, `App.vue:999-1001` | Confirmed, **with the detail-banner caveat**, which the template check is what found. |
| **E8** | The band filters leak a hidden value | Ran the expressions in Node rather than reasoning | `logic.js:1441` (price), `:1463` (revenue). Measured: hidden → "Under $1M" / "Under $500K" / "Under 3,000" / "pre-1995" all **true**; doctors excludes instead | Confirmed and **wider than reported** — four fields, two directions. |
| **E9** | Nothing sorts | Searched the template for a handler and the whole app for any sort | `App.vue:613-617` — a bare `<select>`, no `v-model`, no `@change`. Only `.sort(` calls in `frontend/src` are map quantiles (`logic.js:568`) and admin permission keys | **Refutes the brief.** Nothing sorts listings. |
| **E10** | The map route bypasses the capability | Compared both derivations | `app/api/market.py:618-624` reads `location_disclosed` alone, serves raw `ST_Y(pl.point)`; `app/api/listings.py:475-512` applies the three-tier rule | Confirmed — **but** the open flag also publishes street and name (`seller_listings.py:487-488` sets both from one toggle), so the blast radius is the narrow case in §4. |
| **E11** | Reach of that route | Traced the guard to the matrix and the setting's default | `market.py:627` guards on `market.read`; `permissions.py:19-20, 198` grants it to all members **and to anonymous** when the flag is on; `config.py:33` defaults it off; `scripts/verify-deploy.sh:155` fails production if on | Confirmed. QA-only, already fenced. |
| **E12** | Hiding square feet would crash | Ran the call on a null value | `TypeError` confirmed in Node; six unguarded sites — `logic.js:1033, 1037, 1896, 1938, 2449, 2510` | Confirmed. |
| **E13** | A sixth capability is expensive | Counted its homes and checked whether a constraint can be edited | `levels.py:10`; `migrations/096` and `097`'s CHECKs (097's own comment: *"PostgreSQL has no ALTER ... ALTER CONSTRAINT for a CHECK"*); `capabilities.ts:27, 39`; `tests/test_docs.py:1273` | Confirmed. Six homes, two constraint restatements, one new migration. |
| **E14** | The detail screen renders from the list payload | Searched every `fetch(` site in the frontend | `load.ts:22` fetches `/api/listings?limit=200`; the only other listing fetch is the *seller's* own route. No caller of `/api/listings/{id}` anywhere | Confirmed. The server's document list has no reader; the four documents a buyer sees are fixtures at `logic.js:1899-1904`. |
| **E15** | The three fields degrade cleanly when hidden | Read each render site for a null guard | `logic.js:1926` guards `services` (`hasProse: !!p.services`); `:1930` adds the Hours row unconditionally; `:1934` hard-codes `hasProse: true` for `facility`; `:1928` the same for `staff` | **Refutes my own first draft.** One of three is clean; the others need the guard used at `:1937`. |
| **E16** | City and state are rendered | Searched for any read of either on a listing | `load.ts:216-274` copies neither onto the client shape; `logic.js:1263` parses the state out of the market string with a `"TX"` default | **Refuted.** Sent, never drawn. |
| **E17** | The three side findings | Read each site | `P[0]` fallback at `logic.js:1855` and `:2505`; the `bldg` else-arm at `:1859`, surfacing at `:1873, 1897, 1922, 1936`; `ebitdaLabel` at `:1032`, no template reader | All three confirmed. |

---

## 9. What happens next

Nothing, until you rule. Specifically:

1. **Decision A** — gate Hours, Services offered and Facility description on `IDENTITY`? *(I
   recommend yes.)*
2. **Decision B** — leave the asking price public? *(I recommend yes — and fix the filter leak
   regardless, because revenue leaks through it today.)*
3. **Decision C** — fix the map route to use the same rule as the listing route? *(I recommend yes;
   no debate expected.)*

The filter fix is the one piece I would suggest doing whatever you decide, because it is a live leak
for revenue now and it blocks any future decision to hide a number.
