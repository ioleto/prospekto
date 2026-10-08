import ast,pathlib
def test_controls():
 s=pathlib.Path('app/main.py').read_text(); n={x.name for x in ast.walk(ast.parse(s)) if isinstance(x,ast.FunctionDef)}; assert 'SQLite is not supported' in s and {'require_csrf','require_user','send'}<=n
def test_migration():
 s=pathlib.Path('migrations/002_secure_sending.sql').read_text().lower(); assert 'unique(owner_id,idempotency_key)' in s and 'suppressions' in s and "'uncertain'" in s
