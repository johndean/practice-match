-- Per-buyer disclosure (spec 2026-09-18, directive §4, §16, §18): the buyer/listing
-- authorization relationship the wizard-step audit's finding 4 found missing entirely. Claims the
-- number and the name reserved for A43's unbuilt "Requests" family
-- (docs/superpowers/specs/2026-09-13-admin-control-surface-design.md §5); this table's shape is a
-- superset of that spec's draft (PENDING/APPROVED/DENIED/REVOKED rather than
-- pending/accepted/declined, and the disclosure-level columns directive §4/§16 require), so a
-- later A43 admin-tab build reads this table rather than a second, competing one.
--
-- `request_event` (also reserved by that spec) is deliberately NOT created here: every status
-- transition below already writes an `audit_log` row (target_type='request'; Tasks 5/6), and a
-- per-request history view can read that the way the admin Users/Listings "History" tabs already
-- do, rather than duplicating the trail in a second table nothing else would keep in sync.
CREATE TABLE request (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id                uuid        NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  buyer_user_id             uuid        NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  -- Denormalised from listing.seller_id at creation (directive §4 names it explicitly, and it is
  -- what makes the seller's inbox query -- Task 4's `list_inbox` -- an index-only lookup rather
  -- than a join on every read). This product has no listing-ownership-transfer feature, so there
  -- is no path by which this could drift from listing.seller_id after the row is written.
  seller_user_id            uuid        NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  message                   text,
  status                    text        NOT NULL DEFAULT 'PENDING'
                                        CHECK (status IN ('PENDING','APPROVED','DENIED','REVOKED')),
  requested_disclosure_level text       NOT NULL DEFAULT 'FULL_CONFIDENTIAL'
                                        CHECK (requested_disclosure_level IN
                                          ('IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS','FULL_CONFIDENTIAL')),
  approved_disclosure_level text        CHECK (approved_disclosure_level IN
                                          ('IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS','FULL_CONFIDENTIAL')),
  requested_at              timestamptz NOT NULL DEFAULT now(),
  reviewed_at               timestamptz,
  reviewed_by               uuid        REFERENCES account(id) ON DELETE SET NULL,
  denial_reason             text,
  -- Directive §4: "where applicable". Nothing in this plan writes it (no design surface asks a
  -- seller for an expiry); the authorization check in Task 3 honours it if a later feature does.
  expires_at                timestamptz,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT request_seller_is_not_buyer_ck CHECK (buyer_user_id <> seller_user_id),
  -- One-directional (not a bidirectional `=`): a REVOKED row keeps its approved_disclosure_level
  -- and its original reviewed_at/reviewed_by for history, so "has all three fields" must not imply
  -- "is APPROVED right now" or a revoked row would fail this the moment it is revoked.
  CONSTRAINT request_approved_needs_decision_ck CHECK (
    status <> 'APPROVED' OR (approved_disclosure_level IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
  CONSTRAINT request_denied_needs_review_ck CHECK (status <> 'DENIED' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
  CONSTRAINT request_pending_has_no_decision_ck CHECK (
    status <> 'PENDING' OR (reviewed_at IS NULL AND reviewed_by IS NULL AND approved_disclosure_level IS NULL))
);
-- Directive §23: the authorization check (Task 3) is one indexed lookup on exactly this key. The
-- partial WHERE is what makes "one active request per (listing, buyer)" a database invariant
-- rather than an application promise -- safe to add here because this is a brand-new table with no
-- existing rows, unlike `account`'s one-open-application invariant (CLAUDE.md's A36 note), which
-- could not add a partial unique index without first auditing every row already on QA/production.
CREATE UNIQUE INDEX request_one_active_per_buyer_listing_uq ON request (listing_id, buyer_user_id) WHERE status IN ('PENDING','APPROVED');
CREATE INDEX request_seller_inbox_idx ON request (seller_user_id, status, requested_at DESC);
CREATE INDEX request_buyer_mine_idx  ON request (buyer_user_id, requested_at DESC);
