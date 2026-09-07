# Design request — Rev 3: Admin "Launch sign-ups" tab (and the Permissions tab's Meaning column)

**Date:** 2026-09-08 · **From:** John (VIN Foundation) · **For:** the Rev 3 design package · **Blocks:** Wave 2a Task I5d.5 (`docs/superpowers/plans/2026-09-08-launch-signups-admin.md`)

Two things are owed by Rev 3. **Section 1** is a new fifth tab on the VIN Foundation Admin screen. **Section 2** is a column of plain-language copy the Permissions tab has been rendering empty since it shipped.

Everything below describes *what the screen must let a person do and what data it has to show*. The visual decisions are the designer's. Where an existing V3 pattern already answers a question, this document names it rather than re-inventing it — reuse is preferred over novelty everywhere it fits.

---

## Section 1 — the Admin "Launch sign-ups" tab

### Why it exists

The public Coming Soon page at `foundation.vin` collects email addresses with one promise, printed on the page: **"One message, when it launches. Nothing else, and never shared."** Those addresses are in the production database and nobody at the VIN Foundation can see them, count them, export them, or send the message that was promised. The API for all four now exists. The screen does not, because the approved design has four admin tabs and no fifth.

### Where it lives

The fifth tab on the existing **VIN Foundation Admin** screen (`isAdmin`), beside **Users · Listings · Requests · Data Sources**. Suggested label: **Launch sign-ups**. Its count pill shows the total number of sign-ups.

### The data it has, exactly

The table behind it holds six fields per sign-up, and nothing else. There is no name, no practice, no phone number — the page asked for an address and nothing more:

| Field | Example | Notes |
|---|---|---|
| id | `8f3c…` (uuid) | never shown to a person; it is the row's identity |
| email | `dr.mendes@example.org` | the address as it was typed |
| source | `coming-soon` | which page or campaign collected it; today there is one value |
| consent version | `coming-soon-v1` | which wording of the promise this person agreed to |
| signed up at | 1 September 2026, 14:02 | |
| launch email sent at | *empty*, or a date | empty means this person has not been written to yet |

### What the tab must show

1. **A table of sign-ups, newest first**, built from the six fields above. Four columns is the house style; a workable split is *Address* (with the sign-up date beneath it) · *Where from* (source, with the consent version beneath it) · *Launch email* (a status pill: not sent / sent, with the date beneath it) · a fourth column the designer decides — see the open question about row actions below.
2. **Counts, visible without scrolling.** Three numbers matter and are the reason someone opens this tab: **total sign-ups**, **already emailed**, **not yet emailed**. There is nowhere in the current admin design that shows a summary above a table, so this is genuinely new and the designer should rule on it.
3. **Filters** for *source* and *consent version*. The API returns the list of values that actually exist, with a count for each, so these can be menus rather than free text. If Rev 3 would rather not draw filters, say so and the tab ships without them — the API does not require them.
4. **An Export action** that downloads the whole (filtered) list as a spreadsheet file. One button, table-level, not per row.
5. **A Send launch email action**, table-level, with a confirmation step that is **not** optional (below).
6. **An "already sent" state.** Once the launch email has gone to everyone, the action must say so rather than sitting there looking clickable. If people sign up after the send, the action becomes available again for just those people ("Send to 12 new sign-ups") — that is the correct behaviour and the design should make it readable.
7. **A footnote**, in the position and voice the other four tabs use. Draft, to be edited: *"These addresses came from the Coming Soon page, which promised one message and nothing else. The launch email is sent once per address and never again. Nothing here is shared outside the VIN Foundation."*

### The Send action, in detail

This is the only irreversible thing on the screen and the part most worth the designer's attention.

- **Step 1 — confirm.** Pressing Send must open a confirmation that states the number of people about to be written to ("This will email 1,830 people. It cannot be undone."), and the exact subject line they will see. The system can produce those numbers before anything is sent, so the confirmation is showing real figures, not a guess.
- **Step 2 — sent.** After confirming, the confirmation becomes an acknowledgement: how many were queued, and that they leave over the following hour or so rather than instantly.
- **Refusals the design must have somewhere to put.** Four, each a real answer the screen can receive:
  - *"Confirm your password to continue."* — sending is a re-authenticated action, like Revoke on the Users tab. The existing re-auth prompt is reused.
  - *"The launch email cannot be sent while the site is in coming-soon mode."* — before the site opens, the count is readable and the message is not sendable.
  - *"Your account cannot do this."* — the tab is visible to staff, but only an admin may send.
  - A partial send: the action works in batches of 500 and reports how many are left. Either the design shows that ("500 sent, 1,330 remaining — Send next 500") or it hides it behind a single button that repeats itself; the designer should choose.

### V3 patterns to reuse — named, so nothing is invented

