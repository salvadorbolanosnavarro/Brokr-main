-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Tareas compartidas por el equipo + categorías para tareas y notas
--
-- QUÉ HACE
--   1) Tareas dejan de ser 100% privadas: en cuentas de empresa, cualquier
--      miembro activo del equipo puede ver las tareas de su organización y
--      asignarlas a cualquier otro miembro (no solo a sí mismo), reusando el
--      mismo endpoint POST /org/asignar que ya usan Contactos e Inmuebles
--      (ver routers/organizaciones.py, _TABLAS_ASIGNABLES).
--      En cuentas individuales ("personal") esto no cambia nada: cada quien
--      es el único miembro de su propia organización, así que las tareas
--      siguen siendo, en la práctica, solo suyas.
--   2) Un catálogo de categorías por cuenta (organizacion_categorias):
--      cualquier miembro activo puede crear categorías nuevas; quedan
--      disponibles para todo el equipo (o solo para el dueño, en cuentas
--      individuales). Se pueden etiquetar tareas y notas (actividades) con
--      varias categorías a la vez.
--
-- QUÉ NO HACE
--   No toca las políticas de RLS existentes de "tareas" — no sabemos sus
--   nombres exactos y tocarlas a ciegas es peligroso (mismo criterio que
--   migracion-contactos-asignados-visibles.sql). Solo AGREGA políticas
--   PERMISSIVE adicionales, que Postgres combina con OR: nunca quitan
--   acceso que ya existiera, solo lo amplían.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1) Tareas: org_id + asignado_a ──────────────────────────────────────
alter table public.tareas
  add column if not exists org_id uuid;

alter table public.tareas
  add column if not exists asignado_a uuid;

-- POST /org/asignar (routers/organizaciones.py) siempre manda updated_at en
-- el PATCH, igual que para contactos/propiedades — la tabla necesita la
-- columna para no rechazar la escritura.
alter table public.tareas
  add column if not exists updated_at timestamptz not null default now();

-- Backfill: cada tarea existente hereda el org_id de la membresía activa de
-- quien la creó (cada cuenta, incluida una individual, ya tiene una fila en
-- organizacion_miembros — ver get_org_context() en routers/organizaciones.py).
update public.tareas t
   set org_id = om.org_id
  from public.organizacion_miembros om
 where t.org_id is null
   and om.user_id = t.user_id
   and om.activo = true;

create index if not exists idx_tareas_org_id on public.tareas (org_id);
create index if not exists idx_tareas_asignado_a on public.tareas (org_id, asignado_a);

alter table public.tareas enable row level security;

