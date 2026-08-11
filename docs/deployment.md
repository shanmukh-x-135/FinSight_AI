# Zero-Cost Production Deployment

FinSight's placement/demo deployment has a strict **zero ongoing hosting cost**
constraint. The versioned topology uses free tiers and accepts their operational
limitations instead of adding paid infrastructure.

## Topology

| Resource | Provider | Repository contract |
|---|---|---|
| Frontend | Vercel Hobby | `frontend/vercel.json`; production branch `QA` |
| API | Render Free Web Service | `render.yaml`; Docker backend, Singapore, branch `QA` |
| Database | Neon Free PostgreSQL | External direct PostgreSQL URL supplied as a secret |
| EOD scheduler | GitHub Actions | `.github/workflows/eod.yml` on the default `QA` branch |
| AI prose | Gemini API | Optional key on the Render API only |
| Similarity cache | Ephemeral FAISS | Reconstructed from PostgreSQL after a cold start/restart |

There is no Render PostgreSQL, Render cron, persistent Render disk, Redis, or
Neon-specific SDK. SQLAlchemy, asyncpg, and Alembic use standard PostgreSQL.

## Neon database

Create one Neon Free project manually in a region reasonably close to Render's
Singapore service. Use the **direct** connection string (hostname without the
`-pooler` suffix) for both Render and GitHub Actions. Direct connections are
required because Alembic migrations and the EOD control plane's session advisory
lock must retain PostgreSQL session semantics.

Neon requires TLS. Its copied connection string commonly ends with:

```text
?sslmode=require&channel_binding=require
```

FinSight safely converts `postgres://`/`postgresql://` to
`postgresql+asyncpg://`, maps libpq's `sslmode=require` to asyncpg's
`ssl=require`, and removes the unsupported libpq-only `channel_binding` option.
Do not edit or commit the credential. Copy the same direct URL into:

- Render's secret `DATABASE_URL` environment variable;
- the GitHub Actions repository secret named `DATABASE_URL`.

Create no Neon SDK integration. Neon remains ordinary PostgreSQL and is the
durable source of truth for users, market data, EOD state, reports, chat, and
historical vectors.

## Render Free API

`render.yaml` defines exactly one resource: `finsight-api`, a free Docker web
service on branch `QA`. During Blueprint creation, supply:

| Variable | Source | Required |
|---|---|---|
| `DATABASE_URL` | Direct Neon URL | Yes |
| `CORS_ORIGINS` | Exact Vercel production HTTPS origin, no trailing slash | Yes |
| `GEMINI_API_KEY` | Google AI Studio secret | Yes for Gemini; blank uses deterministic narration |
| `JWT_SECRET` | Generated once by Render Blueprint | Yes |

`APP_ENV=production`, safe logging/debug defaults, and ephemeral
`DATA_DIR=/tmp/finsight-data` are versioned in the Blueprint. Never expose
`GEMINI_API_KEY`, `DATABASE_URL`, or `JWT_SECRET` through frontend variables.

Render Free does not provide a pre-deploy command, so the existing production
startup wrapper runs `alembic upgrade head` before `exec uvicorn`. Migrations are
transactional and the topology runs one API instance. Avoid deploying during an
EOD attempt, confirm the startup logs reach migration head, then verify
`/health/db`.

The free instance can sleep after inactivity. The first visitor may observe a
cold-start delay while the container starts, migrations are checked, and a
requested FAISS generation is reconstructed from Neon. This is acceptable for a
placement demo; persistent disks or paid always-on compute are intentionally not
used.

## GitHub Actions EOD scheduling

`.github/workflows/eod.yml` calls the existing one-shot runner at these
timezone-aware schedules, Monday through Friday:

| Attempt | IST cron |
|---|---|
| 1 | `45 16 * * 1-5` |
| 2 | `45 18 * * 1-5` |
| 3 | `45 20 * * 1-5` |

Each schedule declares `timezone: Asia/Kolkata`. GitHub runs scheduled workflows
from the latest commit on the repository's default branch, which must remain
`QA`. `workflow_dispatch` also allows an operator to start the same workflow
manually.

The workflow installs only `backend/requirements.txt` and runs:

```bash
python -m app.scheduler.runner
```

It does not reproduce target-date, calendar, provider-readiness, locking,
resume, or idempotency logic. Those remain authoritative in the application.
The EOD pipeline contains only market ingestion, news ingestion, and historical
index rebuilding; it does not generate reports or call Gemini. Therefore GitHub
requires only the `DATABASE_URL` secret—never `GEMINI_API_KEY`, JWT, or frontend
variables.

