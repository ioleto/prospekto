import os,pathlib,psycopg
with psycopg.connect(os.environ['DATABASE_URL']) as c:
 c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version text primary key, applied_at timestamptz not null default now())')
 for p in sorted(pathlib.Path('migrations').glob('*.sql')):
  v=p.name.split('_')[0]
  if not c.execute('SELECT 1 FROM schema_migrations WHERE version=%s',(v,)).fetchone(): c.execute(p.read_text());c.execute('INSERT INTO schema_migrations(version) VALUES(%s)',(v,))
