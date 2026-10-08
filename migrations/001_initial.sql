CREATE TABLE IF NOT EXISTS campaigns (
  id text PRIMARY KEY, name text NOT NULL, status text NOT NULL DEFAULT 'draft', created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS prospects (
  id text PRIMARY KEY, campaign_id text REFERENCES campaigns(id) ON DELETE SET NULL,
  company_name text NOT NULL, email text, phone text, website text, provenance text NOT NULL,
  b2c boolean NOT NULL DEFAULT false, consent_documented boolean NOT NULL DEFAULT false,
  consent_proof text, status text NOT NULL DEFAULT 'new', deleted_at timestamptz, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id text PRIMARY KEY, actor text NOT NULL, action text NOT NULL, entity_id text, metadata jsonb, created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prospects_email ON prospects(email);
