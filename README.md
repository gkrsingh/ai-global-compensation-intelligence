# AI Global Compensation Intelligence

Production-oriented application for understanding, calculating, comparing, and
analyzing compensation across countries, roles, experience levels, and employment
types.

## Status

Phases 1–4 complete.

- **Phase 1 — walking skeleton.** FastAPI backend with a liveness/readiness
  health check, React/Vite frontend, PostgreSQL wired locally, CI (lint,
  type-check, test, build, dependency audit) gating every PR, and deployment
  artifacts (systemd unit, Nginx config, CD workflow) written and validated
  locally.
- **Phase 2 — reference data.** Country/currency/exchange-rate/job-family/
  experience-level/employment-type/tax-rule-set/tax-bracket models, an
  idempotent seed mechanism, and real, cited income-tax data for India, the
  US, and Spain, with every simplification explicitly flagged rather than
  left implicit. Read-only endpoints: `GET /api/v1/countries`,
  `GET /api/v1/countries/{code}/tax-rule-sets`.
- **Phase 3 — deterministic calculation engine.** Pure, DB-free currency
  conversion and progressive tax-bracket math (unit-tested against
  hand-worked boundary cases), an orchestration layer that runs them against
  real seeded data, and `POST /api/v1/calculations`. Hand-verified against
  real salary figures in all three seeded countries — e.g. a $150,000 US
  single-filer example checked bracket-by-bracket by hand.
- **Phase 4 — usable frontend.** A real page where someone can enter a
  compensation offer (one or more components — base, bonus, equity, benefit,
  allowance — each with its own amount and currency), pick a country and,
  where more than one applies, a tax regime, submit it, and see the
  computed gross, total compensation, full tax breakdown, and net rendered
  clearly. TypeScript types are generated from the backend's own OpenAPI
  schema rather than hand-duplicated, so frontend and backend contracts
  can't silently drift.

No auth, saved history, offer comparison, or AI yet, and nothing is
deployed to a real server yet — see [Deployment](#deployment).

## Repository structure

```
backend/    FastAPI app, SQLAlchemy/Alembic, pytest — see backend/README.md
frontend/   React/TypeScript/Vite, Vitest — see frontend/README.md
deploy/     systemd unit and Nginx config for the production target
.github/    CI (ci.yml) and CD (deploy.yml) GitHub Actions workflows
```

## Getting started

Prerequisites: WSL2 Ubuntu 24.04, Python 3.12, Node 20 (via nvm), PostgreSQL 16
running locally.

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for setup and commands. Once both
are running (backend on its dev port, frontend on `5173`), the page shows
live backend/database status and the compensation calculator.

## Deployment

`deploy/systemd/comp-intel-backend.service` and `deploy/nginx/comp-intel.conf`
target the real production layout (`/opt/comp-intel/...`, a dedicated
non-root `compintel` service account) and have been validated end-to-end
locally under WSL2's systemd — including a genuine kill-and-restart test and
a real, since-fixed bug where the frontend's built bundle called the backend
directly instead of going through Nginx. Neither has been applied to a real
server, since none has been provisioned yet.

`deploy/systemd/comp-intel-fetch-exchange-rates.service` (oneshot) and its
paired `.timer` (weekdays, 17:30 UTC, `Persistent=true` so a run missed
during downtime catches up at next boot) schedule the real exchange-rate
ingestion added in Phase 6 (see `backend/app/reference_data/
fetch_exchange_rates.py`). Both unit files pass `systemd-analyze verify`
with the same warnings as the already-validated backend unit (harmless
Windows-mount permission bits, not content issues), and the exact command
in `ExecStart` has been run for real against the live provider and a real
database, confirmed by querying `exchange_rates` rows before and after.
Loading the units into a live systemd instance (`systemctl start/enable`)
needs root and hasn't been done, for the same reason as the other two
artifacts — no server is provisioned yet.

`.github/workflows/deploy.yml` is written and reviewed but stays inert
(`workflow_dispatch` only) until a server exists and its required secrets are
configured — see the comments at the top of that file for the exact
prerequisites.

## Stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite
- Dev environment: WSL2 Ubuntu 24.04
- CI/CD: GitHub Actions
- Production target: Ubuntu, Nginx, Gunicorn/Uvicorn, systemd, PostgreSQL (native
  packages, no containers)
