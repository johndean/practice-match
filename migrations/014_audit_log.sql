CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  request_id text,
  actor_id uuid,
  actor_role text,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id text,
  before jsonb,
  after jsonb,
  ip inet,
  ua text,
  reason text
);
CREATE INDEX audit_log_target_idx ON audit_log (target_type, target_id, at DESC);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
REVOKE UPDATE, DELETE ON audit_log FROM CURRENT_USER;
-- Append-only must hold for the role that actually connects. Both the compose role (pm) and
-- Railway's template role (postgres) are SUPERUSERS, which bypass ACLs, so the REVOKEs above are
-- belt and braces only; the trigger is the control (Task I1 ruling, 2026-09-06).
CREATE FUNCTION audit_log_is_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'P0001';
END $$;
CREATE TRIGGER audit_log_append_only
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();
