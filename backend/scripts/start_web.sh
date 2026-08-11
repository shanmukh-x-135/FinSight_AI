#!/bin/sh
set -eu

# Render Free does not provide pre-deploy commands. PostgreSQL transactional DDL
# and a single web instance make an idempotent startup migration appropriate for
# this zero-cost topology.
python -m alembic upgrade head

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
