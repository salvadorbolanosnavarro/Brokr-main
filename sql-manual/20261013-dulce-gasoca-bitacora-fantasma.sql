-- ══════════════════════════════════════════════════════════════════════════
-- DULCE GASOCA (c_1790363193126): borrar 4 cambios de etapa que nunca pasaron
-- ══════════════════════════════════════════════════════════════════════════
-- Antes del arreglo del 29-sep-2026 (commit 5e94941), cambiar la etapa de un
-- cliente que había creado otra cuenta no se guardaba, pero la app igual lo
-- anotaba en la bitácora. Estos 4 registros de Oscar Coria son de esos:
--   25-sep 20:47 UTC  Nuevo → Contactado
--   27-sep 00:15 UTC  Nuevo → Activo   (×2)
--   29-sep 00:30 UTC  Nuevo → Activo
-- El cambio real es el del 29-sep 23:04 UTC y ese NO se toca.
-- Si el conteo no es 4, no se borra nada.
-- ══════════════════════════════════════════════════════════════════════════

begin;

do $$
declare n int;
begin
  select count(*) into n
    from public.actividades
   where contacto_id::text = 'c_1790363193126'
     and tipo = 'cambio_estatus'
     and user_id = '452ab3a8-854d-489f-bbe1-656daf1e82ab'
     and created_at < '2026-09-29 23:00:00+00';
  if n <> 4 then
    raise exception 'Esperaba 4 registros fantasma y hay %; no se borró nada.', n;
  end if;

  delete from public.actividades
   where contacto_id::text = 'c_1790363193126'
     and tipo = 'cambio_estatus'
     and user_id = '452ab3a8-854d-489f-bbe1-656daf1e82ab'
     and created_at < '2026-09-29 23:00:00+00';
end $$;

commit;

-- Lo que queda en su bitácora de cambios de etapa:
select created_at, user_id, texto
  from public.actividades
 where contacto_id::text = 'c_1790363193126' and tipo = 'cambio_estatus'
 order by created_at;
