# Contributing to FinSight AI

Solo project, but disciplined conventions keep it reviewable and scalable. These
standards come from the Engineering Design Document v2.1 (§8.1) and the
Implementation Roadmap.

## Golden rules

- **Analytics before AI.** All indicators, portfolio metrics, sentiment, and
  similarity scores are computed deterministically. The LLM only *explains*
  precomputed results — it never computes indicators, rankings, probabilities,
  or similarity.
- **No duplicated logic.** Small, reusable functions; one source of truth (e.g.
  feature normalization, aggregated sentiment, the context builder).
- **Evidence over speculation.** Every AI recommendation carries evidence, a
  confidence level, historical context, and risks.

## Backend standards

- Python **3.12+**, full type hints everywhere.
- **Pydantic** for validation, **SQLAlchemy** ORM, **Alembic** for migrations
  (never apply schema changes directly to the database).
- Feature-based modules. Each module under `backend/app/<feature>/` follows the
  same internal layout:
  `controller.py · service.py · repository.py · schemas.py · models.py ·
  routes.py · constants.py · exceptions.py · tests.py`
  (not every file is needed in every phase — add them as the feature grows).
- All API routes are versioned under `/api/v1/`.
- Every API response uses the standard envelope
  (`success · message · data · timestamp · requestId`) from Phase 1 onward.
- Unit-test business logic; security-critical modules target 80%+ coverage.

## Frontend standards

- **TypeScript only**, functional components, Server Components where appropriate.
- **Tailwind CSS** + **Shadcn UI**; Lucide icons; card-based layout.
- Semantic colors: green (positive), red (negative), blue (information),
  yellow (warning).
- Build reusable components first, screens second — screens are composed from
  the shared component library and the three page templates (Analytics / Report /
  Management).

## Module naming (deliberate)

- `intelligence/`, **not** `ai/` — it owns RAG, prompts, recommendations, context
  building, report composition, and explainability.
- `history/`, **not** `similarity/` — clearer to a new reader.

## Git workflow

- Work one **phase** at a time; do not start a phase until the previous phase's
  checklist is fully green and the app runs end-to-end.
- Branch per milestone: `feature/*` → `develop` → `main`.
- Conventional commits, scoped by module:
  `feat(auth): ...`, `fix(market): ...`, `test(portfolio): ...`,
  `docs(history): ...`, `chore(ci): ...`.
- Tag each completed phase (e.g. `v0.1.0-skeleton`).

## Secrets

Never commit secrets. `.env*` files are git-ignored; only `*.env.example`
templates are committed. Secrets are supplied via environment variables.

## Definition of Done (per phase)

Feature implemented · unit tests pass · API documented (OpenAPI) · frontend
integrated · code reviewed · no critical bugs · documentation updated.
