# AI Global Compensation Intelligence

Production-oriented application for understanding, calculating, comparing, and
analyzing compensation across countries, roles, experience levels, and employment
types.

## Status

Phase 1A (walking skeleton) in progress: FastAPI backend, React/Vite frontend,
PostgreSQL connectivity, health check, CI. No compensation logic, auth, or AI yet.

## Stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite
- Dev environment: WSL2 Ubuntu 24.04
- CI/CD: GitHub Actions
- Production target: Ubuntu, Nginx, Gunicorn/Uvicorn, systemd, PostgreSQL (native
  packages, no containers)
