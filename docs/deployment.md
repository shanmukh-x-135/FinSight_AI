# Production Deployment (P10.8)

P10.8 turns the deployment scaffolding into a reproducible, fail-closed
production bundle. The target topology is Vercel for the Next.js frontend and a
Render Blueprint for the FastAPI API, managed PostgreSQL, and the one-shot EOD
cron job.

## Versioned topology

| Resource | Configuration | Runtime contract |
|---|---|---|
| Frontend | `frontend/vercel.json` | Vercel project with repository root directory set to `frontend/`. |
| API | `render.yaml` → `finsight-api` | Non-root backend image, database readiness probe, migration pre-deploy, deploy only after CI passes. |
| EOD | `render.yaml` → `finsight-eod` | Same immutable backend build; runs `python -m app.scheduler.runner` at 11:15, 13:15, and 15:15 UTC (16:45, 18:45, and 20:45 IST) on weekdays. The trading-calendar/provider preflight safely skips holidays and incomplete sessions. |
| Database | `render.yaml` → `finsight-db` | Render PostgreSQL 16 with public inbound access blocked; its private connection is shared by API and EOD runner. |

FAISS files remain a disposable cache. Render services use ephemeral
`/tmp/finsight-data`; PostgreSQL-owned vectors and index state reconstruct the
cache after a replacement or restart.

The three cron times are deliberately versioned in `render.yaml`, where Render
defines schedules in UTC. The first successful attempt completes the logical
trading-date run; later invocations detect that checkpoint and exit without
provider work. If data is late or a step fails, the later invocation reuses the
same locked run and resumes its durable checkpoints. Change those UTC times in
the Blueprint if provider availability changes; no application code assumes
these hours.

## Production safety gates

`APP_ENV=production` now refuses to start when:

- `JWT_SECRET` is the default or shorter than 32 characters;
- `DEBUG` or `DB_ECHO` is enabled;
- `CORS_ORIGINS` is empty, wildcarded, non-HTTPS, or contains a trailing slash;
- `DATABASE_URL` selects a synchronous PostgreSQL driver.

Render supplies a standard `postgresql://` connection string. Settings normalize
that provider form to SQLAlchemy's required `postgresql+asyncpg://` form before
the web process or Alembic creates an engine.

## Create the Render resources

1. Merge the verified deployment commit to the protected `main` branch. The
   Blueprint intentionally pins both services to `main`; do not deploy the dirty
   local working tree or a moving feature branch.
2. Connect this repository as a Render Blueprint and select `render.yaml`.
3. Supply the prompted `CORS_ORIGINS` value for both the API and cron services:
   the exact stable Vercel production origin, for example
   `https://app.example.com` (no trailing slash). Multiple stable origins use a
   comma-separated value.
4. Review the declared paid instance/database plans and region before applying
   the Blueprint. Creating the Blueprint provisions billable resources.
5. Wait for the `alembic upgrade head` pre-deploy command and `/health/db` check
   to pass. Do not run migrations from the web startup command.

Render prompts for `sync: false` values only during initial Blueprint creation.
For an existing Blueprint, set new prompted variables manually on both services.
The shared JWT secret is generated once in the Blueprint environment group.
`GEMINI_API_KEY` and `TRADING_ECONOMICS_API_KEY` remain optional: add them to the
API service in Render only when those providers are enabled. Their absence keeps
the deterministic narrator and explicit `not_configured` calendar state.

## Create the Vercel project

1. Import this monorepo, set the project Root Directory to `frontend/`, and set
   the production branch to `main`.
2. Set `NEXT_PUBLIC_API_URL` to the API's stable HTTPS Render/custom-domain URL,
   without a trailing slash. A Preview deployment can call that API only when
   its stable preview/custom origin is also explicitly listed in backend
   `CORS_ORIGINS`; arbitrary Vercel preview hosts are not wildcarded.
3. Deploy. Vercel runs the committed `npm ci` and `npm run build` commands.
4. If the final frontend origin differs from the value supplied to Render,
   update `CORS_ORIGINS` on both Render services and redeploy the API.

`NEXT_PUBLIC_API_URL` is compiled into browser code at build time. Changing it
requires a new Vercel deployment; a runtime-only change cannot update an existing
bundle.

## Verify before traffic

CI must pass backend Ruff/tests (including PostgreSQL concurrency regressions),
frontend lint/tests/build, and both production image builds. Then run the
non-mutating deployed-stack smoke test:

```bash
python3 scripts/smoke_deployment.py \
  --backend-url https://api.example.com \
  --frontend-url https://app.example.com
```

It verifies HTTPS, production mode, API liveness, database readiness, exact CORS,
and the frontend landing page without creating users or financial data.

For a local container rehearsal:

```bash
docker compose up --build -d --wait
python3 scripts/smoke_deployment.py \
  --backend-url http://localhost:8000 \
  --frontend-url http://localhost:3000 \
  --allow-non-production
```