-- Cualquier miembro activo de la organización ve las tareas de su empresa
-- (en cuentas individuales, la organización solo tiene un miembro: el dueño,
-- así que esto no expone nada nuevo).
drop policy if exists "equipo ve tareas de su empresa" on public.tareas;
create policy "equipo ve tareas de su empresa"
  on public.tareas
  for select
  using (
    org_id is not null
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

-- Necesario para que quien reciba una tarea asignada pueda marcarla
-- completada, editarla o reprogramarla sin depender de que el asignador lo
-- haga por ella/él.
drop policy if exists "equipo edita tareas de su empresa" on public.tareas;
create policy "equipo edita tareas de su empresa"
  on public.tareas
  for update
  using (
    org_id is not null
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

-- Los vínculos de una tarea compartida (a qué contacto/inmueble está ligada)
-- también deben ser visibles para el equipo, no solo para quien los creó.
alter table public.tareas_contactos enable row level security;
drop policy if exists "equipo ve vinculos de tareas de su empresa" on public.tareas_contactos;
create policy "equipo ve vinculos de tareas de su empresa"
  on public.tareas_contactos
  for select
  using (
    exists (
      select 1 from public.tareas t
        join public.organizacion_miembros om on om.org_id = t.org_id
       where t.id = tareas_contactos.tarea_id
         and om.user_id = auth.uid() and om.activo = true
    )
  );

alter table public.tareas_propiedades enable row level security;
drop policy if exists "equipo ve vinculos de tareas de su empresa" on public.tareas_propiedades;
create policy "equipo ve vinculos de tareas de su empresa"
  on public.tareas_propiedades
  for select
  using (
    exists (
      select 1 from public.tareas t
        join public.organizacion_miembros om on om.org_id = t.org_id
       where t.id = tareas_propiedades.tarea_id
         and om.user_id = auth.uid() and om.activo = true
    )
  );

-- ── 2) Catálogo de categorías, por cuenta ───────────────────────────────
create table if not exists public.organizacion_categorias (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nombre text not null,
  creado_por uuid not null,
  created_at timestamptz not null default now(),
  unique (org_id, nombre)
);

alter table public.organizacion_categorias enable row level security;

drop policy if exists "equipo ve categorias de su cuenta" on public.organizacion_categorias;
create policy "equipo ve categorias de su cuenta"
  on public.organizacion_categorias
  for select
  using (
    org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

-- Cualquier miembro activo puede crear categorías (folksonomía de equipo,
-- no una lista administrada solo por el dueño/admin).
drop policy if exists "equipo crea categorias en su cuenta" on public.organizacion_categorias;
create policy "equipo crea categorias en su cuenta"
  on public.organizacion_categorias
  for insert
  with check (
    creado_por = auth.uid()
    and org_id in (
      select org_id from public.organizacion_miembros
       where user_id = auth.uid() and activo = true
    )
  );

-- Borrar sí queda más restringido (solo quien la creó, o el owner/admin de
-- la cuenta): una categoría puede estar en uso por varios compañeros y
-- borrarla les quita la etiqueta sin avisarles.
drop policy if exists "creador o admin borra categorias" on public.organizacion_categorias;
create policy "creador o admin borra categorias"
  on public.organizacion_categorias
  for delete
  using (
    creado_por = auth.uid()
    or exists (
      select 1 from public.organizacion_miembros om
       where om.org_id = organizacion_categorias.org_id
         and om.user_id = auth.uid() and om.activo = true
         and om.rol_org in ('owner', 'admin')
    )
  );

create index if not exists idx_organizacion_categorias_org on public.organizacion_categorias (org_id);

-- ── 3) Etiquetado: tareas y notas (actividades) con varias categorías ───
create table if not exists public.tareas_categorias (
  id uuid primary key default gen_random_uuid(),
  tarea_id uuid not null references public.tareas(id) on delete cascade,
  categoria_id uuid not null references public.organizacion_categorias(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (tarea_id, categoria_id)
);
alter table public.tareas_categorias enable row level security;
drop policy if exists "equipo gestiona categorias de tareas de su cuenta" on public.tareas_categorias;
create policy "equipo gestiona categorias de tareas de su cuenta"
  on public.tareas_categorias
  for all
  using (
    exists (
      select 1 from public.organizacion_categorias c
        join public.organizacion_miembros om on om.org_id = c.org_id
       where c.id = tareas_categorias.categoria_id
         and om.user_id = auth.uid() and om.activo = true
    )
  )
  with check (
    exists (
      select 1 from public.organizacion_categorias c
        join public.organizacion_miembros om on om.org_id = c.org_id
       where c.id = tareas_categorias.categoria_id
         and om.user_id = auth.uid() and om.activo = true
    )
  );
create index if not exists idx_tareas_categorias_tarea on public.tareas_categorias (tarea_id);

create table if not exists public.actividades_categorias (
  id uuid primary key default gen_random_uuid(),
  actividad_id uuid not null references public.actividades(id) on delete cascade,
  categoria_id uuid not null references public.organizacion_categorias(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (actividad_id, categoria_id)
);
alter table public.actividades_categorias enable row level security;
drop policy if exists "equipo gestiona categorias de notas de su cuenta" on public.actividades_categorias;
create policy "equipo gestiona categorias de notas de su cuenta"
  on public.actividades_categorias
  for all
  using (
    exists (
      select 1 from public.organizacion_categorias c
        join public.organizacion_miembros om on om.org_id = c.org_id
       where c.id = actividades_categorias.categoria_id
         and om.user_id = auth.uid() and om.activo = true
    )
  )
  with check (
    exists (
      select 1 from public.organizacion_categorias c
        join public.organizacion_miembros om on om.org_id = c.org_id
       where c.id = actividades_categorias.categoria_id
         and om.user_id = auth.uid() and om.activo = true
    )
  );
create index if not exists idx_actividades_categorias_actividad on public.actividades_categorias (actividad_id);

-- ── Verificación ─────────────────────────────────────────────────────────
select 'tareas' as tabla,
       count(*) filter (where org_id is not null) as con_org,
       count(*) filter (where asignado_a is not null) as asignadas,
       count(*) as total
  from public.tareas;
