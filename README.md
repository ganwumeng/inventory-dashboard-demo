# Inventory dashboard service

A small stdlib-only Python web service that exposes warehouse inventory data
to the operations dashboard. It serves bearer-token-protected JSON endpoints
over HTTP (see `service/`) and ships a tiny CLI entry point (`run.py`).

## Layout

- `service/` — the service package: `app.py` (HTTP routes), `auth.py`
  (bearer-token helpers), `store.py` (frozen demo inventory data).
- `docs/` — design documents. Specifications for new endpoints are drafted by
  the project's design workflow and land here before implementation.
- `tests/` — the public test suite: `python3 -m unittest discover -s tests`.
- `run.py` — `python3 run.py [--port N]`; the service token is read from the
  `DASHBOARD_TOKEN` environment variable.

## Implemented features

- Daily inventory report endpoint (`GET /api/reports/daily`) with optional authenticated callback synchronization; see `docs/daily-inventory-report.md`.
