#!/usr/bin/env bash
# Prueba puesta-al-dia-produccion.sql sobre una "producción simulada" (tablas
# de hoy con sus formas viejas): fases 1-2 ya corridas, luego la puesta al día
# dos veces, luego fase 6 y fase 7 dos veces. Comprueba que no se borre nada.
# Uso: PGPORT=54329 bash scripts/e2e/probar_puesta_al_dia.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
P="psql -h ${PGHOST:-/tmp} -p ${PGPORT:-54329} -U postgres -v ON_ERROR_STOP=1 -q"
$P -c "drop database if exists bk_prod" -c "create database bk_prod" >/dev/null
$P -d bk_prod -f tests/sql/produccion_simulada.sql >/dev/null

conteo() {
  $P -d bk_prod -Atc "select (select count(*) from propiedades)||','||(select count(*) from contactos)||','||
    (select count(*) from wa2_mensajes)||','||(select count(*) from wa2_conversaciones)||','||(select count(*) from pipeline_etapas where user_id is not null)||','||
    (select count(*) from actividades)||','||(select count(*) from tareas)"
}
antes=$(conteo)

# Lo que ya corrió en producción: aislamiento + fases 1 y 2 (necesitan las
# columnas de asignación, que en producción ya estaban).
$P -d bk_prod -c "alter table propiedades add column if not exists asignado_a uuid; alter table contactos add column if not exists asignado_a uuid;
  alter table tareas add column if not exists org_id uuid; alter table tareas add column if not exists asignado_a uuid;
  alter table propiedades add column if not exists amenidades text[];" >/dev/null
for f in migracion-aislamiento-organizacion.sql migracion-fase1-inventario.sql migracion-fase2-multimedia.sql; do
  $P -d bk_prod -f "$f" >/dev/null 2>/tmp/bk_prod_err || { echo "FALLÓ $f"; cat /tmp/bk_prod_err; exit 1; }
done

for vuelta in 1 2; do
  $P -d bk_prod -f puesta-al-dia-produccion.sql >/tmp/bk_prod_out 2>/tmp/bk_prod_err || { echo "FALLÓ puesta al día (vuelta $vuelta)"; cat /tmp/bk_prod_err; exit 1; }
done
grep -q "| f" /tmp/bk_prod_out && { echo "FALTAN TABLAS:"; grep "| f" /tmp/bk_prod_out; exit 1; }

for vuelta in 1 2; do
  for f in migracion-fase6-cierres.sql migracion-fase7-sitios.sql; do
    [ -f "$f" ] || continue
    $P -d bk_prod -f "$f" >/dev/null 2>/tmp/bk_prod_err || { echo "FALLÓ $f (vuelta $vuelta)"; cat /tmp/bk_prod_err; exit 1; }
  done
done

despues=$(conteo)
[ "$antes" = "$despues" ] || { echo "CAMBIARON LOS CONTEOS: antes $antes, después $despues"; exit 1; }
echo "Puesta al día OK (2 vueltas; luego fase 6 y 7 si están en esta rama). Conteos intactos: $despues"
