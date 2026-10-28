-- ══════════════════════════════════════════════════════════════════════════
-- Bitácora: un solo registro por cambio de etapa
-- ══════════════════════════════════════════════════════════════════════════
-- En producción existe un trigger que no estaba en el repo:
--   trg_contacto_estatus → bk_contacto_cambio_estatus()
-- Hacía dos cosas cada vez que cambiaba la etapa de un contacto:
--   a) llenar contactos.fecha_cambio_estatus (lo usa Estadísticas)   → SE QUEDA
--   b) escribir "Estatus cambiado de "x" a "y"" en la bitácora        → SE QUITA
-- La app ya escribe su propio "Etapa: X → Y" con la persona que hizo el
-- cambio, así que cada cambio quedaba dos veces, y la línea del trigger se
-- le atribuía al DUEÑO del contacto en vez de a quien lo movió.
--
-- Qué hace este script:
--   1) Reemplaza la función: solo actualiza fecha_cambio_estatus.
--   2) Borra las líneas del trigger que ya tienen su gemela de la app
--      (mismo contacto, a menos de 1 minuto). Las que NO tienen gemela se
--      quedan: son cambios hechos por otro camino (lote, borrar una etapa) y
--      son el único registro que hay de ellos.
-- Todo en una transacción. Para deshacer el paso 1:
-- 20261013-bitacora-sin-cambios-de-etapa-duplicados-REVERSA.sql
-- (el paso 2 no se puede deshacer: son líneas repetidas).
-- ══════════════════════════════════════════════════════════════════════════

begin;

create or replace function public.bk_contacto_cambio_estatus()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $function$
begin
  if new.estatus is distinct from old.estatus then
    new.fecha_cambio_estatus := now();
  end if;
  return new;
end;
$function$;

-- Cuántas se van a borrar (aparece en el resultado).
select count(*) as lineas_repetidas_a_borrar
  from public.actividades t
 where t.tipo = 'cambio_estatus'
   and t.texto like 'Estatus cambiado de %'
   and exists (
     select 1 from public.actividades a
      where a.tipo = 'cambio_estatus'
        and a.contacto_id::text = t.contacto_id::text
        and a.id <> t.id
        and a.texto like 'Etapa:%'
        and abs(extract(epoch from (a.created_at - t.created_at))) < 60);

delete from public.actividades t
 where t.tipo = 'cambio_estatus'
   and t.texto like 'Estatus cambiado de %'
   and exists (
     select 1 from public.actividades a
      where a.tipo = 'cambio_estatus'
        and a.contacto_id::text = t.contacto_id::text
        and a.id <> t.id
        and a.texto like 'Etapa:%'
        and abs(extract(epoch from (a.created_at - t.created_at))) < 60);

commit;
