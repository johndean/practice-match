# Ruling D-C60 — the admin decision loop is closed, and the applicant reads the real reason

**John, 2026-09-21, verbatim:**

> The VIN Foundation Admin should have the option to request further information from applciation
> and or add detailed explanation of the rejection

**Ruled the same day**, on the audit below: **close the whole loop** (a proper multi-line note
drawer AND the read-back on the row), and **show the applicant the real decline reason in the app**.

## What already worked when he asked — measured, not assumed

Both capabilities existed and completed. `POST /api/admin/users/{id}/decide` takes `approve`,
`decline` and `request_info` (`app/api/admin_users.py:108`); a note is MANDATORY on decline and
request-info (`:129`) and bounded at **4,000 characters** (`:160`, `:276`); it is stored
(`:713-717` — `decision_note` for approve/decline, `info_request` for request_info), audited
(`:755-757`) and emailed to the applicant under the heading "What the reviewer wrote:"
(`app/mail/templates.py:169-174`). The applicant answers in a real textarea on the gate's "More
information requested" card, and `app/api/applications.py:282-283` stores the reply.

**So the server was never the constraint. The writing surface and the read-back were.**

## The five gaps (each survived an adversarial check that defaulted to refuting)

1. **`window.prompt` is one line.** `frontend/src/admin/users.ts:421-423` is the entire
   note-capture surface. The server offers 4,000 characters and the UI offers about one line of
   them — which is John's sentence exactly.
2. **Any refusal destroys the note.** `note` is a local (`:424-434`); the prompt is re-opened with
   no default. A `409 STATE`, a `409 ROLE_CONFLICT`, a network failure or text over 4,000
   characters all lose it — and the over-length refusal renders as a generic "The request could
   not be understood", which does not mention length.
3. **No reviewer can read back any note.** `LIST_SQL` (`admin_users.py:509-530`) omits
   `decision_note`, `info_request` and `answer`, and the list payload is all the tab reads. The
   question is invisible from the moment it is sent, including to a colleague.
4. **The applicant's reply is invisible to the person who asked for it.** The row returns to the
   queue showing the applicant's ORIGINAL words (`users.ts:344-358` reads `fields.intent`), with no
   marker that anything was asked or answered. A broken working loop, not a cosmetic gap.
5. **No follow-up question is possible** (`request_info` is allowed from `pending` only,
   `:135`) and the screen does not say why the button disappeared.

`GET /api/admin/users/{account_id}` ALREADY serves `decision_note`, `info_request`, `answer`,
`answered_at` and the application history (`:592-628`) — **and has zero callers in `frontend/`**.
The same "server built, client never wired" shape A36 found in `users.ts` itself.

## The live defect this also removes

The declined applicant's in-app card **hard-codes** "Reason given: Affiliation not verified"
(`frontend/src/logic.js`), so EVERY declined applicant reads that sentence whatever the reviewer
wrote, while `applications.py:316` already serves them the real `decision_note` and nothing renders
it. Fabricated data shown to a real person — what D-C53 exists to remove.

## Precedent, so nothing here is invented

- The **Listings** tab already puts a rejection reason back on its own row
  (`frontend/src/admin/listings.ts:190`), commented as "the one thing its seller is owed and the
  one thing the reviewer needs to see beside the pill." The Users tab had no equivalent: two admin
  tabs, two answers to one question.
- V3 draws no decision drawer, but the **interest modal** is structurally one already — scrim,
  title, 30 px close, textarea, a `modal.error` slot (exactly what gap 2 needs) and a
  primary/secondary button pair. The applicant-answer card's own textarea is the closer match for
  a field inside a card. Composing from these is the A8 pattern.
- CLAUDE.md already lists "an application detail or drill-down" as an unbuilt composition item for
  the admin spec. This ruling answers part of it.

## Consequence John accepted

Showing the real reason in-app means **reviewers write knowing the applicant reads it verbatim** —
the same contract the decline email already has.

## Scope

Amendment family **A54**. `LIST_SQL` gains the three fields. Approved states that render the Users
tab and the declined gate card re-base, MEASURED (the A33 method) rather than predicted.
