# Frontend

React + TypeScript, built with Vite.

## Setup

```bash
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL to match your backend port
```

## Commands

```bash
npm run dev                # start the Vite dev server
npm run build               # type-check (tsc -b) and build for production
npm run lint                 # eslint .
npm run format                # prettier --check .
npm run format:write           # prettier --write .
npm run test                    # vitest run
npm run generate:api-types       # regenerate src/api/schema.d.ts from a locally
                                   # running backend's OpenAPI schema (the
                                   # backend must be up on the port hardcoded
                                   # in the script)
```
