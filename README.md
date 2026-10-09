# Prospekto

Prospekto is a deliberately bounded French-language prospecting workspace. The runtime database is **PostgreSQL only**; SQLite is not supported or used by the application.

## Local / Portainer deployment

1. Copy `.env.example` to `.env` and set every required secret. Generate an Argon2 password hash; do not put a plaintext password in the repository.
2. Set `SWAG_NETWORK` to the existing Docker network used by SWAG (the network must already exist; it is not created by this Compose project).
3. Run `docker compose up --build` (or deploy the same Compose file in Portainer).
4. Put the app behind SWAG/reverse proxy using `swag/prospekto.subdomain.conf`; set `COOKIE_SECURE=true` only when HTTPS is active.

The app container runs `python -m app.migrate` before Uvicorn. Migrations are versioned and recorded in `schema_migrations`; each migration runs in the same PostgreSQL transaction as its version record.

### Login

Open `/login`. Enter the value of `ADMIN_USERNAME` (default: `admin`) and the password corresponding to the Argon2id hash in `ADMIN_PASSWORD_HASH`. There is no database-stored admin account to create: authentication is configured from the container environment at startup. Do not use or commit a plaintext password.

## Current limits

SMTP profiles store authenticated encrypted passwords, but actual SMTP tests and sending are intentionally disabled. Collection, AI enrichment, external connectors, background retries, and production observability are not implemented. `/api/status` reports these flags explicitly. Do not treat this as a production sending system until those capabilities have been separately reviewed and implemented.

## Tests

The regression tests require a reachable PostgreSQL `DATABASE_URL` and configured test secrets. A Docker-based PostgreSQL integration test is recommended in CI; this repository does not claim that test has run unless its output is available.
