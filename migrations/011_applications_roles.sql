CREATE TABLE application (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('buyer','seller')),
  fields jsonb NOT NULL,
  flags text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','needs_review','approved','declined')),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  decided_by uuid REFERENCES account(id),
  decided_at timestamptz,
  decision_note text,
  info_request text
);
CREATE INDEX application_queue_idx ON application (status, submitted_at);

CREATE TABLE role_grant (
  id bigserial PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('buyer','seller','staff','admin')),
  granted_by uuid NOT NULL REFERENCES account(id),
  granted_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE UNIQUE INDEX role_grant_active_idx ON role_grant (account_id, role) WHERE revoked_at IS NULL;
