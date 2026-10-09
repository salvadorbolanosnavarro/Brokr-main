-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Blindaje de aislamiento entre organizaciones (Fase 0a)
--
-- QUÉ HACE
--   Agrega una política RESTRICTIVE ("candado") a propiedades, contactos y
--   tareas. En Postgres las políticas permissive se combinan con OR (cada una
--   AMPLÍA lo que se ve) y las restrictive con AND (cada una LIMITA). Así que
--   aunque exista en Supabase alguna política vieja demasiado abierta (las de
--   propiedades/contactos no están en el repo y no sabemos qué dicen), este
--   candado garantiza que un usuario con sesión NUNCA vea filas de otra
--   organización. Lo que ya decidían los permisos del equipo (ver inventario
--   completo, ver contactos del equipo, asignados) sigue igual: el candado
--   sólo quita, nunca da.
--
--   Una fila pasa el candado si:
--     · la capturó el propio usuario (user_id), o
--     · está asignada al usuario (asignado_a), o
--     · su org_id es una organización donde el usuario es miembro activo, o
--     · no tiene org_id pero su dueño es miembro activo de una organización
--       del usuario (filas viejas antes de que existiera org_id).
--
-- QUÉ NO TOCA
--   · No borra ni cambia ninguna política existente ni ningún dato.
--   · El backend usa la service key (se salta RLS): Bolsa, micrositio público,
--     admin.html y el importador siguen funcionando igual.
--   · El público anónimo (micrositio) lee por la vista propiedades_publicas,
--     que no pasa por este candado (sólo aplica al rol "authenticated").
--
-- Idempotente. Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

-- Organizaciones activas del usuario con sesión.
create or replace function public.mis_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select org_id from organizacion_miembros
   where user_id = auth.uid() and activo = true
$$;

-- ¿La fila es visible para quien navega, a nivel organización?
create or replace function public.fila_de_mi_organizacion(
  p_user_id uuid, p_org_id uuid, p_asignado uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select
       p_user_id = auth.uid()
    or p_asignado = auth.uid()
    or (p_org_id is not null and p_org_id in (select public.mis_org_ids()))
    or (p_org_id is null and exists (
          select 1 from organizacion_miembros om
           where om.user_id = p_user_id and om.activo = true
             and om.org_id in (select public.mis_org_ids())
        ))
$$;

revoke all on function public.mis_org_ids() from public;
revoke all on function public.fila_de_mi_organizacion(uuid, uuid, uuid) from public;
grant execute on function public.mis_org_ids() to authenticated;
grant execute on function public.fila_de_mi_organizacion(uuid, uuid, uuid) to authenticated;

-- ── propiedades ──
alter table public.propiedades enable row level security;
drop policy if exists "candado organizacion" on public.propiedades;
create policy "candado organizacion"
  on public.propiedades
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

-- ── contactos ──
alter table public.contactos enable row level security;
drop policy if exists "candado organizacion" on public.contactos;
create policy "candado organizacion"
  on public.contactos
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

-- ── tareas ──
alter table public.tareas enable row level security;
drop policy if exists "candado organizacion" on public.tareas;
create policy "candado organizacion"
  on public.tareas
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

commit;

-- ── Diagnóstico (opcional) ──────────────────────────────────────────────────
-- 1) ¿Quién es miembro de tu organización? (cambia el correo). Si aparece
--    una cuenta que no es de tu equipo (p. ej. "Atta Tech"), esa cuenta ve tu
--    inventario y tus contactos y tú los suyos. Para sacarla: Equipo → quitar
--    miembro (o pídeselo a Claude).
--
-- select u.email, om.rol_org, om.activo, om.user_id
--   from organizacion_miembros om
--   join auth.users u on u.id = om.user_id
--  where om.org_id in (select org_id from organizacion_miembros m2
--                       join auth.users u2 on u2.id = m2.user_id
--                      where u2.email = 'TU_CORREO@AQUI.com' and m2.activo)
--  order by om.activo desc, u.email;
--
-- 2)
-- Cambia el correo y corre esto para ver de quién son los inmuebles que esa
-- cuenta tiene en su organización, agrupados por quién los capturó:
--
-- with yo as (
--   select u.id, om.org_id
--     from auth.users u
--     left join organizacion_miembros om on om.user_id = u.id and om.activo
--    where u.email = 'TU_CORREO@AQUI.com'
-- )
-- select p.org_id, p.user_id, u.email as capturo, count(*) as inmuebles,
--        (p.org_id = (select org_id from yo limit 1)) as es_de_mi_org
--   from propiedades p
--   left join auth.users u on u.id = p.user_id
--  where p.org_id = (select org_id from yo limit 1)
--     or p.user_id = (select id from yo limit 1)
--  group by 1, 2, 3
--  order by inmuebles desc;

select polname, polpermissive, polcmd, polrelid::regclass as tabla
  from pg_policy
 where polrelid in ('public.propiedades'::regclass,
                    'public.contactos'::regclass,
                    'public.tareas'::regclass)
 order by tabla, polname;
