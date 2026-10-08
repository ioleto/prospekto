import os
from pathlib import Path
import psycopg


def main():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("DATABASE_URL must be a PostgreSQL URL")
    root = Path(__file__).resolve().parent.parent
    migrations = sorted((root / "migrations").glob("*.sql"))
    with psycopg.connect(url) as db:
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        for path in migrations:
            version = path.name.split("_", 1)[0]
            if db.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,)).fetchone():
                continue
            db.execute(path.read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))


if __name__ == "__main__":
    main()
