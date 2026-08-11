# Infrastructure

The production infrastructure contract is intentionally rooted where each
provider discovers it:

- [`../render.yaml`](../render.yaml) — Render Free API-only Blueprint.
- [`../frontend/vercel.json`](../frontend/vercel.json) — Vercel frontend build
  configuration.
- [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) — required CI
  gates before Render auto-deploys.
- [`../.github/workflows/eod.yml`](../.github/workflows/eod.yml) — timezone-aware
  EOD attempts against externally managed Neon PostgreSQL.

Operator setup, secrets, smoke checks, and rollback guidance live in
[`../docs/deployment.md`](../docs/deployment.md).
