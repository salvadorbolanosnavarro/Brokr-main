#!/usr/bin/env bash
# Corre todas las migraciones de paridad (dos veces, para probar que son
# idempotentes) sobre un Postgres local con el esqueleto tipo Supabase.
# Uso: PGPORT=54329 bash scripts/e2e/probar_migraciones.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
P="psql -h ${PGHOST:-/tmp} -p ${PGPORT:-54329} -U postgres -v ON_ERROR_STOP=1 -q"
$P -c "drop database if exists bk_mig" -c "create database bk_mig" >/dev/null
$P -d bk_mig -f tests/sql/supabase_stub.sql >/dev/null
for vuelta in 1 2; do
  for f in migracion-aislamiento-organizacion.sql migracion-fase*.sql; do
    $P -d bk_mig -f "$f" >/dev/null 2>/tmp/bk_mig_err || { echo "FALLÓ $f (vuelta $vuelta)"; cat /tmp/bk_mig_err; exit 1; }
  done
done
echo "Migraciones OK (2 vueltas)"
