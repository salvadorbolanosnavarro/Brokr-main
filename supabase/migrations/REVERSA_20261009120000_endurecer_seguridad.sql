-- ══════════════════════════════════════════════════════════════════════════
-- REVERSA de 20261009120000_endurecer_seguridad.sql
-- ══════════════════════════════════════════════════════════════════════════
-- Deja todo exactamente como estaba antes de la migración, usando la foto
-- que la migración guardó en el esquema respaldo_seguridad_20261009:
--   · permisos (GRANTs) de las 7 tablas/vistas,
--   · RLS encendido/apagado y opciones de las vistas (security_invoker),
--   · la política original de UPDATE del bucket avatares,
--   · el search_path original de las funciones.
-- Al final borra la foto. Todo en una sola transacción.
--
-- OJO: este archivo NO empieza con número a propósito, para que la CLI de
-- Supabase nunca lo aplique sola. Solo se corre a mano en el SQL Editor.
-- ══════════════════════════════════════════════════════════════════════════

begin;

do $$
begin
  if to_regclass('respaldo_seguridad_20261009.relaciones') is null then
    raise exception 'No existe la foto respaldo_seguridad_20261009: la migración no se aplicó o ya se revirtió.';
  end if;
end $$;

-- ── Permisos, RLS y opciones de vistas ───────────────────────────────────
do $$
declare
  r   record;
  a   record;
  rol text;
begin
  for r in select * from respaldo_seguridad_20261009.relaciones loop
    continue when to_regclass(r.relacion) is null;

    -- Quitar todos los permisos actuales que no son del dueño…
    for a in
      select distinct x.grantee
        from pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) x
       where c.oid = r.relacion::regclass and x.grantee <> c.relowner
    loop
      rol := case when a.grantee = 0 then 'public' else quote_ident(a.grantee::regrole::text) end;
      execute format('revoke all on %s from %s', r.relacion, rol);
    end loop;

    -- …y volver a dar exactamente los que había.
    for a in
      select x.grantee, x.privilege_type, x.is_grantable
        from pg_class c, aclexplode(coalesce(r.relacl, acldefault('r', c.relowner))) x
       where c.oid = r.relacion::regclass and x.grantee <> c.relowner
    loop
      rol := case when a.grantee = 0 then 'public' else quote_ident(a.grantee::regrole::text) end;
      execute format('grant %s on %s to %s%s', a.privilege_type, r.relacion, rol,
                     case when a.is_grantable then ' with grant option' else '' end);
    end loop;

    if r.relkind = 'r' then
      execute format('alter table %s %s row level security', r.relacion,
                     case when r.relrowsecurity then 'enable' else 'disable' end);
    elsif r.relkind = 'v' then
      execute format('alter view %s reset (security_invoker)', r.relacion);
      if r.reloptions is not null then
        execute format('alter view %s set (%s)', r.relacion, array_to_string(r.reloptions, ', '));
      end if;
    end if;
  end loop;
end $$;

-- ── Políticas ────────────────────────────────────────────────────────────
drop policy if exists "propiedades_avm_lectura_publica" on public.propiedades_avm;
drop policy if exists "avatares_actualizar_solo_dueno" on storage.objects;

do $$
declare p record;
begin
  for p in select * from respaldo_seguridad_20261009.politicas loop
    if not exists (select 1 from pg_policies
                    where schemaname = p.esquema and tablename = p.tabla and policyname = p.nombre) then
      execute format('create policy %I on %I.%I as %s for %s to %s%s%s',
        p.nombre, p.esquema, p.tabla, p.permissive, p.cmd,
        (select string_agg(case when x = 'public' then 'public' else quote_ident(x) end, ', ')
           from unnest(p.roles) x),
        case when p.qual       is not null then ' using (' || p.qual || ')' else '' end,
        case when p.with_check is not null then ' with check (' || p.with_check || ')' else '' end);
    end if;
  end loop;
end $$;

-- ── search_path de las funciones ─────────────────────────────────────────
do $$
declare
  f   record;
  sp  text;
begin
  for f in select * from respaldo_seguridad_20261009.funciones loop
    continue when to_regprocedure(f.firma) is null;
    select substr(c, length('search_path=') + 1) into sp
      from unnest(f.proconfig) c
     where c like 'search_path=%';
    if sp is null then
      execute format('alter function %s reset search_path', f.firma);
    else
      execute format('alter function %s set search_path to %s', f.firma, sp);
    end if;
  end loop;
end $$;

-- ── Borrar la foto ───────────────────────────────────────────────────────
drop schema respaldo_seguridad_20261009 cascade;

commit;
