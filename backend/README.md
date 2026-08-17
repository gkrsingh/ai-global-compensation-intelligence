# Backend

FastAPI, SQLAlchemy, Alembic, PostgreSQL.

## Prerequisites

- Python 3.12
- PostgreSQL 16, running locally

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # then edit DATABASE_URL once the role/database below exist
```

Create the local role and databases (adjust the password):

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE compintel_app WITH LOGIN PASSWORD 'changeme';
CREATE DATABASE compintel_dev OWNER compintel_app;
CREATE DATABASE compintel_test OWNER compintel_app;
SQL
```

`compintel_test` is used exclusively by the pytest suite (see `.env.test.example`) so tests never touch dev data.

## Commands

```bash
.venv/bin/uvicorn app.main:app --reload   # dev server
.venv/bin/pytest                           # tests
.venv/bin/ruff check .                      # lint
.venv/bin/mypy app tests                     # type-check
.venv/bin/alembic upgrade head                # apply migrations
.venv/bin/pip-audit                            # dependency vulnerability scan
```

## Data ingestion scripts

Both are idempotent (natural-key upsert), safe to re-run, and make real
outbound calls — so they are run deliberately, never from the request path.

```bash
.venv/bin/python -m app.reference_data.seed                  # reference data + occupation mappings
.venv/bin/python -m app.reference_data.fetch_exchange_rates  # real ECB rates via Frankfurter
.venv/bin/python -m app.market_data.ingest                   # real US wage data via BLS OEWS
```

`app.market_data.ingest` fetches only the occupations actually mapped to a
job family (see `app/market_data/seed.py`) rather than all 1,104 SOC
occupations. It needs no API key: the BLS v1 public endpoint is keyless, and
was confirmed sufficient for this volume (25 series per request; one
occupation costs 7). Re-running for the same vintage updates rows in place;
a new vintage inserts new rows and keeps the previous ones as history.

See the root README's "Market data coverage" section for what is and is not
covered, and the real limitations of the US figures.
