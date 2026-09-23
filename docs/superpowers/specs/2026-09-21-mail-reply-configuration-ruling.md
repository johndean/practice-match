# D-C64 — Where replies go, and who may change it

**Ruled by John, 2026-09-21.** A record of decisions, not a new design. The Admin Settings tab
and the re-authentication dialog are already designed in
`docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` and already planned as
family **A41** in `docs/superpowers/plans/2026-09-14-admin-control-surface.md`; John approved
A41–A47 on 2026-09-13 and again on 2026-09-14 ("I already said YES to this: A41–A47"). Nothing
here reopens that. This ruling adds **one Settings row** and the configuration behind it.

## 1. What prompted it

Enabling Resend on QA surfaced that `MAIL_REPLY_TO` is a documented placeholder
(`.env.example:19`, "placeholder until the VIN Foundation names the mailbox replies should
reach"), and that nothing in the product ingests inbound mail. `app/api/webhooks.py` handles
outbound Resend events only (`email.delivered`, `email.bounced`, `email.complained`); it is not
a path for receiving replies. John's words: *"surface the email address to use in the VIN
FOUNDATION ADMIN."*

## 2. The rulings

1. **No inbound ingestion.** Replies are read by a human in a normal mailbox. The product does
   not receive, parse, thread or store inbound email. Reconsider only if an audit requirement
   demands it.
2. **The reply-to mailbox becomes an editable Admin Settings row** — a row ADDITIONAL to the four
   in the admin control surface spec §2 (market data, census vintage, launch mail, api tokens)
   and to the Permissions row planned as row 5 (plan Task 19). §2's ruled table is amended by
   this ruling to carry it.
3. **The value is NOT seeded.** `practicematch@foundation.vin` was considered and rejected as a
   seed because nobody has confirmed the mailbox exists. This programme's own rule — A-I5d.4,
   "Do not invent the address" — applies: a seeded mailbox that receives nothing loses replies
   silently, which is worse than the placeholder, which at least bounces. The row ships empty,
   the code falls back to `settings.mail_reply_to`, and the VIN Foundation sets the real address
   in Admin once the mailbox exists.
4. **`settings.write` is in `REAUTH`.** Changing where member replies go passes through the
   step-up dialog A41 Task 4 builds. This is spec §1 rule 4 applied consistently ("Every action
   in REAUTH … passes through the re-authentication dialog"), and it closes a verified bypass: a
   permission in neither `REAUTH` nor `TOKEN_DENIED` lets an api token holding `admin` change the
   reply-to on every outgoing email with no password and no person present.
5. **The address must be on an approved domain.** `REPLY_TO_DOMAINS = ("foundation.vin",)`; any
   other domain is refused 422 naming the allowed set. Defence in depth beside the step-up, and
   the control that makes redirection off-domain impossible rather than merely audited.
6. **The address is resolved at ENQUEUE time and stored on the outbox row**, not read at send
   time. Reading a mutable setting inside the sender would break the Resend idempotency
   invariant — attempt N and attempt N+1 of one row would carry different payloads under one
   idempotency key — and would leave no record of which address a sent message actually carried.
   Storing it per row fixes both.

## 3. Corrections this design went through, recorded so they are not re-made

Each was produced by adversarial verification of the first draft and each refuted it.

- **REAUTH membership never barred drawing a control.** The first draft held that
  `engine.activate` and `signups.notify` could not be drawn, citing A36's Revoke. A36's bar was
  the missing step-up ELEMENT, not the REAUTH row, and CLAUDE.md's A53 paragraph already warns
  that "A36's identically-worded ruling does not transfer". Spec §3 composes that element and
  §2 draws both controls.
- **`base_url` is not a body-injection mechanism.** It is interpolated into the shared
  `TEXT_DOC`/`HTML_DOC` envelopes; each template body is formatted from its own `params` tuple,
  so a `{reply_to}` in a body raises `KeyError` unless added to that tuple.
- **The declined email's "reply with more information" is design copy naming an in-product
  button**, ported verbatim from the declined gate card and pinned to the design file by
  `tests/mail/test_templates.py`. It is not a mailbox pointer, and re-wording it would be a
  design amendment. The same sentence also serves `seller_application_declined`, for which no
  seller application screen exists (A47, unbuilt).
- **A suspended account is not wholly locked out.** `RESETTABLE_STATES` gates only the ISSUING
  endpoint; `POST /auth/password/reset` performs no state check and suspension does not retire
  outstanding `email_token` rows, so an account suspended while holding an unexpired reset token
  can still redeem it. Logged as its own finding in §5; it changes no decision here.
- **Migration numbering is by reserved band**, not highest-plus-one (`DEPLOY.md:132`, :137):
  platform and hotfix migrations take **090–099**, where 097 and 098 are free. A number is
  claimed by adding its row to `docs/MIGRATIONS.md` in the same commit.

## 4. Consequences accepted

- **The four frozen `admin-*` hashes must NOT move.** An earlier draft of this ruling said the
  fifth tab re-bases them and that spec §1 rule 6 carried the re-pin. Both halves were wrong, and
  the correction is recorded rather than quietly edited: rule 6 says a composition "ADDS elements
  behind adapter presence or a new tab, so the four captures keep their pixels through the oracle
  stub", and plan Task 3 rules it outright — "**Re-basing states: NONE** … This is the one task in
  A41 where a frozen hash could legitimately move, and it must not. **Therefore the tab is gated on
  adapter presence** (`sc-if` on a render value `admin.hasSettings`)". A moved `admin-*` hash means
  the adapter gate did not hold; the response is to fix the gate, never to re-pin.
- `settings.write` entering `MATRIX`, `REAUTH` and `AUDITED` moves several count pins
  (`PM.ADMINISTRATIVE` 20 → 21 in two independent places) and requires the generated TypeScript
  twin to be regenerated in the same commit.
- The settings router is mounted only under `SITE_MODE=app`, so this row does not exist on
  production until launch. Accepted; production sends no mail today either.

## 5. Open items, owned by John

1. **The mailbox itself.** Nothing ships a real address until the VIN Foundation names one.
2. **`RESEND_WEBHOOK_SECRET` is unset on api**, so every Resend event is rejected: bounces never
   suppress, complaints never suppress, `delivered_at` is never stamped. Register
   `https://qa.foundation.vin/api/webhooks/resend` and set the signing secret on api only.
3. **A suspended account can redeem a pre-existing reset token** (§3). It does not restore
   access — `REFUSED_STATES` still blocks sign-in — but it is a state nobody designed. Whether
   suspension should retire outstanding tokens is a lifecycle question and John's to rule.