Every one of these already exists in `Practice Match V3.dc.html` and should be reused rather than redrawn:

| Need | Existing pattern | Where it is |
|---|---|---|
| The tab itself | `admin.tabs` — a pill-counted button, one style for active and one for inactive, in the navy band under the "VIN Foundation Admin" heading | `adminVals()`, the `tabs:` array |
| The table shell | the white, rounded, hairline-bordered card with `overflow: hidden` and `shadow-sm` | the `isAdmin` block |
| The column header row | `admin.headStyle` + `admin.columns` — a CSS grid whose template string is declared per tab (`grid: "1.1fr 1.5fr .7fr 1fr"` on Users), uppercase 10.5 px steel labels | `adminVals()`, `sets.<tab>.grid` |
| A table row | `admin.rows` → `row.cells` → the `cell(main, sub, pill, pillTone, actions)` shape: an optional pill, a 14 px navy main line, a 12.5 px steel sub-line, and a right-aligned button group | `adminVals()`, `cell()` |
| Status pills | the five existing tones — `ok` (navy on white), `warn` (navy on pale blue), `bad` (grey on white, dark border), `info` (navy on white, blue border), `mute` (grey on off-white). "Sent" reads as `ok`; "Not sent" reads as `mute`. **No sixth tone, please** | `adminVals()`, `cell()`'s `tones` map |
| Buttons | `A(label, tone)` — uppercase 12 px display type, 7×12 padding, 6 px radius. `primary` = white on blue; `danger` = grey text, subtle border; default = navy on white | `adminVals()`, `A()` |
| The confirmation | the buyer's **"Request information" modal** on the detail screen: a fixed `rgba(0,58,112,.55)` scrim, a 520 px white card, a band header carrying `modal.title` and `modal.sub` with an X close button, a body, an error strip, and a primary/secondary button pair — and it already has exactly the two-state form → sent shape this needs | the `interestOpen` block; `modal:` in `renderVals()` |
| The key-figure block inside the confirmation | that same modal's `modal.shared` list — steel label left, navy value right, on an off-white rounded panel. "People to email · 1,830" fits it exactly | the `interestOpen` block |
| The footnote | the 12 px steel paragraph under the table, `max-width: 90ch` | `admin.footnote` |

### What is genuinely new, and needs a decision rather than a reuse

1. **A summary of counts above a table.** No admin tab has one.
2. **Table-level actions.** Every existing admin action is a button inside a row. Export and Send belong to the whole table. Where do they sit — a bar above the table, the top-right of the card header, beneath the footnote?
3. **Filter controls in an admin table.** None of the four existing tabs has any.
4. **A row action, or none.** The other four tabs all have a fourth "action" column. This table may not need one. If it does not, does the row keep a fourth column of information instead, or does the grid become three columns?

### The states the visual oracle needs

The Playwright suite compares the built app against the design at **zero pixels**, and each state has to be reachable in the design file as well as in the app. Please make each of these a distinct, reachable state:

