CREATE EXTENSION IF NOT EXISTS citext;
CREATE TABLE IF NOT EXISTS smtp_profiles (
  id bigserial PRIMARY KEY, owner_id text NOT NULL, name text NOT NULL, host text NOT NULL,
  port integer NOT NULL CHECK (port BETWEEN 1 AND 65535), username text NOT NULL,
  password_ciphertext text NOT NULL, use_tls boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner_id, name)
);
CREATE TABLE IF NOT EXISTS suppressions (
  email citext PRIMARY KEY, reason text NOT NULL DEFAULT 'manual', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS send_attempts (
  id bigserial PRIMARY KEY, owner_id text NOT NULL, prospect_id text NOT NULL REFERENCES prospects(id),
  profile_id bigint NOT NULL REFERENCES smtp_profiles(id), idempotency_key text NOT NULL,
  status text NOT NULL CHECK (status IN ('sending','sent','uncertain','failed')),
  subject text NOT NULL, body text NOT NULL, error_code text, error_message text,
  sent_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner_id, idempotency_key)
);
