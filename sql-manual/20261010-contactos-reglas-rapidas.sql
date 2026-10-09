-- ══════════════════════════════════════════════════════════════════════════
-- Contactos: mismas reglas de seguridad, calculadas una vez por consulta
-- ══════════════════════════════════════════════════════════════════════════
-- Problema: la lista de contactos tardaba más de 8 s y la base la cancelaba
-- ("statement timeout"). Las reglas llamaban funciones (mi_org, org_permiso,
-- fila_de_mi_organizacion, contacto_en_mis_tareas…) UNA VEZ POR CADA FILA de
-- los ~30,000 contactos, aunque el resultado no depende de la fila.
--
-- Arreglo: las mismas condiciones, pero
--   · auth.uid(), mi_org(), es_admin_org(), org_permiso() van dentro de
--     (select …): Postgres los calcula una sola vez por consulta;
--   · fila_de_mi_organizacion() y contacto_en_mis_tareas() se reemplazan por
--     dos funciones que devuelven LA LISTA completa una sola vez
--     (companeros_activos_de_mi_org, contactos_de_mis_tareas).
-- Nadie ve ni puede cambiar nada distinto a hoy. No toca datos.
--
-- Guarda las reglas actuales en respaldo_contactos_20261010 para que
-- 20261010-contactos-reglas-rapidas-REVERSA.sql las deje exactamente igual.
-- Todo en una sola transacción.
-- ══════════════════════════════════════════════════════════════════════════

begin;

-- ── 0) Foto de las reglas actuales (solo la primera vez) ─────────────────
create schema if not exists respaldo_contactos_20261010;
revoke all on schema respaldo_contactos_20261010 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_contactos_20261010.politicas') is not null then
    raise notice 'La foto de reglas de contactos ya existe; no se vuelve a tomar.';
    return;
  end if;
  create table respaldo_contactos_20261010.politicas (
    nombre name primary key, permissive text, roles name[], cmd text, qual text, with_check text
  );
  revoke all on respaldo_contactos_20261010.politicas from public, anon, authenticated;
  insert into respaldo_contactos_20261010.politicas
  select policyname, permissive, roles, cmd, qual, with_check
    from pg_policies where schemaname = 'public' and tablename = 'contactos';
end $$;

-- ── 1) Funciones que devuelven la lista completa una sola vez ────────────
-- Compañeros activos de mi empresa (lo que fila_de_mi_organizacion revisaba
-- por cada contacto sin empresa).
create or replace function public.companeros_activos_de_mi_org()
returns setof uuid
language sql stable security definer
set search_path = public, pg_temp
as $$
  select om.user_id from public.organizacion_miembros om
   where om.activo = true and om.org_id in (select public.mis_org_ids())
$$;

-- Contactos que me tocan por mis tareas asignadas: mismas condiciones que
-- contacto_en_mis_tareas(id, org_id, user_id), pero para todos a la vez.
create or replace function public.contactos_de_mis_tareas()
returns setof text
language sql stable security definer
set search_path = public, pg_temp
as $$
  with mias as (
    select t.id, t.contacto_id::text as contacto_id, t.org_id
      from public.tareas t
     where t.asignado_a = auth.uid()
  ), pares as (
    select contacto_id, org_id from mias where contacto_id is not null
    union
    select tc.contacto_id::text, m.org_id
      from public.tareas_contactos tc join mias m on m.id = tc.tarea_id
  )
  select c.id::text
    from pares p
    join public.contactos c on c.id::text = p.contacto_id
   where p.org_id::text = c.org_id::text
      or exists (select 1 from public.organizacion_miembros om
                  where om.org_id = p.org_id and om.user_id::text = c.user_id::text)
$$;

revoke all on function public.companeros_activos_de_mi_org() from public, anon;
revoke all on function public.contactos_de_mis_tareas() from public, anon;
grant execute on function public.companeros_activos_de_mi_org() to authenticated, service_role;
grant execute on function public.contactos_de_mis_tareas() to authenticated, service_role;

-- ── 2) Reglas nuevas (mismos nombres, mismos roles, mismas condiciones) ──
drop policy if exists "candado organizacion" on public.contactos;
create policy "candado organizacion" on public.contactos
  as restrictive for all to authenticated
  using (
       user_id = (select auth.uid())
    or asignado_a = (select auth.uid())
    or (org_id is not null and org_id in (select public.mis_org_ids()))
    or (org_id is null and user_id in (select public.companeros_activos_de_mi_org()))
  )
  with check (
       user_id = (select auth.uid())
    or asignado_a = (select auth.uid())
    or (org_id is not null and org_id in (select public.mis_org_ids()))
    or (org_id is null and user_id in (select public.companeros_activos_de_mi_org()))
  );

drop policy if exists "agente ve contactos de sus tareas asignadas" on public.contactos;
create policy "agente ve contactos de sus tareas asignadas" on public.contactos
  for select to public
  using (id::text in (select public.contactos_de_mis_tareas()));

drop policy if exists "agente ve sus contactos asignados" on public.contactos;
create policy "agente ve sus contactos asignados" on public.contactos
  for select to public
  using (asignado_a = (select auth.uid()));

drop policy if exists "contactos_own_select" on public.contactos;
create policy "contactos_own_select" on public.contactos
  for select to public
  using ((select auth.uid()) = user_id);

drop policy if exists "contactos_own_update" on public.contactos;
create policy "contactos_own_update" on public.contactos
  for update to public
  using ((select auth.uid()) = user_id);

drop policy if exists "contactos_own_delete" on public.contactos;
create policy "contactos_own_delete" on public.contactos
  for delete to public
  using ((select auth.uid()) = user_id);

drop policy if exists "org_ve_contactos" on public.contactos;
create policy "org_ve_contactos" on public.contactos
  for select to public
  using ((org_id = (select public.mi_org()))
         and ((select public.org_permiso('ver_contactos_equipo'::text)) or (user_id = (select auth.uid()))));

drop policy if exists "org_edita_contactos" on public.contactos;
create policy "org_edita_contactos" on public.contactos
  for update to public
  using ((org_id = (select public.mi_org()))
         and ((select public.es_admin_org()) or (user_id = (select auth.uid()))))
  with check (org_id = (select public.mi_org()));

drop policy if exists "org_borra_contactos" on public.contactos;
create policy "org_borra_contactos" on public.contactos
  for delete to public
  using ((org_id = (select public.mi_org()))
         and ((select public.es_admin_org()) or (user_id = (select auth.uid()))));

drop policy if exists "insertar_propio_en_mi_org" on public.contactos;
create policy "insertar_propio_en_mi_org" on public.contactos
  for insert to authenticated
  with check ((user_id = (select auth.uid()))
              and (not (org_id is distinct from (select public.mi_org()))));

-- ── 3) Si en producción hubiera una regla que este script no conoce, se
--       detiene y no cambia nada (todas deben estar en la foto).
do $$
declare n int;
begin
  select count(*) into n from pg_policies p
   where p.schemaname = 'public' and p.tablename = 'contactos'
     and p.policyname not in (select nombre from respaldo_contactos_20261010.politicas);
  if n > 0 then
    raise exception 'Hay % regla(s) nuevas que no estaban en la foto; no se aplicó nada.', n;
  end if;
  select count(*) into n from respaldo_contactos_20261010.politicas b
   where not exists (select 1 from pg_policies p where p.schemaname = 'public'
                       and p.tablename = 'contactos' and p.policyname = b.nombre);
  if n > 0 then
    raise exception 'Faltan % regla(s) de las que había; no se aplicó nada.', n;
  end if;
end $$;

commit;
