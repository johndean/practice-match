-- §9 license_audit: re-read each source's terms URL quarterly; flag drift for staff review.
-- The licence LEDGER (license_audit_log), distinct from the security audit trail (app.auth.audit,
-- A-C0 ¶3) -- this table is never read or written by anything in app/auth/.
ALTER TABLE dataset_registry ADD COLUMN drift_flagged boolean NOT NULL DEFAULT false;
CREATE TABLE license_audit_log (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL REFERENCES dataset_registry(dataset_key),
  checked_at timestamptz NOT NULL DEFAULT now(),
  url text NOT NULL,
  content_sha256 text,
  http_status integer,
  changed boolean NOT NULL DEFAULT false
);
CREATE INDEX license_audit_log_ds_idx ON license_audit_log (dataset_key, checked_at DESC);
