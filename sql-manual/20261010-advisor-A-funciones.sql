-- ══════════════════════════════════════════════════════════════════════════
-- Security Advisor · A) Quién puede ejecutar las funciones SECURITY DEFINER
-- ══════════════════════════════════════════════════════════════════════════
-- A1. admin_update_usuario: nadie de fuera (ningún código la usa).
-- A2. Funciones que solo usan los triggers: nadie de fuera. Los triggers
--     siguen funcionando: Postgres no revisa este permiso al dispararlos.
-- A3. Funciones de las reglas de seguridad (RLS): fuera visitantes sin
--     sesión (anon) y public; los usuarios con sesión (authenticated) siguen.
-- service_role (el backend) conserva el permiso en todas.
--
-- Antes guarda una foto de los permisos en respaldo_advisor_20261010 para
-- que 20261010-advisor-A-funciones-REVERSA.sql los deje exactamente igual.
-- Todo en una sola transacción. Se puede correr dos veces sin efecto extra.
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_advisor_20261010;
revoke all on schema respaldo_advisor_20261010 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_advisor_20261010.funciones_permisos') is not null then
    raise notice 'La foto de permisos de funciones ya existe; no se vuelve a tomar.';
    return;
  end if;
  create table respaldo_advisor_20261010.funciones_permisos (
    firma  text primary key,
    proacl aclitem[]
  );
  revoke all on respaldo_advisor_20261010.funciones_permisos from public, anon, authenticated;
  insert into respaldo_advisor_20261010.funciones_permisos
  select p.oid::regprocedure::text, p.proacl
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
     and p.proname in ('admin_update_usuario',
                       'handle_new_user', 'set_org_id', 'protect_usuarios_sensitive_fields',
                       'bk_contacto_cambio_estatus', 'rls_auto_enable',
                       'mis_org_ids', 'fila_de_mi_organizacion', 'contacto_en_mis_tareas',
                       'mi_org', 'es_admin_org', 'mi_rol_org', 'org_permiso');
end $$;

do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as firma, p.proname
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and p.proname in ('admin_update_usuario',
                         'handle_new_user', 'set_org_id', 'protect_usuarios_sensitive_fields',
                         'bk_contacto_cambio_estatus', 'rls_auto_enable',
                         'mis_org_ids', 'fila_de_mi_organizacion', 'contacto_en_mis_tareas',
                         'mi_org', 'es_admin_org', 'mi_rol_org', 'org_permiso')
  loop
    if f.proname in ('mis_org_ids', 'fila_de_mi_organizacion', 'contacto_en_mis_tareas',
                     'mi_org', 'es_admin_org', 'mi_rol_org', 'org_permiso') then
      -- A3: las usan las reglas RLS de usuarios con sesión.
      execute format('revoke execute on function %s from public, anon', f.firma);
      execute format('grant execute on function %s to authenticated, service_role', f.firma);
    else
      -- A1 y A2.
      execute format('revoke execute on function %s from public, anon, authenticated', f.firma);
      execute format('grant execute on function %s to service_role', f.firma);
    end if;
  end loop;
end $$;

commit;
