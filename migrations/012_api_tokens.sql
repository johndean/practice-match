CREATE TABLE api_token (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  role text NOT NULL CHECK (role IN ('buyer','seller','staff','admin')),
  token_hash text NOT NULL UNIQUE,
  created_by uuid NOT NULL REFERENCES account(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  last_used_at timestamptz
);