GitHub Actions schedules are best-effort rather than hard real-time. Runs may be
delayed during platform load. The three post-market attempts, provider readiness
gate, database advisory lock, completed-run short circuit, and resumable
checkpoints make that delay acceptable. For private repositories, monitor the
account's included Actions minutes; a public placement repository does not need
paid scheduling infrastructure.

## Vercel Hobby frontend

1. Import the repository and set the Root Directory to `frontend/`.
2. Set the production branch to `QA`.
3. Set `NEXT_PUBLIC_API_URL` to the final Render HTTPS origin without a trailing
   slash.
4. Deploy with the committed `npm ci` and `npm run build` commands.

Production builds reject missing, local, non-HTTPS, credential-bearing, or
path-bearing API origins. Changing `NEXT_PUBLIC_API_URL` requires a new build.
Vercel Hobby is appropriate only while this remains a personal, non-commercial
placement project.

## First deployment order

1. Ensure CI is green on `QA` and GitHub reports `QA` as the default branch.
2. Create Neon Free, copy its direct TLS connection string, and retain it only
   in provider secret stores.
3. Add repository secret `DATABASE_URL` in GitHub Actions.
4. Create the Render Blueprint, enter the Neon URL and the anticipated Vercel
   origin, and optionally enter the Gemini key.
5. Verify Render startup migrations and `/health/db`.
6. Create Vercel, set `NEXT_PUBLIC_API_URL`, and deploy from `QA`.
7. If the final Vercel origin differs, update Render `CORS_ORIGINS` and redeploy.
8. Run the smoke verifier below.
9. Manually dispatch EOD once after market data is available and inspect its
   Actions log plus the protected EOD status endpoint.

Do not paste secrets into issues, chat, workflow inputs, command-line arguments,
documentation, or screenshots.

## Verification

```bash
python3 scripts/smoke_deployment.py \
  --backend-url https://your-api.onrender.com \
  --frontend-url https://your-app.vercel.app
```

The non-mutating script checks HTTPS, production mode, API liveness, Neon
readiness, exact CORS, and the frontend landing page.

Local rehearsal remains:

```bash
docker compose up --build -d --wait
python3 scripts/smoke_deployment.py \
  --backend-url http://localhost:8000 \
  --frontend-url http://localhost:3000 \
  --allow-non-production
```

## EOD status and recovery

Administrators can inspect, but not start, EOD work through:

```text
GET /api/v1/admin/jobs/eod/status
GET /api/v1/admin/jobs/eod/status?target_trading_date=YYYY-MM-DD
```

For a current-date retry, use **Run workflow** on the EOD Actions workflow. For
a specific date, run the existing runner in an authorized one-off environment:

```bash
python -m app.scheduler.runner --target-trading-date YYYY-MM-DD
```

Never pass the Neon URL as a workflow-dispatch input. A completed date is a
no-op, a partial/failed run resumes, and a recent running heartbeat must be
allowed to finish. Inspect correlated structured logs and the protected status
before retrying.

## Free-tier limitations

- Render Free may cold-start after inactivity and provides no persistent disk.
- GitHub Actions schedules can be delayed and are not a hard real-time SLA.
- Neon Free compute, storage, transfer, and inactivity limits apply; monitor the
  Neon dashboard and keep a manual export appropriate to the demo's data value.
- Free provider limits and policies can change; review them before the public
  resume demo.
- Gemini free quota/rate limits apply. Deterministic grounded narration remains
  the safe fallback if quota or the provider is unavailable.
- This architecture is deliberately for a low-traffic college placement/demo
  project, not a commercial service.

These limitations do not justify adding paid Render PostgreSQL, Render cron,
persistent disks, Redis, or enterprise infrastructure.

## Staging/public-demo acceptance

- CI is green on the exact `QA` commit and both production images build.
- Render startup reaches Alembic head; `/health` and `/health/db` pass after a
  cold start.
- The deployment smoke script passes with exact HTTPS origins.
- Auth isolation, portfolio/watchlist, dashboard, reports/exports, and chat work
  using Neon-persisted data.
- EOD completes all checkpoints, later same-date attempts no-op, and a controlled
  partial run resumes without duplicates.
- Replacing/restarting Render clears local FAISS files and a history request
  reconstructs them from Neon.
- One Gemini response and one forced deterministic fallback expose the correct
  provenance without leaking prompts or credentials.
- GitHub contains only `DATABASE_URL`; Gemini remains only on Render.
- Provider logs contain request/correlation IDs but no tokens, database URLs,
  prompts, or provider payloads.

Cloud-account creation, secrets, default-branch configuration, usage monitoring,
and pressing deploy/run controls remain manual operator actions. Repository
configuration does not claim those external steps have occurred.
