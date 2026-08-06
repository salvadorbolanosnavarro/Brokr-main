-- =============================================================================
-- Broquer · Tareas — vínculos múltiples + recordatorio de cita
-- Pégalo en Supabase > SQL Editor y dale Run. Es seguro correrlo aunque ya
-- exista (todo "if not exists"). No borra ni toca tus tareas actuales.
-- =============================================================================

-- Una tarea puede tener VARIOS contactos vinculados (antes solo uno).
create table if not exists tareas_contactos (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null,
  tarea_id    uuid not null references tareas(id) on delete cascade,
  contacto_id text not null references contactos(id) on delete cascade,
  created_at  timestamptz default now(),
  unique (tarea_id, contacto_id)
);

-- Una tarea puede tener VARIOS inmuebles vinculados (antes solo uno).
create table if not exists tareas_propiedades (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null,
  tarea_id     uuid not null references tareas(id) on delete cascade,
  propiedad_id uuid not null references propiedades(id) on delete cascade,
  created_at   timestamptz default now(),
  unique (tarea_id, propiedad_id)
);

create index if not exists idx_tareas_contactos_tarea      on tareas_contactos (tarea_id);
create index if not exists idx_tareas_contactos_contacto    on tareas_contactos (contacto_id);
create index if not exists idx_tareas_propiedades_tarea     on tareas_propiedades (tarea_id);
create index if not exists idx_tareas_propiedades_propiedad on tareas_propiedades (propiedad_id);

-- Notas libres de la tarea (antes solo existía el título) y control del
-- recordatorio de cita: cuándo mandarlo y si ya se mandó, para no repetirlo.
alter table tareas add column if not exists notas text;
alter table tareas add column if not exists recordatorio_enviado boolean default false;
alter table tareas add column if not exists recordatorio_minutos_antes int default 60;

-- =============================================================================
-- SEGURIDAD (RLS) — el backend usa la service_role key y se brinca esto;
-- esto protege el acceso directo desde el frontend (Tareas, Contactos, Inmuebles).
-- =============================================================================
alter table tareas_contactos    enable row level security;
alter table tareas_propiedades  enable row level security;

drop policy if exists "dueño ve sus vinculos de tarea-contacto"    on tareas_contactos;
drop policy if exists "dueño ve sus vinculos de tarea-propiedad"   on tareas_propiedades;

create policy "dueño ve sus vinculos de tarea-contacto"  on tareas_contactos   for all using (user_id = auth.uid());
create policy "dueño ve sus vinculos de tarea-propiedad" on tareas_propiedades for all using (user_id = auth.uid());
