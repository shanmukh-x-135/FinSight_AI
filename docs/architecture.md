# Architecture

The authoritative architecture, data model, and technology decisions live in the
**FinSight AI — Engineering Design Document v2.1**. This file is a lightweight
pointer plus notes on what exists *right now*; it intentionally does not
duplicate the design document.

## Source of truth

- **Engineering Design Document v2.1** — system, AI, data, and UI architecture.
- **Implementation Roadmap v1.0** — the day-to-day, phase-by-phase build plan.

## Style

Modular monolith: a single FastAPI application organized into independent,
feature-owned modules communicating through shared services rather than network
calls (design doc §4.1). Five principles: modularity by feature, event-driven
processing, deterministic analytics before AI reasoning, RAG, and explainability
by default.

## High-level topology

```
User → Next.js (frontend) → REST API → FastAPI (backend)
                                          │
              ┌───────────────┬───────────┼───────────────┐
          PostgreSQL        Redis        FAISS      Background Scheduler
                                                          │
                                                     LLM APIs (Gemini)
```

The frontend talks **only** to the backend; nothing calls the database or vector
store directly.

## Backend modules (`backend/app/`)

| Module          | Responsibility                                                        | First built |
|-----------------|----------------------------------------------------------------------|-------------|
| `shared`        | DB engine/session, exceptions, middleware, security, utils           | Phase 0     |
| `auth`          | Registration, login, JWT, preferences, risk profile                  | Phase 1     |
| `market`        | Market data ingestion, technical indicators, sectors, fundamentals   | Phase 2     |
| `portfolio`     | Portfolio/watchlist CRUD, diversification, exposure, risk             | Phase 3     |
| `history`       | Feature engineering, embeddings, FAISS similarity, statistics        | Phase 4     |
| `intelligence`  | RAG, context/prompt builders, recommendations, report composition    | Phase 6     |
| `reports`       | Report listing/detail, Markdown/PDF export                           | Phase 8     |
| `chat`          | Conversational assistant reusing the RAG pipeline                    | Phase 9     |
| `scheduler`     | Orchestrates post-market-close background jobs                        | Phase 2+    |

## What exists as of Phase 0

- FastAPI app factory (`app/main.py::create_app`) with centralized exception
  handlers and a request-ID middleware.
- Structured JSON logging (`config/logging.py`) correlated by request ID.
- Async SQLAlchemy engine + session dependency (`app/shared/database.py`).
- Alembic configured with an empty baseline migration (`0001_baseline`).
- Health probes: `GET /health`, `GET /health/db`.
- Next.js placeholder landing page that reports backend connectivity.
- Docker Compose bringing up Postgres + backend + frontend.

Every feature-module folder exists (with `__init__.py`) but is otherwise empty —
each later phase fills in its own module using the standard internal layout
described in `CONTRIBUTING.md`.

## Configuration

- `config/settings.py` — Pydantic `BaseSettings`, validated once at startup.
- `config/logging.py` — JSON logging + request-ID context.
- `config/constants.py`, `config/prompts.py`
  (prompts populated from Phase 6).
