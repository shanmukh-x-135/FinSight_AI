#!/usr/bin/env bash
# Start/stop an isolated local PostgreSQL 16 cluster for native (non-Docker) dev.
# Data lives in ./.localdb (git-ignored). Socket goes in a short /tmp path to
# avoid Postgres's 103-byte Unix-socket path limit.
#
# Usage:
#   scripts/run_local_postgres.sh start
#   scripts/run_local_postgres.sh stop
#   scripts/run_local_postgres.sh status
#
# Prefer `docker compose up` when Docker is available; this is a fallback.
set -euo pipefail

PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@16/bin}"
PGDATA="${PGDATA:-$(pwd)/.localdb}"
SOCKDIR="${SOCKDIR:-/tmp/finsight-pg}"
PORT="${PORT:-5432}"

case "${1:-}" in
  start)
    mkdir -p "$SOCKDIR"
    if [ ! -d "$PGDATA/base" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U postgres --auth=trust >/dev/null
    fi
    "$PGBIN/pg_ctl" -D "$PGDATA" \
      -o "-p $PORT -k $SOCKDIR -c listen_addresses=127.0.0.1" \
      -l "$PGDATA/server.log" start
    sleep 2
    "$PGBIN/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -v ON_ERROR_STOP=0 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='finsight') THEN
    CREATE ROLE finsight WITH LOGIN PASSWORD 'finsight';
  END IF;
END \$\$;
SELECT 'CREATE DATABASE finsight OWNER finsight'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='finsight')\gexec
SQL
    echo "Postgres running on 127.0.0.1:$PORT (db/user/pass = finsight)"
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" stop
    ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status
    ;;
  *)
    echo "usage: $0 {start|stop|status}" >&2
    exit 1
    ;;
esac