## Operations and rollback

### EOD status and manual recovery

The API exposes a read-only administrator endpoint:

```text
GET /api/v1/admin/jobs/eod/status
GET /api/v1/admin/jobs/eod/status?target_trading_date=YYYY-MM-DD
```

It returns the logical run, ordered step checkpoints, attempts, bounded error
summaries, counters, timestamps, and `rerun_recommended`. It never starts work.
Use an administrator access token in the normal `Authorization: Bearer ...`
header; do not place tokens in URLs, documentation, shell history, or chat.

For the current market date, use Render's manual **Trigger Run** action on
`finsight-eod`. A completed run is a no-op; failed/partial runs resume; a recent
running heartbeat should be allowed to finish. For a specific recovery date,
run the same image as a one-off job with:

```bash
python -m app.scheduler.runner --target-trading-date YYYY-MM-DD
```

Do not add an HTTP endpoint that performs the full EOD pipeline: it is long
running and belongs in the external worker topology. A non-zero cron exit,
`eod_runner_incomplete`, `eod_runner_failed`, or a failed/partial status after
the final same-day attempt requires operator review. Configure the hosting
provider's job-failure email notification after creating the service; an
external observability platform is not required for this project.

### Recovery checklist

1. Check `/health/db`, then inspect the protected EOD status and correlated
   structured logs (`correlation_id`, `run_id`, and request ID where relevant).
2. If the provider was merely late/unavailable, trigger the same runner again.
   Idempotent writes and durable checkpoints make this safe.
3. If the API image is faulty, roll back to the last known-good provider deploy.
   Do not downgrade the database automatically.
4. Before every schema-changing deploy, confirm the managed database has a
   recent restorable backup. At least once in staging, restore a backup into a
   temporary database, apply `alembic upgrade head`, and verify `/health/db`.
5. If FAISS files disappear or are corrupt, restart the API and verify a history
   request reconstructs the cache from PostgreSQL. Do not treat `/tmp` as a
   backup.

### Staging acceptance (P10.11)

Record the date, commit SHA, URLs, and pass/fail evidence for each item. Staging
may use the same architecture with the optional Gemini key omitted until the
deterministic path is proven.

- CI passes on the exact commit; the fresh-database Alembic upgrade/check gate
  and both production container builds are green.
- Render pre-deploy migrations reach Alembic head and `/health` plus `/health/db`
  pass after a clean restart.
- The deployment smoke script passes HTTPS, production mode, database, exact
  CORS, and frontend checks.
- Register/login/refresh/logout work; a second user cannot read the first user's
  portfolio, reports, or chat history.
- Add a holding and watchlist entry; dashboard, market, portfolio, history, and
  watchlist pages load real persisted data without browser console errors.
- Run an explicit historical backfill/rebuild once, remove the ephemeral FAISS
  cache by replacing/restarting the service, and verify history reconstruction.
- Generate and reopen a report; export both Markdown and PDF and verify evidence,
  Unicode sanitization, and download integrity.
- Ask a grounded chat question, reload history, and verify evidence, confidence,
  risks, sources, and generation provenance.
- Run EOD for a known trading date, confirm all three checkpoints complete, then
  rerun the same date and verify it is a no-op. Exercise a controlled failed step
  in staging and confirm the next attempt resumes rather than duplicates data.
- With a staging Gemini key and conservative quota, verify one successful Gemini
  response and one forced fallback (for example, temporarily invalid key), then
  confirm metadata identifies the actual backend in both cases.
- Restart API and cron containers, repeat core reads, and inspect structured logs
  for request IDs without prompts, tokens, credentials, or provider payloads.
- Complete one temporary-database backup restore drill and record the recovery
  time. Delete the temporary restored database after verification.

Only the first three bullets and core auth/data/report/chat flows block an
initial private staging deployment. EOD retry/resume, restart reconstruction,
Gemini/fallback, and backup restore evidence block the public resume demo.

- Render sends `SIGTERM`; the exec-form server command and 60-second shutdown
  window allow FastAPI lifespan cleanup to finish.
- The backend startup wrapper binds to Render's runtime `PORT` and uses `exec`,
  so proxy routing and Unix signals reach Uvicorn correctly.
- The web service never runs EOD work. Only the cron service invokes the durable,
  locked, resumable pipeline.
- Roll back application images through the provider. Do not automatically run
  `alembic downgrade`; restore/repair the database only from an explicitly tested
  backup procedure.
- Rotating `JWT_SECRET` immediately invalidates every issued access and refresh
  token. Schedule that user-visible effect.
- Provider keys remain provider-managed secrets and must never be passed as
  Docker build arguments or committed files.

Cloud-account creation, billing approval, DNS ownership, provider credentials,
and pressing the deploy controls remain external operator actions. The repository
contains no credentials and does not claim that those external actions occurred.
