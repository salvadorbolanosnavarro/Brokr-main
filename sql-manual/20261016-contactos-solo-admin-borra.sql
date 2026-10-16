-- ══════════════════════════════════════════════════════════════════════════
-- Contactos y clientes: en Broquer para Empresas solo el dueño o un
-- administrador los puede borrar
-- ══════════════════════════════════════════════════════════════════════════
-- Problema: un agente (miembro que no es dueño ni admin) podía borrar, uno por
-- uno, los contactos que él mismo creó, porque la base lo dejaba con
-- "contactos_own_delete" (user_id = yo) y "org_borra_contactos"
-- (… or user_id = yo). El borrado masivo ya estaba bloqueado en el servidor
-- (routers/bulk_delete.py) y los inmuebles también; los contactos sueltos no.
--
-- Arreglo: las dos reglas de borrado siguen igual, pero "quien lo creó" ya no
-- alcanza si esa persona es agente de una empresa. Las cuentas personales y
-- el dueño/admin de una empresa borran exactamente lo mismo que hoy.
-- No toca datos ni las reglas de ver, crear o editar.
--
-- Guarda las dos reglas actuales en respaldo_contactos_borrar_20261016 para
-- que 20261016-contactos-solo-admin-borra-REVERSA.sql las deje igual.
-- Todo en una sola transacción.
-- ══════════════════════════════════════════════════════════════════════════

begin;

-- ── 0) Foto de las reglas de borrado actuales (solo la primera vez) ──────
create schema if not exists respaldo_contactos_borrar_20261016;
revoke all on schema respaldo_contactos_borrar_20261016 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_contactos_borrar_20261016.politicas') is not null then
    raise notice 'La foto de reglas de borrado ya existe; no se vuelve a tomar.';
    return;
  end if;
  create table respaldo_contactos_borrar_20261016.politicas (
    nombre name primary key, permissive text, roles name[], cmd text, qual text, with_check text
  );
  revoke all on respaldo_contactos_borrar_20261016.politicas from public, anon, authenticated;
  insert into respaldo_contactos_borrar_20261016.politicas
  select policyname, permissive, roles, cmd, qual, with_check
    from pg_policies
   where schemaname = 'public' and tablename = 'contactos'
     and policyname in ('contactos_own_delete', 'org_borra_contactos');
end $$;

-- ── 1) ¿Soy agente (no dueño ni admin) de alguna empresa? ────────────────
-- Misma regla que routers/bulk_delete.py: en una empresa, solo owner/admin.
create or replace function public.soy_agente_de_empresa()
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
      from public.organizacion_miembros om
      join public.organizaciones o on o.id = om.org_id
     where om.user_id = auth.uid()
       and om.activo = true
       and coalesce(o.tipo, 'personal') = 'empresa'
       and coalesce(om.rol_org, 'agente') not in ('owner', 'admin')
  )
$$;

revoke all on function public.soy_agente_de_empresa() from public, anon;
grant execute on function public.soy_agente_de_empresa() to authenticated, service_role;

-- ── 2) Reglas de borrado (mismos nombres y roles) ─────────────────────────
drop policy if exists "contactos_own_delete" on public.contactos;
create policy "contactos_own_delete" on public.contactos
  for delete to public
  using (((select auth.uid()) = user_id)
         and not (select public.soy_agente_de_empresa()));

drop policy if exists "org_borra_contactos" on public.contactos;
create policy "org_borra_contactos" on public.contactos
  for delete to public
  using ((org_id = (select public.mi_org()))
         and ((select public.es_admin_org())
              or ((user_id = (select auth.uid()))
                  and not (select public.soy_agente_de_empresa()))));

-- ── 3) Si en producción hubiera otra regla que deje borrar contactos, se
--       detiene y no cambia nada (el agente podría seguir borrando por ahí).
do $$
declare n int;
begin
  select count(*) into n from pg_policies p
   where p.schemaname = 'public' and p.tablename = 'contactos'
     and p.cmd in ('DELETE', 'ALL') and p.permissive = 'PERMISSIVE'
     and p.policyname not in ('contactos_own_delete', 'org_borra_contactos');
  if n > 0 then
    raise exception 'Hay % regla(s) más que dejan borrar contactos; no se aplicó nada.', n;
  end if;
  select count(*) into n from respaldo_contactos_borrar_20261016.politicas;
  if n <> 2 then
    raise exception 'Se esperaban 2 reglas de borrado en la foto y hay %; no se aplicó nada.', n;
  end if;
end $$;

commit;
