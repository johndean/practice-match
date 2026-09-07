CREATE TABLE email_outbox (
  id bigserial PRIMARY KEY,
  to_email citext NOT NULL,
  template text NOT NULL,
  params jsonb NOT NULL DEFAULT '{}',
  idempotency_key text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','suppressed','failed','bounced','complained')),
  provider_id text,
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  -- When RESEND said the recipient's mail server accepted it (the `email.delivered` webhook),
  -- which is a different fact from `sent_at` (when WE handed it to Resend) and the one staff
  -- need when a member says the email never arrived. Task I6 fix round 1, F3.
  delivered_at timestamptz
);
CREATE INDEX email_outbox_due_idx ON email_outbox (status, next_attempt_at) WHERE status = 'queued';

CREATE TABLE email_suppression (
  email citext PRIMARY KEY,
  reason text NOT NULL CHECK (reason IN ('bounce','complaint','manual')),
  at timestamptz NOT NULL DEFAULT now()
);
