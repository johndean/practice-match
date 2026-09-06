-- Coming Soon production mode (spec 2026-09-06): launch-notification sign-ups from foundation.vin.
-- gen_random_uuid() is built in from PostgreSQL 13; both Railway databases are pinned to postgis/postgis:16-3.5 (DEPLOY.md). IF NOT EXISTS matches 001_init.sql.
-- No email is sent from here; the Identity wave's Resend pipeline reads this table at launch.
CREATE TABLE IF NOT EXISTS interest_signup (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text        NOT NULL,
  email_normalised text        NOT NULL UNIQUE,
  consent_version  text        NOT NULL,
  source           text        NOT NULL DEFAULT 'coming-soon',
  created_at       timestamptz NOT NULL DEFAULT now()
);
