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
