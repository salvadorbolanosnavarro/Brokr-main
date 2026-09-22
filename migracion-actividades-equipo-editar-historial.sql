-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Notas de bitácora (actividades) visibles por todo el equipo,
-- editables y eliminables, con historial para el dueño de la empresa
--
-- QUÉ HACE
--   1) org_id en actividades: en cuentas de empresa, cualquier miembro activo
--      ve, edita y elimina las notas de su organización (antes cada nota
--      solo la veía/tocaba quien la escribió — mismo hueco que tenía
--      "tareas" antes de migracion-tareas-equipo-categorias.sql). En cuentas
--      individuales no cambia nada: la organización solo tiene un miembro.
--   2) actividades_historial: cada vez que se edita o se elimina una nota,
--      queda una copia de cómo estaba ANTES en esta tabla — sin relación de
--      llave foránea con cascada hacia actividades, precisamente para que
--      sobreviva cuando la nota original se borra. Solo el owner/admin de
--      la cuenta puede leerla.
--   3) editado_en / editado_por en actividades: para mostrar "(editada)" en
--      el momento sin tener que consultar el historial completo.
--
-- QUÉ NO HACE
--   No toca las políticas de RLS existentes de "actividades" — no sabemos
--   sus nombres exactos y tocarlas a ciegas es peligroso (mismo criterio que
--   migracion-contactos-asignados-visibles.sql y la migración de tareas).
--   Solo AGREGA políticas PERMISSIVE adicionales: nunca quitan acceso que ya
--   existiera, solo lo amplían.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1) org_id + marca de edición en actividades ─────────────────────────
alter table public.actividades
  add column if not exists org_id uuid;

alter table public.actividades
  add column if not exists editado_en timestamptz;

alter table public.actividades
  add column if not exists editado_por uuid;

-- Backfill: cada actividad hereda el org_id del contacto o la propiedad a la
-- que pertenece (los dos ya tienen org_id — ver migracion-asignacion-agente.sql
-- y el resto del esquema). Si no tiene ninguno de los dos vínculos, hereda el
-- org_id de quien la escribió.
update public.actividades a
   set org_id = c.org_id
  from public.contactos c
 where a.org_id is null and a.contacto_id = c.id;

update public.actividades a
   set org_id = p.org_id
  from public.propiedades p
 where a.org_id is null and a.propiedad_id = p.id;

update public.actividades a
   set org_id = om.org_id
  from public.organizacion_miembros om
 where a.org_id is null
   and om.user_id = a.user_id
   and om.activo = true;

create index if not exists idx_actividades_org_id on public.actividades (org_id);

alter table public.actividades enable row level security;

drop policy if exists "equipo ve notas de su empresa" on public.actividades;
create policy "equipo ve notas de su empresa"
  on public.actividades
  for select
  using (
    org_id is not null
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

drop policy if exists "equipo edita notas de su empresa" on public.actividades;
create policy "equipo edita notas de su empresa"
  on public.actividades
  for update
  using (
    org_id is not null
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

drop policy if exists "equipo elimina notas de su empresa" on public.actividades;
create policy "equipo elimina notas de su empresa"
  on public.actividades
  for delete
  using (
    org_id is not null
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

-- ── 2) Historial de ediciones y eliminaciones (solo lectura para el dueño) ──
create table if not exists public.actividades_historial (
  id uuid primary key default gen_random_uuid(),
  actividad_id uuid not null,     -- SIN fk con cascada a propósito: debe
                                   -- sobrevivir a que se borre la nota original
  org_id uuid not null,
  accion text not null check (accion in ('editar', 'eliminar')),
  usuario_id uuid not null,       -- quien editó o eliminó
  tipo text,
  texto_anterior text,
  adjuntos_anterior jsonb,
  contacto_id uuid,
  propiedad_id uuid,
  created_at timestamptz not null default now()
);

alter table public.actividades_historial enable row level security;

-- Solo owner/admin de la cuenta pueden leer el historial — es información
-- sensible de auditoría, no algo que cualquier agente deba poder consultar.
drop policy if exists "admin lee el historial de su empresa" on public.actividades_historial;
create policy "admin lee el historial de su empresa"
  on public.actividades_historial
  for select
  using (
    exists (
      select 1 from public.organizacion_miembros om
       where om.org_id = actividades_historial.org_id
         and om.user_id = auth.uid() and om.activo = true
         and om.rol_org in ('owner', 'admin')
    )
  );

-- Cualquier miembro activo de la cuenta puede escribir su propia entrada de
-- auditoría (la escritura ES la auditoría: pasa en el mismo momento en que
-- ese miembro edita o borra la nota).
drop policy if exists "equipo registra su propia edicion o borrado" on public.actividades_historial;
create policy "equipo registra su propia edicion o borrado"
  on public.actividades_historial
  for insert
  with check (
    usuario_id = auth.uid()
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

create index if not exists idx_actividades_historial_actividad on public.actividades_historial (actividad_id);
create index if not exists idx_actividades_historial_org on public.actividades_historial (org_id, created_at desc);

-- ── Verificación ─────────────────────────────────────────────────────────
select 'actividades' as tabla,
       count(*) filter (where org_id is not null) as con_org,
       count(*) as total
  from public.actividades;
