# Infrastructure

The production infrastructure contract is intentionally rooted where each
provider discovers it:

- [`../render.yaml`](../render.yaml) — Render API, EOD cron, and PostgreSQL
  Blueprint.
- [`../frontend/vercel.json`](../frontend/vercel.json) — Vercel frontend build
  configuration.
- [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) — required CI
  gates before Render auto-deploys.

Operator setup, secrets, smoke checks, and rollback guidance live in
[`../docs/deployment.md`](../docs/deployment.md).
