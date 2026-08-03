# FinSight AI

AI-powered financial intelligence platform that turns raw end-of-day market
data into personalized, explainable investment intelligence. It combines
deterministic financial analytics, historical market similarity retrieval,
technical indicators, news sentiment, and Retrieval-Augmented Generation (RAG)
to produce market and portfolio reports. It is a research assistant, not a
price-prediction engine — every insight carries evidence, confidence, and risk.

> **Status:** Phase 0 — Project Setup (skeleton). Both servers boot, the backend
> talks to PostgreSQL, and health checks pass. Feature work begins in Phase 1.

## Architecture

A **modular monolith**: a single FastAPI backend organized into feature modules
(`auth`, `market`, `portfolio`, `history`, `intelligence`, `reports`, `chat`,
`scheduler`, `shared`) and a Next.js frontend. See
[`docs/architecture.md`](docs/architecture.md); the authoritative source is the
Engineering Design Document v2.1.

## Repository layout

```
finsight-ai/
├── backend/            FastAPI app (app/), config (config/), Alembic, tests
├── frontend/           Next.js + TypeScript + Tailwind + Shadcn UI
├── docker/             Dockerfiles for backend and frontend
├── docs/               Design/architecture notes (per-phase docs added later)
├── scripts/            Dev/ops helper scripts
├── tests/              Cross-cutting integration/e2e/fixtures (per design §6.10)
├── infrastructure/     IaC notes/scripts
└── docker-compose.yml  Local full-stack dev
```

## Prerequisites

- **Docker + Docker Compose** (recommended path), **or** for running natively:
  - Python **3.12+**
  - Node **20+**
  - PostgreSQL **16**

## Quick start (Docker — recommended)

```bash
cp backend/.env.example backend/.env      # adjust if needed
docker compose up --build
```

This starts three services:

| Service  | URL                     | Notes                          |
|----------|-------------------------|--------------------------------|
| Frontend | http://localhost:3000   | Landing page shows API status  |
| Backend  | http://localhost:8000   | `/docs` for OpenAPI            |
| Postgres | localhost:5432          | user/pass/db all `finsight`    |

The backend applies Alembic migrations on startup, then serves. Open
http://localhost:3000 — it should read **"Backend connected."**

## Running natively (without Docker)

**Backend**

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # set DATABASE_URL to your Postgres
alembic upgrade head                       # apply migrations
uvicorn app.main:app --reload              # http://localhost:8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env.local                 # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                # http://localhost:3000
```

## Health checks

```bash
curl http://localhost:8000/health          # {"status":"ok",...}
curl http://localhost:8000/health/db       # {"status":"ok","database":"reachable"}
```

## Running tests

```bash
cd backend
pytest                                     # smoke tests use an in-memory SQLite DB
```

## Environment variables

All backend variables are documented in [`backend/.env.example`](backend/.env.example)
and validated at startup by `config/settings.py` (the two are kept in sync).
`DATABASE_URL` is required; secrets are never committed.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for coding standards, module layout, and
branch/commit conventions.
