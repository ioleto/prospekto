# Prospekto — CDC audit status (2026-10-14)

## Scope and evidence

This audit documents the state of `main` at commit `e691d127d4220e30434797c9c982cdb4d0215291` on 2026-10-14. It is a documentation-only audit against the Prospekto CDC sections 1–14 and acceptance criteria 1–15 supplied in the parent conversation. Evidence was taken from the repository code, SQL migrations, tests, Docker/CI files and existing docs; no production secrets or data were accessed.

**Status vocabulary:** Implemented = visible in code and covered by a relevant test or direct code evidence; Partial = some building blocks exist but the end-to-end requirement is incomplete or unproven; Missing = no sufficient implementation evidence; External validation = cannot be established from repository evidence.

## Current conclusion

The repository contains a working-looking FastAPI/PostgreSQL internal CRM slice: session login, CSRF checks on mutating forms, prospects, suppression/opposition, CSV export, campaigns, SMTP profile encryption, migrations, Docker and CI. The audit does **not** establish a production-ready or complete CDC implementation. In particular, discovery connector gating/provenance, real discovery workflow, duplicate policy, sending confirmation/idempotency, rate limits, audit trail, backup/restore operations, and Portainer/SWAG production validation remain incomplete or unverified. No claim of legal compliance is made.

## Verified test evidence

- Repository CI defines PostgreSQL 16 service, migrations, `python -m pytest -q`, and Docker build.
- Tests visible in `main`: `tests/test_app.py`, `tests/test_campaign_postgres_roundtrip.py`, `tests/test_campaign_regressions.py`.
- Local execution was not reproducible in this worker because the mounted inputs were source snapshots without a checked-out package/database service; therefore no local pass count is claimed. CI configuration is **defined, not independently executed here**. The tests themselves cover health/status, login/CSRF, prospect suppression, campaign creation and SMTP ciphertext round-trip; they do not prove complete UI workflows or production behavior.

## Security and operations caveats

- Argon2 password hashing, Fernet SMTP password encryption and CSRF helpers are present by code evidence.
- Session/rate-limit hardening, secure cookie attributes, login throttling persistence and authorization boundaries require explicit verification; `LOGIN_ATTEMPTS` is an in-process structure and is not evidence of a complete rate-limit policy.
- No evidence was found for a real connector integration, Mammouth availability handling, discovery provenance enforcement, audit log, idempotent send/outbox, manual confirmation gate, suppression enforcement at send time, or backup retention/restore drill.
- Docker/compose and SWAG/Portainer docs are configuration/documentation only; no deployment or `prospekto.ioleto.fr` validation was performed.

## Prioritized next development tasks

1. Define and test the acceptance contract for discovery connectors: explicit opt-in/gating, provenance, no fabricated results, Mammouth-unavailable behavior, deduplication and import auditability.
2. Implement a safe send state machine: manual confirmation, idempotency key/outbox, suppression re-check, SMTP transport/error handling, and immutable audit events; keep real sending disabled by default.
3. Add authorization/session/rate-limit tests and production-safe cookie/security configuration; test duplicate and concurrent requests.
4. Complete campaign/prospect UI workflows and evidence-based end-to-end tests (not model/field-only tests).
5. Document and rehearse backup/export/restore/retention, then validate Portainer + SWAG routing/TLS/health checks in an approved environment.

Estimates are intentionally omitted: no planning baseline or execution sizing was supplied. Any future phase estimate must be labelled tentative. Resume by reading `docs/cdc-audit-2026-10-14.md`, checking the audited commit, then updating statuses only with new repository or approved external evidence.

## Detailed checklist

See [`docs/cdc-audit-2026-10-14.md`](docs/cdc-audit-2026-10-14.md).