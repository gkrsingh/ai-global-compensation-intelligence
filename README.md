# AI Global Compensation Intelligence

Production-oriented application for understanding, calculating, comparing, and
analyzing compensation across countries, roles, experience levels, and employment
types.

## Status

Phases 1–10 complete.

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

- **Phase 5 — auth.** Argon2id password hashing, JWT access tokens with
  opaque, revocable refresh tokens, and saved calculation history.
- **Phase 6 — real exchange rates.** A provider interface with a
  Frankfurter adapter pinned to ECB reference rates, and a scheduled,
  idempotent ingestion script.
- **Phase 7 — offer comparison.** Normalize several saved calculations into
  one currency and show the gaps between them.
- **Phase 8 — AI negotiation insight.** A provider interface (Gemini and
  Anthropic adapters, switchable by env var), versioned prompt templates,
  and — the part that matters — a post-hoc numeric-consistency checker that
  extracts every number from the model's output and verifies it traces back
  to the grounded data, regenerating or refusing rather than showing
  unverified figures. The AI never computes a number.
- **Phase 9 — production hardening.** Rate limiting on auth and
  cost-sensitive endpoints, security headers, explicit timeouts on every
  external call, a secret-leak sweep, and real request-ID tracing through
  the logs.
- **Phase 10 — market context.** Published US wage distributions (BLS OEWS)
  shown beside a calculation, kept structurally separate from computed
  figures — see [Market data coverage](#market-data-coverage) for exactly
  what is and is not covered, and why.

Nothing is deployed to a real server yet — see [Deployment](#deployment).

## Market data coverage

Market compensation figures are **statistical estimates from a survey**, not
facts like a tax bracket or a published exchange rate. They carry a sample, a
methodology, real uncertainty, and a shelf life. This project keeps that
distinction structurally: market data has no foreign key into the calculation
pipeline, provenance columns are mandatory, and the UI renders a distribution
with its source and caveats rather than a single confident number.

| Country | Status | Source |
| --- | --- | --- |
| United States | Supported | BLS OEWS, national, full wage percentiles |
| Spain | **Not supported** | INE EAES publishes occupation **or** percentiles, never both together |
| India | **Not supported** | No free, occupation-level published wage distribution |

### Why India is not supported

Stated plainly because it is a real limitation, not an oversight, and because
it is the market this project's author most wants covered.

India's Periodic Labour Force Survey (PLFS) is a genuine, high-quality
official source, and it does publish earnings — but only as **average monthly
earnings broken down by employment type and gender** (e.g. regular
wage/salaried employees, 2025), not as a wage distribution by occupation.
There is no free JSON API; `microdata.gov.in` distributes microdata files that
require registration and your own statistical analysis.

Deriving occupation-level percentiles ourselves from that microdata would mean
publishing a statistic **we** computed while presenting it as an official
figure. That is precisely the manufactured precision this project exists to
avoid, so India is marked unsupported instead. The API answers a request for
Indian market context with an explicit `available: false` and a stated reason,
never an empty response.

This would become supportable if MoSPI began publishing occupation-by-earnings
cross-tabulations (NCO-coded) as a citable aggregate, or via ILOSTAT if a
working, verifiable access path for its ISCO-08 earnings-by-occupation
indicator can be established — attempted during Phase 10 research, not
successfully verified.

### Why Spain is not supported

Spain's INE does offer a real, free, keyless JSON API, and it was verified
working. The blocker is the shape of the data: the salary-structure survey
(EAES) publishes **mean gross annual salary by CNO-11 major occupation group**,
or **percentiles by region** — never occupation and percentiles together. The
occupation bucket a software engineer falls into ("Otros técnicos y
profesionales científicos e intelectuales") also lumps together engineers,
lawyers, economists and architects, so a single mean from it would bias
downward for a technology role and could not tell a user whether they are above
or below market. The schema deliberately supports mean-only data so Spain can
be added without a migration if INE ever publishes occupation × percentile
cross-tabs.

### Known limitations of the US data

- **Excludes bonuses and equity.** OEWS wages are straight-time gross pay:
  base, cost-of-living allowances, commissions and *production* bonuses are
  included; overtime, *non-production* bonuses (the typical annual bonus),
  benefits and stock are excluded. For technology roles this is frequently
  20–50% of total compensation, so the UI states it as a prominent warning.
- **Gross, not net.** Compare against your gross figure, never your net.
- **No seniority or specialisation.** OEWS publishes a distribution per
  occupation and nothing about levels; "Software Developers" is one bucket
  covering backend, frontend, mobile and ML alike. Locate yourself in the
  range rather than reading a percentile as a level.
- **National only.** Nothing in the app collects a user's location, so there
  is no honest basis for selecting a metro area. Metro and state data exist in
  OEWS and the schema is ready for them; adding a location field would unlock
  them.
- **Mapping quality varies and is labeled.** Software Engineering → SOC
  15-1252 is a close match; Product Management is a *poor* match because
  SOC-2018 has no product management occupation at all.
- **Annually published, with a real lag.** The May 2025 vintage was released
  2026-05-15. Both dates are stored and shown.
- **Self-employed excluded** from the survey entirely.

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
