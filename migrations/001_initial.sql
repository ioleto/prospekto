CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prospects (id TEXT PRIMARY KEY, campaign_id TEXT, company_name TEXT NOT NULL, email TEXT, phone TEXT, website TEXT, provenance TEXT NOT NULL, b2c INTEGER NOT NULL DEFAULT 0, consent_documented INTEGER NOT NULL DEFAULT 0, consent_proof TEXT, status TEXT NOT NULL DEFAULT 'new', deleted_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity_id TEXT, metadata TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_prospects_email ON prospects(email);
