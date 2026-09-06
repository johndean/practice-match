CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE account (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext NOT NULL UNIQUE,                                   -- any domain; case-insensitive
  password_hash text NOT NULL,
  state text NOT NULL CHECK (state IN ('unverified','verified','pending','needs_review','declined','active','suspended','revoked')),
  display_name text,
  affiliation_label text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_sign_in_at timestamptz
);

CREATE TABLE session (
  id_hash text PRIMARY KEY,                                       -- sha256 of the 256-bit random id; the id itself is never stored
  account_id uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  reauth_at timestamptz,
  ip inet,
  user_agent text,
  revoked_at timestamptz
);
CREATE INDEX session_account_idx ON session (account_id) WHERE revoked_at IS NULL;

CREATE TABLE email_token (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES account(id) ON DELETE CASCADE,
  purpose text NOT NULL CHECK (purpose IN ('verify','reset','invite')),
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz
);
