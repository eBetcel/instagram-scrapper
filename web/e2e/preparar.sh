#!/usr/bin/env bash
# Recria o banco agenda_e2e, aplica as migrações e semeia o evento e os convites do smoke.
# Precisa do Postgres (5432) e do Mailpit (1025/8025) do docker-compose da raiz rodando.
set -euo pipefail
cd "$(dirname "$0")"
export DATABASE_URL="postgresql+psycopg://agenda:agenda@localhost:5432/agenda_e2e"
BACKEND="$(cd ../../backend && pwd)"
uv run --project "$BACKEND" python - <<'PY'
import psycopg
with psycopg.connect("postgresql://agenda:agenda@localhost:5432/agenda", autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS agenda_e2e WITH (FORCE)")
    c.execute("CREATE DATABASE agenda_e2e")
PY
(cd "$BACKEND" && uv run alembic upgrade head > /dev/null)
uv run --project "$BACKEND" python semear.py