| State | What it shows |
|---|---|
| `admin-launch-signups` | the tab at rest — a populated table, the counts, both actions available |
| `admin-launch-signups-empty` | no sign-ups yet (the table's empty state, which the other tabs also lack — one is needed here because a fresh QA database really is empty) |
| `admin-launch-signups-confirm` | the confirmation open, showing the number of people and the subject line |
| `admin-launch-signups-sent` | the acknowledgement, immediately after sending |
| `admin-launch-signups-all-sent` | the tab at rest with every sign-up already emailed — the Send action in its "nothing to send" form |

If the design chooses to draw the partial-send state ("1,330 remaining") or the coming-soon refusal, those become oracle states too; if it does not, the tab simply will not have them.

### Rules this screen inherits, for the designer's information

- The four admin tabs are **not** responsive today and neither is this one; it is a desktop screen at 1440 px.
- No new typeface, no new colour, no new pill tone, no new button tone. The design system is `colors_and_type.css` + `preview/_preview.css` + `ui_kits/vin/kit.css`.
- Nothing on this screen is a map, so no attribution line is required here.
- The address column shows real email addresses to staff. That is intended and is the point of the tab; there is no redaction requirement.

---

## Section 2 — Also owed by Rev 3: plain-language "Meaning" values for the Admin → Permissions table

**John:** *"Rev 3 must provide stakeholder-approved plain-language Meaning values before this is considered complete."*

The Admin → Permissions tab is a read-only view of the one permission matrix the whole system is governed by. Its table already has a **Meaning** column, and that column is **empty on every row today** — deliberately: the code carries no plain-language description of any permission, and rather than print a permission's own machine name twice, the column was left blank until this copy is ruled. (`frontend/src/admin/permissions.ts`: *"a permission without one gets an EMPTY Meaning cell — never a second copy of its own name … Absent beats faked."*)

**What is needed:** one sentence per row, in the voice a VIN Foundation board member would use, saying what a person holding this permission can do. Not the endpoint, not the screen name — the capability. For example, `users.decide` might read *"Approve, decline, suspend or withdraw a member's access."*

**The columns of that table**, for reference, are: Permission · **Meaning** · Anonymous · Applicant · Buyer · Seller · Staff · Admin. The tick columns are generated from the code and are not the designer's to fill.

**Every permission, with the Meaning cell empty for the designer and the stakeholders to fill.** "Held by" and "what it governs" are given only as context for writing the sentence — they are not copy.

| # | Permission | Held by | What it governs (context — not the copy) | **Meaning** *(to be written)* |
|---|---|---|---|---|
| 1 | `abuse.investigate` | Admin | reading the contents of member-to-member messages during an abuse investigation; every such read is logged | |
| 2 | `account.self` | everyone signed in | your own account: your details, your password, signing out, the status of your own application | |
| 3 | `audit.read` | Staff, Admin | reading the audit trail of who did what | |
| 4 | `data_sources.read` | Staff, Admin | the Data Sources tab: which datasets are cleared, unresolved or blocked | |
| 5 | `engine.activate` | Admin | switching which mapping engine the platform uses; needs a fresh password | |
| 6 | `layer.google_live` | Buyer, Seller, Staff, Admin | the live Google map layers, where the licence and the engine allow them | |
| 7 | `layer.satellite` | Buyer, Seller, Staff, Admin | the satellite view toggle on the map | |
| 8 | `licence.decide` | Admin | recording a licence decision about a dataset — what may and may not be shown; needs a fresh password | |
| 9 | `listing.manage_own` | Seller | creating and editing your own practice listings | |
| 10 | `listing.publish` | Staff, Admin | making a listing visible to buyers, or taking it back down | |
| 11 | `listing.read` | Buyer, Seller, Staff, Admin | viewing published practice listings | |
| 12 | `listing.review` | Staff, Admin | the Listings tab: reviewing what sellers have submitted | |
| 13 | `market.read` | Buyer, Seller, Staff, Admin (and anonymous visitors only while the platform is set to public market data) | the community and market data on the map and in the listings | |
| 14 | `page.admin` | Staff, Admin | reaching the VIN Foundation Admin screen at all | |
| 15 | `page.browse` | Buyer, Seller, Staff, Admin | the Browse screen | |
| 16 | `page.gate` | everyone, including signed-out visitors | the sign-in, apply, under-review and not-granted screens | |
| 17 | `page.seller` | Seller | the seller's own dashboard and listing wizard | |
| 18 | `permissions.read` | Staff, Admin | this table | |
| 19 | `request.answer_own` | Seller | answering the requests buyers send about your own listings | |
| 20 | `request.create` | Buyer, Seller | asking a seller for information about a practice | |
| 21 | `request.oversee` | Staff, Admin | the Requests tab: seeing that a request exists and whether it was answered, never its contents | |
| 22 | `request.read_own` | Buyer, Seller | your own conversations | |
| 23 | `roles.grant` | Admin | granting or removing a role — including making somebody staff or an admin; needs a fresh password | |
| 24 | `seller.apply` | Buyer | applying to become a seller | |
| 25 | `signups.export` | Staff, Admin | downloading the Coming Soon launch sign-up list as a file; every download is logged | |
| 26 | `signups.notify` | Admin | sending the one launch email the Coming Soon page promised; cannot be undone, needs a fresh password | |
| 27 | `signups.read` | Staff, Admin | seeing and counting the Coming Soon launch sign-ups | |
| 28 | `tokens.manage` | Admin | creating and withdrawing the automated credentials the platform's own tooling uses; needs a fresh password | |
| 29 | `users.decide` | Staff, Admin | approving, declining, asking for more information, or suspending a member | |
| 30 | `users.review` | Staff, Admin | the Users tab: the list of applicants and members | |
| 31 | `users.revoke` | Staff, Admin | permanently withdrawing a member's access; needs a fresh password | |
| 32 | `users.view_detail` | Staff, Admin | opening one applicant's full application; every view is logged | |

**Notes for whoever writes these.**

- Thirty-two rows. Rows 25–27 are new as of 2026-09-08 (Wave 2a Task I5d); the other twenty-nine have existed since the matrix shipped.
- Several rows say *"needs a fresh password"*. That is a real property (the system requires the person to re-enter their password within the last ten minutes before it will do these things) and the Meaning sentence is a good place to say so in plain words, but that is the writer's choice.
- Several rows say *"is logged"*. Also real, also worth saying plainly.
- The table is generated from the code, so if a permission is added later it appears here with an empty Meaning cell until somebody writes one. That is by design — the missing sentence is visible rather than invented.
