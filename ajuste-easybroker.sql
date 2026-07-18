-- =============================================================================
-- Broquer para empresas — ajuste del inventario de EasyBroker
-- Copiar TODO, pegar en Supabase > SQL Editor, botón Run.
--
-- QUÉ ARREGLA
--   La cuenta de EasyBroker es UNA por empresa. Hasta ahora el inventario
--   estaba amarrado a la persona que importaba, así que cinco agentes de la
--   misma inmobiliaria importando daban cinco copias de cada propiedad.
--   Esto lo amarra a la empresa.
--
--   De paso registra el permiso nuevo "Conectar cuentas" en la base de datos.
--
-- NO ROMPE NADA. Hoy cada quien tiene su propia empresa, así que no hay nada
-- que colisione. Si algo saliera mal, se deshace solo.
-- =============================================================================

begin;

-- ── 1. Seguro: ¿hay duplicados que impidan el cambio? ──
do $$
declare n int;
begin
  select count(*) into n from (
    select org_id, eb_public_id
      from propiedades
     where eb_public_id is not null and org_id is not null
     group by 1, 2
    having count(*) > 1
  ) d;

  if n > 0 then
    raise exception
      'Hay % grupos de propiedades repetidas de EasyBroker. No se tocó nada. Avísale a Claude.', n;
  end if;
end $$;

-- ── 2. Fuera la regla vieja (amarrada a la persona) ──
do $$
declare r record;
begin
  -- Si es una restricción con nombre
  for r in
    select con.conname
      from pg_constraint con
      join pg_class rel on rel.oid = con.conrelid
      join pg_namespace ns on ns.oid = rel.relnamespace
     where ns.nspname = 'public' and rel.relname = 'propiedades'
       and con.contype = 'u'
       and pg_get_constraintdef(con.oid) like '%user_id%'
       and pg_get_constraintdef(con.oid) like '%eb_public_id%'
  loop
    execute format('alter table public.propiedades drop constraint %I', r.conname);
  end loop;

  -- Si es un índice suelto
  for r in
    select i.indexname
      from pg_indexes i
      join pg_class c on c.relname = i.indexname
      join pg_index x on x.indexrelid = c.oid
     where i.schemaname = 'public' and i.tablename = 'propiedades'
       and x.indisunique
       and i.indexdef like '%user_id%'
       and i.indexdef like '%eb_public_id%'
  loop
    execute format('drop index if exists public.%I', r.indexname);
  end loop;
end $$;

-- ── 3. La regla nueva: una propiedad de EasyBroker por EMPRESA ──
-- Sin filtro parcial a propósito: así el backend puede usarla para el upsert.
-- Las propiedades capturadas a mano (sin eb_public_id) no se ven afectadas.
create unique index if not exists propiedades_org_eb_uniq
  on public.propiedades (org_id, eb_public_id);

-- ── 4. Permiso nuevo: "Conectar cuentas" ──
-- Debe coincidir con DEFAULTS_AGENTE de routers/organizaciones.py.
create or replace function org_permiso(p_clave text)
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  m          record;
  v_override jsonb;
begin
  select rol_org, permisos into m
    from organizacion_miembros
   where user_id = auth.uid()
     and activo = true
   limit 1;

  if not found then
    return false;
  end if;

  if m.rol_org in ('owner', 'admin') then
    return true;
  end if;

  v_override := m.permisos -> p_clave;
  if v_override is not null and jsonb_typeof(v_override) = 'boolean' then
    return v_override::boolean;
  end if;

  return case p_clave
    when 'ver_telefonos'           then false
    when 'ver_comisiones'          then false
    when 'gestionar_integraciones' then false
    when 'ver_inventario_completo' then true
    when 'ver_contactos_equipo'    then true
    when 'exportar'                then true
    when 'ver_estadisticas_equipo' then false
    else false
  end;
end;
$$;

commit;

-- ── Resultado ──
select
  (select count(*) from pg_indexes
    where schemaname='public' and tablename='propiedades'
      and indexname='propiedades_org_eb_uniq')                as regla_nueva_lista,
  (select count(*) from propiedades where eb_public_id is not null) as props_de_easybroker,
  (select count(*) from organizaciones)                       as empresas;
