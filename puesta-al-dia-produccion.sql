-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — PUESTA AL DÍA DE PRODUCCIÓN (todo lo que está en main, SIN fase 6
-- ni fase 7)
--
-- CÓMO SE CORRE: Supabase → SQL Editor → New query → pegar todo → Run.
-- Va en UNA sola transacción: si algo falla, no se aplica NADA y la base queda
-- igual que antes (copia el error y mándaselo a Claude). Se puede correr las
-- veces que sea: lo que ya existe se salta.
--
-- REGLAS QUE CUMPLE
--   · No borra filas, tablas ni columnas. No hay DELETE ni DROP TABLE/COLUMN.
--     Sí hay "drop policy/trigger if exists" + volver a crearlos (son reglas
--     de acceso que este mismo archivo recrea igual) y se reemplaza el índice
--     único viejo de EasyBroker (user_id, eb_public_id) por el de empresa.
--   · Tolera tablas que ya existen con otra forma: agrega las columnas que
--     falten y quita el NOT NULL de columnas viejas que Broquer ya no llena
--     (pipeline_etapas, fuentes_captacion, respuestas_guardadas).
--   · Dos migraciones originales borraban datos (mensajes de WhatsApp
--     repetidos y huérfanos de números borrados). Aquí NO se borra nada: las
--     reglas se crean sólo si no hay repetidos, y las ligas como NOT VALID.
--
-- QUÉ HACE, EN ORDEN
--   1. Cuentas: usuarios (+módulos desactivados, acceso completo, trial Max,
--      token de notificaciones iOS), invitaciones (+traer datos), suscripciones
--      (+trial, periodo, asientos), demos_agendadas (tabla nueva),
--      wa_conversations (+no leídos).
--   2. Inmuebles/contactos: asignado_a, descripción privada, Bolsa, comisión
--      real, columnas de EasyBroker; regla única (org_id, eb_public_id) que
--      usa el importador; función org_permiso (sólo si no existe).
--   3. Tareas: vínculos múltiples, adjuntos, tareas de equipo y asignadas,
--      organizacion_categorias, tareas_categorias, actividades_categorias.
--   4. Bitácora: adjuntos de notas (bucket adjuntos-historial), notas de
--      equipo, editar/eliminar con actividades_historial.
--   5. Aislamiento entre organizaciones (candado), contactos visibles por
--      asignación o por tareas, y reparar inmuebles/contactos sin empresa.
--   6. Consola admin (correos, facturas_cfdi), función eliminar usuario,
--      caché del AVM (avm_scrape_cache), cuentas de correo (correo_cuentas).
--   7. Finanzas: fin_cuentas, fin_categorias, fin_movimientos + bucket
--      fin-comprobantes.
--   8. Firma electrónica: firma_documentos, firma_firmantes, firma_eventos,
--      firma_campos, firma_paginas, firma_contrato_jobs + bucket firmas.
--   9. Cumplimiento PLD: columnas del aviso a la UIF.
--  10. WhatsApp: wa2_agenda, wa2_automatizaciones, wa2_campanas,
--      wa2_campana_envios, wa2_flujo_estados y columnas nuevas; reglas
--      anti-duplicado y ligas de borrado (sin borrar nada existente).
--  11. Generador de video (video_jobs) y buckets que usa el código si faltan:
--      videos-fichas, wa-media, machotes-contrato, pld-expedientes.
--  12-16. Fases 1 a 5 de paridad (1 y 2 ya corrieron; 3 y 4 toleran tus
--      tablas viejas; 5 incluye las tablas del buscador).
--
-- DIFERENCIAS CONTRA LOS ARCHIVOS ORIGINALES (a propósito)
--   · contacto_id es texto (no uuid) en actividades_historial, fin_movimientos,
--     firma_firmantes, requerimientos_busqueda y busqueda_resultados: los
--     contactos de Broquer usan ids 'c_…' y con uuid fallaban al guardar.
--   · video_jobs y firma_contrato_jobs no tenían migración en el repo; se
--     crearon con las columnas que usa el código.
--
-- NO INCLUYE: fase 6 (cierres), fase 7 (sitios), schema.sql y
-- whatsapp_chatgpt_schema.sql (sus tablas ya existen), migracion-easybroker-
-- ubicacion.sql (arreglo de datos que ya corriste) ni los archivos de
-- diagnóstico. Tampoco las tablas de Facebook (fb_ad_entities,
-- fb_leads_recibidos, fb_audiences): su migración no está en el repo.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

-- ════════════════════════════════════════════════════════════════════════
-- 1. Columnas nuevas en tablas que ya existen (cuentas, suscripciones, móvil)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-admin-modulos-acceso.sql)
ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS modulos_desactivados text[] NOT NULL DEFAULT '{}'::text[];

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS acceso_completo_hasta timestamptz;

COMMENT ON COLUMN public.usuarios.modulos_desactivados IS
  'Claves de módulos que un admin desactivó para esta cuenta desde la Consola. Vacío = todos los módulos de su plan disponibles.';

COMMENT ON COLUMN public.usuarios.acceso_completo_hasta IS
  'Vencimiento de un acceso completo otorgado a mano por un admin (independiente del rol "equipo" y de Stripe). NULL = sin ese acceso.';

-- (migracion-trial-max.sql)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS trial_max_usado boolean DEFAULT false;

-- (migracion-movil.sql)
alter table wa_conversations
  add column if not exists unread_count int not null default 0;

update wa_conversations set unread_count = 0 where unread_count is null;

alter table usuarios
  add column if not exists apns_token text;

create index if not exists idx_usuarios_apns on usuarios (apns_token)
  where apns_token is not null;

create index if not exists idx_wa_conv_unread
  on wa_conversations (user_id) where unread_count > 0;

-- (migracion-invitacion-datos.sql)
ALTER TABLE public.organizacion_invitaciones
  ADD COLUMN IF NOT EXISTS traer_datos boolean NOT NULL DEFAULT false;

-- (migracion-demo-trial.sql)
ALTER TABLE public.suscripciones
  ADD COLUMN IF NOT EXISTS trial_hasta timestamptz;

COMMENT ON COLUMN public.suscripciones.trial_hasta IS
  'Vencimiento del trial sin tarjeta de Broquer Max. NULL en suscripciones de pago.';

CREATE TABLE IF NOT EXISTS public.demos_agendadas (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre     text NOT NULL,
  contacto   text NOT NULL,           -- teléfono o correo
  fecha      date NOT NULL,
  hora       text NOT NULL,           -- "HH:MM"
  mensaje    text DEFAULT '',
  origen     text DEFAULT '',         -- landing | index
  user_id    uuid,                    -- si venía con sesión
  created_at timestamptz DEFAULT now()
);

ALTER TABLE public.demos_agendadas ENABLE ROW LEVEL SECURITY;


-- migracion-suscripcion-empresas.sql (los índices y el default sólo si las
-- columnas existen en esta base)
alter table public.suscripciones
  add column if not exists periodo  text,
  add column if not exists asientos integer;
do $$
begin
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'suscripciones' and column_name = 'org_id')
     and exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'suscripciones' and column_name = 'plan_id') then
    create index if not exists idx_suscripciones_org_plan on public.suscripciones (org_id, plan_id);
  end if;
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'suscripciones' and column_name = 'stripe_subscription_id') then
    create index if not exists idx_suscripciones_stripe_sub on public.suscripciones (stripe_subscription_id);
  end if;
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'organizaciones' and column_name = 'asientos_max') then
    alter table public.organizaciones alter column asientos_max set default 5;
  end if;
end $$;


-- ════════════════════════════════════════════════════════════════════════
-- 2. Inmuebles y contactos: columnas de EasyBroker, Bolsa, comisión, asignación
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-asignacion-agente.sql)
alter table public.contactos
  add column if not exists asignado_a uuid;

alter table public.propiedades
  add column if not exists asignado_a uuid;

create index if not exists idx_contactos_asignado_a
  on public.contactos (org_id, asignado_a);

create index if not exists idx_propiedades_asignado_a
  on public.propiedades (org_id, asignado_a);

-- (migracion-descripcion-privada.sql)
alter table contactos
  add column if not exists descripcion_privada text;

-- (migracion-bolsa.sql)
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS en_bolsa boolean NOT NULL DEFAULT false;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_comision numeric;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_notas text;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_fecha timestamptz;

CREATE INDEX IF NOT EXISTS idx_propiedades_en_bolsa
  ON propiedades (bolsa_fecha DESC)
  WHERE en_bolsa = true;

-- (migracion-comision-real.sql)
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS comision_real numeric;

-- (migracion-easybroker.sql)
ALTER TABLE propiedades
  ADD COLUMN IF NOT EXISTS num_exterior  text,
  ADD COLUMN IF NOT EXISTS num_interior  text,
  ADD COLUMN IF NOT EXISTS estado        text,
  ADD COLUMN IF NOT EXISTS medio_bano    int,
  ADD COLUMN IF NOT EXISTS nivel         text,
  ADD COLUMN IF NOT EXISTS mantenimiento numeric,
  ADD COLUMN IF NOT EXISTS amenidades    text[];


-- ajuste-easybroker.sql: el importador guarda con "una propiedad de
-- EasyBroker por empresa" (org_id, eb_public_id). Si hay repetidas, NO se
-- toca nada de esto (se avisa) y el resto del archivo sigue.
do $$
declare n int; r record;
begin
  select count(*) into n from (
    select org_id, eb_public_id from public.propiedades
     where eb_public_id is not null and org_id is not null
     group by 1, 2 having count(*) > 1) d;
  if n > 0 then
    raise notice 'AVISO: hay % grupos de inmuebles de EasyBroker repetidos en la misma empresa. No se creó la regla única (org_id, eb_public_id); el importador puede fallar al guardar. Avísale a Claude.', n;
    return;
  end if;
  -- La regla vieja (user_id, eb_public_id) se reemplaza por la de empresa.
  for r in
    select con.conname from pg_constraint con
      join pg_class rel on rel.oid = con.conrelid
      join pg_namespace ns on ns.oid = rel.relnamespace
     where ns.nspname = 'public' and rel.relname = 'propiedades' and con.contype = 'u'
       and pg_get_constraintdef(con.oid) like '%user_id%' and pg_get_constraintdef(con.oid) like '%eb_public_id%'
  loop
    execute format('alter table public.propiedades drop constraint %I', r.conname);
  end loop;
  for r in
    select i.indexname from pg_indexes i
      join pg_class c on c.relname = i.indexname
      join pg_index x on x.indexrelid = c.oid
     where i.schemaname = 'public' and i.tablename = 'propiedades' and x.indisunique
       and i.indexdef like '%user_id%' and i.indexdef like '%eb_public_id%'
  loop
    execute format('drop index if exists public.%I', r.indexname);
  end loop;
  create unique index if not exists propiedades_org_eb_uniq on public.propiedades (org_id, eb_public_id);
end $$;

-- org_permiso (ajuste-easybroker.sql): permisos del equipo que usan las
-- reglas de lectura (ver comisiones, ver contactos del equipo…). Sólo se
-- crea si no existe: si producción ya tiene una versión, no se toca.
do $do$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'public' and p.proname = 'org_permiso') then
    return;
  end if;
  execute $fn$
create function public.org_permiso(p_clave text)
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
$$
  $fn$;
end $do$;


-- ════════════════════════════════════════════════════════════════════════
-- 3. Tareas: vínculos, adjuntos, equipo y categorías
-- ════════════════════════════════════════════════════════════════════════
-- contacto_en_mis_tareas (más abajo) lee tareas.contacto_id: si la base es
-- muy vieja y no la tiene, se agrega vacía.
alter table public.tareas add column if not exists contacto_id text;
alter table public.tareas add column if not exists propiedad_id uuid;
-- (tareas-vinculos-schema.sql)
create table if not exists tareas_contactos (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null,
  tarea_id    uuid not null references tareas(id) on delete cascade,
  contacto_id text not null references contactos(id) on delete cascade,
  created_at  timestamptz default now(),
  unique (tarea_id, contacto_id)
);

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

alter table tareas add column if not exists notas text;
alter table tareas add column if not exists recordatorio_enviado boolean default false;
alter table tareas add column if not exists recordatorio_minutos_antes int default 60;

alter table tareas_contactos    enable row level security;
alter table tareas_propiedades  enable row level security;

drop policy if exists "dueño ve sus vinculos de tarea-contacto"    on tareas_contactos;
drop policy if exists "dueño ve sus vinculos de tarea-propiedad"   on tareas_propiedades;

create policy "dueño ve sus vinculos de tarea-contacto"  on tareas_contactos   for all using (user_id = auth.uid());
create policy "dueño ve sus vinculos de tarea-propiedad" on tareas_propiedades for all using (user_id = auth.uid());

-- (migracion-tareas-adjuntos.sql)
alter table public.tareas
  add column if not exists adjuntos jsonb not null default '[]'::jsonb;

alter table public.tareas
  drop constraint if exists tareas_adjuntos_es_arreglo;
alter table public.tareas
  add constraint tareas_adjuntos_es_arreglo check (jsonb_typeof(adjuntos) = 'array');

-- (migracion-tareas-equipo-categorias.sql)
alter table public.tareas
  add column if not exists org_id uuid;

alter table public.tareas
  add column if not exists asignado_a uuid;

alter table public.tareas
  add column if not exists updated_at timestamptz not null default now();

update public.tareas t
   set org_id = om.org_id
  from public.organizacion_miembros om
 where t.org_id is null
   and om.user_id = t.user_id
   and om.activo = true;

create index if not exists idx_tareas_org_id on public.tareas (org_id);
create index if not exists idx_tareas_asignado_a on public.tareas (org_id, asignado_a);

alter table public.tareas enable row level security;

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

-- tareas_categorias / actividades_categorias: la columna que apunta a la
-- tarea o nota usa el MISMO tipo que tareas.id / actividades.id de esta base.
do $$
declare t_tarea text; t_act text;
begin
  select format_type(a.atttypid, a.atttypmod) into t_tarea from pg_attribute a
   where a.attrelid = 'public.tareas'::regclass and a.attname = 'id';
  select format_type(a.atttypid, a.atttypmod) into t_act from pg_attribute a
   where a.attrelid = 'public.actividades'::regclass and a.attname = 'id';
  execute format($f$create table if not exists public.tareas_categorias (
    id uuid primary key default gen_random_uuid(),
    tarea_id %s not null references public.tareas(id) on delete cascade,
    categoria_id uuid not null references public.organizacion_categorias(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (tarea_id, categoria_id))$f$, t_tarea);
  execute format($f$create table if not exists public.actividades_categorias (
    id uuid primary key default gen_random_uuid(),
    actividad_id %s not null references public.actividades(id) on delete cascade,
    categoria_id uuid not null references public.organizacion_categorias(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (actividad_id, categoria_id))$f$, t_act);
end $$;
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



-- ════════════════════════════════════════════════════════════════════════
-- 4. Historial de notas (bitácora): adjuntos, equipo, editar y eliminar
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-actividades-adjuntos.sql)
alter table actividades
  add column if not exists adjuntos jsonb not null default '[]'::jsonb;

alter table actividades
  drop constraint if exists actividades_adjuntos_es_arreglo;
alter table actividades
  add constraint actividades_adjuntos_es_arreglo check (jsonb_typeof(adjuntos) = 'array');

insert into storage.buckets (id, name, public)
select 'adjuntos-historial', 'adjuntos-historial', true
where not exists (select 1 from storage.buckets where id = 'adjuntos-historial');

drop policy if exists "lectura publica de adjuntos de historial" on storage.objects;
create policy "lectura publica de adjuntos de historial"
  on storage.objects for select
  using (bucket_id = 'adjuntos-historial');

drop policy if exists "usuarios autenticados suben adjuntos de historial" on storage.objects;
create policy "usuarios autenticados suben adjuntos de historial"
  on storage.objects for insert
  with check (bucket_id = 'adjuntos-historial' and auth.role() = 'authenticated');

-- (migracion-actividades-equipo-editar-historial.sql)
alter table public.actividades
  add column if not exists org_id uuid;

alter table public.actividades
  add column if not exists editado_en timestamptz;

alter table public.actividades
  add column if not exists editado_por uuid;

update public.actividades a
   set org_id = c.org_id
  from public.contactos c
 where a.org_id is null and a.contacto_id::text = c.id::text;

update public.actividades a
   set org_id = p.org_id
  from public.propiedades p
 where a.org_id is null and a.propiedad_id::text = p.id::text;

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

create table if not exists public.actividades_historial (
  id uuid primary key default gen_random_uuid(),
  actividad_id text not null,     -- SIN fk con cascada a propósito: debe
  org_id uuid not null,
  accion text not null check (accion in ('editar', 'eliminar')),
  usuario_id uuid not null,       -- quien editó o eliminó
  tipo text,
  texto_anterior text,
  adjuntos_anterior jsonb,
  contacto_id text,               -- texto: los contactos usan ids 'c_…'
  propiedad_id uuid,
  created_at timestamptz not null default now()
);

alter table public.actividades_historial enable row level security;

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
-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table public.actividades_historial add column if not exists created_at timestamptz not null default now();
create index if not exists idx_actividades_historial_org on public.actividades_historial (org_id, created_at desc);



-- ════════════════════════════════════════════════════════════════════════
-- 5. Aislamiento entre organizaciones y visibilidad de contactos
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-aislamiento-organizacion.sql)
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

alter table public.propiedades enable row level security;
drop policy if exists "candado organizacion" on public.propiedades;
create policy "candado organizacion"
  on public.propiedades
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

alter table public.contactos enable row level security;
drop policy if exists "candado organizacion" on public.contactos;
create policy "candado organizacion"
  on public.contactos
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

alter table public.tareas enable row level security;
drop policy if exists "candado organizacion" on public.tareas;
create policy "candado organizacion"
  on public.tareas
  as restrictive
  for all
  to authenticated
  using (public.fila_de_mi_organizacion(user_id, org_id, asignado_a))
  with check (public.fila_de_mi_organizacion(user_id, org_id, asignado_a));

-- (migracion-contactos-asignados-visibles.sql)
alter table public.contactos enable row level security;

drop policy if exists "agente ve sus contactos asignados" on public.contactos;

create policy "agente ve sus contactos asignados"
  on public.contactos
  for select
  using (asignado_a = auth.uid());

-- (migracion-tareas-contactos-visibles.sql)
create or replace function public.contacto_en_mis_tareas(
  p_contacto text, p_org text, p_duenio text
) returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
      from public.tareas t
     where t.asignado_a = auth.uid()
       and (
             t.contacto_id::text = p_contacto
          or exists (select 1 from public.tareas_contactos tc
                      where tc.tarea_id = t.id and tc.contacto_id::text = p_contacto)
       )
       and (
             t.org_id::text = p_org
          or exists (select 1 from public.organizacion_miembros om
                      where om.org_id = t.org_id and om.user_id::text = p_duenio)
       )
  );
$$;

revoke all on function public.contacto_en_mis_tareas(text, text, text) from public;
grant execute on function public.contacto_en_mis_tareas(text, text, text) to authenticated;

alter table public.contactos enable row level security;

drop policy if exists "agente ve contactos de sus tareas asignadas" on public.contactos;

create policy "agente ve contactos de sus tareas asignadas"
  on public.contactos
  for select
  using (public.contacto_en_mis_tareas(id::text, org_id::text, user_id::text));


-- migracion-org-huerfanas.sql: inmuebles y contactos sin empresa se pasan a
-- la empresa activa de quien los capturó (sólo llena org_id vacío).
update public.propiedades p set org_id = m.org_id
  from public.organizacion_miembros m
 where p.org_id is null and m.user_id = p.user_id and m.activo = true;
update public.contactos c set org_id = m.org_id
  from public.organizacion_miembros m
 where c.org_id is null and m.user_id = c.user_id and m.activo = true;


-- ════════════════════════════════════════════════════════════════════════
-- 6. Consola de administración, eliminar usuario, AVM, correo
-- ════════════════════════════════════════════════════════════════════════
-- correos y facturas_cfdi ya existen: se aseguran las columnas que usan
-- los índices antes de crearlos.
-- (migracion-admin-consola.sql)
create table if not exists public.correos (
  id          uuid primary key default gen_random_uuid(),
  direccion   text not null check (direccion in ('entrante','saliente')),
  de_email    text,
  de_nombre   text,
  para_email  text,
  asunto      text,
  cuerpo      text,
  user_id     uuid references auth.users(id) on delete set null,
  leido       boolean not null default false,
  estado      text default 'recibido',
  resend_id   text,
  created_at  timestamptz not null default now()
);

alter table public.correos add column if not exists direccion text;
alter table public.correos add column if not exists leido boolean not null default false;
alter table public.correos add column if not exists user_id uuid;
alter table public.correos add column if not exists created_at timestamptz not null default now();
create index if not exists correos_direccion_fecha_idx
  on public.correos (direccion, created_at desc);
create index if not exists correos_leido_idx
  on public.correos (leido) where leido = false;
create index if not exists correos_user_idx
  on public.correos (user_id);

alter table public.correos enable row level security;

create table if not exists public.facturas_cfdi (
  stripe_invoice_id text primary key,
  user_id           uuid references auth.users(id) on delete set null,
  uuid_cfdi         text,
  estado            text not null default 'pendiente'
                    check (estado in ('pendiente','emitida','cancelada','no_requiere')),
  monto             numeric(12,2),
  notas             text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

alter table public.facturas_cfdi add column if not exists estado text not null default 'pendiente';
alter table public.facturas_cfdi add column if not exists user_id uuid;
alter table public.facturas_cfdi add column if not exists created_at timestamptz not null default now();
alter table public.facturas_cfdi add column if not exists updated_at timestamptz not null default now();
create index if not exists facturas_cfdi_estado_idx
  on public.facturas_cfdi (estado, created_at desc);
create index if not exists facturas_cfdi_user_idx
  on public.facturas_cfdi (user_id);

alter table public.facturas_cfdi enable row level security;

create or replace function public.tocar_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists facturas_cfdi_touch on public.facturas_cfdi;
create trigger facturas_cfdi_touch
  before update on public.facturas_cfdi
  for each row execute function public.tocar_updated_at();

-- (migracion-eliminar-usuario.sql)
create or replace function public.admin_eliminar_usuario_total(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_email      text;
  v_resumen    jsonb := '{}'::jsonb;
  v_filas      bigint;
  v_tabla      record;
  v_pendientes text[];
  v_fallidas   text[];
  v_pasada     int;
  v_col        text;
begin
  select email into v_email from auth.users where id = p_user_id;
  if v_email is null then
    return jsonb_build_object('ok', false, 'error', 'El usuario no existe.');
  end if;

  if to_regclass('public.organizacion_miembros') is not null
     and to_regclass('public.organizaciones') is not null then
    delete from public.organizacion_miembros
     where org_id in (select id from public.organizaciones where owner_id = p_user_id);
    get diagnostics v_filas = row_count;
    if v_filas > 0 then
      v_resumen := v_resumen || jsonb_build_object('organizacion_miembros (de sus empresas)', v_filas);
    end if;
  end if;

  for v_pasada in 1..3 loop
    v_fallidas := '{}';
    for v_tabla in
      select c.table_name, c.column_name
        from information_schema.columns c
        join information_schema.tables t
          on t.table_schema = c.table_schema and t.table_name = c.table_name
       where c.table_schema = 'public'
         and t.table_type   = 'BASE TABLE'
         and c.column_name in ('user_id', 'owner_id')
         and c.data_type    = 'uuid'
         and c.table_name  <> 'usuarios'
       order by c.table_name
    loop
      if v_pasada > 1 and not (v_tabla.table_name || '.' || v_tabla.column_name) = any(v_pendientes) then
        continue;
      end if;
      begin
        execute format('delete from public.%I where %I = $1',
                       v_tabla.table_name, v_tabla.column_name)
          using p_user_id;
        get diagnostics v_filas = row_count;
        if v_filas > 0 then
          v_col := v_tabla.table_name
                   || case when v_tabla.column_name = 'owner_id' then ' (owner)' else '' end;
          v_resumen := v_resumen
            || jsonb_build_object(v_col, coalesce((v_resumen->>v_col)::bigint, 0) + v_filas);
        end if;
      exception when others then
        v_fallidas := v_fallidas || (v_tabla.table_name || '.' || v_tabla.column_name);
      end;
    end loop;
    exit when coalesce(array_length(v_fallidas, 1), 0) = 0;
    v_pendientes := v_fallidas;
  end loop;

  if coalesce(array_length(v_fallidas, 1), 0) > 0 then
    return jsonb_build_object(
      'ok', false,
      'error', 'No se pudieron limpiar estas tablas: ' || array_to_string(v_fallidas, ', '),
      'borrado_parcial', v_resumen
    );
  end if;

  delete from public.usuarios where id = p_user_id;
  get diagnostics v_filas = row_count;
  if v_filas > 0 then
    v_resumen := v_resumen || jsonb_build_object('usuarios', v_filas);
  end if;

  delete from auth.users where id = p_user_id;

  return jsonb_build_object('ok', true, 'email', v_email, 'borrado', v_resumen);
end;
$$;

revoke execute on function public.admin_eliminar_usuario_total(uuid) from public;
revoke execute on function public.admin_eliminar_usuario_total(uuid) from anon;
revoke execute on function public.admin_eliminar_usuario_total(uuid) from authenticated;
grant  execute on function public.admin_eliminar_usuario_total(uuid) to service_role;

-- (migracion-avm-cache.sql)
create table if not exists avm_scrape_cache (
  url text primary key,
  host text not null,
  colonia text,
  ciudad text,
  fetch_status text not null,
  page_text text not null,
  creado_en timestamptz not null default now()
);

create index if not exists avm_scrape_cache_creado_idx
  on avm_scrape_cache (creado_en);

create index if not exists avm_scrape_cache_colonia_idx
  on avm_scrape_cache (colonia, ciudad);

alter table avm_scrape_cache enable row level security;

-- (migracion-correo.sql)
create table if not exists public.correo_cuentas (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null,
  org_id     uuid,
  email      text not null,
  usuario    text not null,
  imap_host  text not null,
  imap_port  integer not null default 993,
  smtp_host  text not null,
  smtp_port  integer not null default 587,
  smtp_ssl   boolean not null default false,
  secreto    text not null,          -- contraseña de aplicación, cifrada (Fernet)
  activo     boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_correo_cuentas_user
  on public.correo_cuentas (user_id);

alter table public.correo_cuentas enable row level security;



-- ════════════════════════════════════════════════════════════════════════
-- 7. Finanzas (no existía en producción)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-finanzas.sql)
CREATE TABLE IF NOT EXISTS fin_cuentas (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL,
  team_id        uuid,                          -- futuro: finanzas por equipo
  nombre         text NOT NULL,                 -- "BBVA", "Efectivo", "AMEX"
  tipo           text NOT NULL DEFAULT 'banco', -- banco | efectivo | tarjeta | otra
  saldo_inicial  numeric NOT NULL DEFAULT 0,    -- editable; el saldo vivo se calcula
  moneda         text NOT NULL DEFAULT 'MXN',
  activa         boolean NOT NULL DEFAULT true, -- desactivar en vez de borrar si tiene historial
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fin_cuentas_user ON fin_cuentas (user_id);

ALTER TABLE fin_cuentas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fin_cuentas_owner ON fin_cuentas;
CREATE POLICY fin_cuentas_owner ON fin_cuentas
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS fin_categorias (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL,
  team_id     uuid,
  nombre      text NOT NULL,
  tipo        text NOT NULL DEFAULT 'gasto',    -- ingreso | gasto
  clave       text,                             -- clave interna de las sembradas
  orden       int NOT NULL DEFAULT 100,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fin_categorias_user ON fin_categorias (user_id);

ALTER TABLE fin_categorias ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fin_categorias_owner ON fin_categorias;
CREATE POLICY fin_categorias_owner ON fin_categorias
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS fin_movimientos (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL,
  team_id        uuid,
  tipo           text NOT NULL,                 -- ingreso | gasto
  monto          numeric NOT NULL CHECK (monto >= 0),
  fecha          date NOT NULL DEFAULT CURRENT_DATE,
  concepto       text NOT NULL DEFAULT '',
  notas          text,
  categoria_id   uuid REFERENCES fin_categorias(id) ON DELETE SET NULL,
  cuenta_id      uuid REFERENCES fin_cuentas(id)    ON DELETE SET NULL,
  propiedad_id   uuid,                          -- liga opcional a propiedades.id
  contacto_id    text,                          -- liga opcional a contactos.id (ids 'c_…')
  origen         text NOT NULL DEFAULT 'manual',-- manual | ticket | comision_auto
  comprobante    text,                          -- ruta en el bucket fin-comprobantes
  comprobante_mime text,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()      -- rastro de ediciones
);

CREATE INDEX IF NOT EXISTS fin_mov_user_fecha ON fin_movimientos (user_id, fecha DESC);
CREATE INDEX IF NOT EXISTS fin_mov_propiedad  ON fin_movimientos (propiedad_id) WHERE propiedad_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS fin_mov_cuenta     ON fin_movimientos (cuenta_id)    WHERE cuenta_id IS NOT NULL;

ALTER TABLE fin_movimientos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fin_movimientos_owner ON fin_movimientos;
CREATE POLICY fin_movimientos_owner ON fin_movimientos
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

INSERT INTO storage.buckets (id, name, public)
SELECT 'fin-comprobantes', 'fin-comprobantes', false
WHERE NOT EXISTS (SELECT 1 FROM storage.buckets WHERE id = 'fin-comprobantes');

DROP POLICY IF EXISTS "dueño lee sus comprobantes" ON storage.objects;
CREATE POLICY "dueño lee sus comprobantes"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'fin-comprobantes' AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS "dueño escribe sus comprobantes" ON storage.objects;
CREATE POLICY "dueño escribe sus comprobantes"
  ON storage.objects FOR INSERT
  WITH CHECK (bucket_id = 'fin-comprobantes' AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS "dueño borra sus comprobantes" ON storage.objects;
CREATE POLICY "dueño borra sus comprobantes"
  ON storage.objects FOR DELETE
  USING (bucket_id = 'fin-comprobantes' AND (storage.foldername(name))[1] = auth.uid()::text);



-- ════════════════════════════════════════════════════════════════════════
-- 8. Firma electrónica (no existía en producción)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-firmas.sql)
create table if not exists firma_documentos (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null,
  propiedad_id        uuid,
  titulo              text not null,

  tipo                text not null default 'otro',

  nivel               text not null default 'simple',

  estado              text not null default 'borrador',

  folio               text unique,

  archivo_ruta        text,
  archivo_nombre      text,
  archivo_bytes       bigint,
  paginas             integer,
  hash_original       text,          -- SHA-256 hex del PDF original

  firmado_ruta        text,
  hash_firmado        text,

  exige_ine           boolean not null default false,

  mensaje             text,          -- nota del agente para los firmantes
  vence_at            timestamptz,
  completado_at       timestamptz,
  cancelado_at        timestamptz,
  motivo_cancelacion  text,

  nom151_ruta         text,
  nom151_folio        text,
  nom151_at           timestamptz,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

alter table firma_documentos add column if not exists propiedad_id       uuid;
alter table firma_documentos add column if not exists exige_ine          boolean not null default false;
alter table firma_documentos add column if not exists nom151_ruta        text;
alter table firma_documentos add column if not exists nom151_folio       text;
alter table firma_documentos add column if not exists nom151_at          timestamptz;

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table firma_documentos add column if not exists created_at timestamptz not null default now();
create index if not exists firma_documentos_user_idx
  on firma_documentos (user_id, created_at desc);
create index if not exists firma_documentos_estado_idx
  on firma_documentos (user_id, estado);
create index if not exists firma_documentos_propiedad_idx
  on firma_documentos (propiedad_id) where propiedad_id is not null;

create table if not exists firma_firmantes (
  id                  uuid primary key default gen_random_uuid(),

  user_id             uuid not null,
  documento_id        uuid not null references firma_documentos(id) on delete cascade,

  contacto_id         text,          -- contactos.id (ids 'c_…')
  expediente_id       uuid,          -- pld_expedientes.id (si ya está identificado)

  nombre              text not null,
  email               text,
  telefono            text,          -- E.164, ej +524431234567

  rol                 text not null default 'otro',

  orden               integer,
  obligatorio         boolean not null default true,

  token               text unique,   -- la liga privada de esta persona
  estado              text not null default 'pendiente',

  otp_hash            text,
  otp_expira_at       timestamptz,
  otp_intentos        integer not null default 0,
  otp_canal           text,          -- whatsapp | email
  otp_enviado_at      timestamptz,
  verificado_at       timestamptz,

  firmado_at          timestamptz,
  rechazado_at        timestamptz,
  motivo_rechazo      text,

  trazo_ruta          text,          -- PNG del trazo
  ine_frente_ruta     text,
  ine_reverso_ruta    text,

  ip                  text,
  user_agent          text,
  geo_lat             double precision,
  geo_lng             double precision,
  geo_precision       double precision,

  consentimiento_at   timestamptz,
  consentimiento_texto text,

  created_at          timestamptz not null default now()
);

alter table firma_firmantes add column if not exists expediente_id    uuid;
alter table firma_firmantes add column if not exists ine_frente_ruta  text;
alter table firma_firmantes add column if not exists ine_reverso_ruta text;
alter table firma_firmantes add column if not exists geo_precision    double precision;

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table firma_firmantes add column if not exists created_at timestamptz not null default now();
create index if not exists firma_firmantes_doc_idx
  on firma_firmantes (documento_id, orden nulls first, created_at);
create index if not exists firma_firmantes_user_idx
  on firma_firmantes (user_id);
create index if not exists firma_firmantes_contacto_idx
  on firma_firmantes (contacto_id) where contacto_id is not null;

create unique index if not exists firma_firmantes_token_uniq
  on firma_firmantes (token) where token is not null;

create table if not exists firma_eventos (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid references firma_documentos(id) on delete cascade,
  firmante_id   uuid references firma_firmantes(id) on delete set null,

  tipo          text not null,
  detalle       text,
  actor         text,          -- agente | firmante | sistema
  ip            text,
  user_agent    text,
  payload       jsonb,
  created_at    timestamptz not null default now()
);

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table firma_eventos add column if not exists created_at timestamptz not null default now();
create index if not exists firma_eventos_doc_idx
  on firma_eventos (documento_id, created_at);
create index if not exists firma_eventos_user_idx
  on firma_eventos (user_id, created_at desc);

alter table firma_documentos enable row level security;
alter table firma_firmantes  enable row level security;
alter table firma_eventos    enable row level security;

drop policy if exists "dueño gestiona sus documentos" on firma_documentos;
create policy "dueño gestiona sus documentos"
  on firma_documentos for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño gestiona sus firmantes" on firma_firmantes;
create policy "dueño gestiona sus firmantes"
  on firma_firmantes for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño solo lee su bitacora" on firma_eventos;
create policy "dueño solo lee su bitacora"
  on firma_eventos for select
  using (user_id = auth.uid());

insert into storage.buckets (id, name, public)
select 'firmas', 'firmas', false
where not exists (select 1 from storage.buckets where id = 'firmas');

drop policy if exists "dueño lee sus archivos de firma" on storage.objects;
create policy "dueño lee sus archivos de firma"
  on storage.objects for select
  using (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "dueño escribe sus archivos de firma" on storage.objects;
create policy "dueño escribe sus archivos de firma"
  on storage.objects for insert
  with check (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "dueño borra sus archivos de firma" on storage.objects;
create policy "dueño borra sus archivos de firma"
  on storage.objects for delete
  using (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);

-- (migracion-firmas-campos.sql)
create table if not exists firma_campos (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid not null references firma_documentos(id) on delete cascade,
  firmante_id   uuid not null references firma_firmantes(id) on delete cascade,

  pagina        integer not null,          -- 1 = primera hoja

  tipo          text not null default 'firma',

  x             double precision not null,
  y             double precision not null,
  ancho         double precision not null,
  alto          double precision not null,

  created_at    timestamptz not null default now(),

  constraint firma_campos_pagina_ok  check (pagina >= 1),
  constraint firma_campos_x_ok       check (x >= 0 and x <= 1),
  constraint firma_campos_y_ok       check (y >= 0 and y <= 1),
  constraint firma_campos_ancho_ok   check (ancho > 0 and ancho <= 1),
  constraint firma_campos_alto_ok    check (alto  > 0 and alto  <= 1)
);

create index if not exists firma_campos_doc_idx
  on firma_campos (documento_id, pagina);
create index if not exists firma_campos_firmante_idx
  on firma_campos (firmante_id);
create index if not exists firma_campos_user_idx
  on firma_campos (user_id);

create table if not exists firma_paginas (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid not null references firma_documentos(id) on delete cascade,
  pagina        integer not null,
  ruta          text not null,
  ancho_pt      double precision,          -- tamaño real de la hoja en puntos
  alto_pt       double precision,
  created_at    timestamptz not null default now()
);

create unique index if not exists firma_paginas_uniq
  on firma_paginas (documento_id, pagina);

alter table firma_documentos
  add column if not exists campos_colocados boolean not null default false;

alter table firma_documentos
  add column if not exists rubrica_todas boolean not null default false;

alter table firma_campos  enable row level security;
alter table firma_paginas enable row level security;

drop policy if exists "dueño gestiona sus campos" on firma_campos;
create policy "dueño gestiona sus campos"
  on firma_campos for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño ve sus paginas" on firma_paginas;
create policy "dueño ve sus paginas"
  on firma_paginas for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());


-- firma_contrato_jobs: contratos.html → "mandar a firmar" encola aquí la
-- conversión del contrato a PDF (routers/firmas.py). El código la usa pero
-- nunca tuvo migración en el repo.
create table if not exists public.firma_contrato_jobs (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  tipo          text,
  estado        text not null default 'pendiente',   -- pendiente | procesando | listo | error
  documento_id  uuid,
  folio         text,
  paginas       integer,
  error         text,
  terminado_en  timestamptz,
  created_at    timestamptz not null default now()
);
-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table public.firma_contrato_jobs add column if not exists created_at timestamptz not null default now();
create index if not exists firma_contrato_jobs_user_idx on public.firma_contrato_jobs (user_id, created_at desc);
alter table public.firma_contrato_jobs enable row level security;
drop policy if exists "dueño ve sus procesos de contrato" on public.firma_contrato_jobs;
create policy "dueño ve sus procesos de contrato" on public.firma_contrato_jobs
  for select using (user_id = auth.uid());


-- ════════════════════════════════════════════════════════════════════════
-- 9. Cumplimiento (PLD): avisos a la UIF
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-pld-aviso-inm.sql)
alter table public.pld_config
  add column if not exists rfc_sujeto_obligado text,
  add column if not exists clave_entidad_colegiada text;

alter table public.pld_operaciones
  add column if not exists aviso_datos jsonb not null default '{}'::jsonb,
  add column if not exists folio_uif text,
  add column if not exists modificado_at timestamptz;

alter table public.pld_avisos
  add column if not exists formato text,
  add column if not exists descargado_at timestamptz,
  add column if not exists subido_at timestamptz,
  add column if not exists rechazado_at timestamptz,
  add column if not exists motivo_rechazo text,
  add column if not exists aviso_origen_id uuid,
  add column if not exists operacion_id uuid,
  add column if not exists descripcion_modificacion text;

do $$
declare r record;
begin
  for r in
    select conname from pg_constraint
     where conrelid = 'public.pld_avisos'::regclass and contype = 'c'
       and (pg_get_constraintdef(oid) ilike '%estatus%' or pg_get_constraintdef(oid) ilike '%tipo%')
  loop
    execute format('alter table public.pld_avisos drop constraint %I', r.conname);
  end loop;
end $$;

alter table public.pld_avisos
  add constraint pld_avisos_estatus_ciclo_check
  check (estatus in ('borrador', 'generado', 'subido', 'presentado', 'rechazado', 'descartado')) not valid;
alter table public.pld_avisos
  add constraint pld_avisos_tipo_ciclo_check
  check (tipo is null or tipo in ('normal', 'en_ceros', 'inusual_24h', 'modificatorio')) not valid;

alter table public.pld_config
  add column if not exists alertas_enviadas jsonb not null default '{}'::jsonb;



-- ════════════════════════════════════════════════════════════════════════
-- 10. WhatsApp: agenda, automatizaciones, campañas, flujos y blindaje
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-coexistencia-agenda.sql)
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_chat text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_agenda text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_wa text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS conocido boolean DEFAULT false;

CREATE TABLE IF NOT EXISTS wa2_agenda (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid,
  telefono text NOT NULL,
  nombre text,
  conocido boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS wa2_agenda_numero_tel
  ON wa2_agenda (numero_id, telefono);

ALTER TABLE wa2_agenda ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_agenda_owner ON wa2_agenda;
CREATE POLICY wa2_agenda_owner ON wa2_agenda
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

ALTER TABLE wa2_numeros ADD COLUMN IF NOT EXISTS numero_personal text;

-- (migracion-wa2-automatizaciones.sql)
CREATE TABLE IF NOT EXISTS wa2_automatizaciones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid,
  nombre text NOT NULL,
  activa boolean DEFAULT true,
  disparador text DEFAULT 'palabra',
  palabras jsonb DEFAULT '[]'::jsonb,
  acciones jsonb DEFAULT '[]'::jsonb,
  veces_usada integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table wa2_automatizaciones add column if not exists created_at timestamptz not null default now();
CREATE INDEX IF NOT EXISTS wa2_automatizaciones_user
  ON wa2_automatizaciones (user_id, created_at DESC);

ALTER TABLE wa2_automatizaciones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_automatizaciones_owner ON wa2_automatizaciones;
CREATE POLICY wa2_automatizaciones_owner ON wa2_automatizaciones
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- (migracion-wa2-campanas.sql)
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS etiquetas jsonb DEFAULT '[]'::jsonb;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS opt_out boolean DEFAULT false;

CREATE TABLE IF NOT EXISTS wa2_campanas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid NOT NULL,
  nombre text NOT NULL,
  plantilla text NOT NULL,
  idioma text DEFAULT 'es_MX',
  variables jsonb DEFAULT '[]'::jsonb,
  etiqueta text,
  estado text DEFAULT 'enviando',
  total integer DEFAULT 0,
  enviados integer DEFAULT 0,
  fallidos integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  terminado_at timestamptz
);

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table wa2_campanas add column if not exists created_at timestamptz not null default now();
CREATE INDEX IF NOT EXISTS wa2_campanas_user
  ON wa2_campanas (user_id, created_at DESC);

ALTER TABLE wa2_campanas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_campanas_owner ON wa2_campanas;
CREATE POLICY wa2_campanas_owner ON wa2_campanas
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS wa2_campana_envios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campana_id uuid NOT NULL,
  user_id uuid NOT NULL,
  contacto_id uuid,
  wa_id text,
  nombre text,
  estado text DEFAULT 'pendiente',
  error text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa2_campana_envios_campana
  ON wa2_campana_envios (campana_id);

ALTER TABLE wa2_campana_envios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_campana_envios_owner ON wa2_campana_envios;
CREATE POLICY wa2_campana_envios_owner ON wa2_campana_envios
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- (migracion-wa2-modos-flujos.sql)
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_modo text;
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_pausada_hasta timestamptz;
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_sesion_nueva boolean DEFAULT false;

UPDATE wa2_conversaciones
   SET ia_modo = CASE WHEN ai_enabled = false THEN 'off' ELSE 'auto' END
 WHERE ia_modo IS NULL;

ALTER TABLE wa2_conversaciones ALTER COLUMN ia_modo SET DEFAULT 'auto';

ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS modo_ia text DEFAULT 'siempre_encendida';
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS pausa_al_responder boolean DEFAULT true;
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS pausa_duracion_min integer DEFAULT 0;
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS nuevos_meses integer DEFAULT 3;

CREATE TABLE IF NOT EXISTS wa2_flujo_estados (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  conversacion_id uuid NOT NULL UNIQUE,
  automatizacion_id uuid NOT NULL,
  paso integer DEFAULT 0,
  datos jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa2_flujo_estados_conv
  ON wa2_flujo_estados (conversacion_id);

ALTER TABLE wa2_flujo_estados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_flujo_estados_owner ON wa2_flujo_estados;
CREATE POLICY wa2_flujo_estados_owner ON wa2_flujo_estados
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- (migracion-asesor-ctx.sql)
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS asesor_ctx jsonb;

-- (migracion-whatsapp-last-inbound.sql)
alter table wa2_conversaciones
  add column if not exists last_inbound_at timestamptz;

update wa2_conversaciones
  set last_inbound_at = last_message_at
  where last_inbound_at is null;

-- (migracion-whatsapp-no-leida.sql)
ALTER TABLE wa2_conversaciones
  ADD COLUMN IF NOT EXISTS no_leida boolean NOT NULL DEFAULT false;

ALTER TABLE wa2_conversaciones
  ADD COLUMN IF NOT EXISTS last_inbound_wamid text;

CREATE INDEX IF NOT EXISTS idx_wa2_conv_pendientes
  ON wa2_conversaciones (user_id, no_leida);

-- (migracion-whatsapp-token.sql)
alter table wa2_numeros
  add column if not exists token_valido boolean not null default true;

alter table wa2_numeros
  add column if not exists token_error_at timestamptz;

-- (migracion-whatsapp-ultimas-propiedades.sql)
alter table wa2_conversaciones
  add column if not exists ultimas_propiedades jsonb not null default '[]'::jsonb;

-- (migracion-whatsapp-zona-horaria.sql)
alter table wa2_entrenamiento
  add column if not exists zona_horaria text not null default 'America/Mexico_City';


-- migracion-whatsapp-blindaje.sql SIN el DELETE de mensajes duplicados: la
-- regla "un mensaje de Meta una sola vez" sólo se crea si no hay repetidos.
alter table public.wa2_entrenamiento add column if not exists conocimiento text;
alter table public.wa2_mensajes add column if not exists entrega_error text;
alter table public.wa2_mensajes add column if not exists media_path text;
do $$
declare n int;
begin
  select count(*) into n from (
    select wa_message_id from public.wa2_mensajes
     where wa_message_id is not null group by 1 having count(*) > 1) d;
  if n = 0 then
    create unique index if not exists wa2_mensajes_wa_message_id_uniq
      on public.wa2_mensajes (wa_message_id) where wa_message_id is not null;
  else
    raise notice 'AVISO: % mensajes de WhatsApp repetidos; no se creó la regla única (no se borró nada).', n;
  end if;
end $$;
-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table public.wa2_mensajes add column if not exists created_at timestamptz not null default now();
create index if not exists wa2_mensajes_conv_fecha_idx on public.wa2_mensajes (conversacion_id, created_at desc);
create index if not exists wa2_conversaciones_user_fecha_idx on public.wa2_conversaciones (user_id, last_message_at desc);

-- migracion-whatsapp-borrar-numero.sql SIN borrar huérfanos: las ligas
-- "al borrar un número se borra todo lo suyo" se crean NOT VALID (aplican a
-- lo nuevo y a los borrados de ahora en adelante; no revisan ni tocan lo que
-- ya existe). Si la liga ya existe, se deja como está.
do $$
declare r record;
begin
  for r in select * from (values
      ('wa2_conversaciones',  'wa2_conversaciones_numero_fk',     'numero_id',       'wa2_numeros'),
      ('wa2_mensajes',        'wa2_mensajes_conversacion_fk',     'conversacion_id', 'wa2_conversaciones'),
      ('wa2_contactos',       'wa2_contactos_numero_fk',          'numero_id',       'wa2_numeros'),
      ('wa2_agenda',          'wa2_agenda_numero_fk',             'numero_id',       'wa2_numeros'),
      ('wa2_entrenamiento',   'wa2_entrenamiento_numero_fk',      'numero_id',       'wa2_numeros'),
      ('wa2_campanas',        'wa2_campanas_numero_fk',           'numero_id',       'wa2_numeros'),
      ('wa2_automatizaciones','wa2_automatizaciones_numero_fk',   'numero_id',       'wa2_numeros')
    ) as v(tabla, nombre, columna, destino)
  loop
    if to_regclass('public.' || r.tabla) is null or to_regclass('public.' || r.destino) is null then continue; end if;
    if not exists (select 1 from information_schema.columns
                    where table_schema = 'public' and table_name = r.tabla and column_name = r.columna) then continue; end if;
    if exists (select 1 from pg_constraint where conname = r.nombre and conrelid = ('public.' || r.tabla)::regclass) then continue; end if;
    execute format('alter table public.%I add constraint %I foreign key (%I) references public.%I(id) on delete cascade not valid',
                   r.tabla, r.nombre, r.columna, r.destino);
  end loop;
end $$;


-- ════════════════════════════════════════════════════════════════════════
-- 11. Generador de video y archivos (buckets que el código usa)
-- ════════════════════════════════════════════════════════════════════════
-- video_jobs: video.html → "generar video del inmueble" (routers/video.py).
-- El código la usa pero nunca tuvo migración en el repo.
create table if not exists public.video_jobs (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  propiedad_id  uuid,
  formato       text,                 -- 9:16 | 16:9
  estado        text not null default 'pendiente',   -- pendiente | procesando | listo | error
  fotos         text[] not null default '{}'::text[],
  titulo        text,
  video_url     text,
  duracion_seg  numeric,
  error         text,
  terminado_en  timestamptz,
  creado_en     timestamptz not null default now()
);
create index if not exists video_jobs_user_idx on public.video_jobs (user_id, creado_en desc);
create index if not exists video_jobs_propiedad_idx on public.video_jobs (propiedad_id) where propiedad_id is not null;
alter table public.video_jobs enable row level security;
drop policy if exists "dueño ve sus videos" on public.video_jobs;
create policy "dueño ve sus videos" on public.video_jobs for select using (user_id = auth.uid());

-- Buckets que usa el código. Sólo se crean si faltan; si ya existen no se
-- cambia nada de ellos. (El backend entra con la llave de servicio.)
insert into storage.buckets (id, name, public)
select v.id, v.id, v.publico
  from (values ('videos-fichas', true), ('wa-media', true),
               ('machotes-contrato', false), ('pld-expedientes', false)) as v(id, publico)
 where not exists (select 1 from storage.buckets b where b.id = v.id);


-- ════════════════════════════════════════════════════════════════════════
-- 12. Fase 1 — inventario (ya corrida; se repite sin efecto)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-fase1-inventario.sql)
alter table public.propiedades
  add column if not exists subtipo text,
  add column if not exists operaciones jsonb not null default '[]'::jsonb,
  add column if not exists precio_unidad text not null default 'total',
  add column if not exists mantenimiento_incluido text not null default 'no_indicado',
  add column if not exists antiguedad integer,
  add column if not exists condicion text,
  add column if not exists disposicion text,
  add column if not exists orientacion text,
  add column if not exists pisos_edificio integer,
  add column if not exists caracteristicas text[] not null default '{}'::text[],
  add column if not exists otras_caracteristicas text,
  add column if not exists lat double precision,
  add column if not exists lng double precision,
  add column if not exists fecha_cierre timestamptz;

create index if not exists idx_propiedades_caracteristicas on public.propiedades using gin (caracteristicas);
create index if not exists idx_propiedades_operaciones on public.propiedades using gin (operaciones);

update public.propiedades set subtipo = tipo
 where subtipo is null and tipo in ('casa','departamento','terreno','local','oficina','bodega');

update public.propiedades
   set operaciones = jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
         'tipo', operacion,
         'precio', precio,
         'moneda', coalesce(nullif(moneda, ''), 'MXN'),
         'unidad', 'total')))
 where operaciones = '[]'::jsonb
   and operacion in ('venta', 'renta');

create or replace function public.bk_normaliza(t text)
returns text language sql immutable as $$
  select btrim(regexp_replace(
           lower(translate(coalesce(t, ''), 'áéíóúüñÁÉÍÓÚÜÑàèìòùÀÈÌÒÙ', 'aeiouunaeiouunaeiouaeiou')),
           '[^a-z0-9]+', ' ', 'g'))
$$;

create temporary table _bk_alias(nombre text primary key, clave text) on commit drop;
insert into _bk_alias(nombre, clave) values
  ('a c', 'aire_acondicionado'),
  ('accesibilidad', 'rampas'),
  ('acceso a la playa', 'acceso_playa'),
  ('acceso controlado', 'acceso_controlado'),
  ('acceso playa', 'acceso_playa'),
  ('aire acondicionado', 'aire_acondicionado'),
  ('alberca', 'alberca'),
  ('amueblada', 'amueblado'),
  ('amueblado', 'amueblado'),
  ('anden', 'anden'),
  ('area comun', 'area_comun'),
  ('area de asador', 'asador'),
  ('area de juegos infantiles', 'juegos_infantiles'),
  ('area de lavado', 'lavanderia'),
  ('area infantil', 'juegos_infantiles'),
  ('area para mascotas', 'pet_friendly_area'),
  ('areas comunes', 'area_comun'),
  ('areas verdes', 'area_comun'),
  ('asador', 'asador'),
  ('ascensor', 'elevador'),
  ('azotea', 'roof_garden'),
  ('balcon', 'balcon'),
  ('banjercito', 'fin_issfam'),
  ('bbq', 'asador'),
  ('bodega', 'bodega_interna'),
  ('bodega cuarto de guardado', 'bodega_interna'),
  ('bodega interna', 'bodega_interna'),
  ('business center', 'business_center'),
  ('calefaccion', 'calefaccion'),
  ('calentador solar', 'panel_solar'),
  ('campo de golf', 'golf'),
  ('cancha basquetbol', 'cancha_basquetbol'),
  ('cancha de basquetbol', 'cancha_basquetbol'),
  ('cancha de futbol', 'cancha_futbol'),
  ('cancha de padel', 'padel'),
  ('cancha de tenis', 'tenis'),
  ('cancha futbol', 'cancha_futbol'),
  ('casa club', 'casa_club'),
  ('caseta de vigilancia', 'acceso_controlado'),
  ('centro de negocios', 'business_center'),
  ('chimenea', 'chimenea'),
  ('cine', 'cine'),
  ('cisterna', 'cisterna'),
  ('clima', 'aire_acondicionado'),
  ('closets', 'closets'),
  ('club house', 'casa_club'),
  ('cochera techada', 'estacionamiento_techado'),
  ('cocina equipada', 'cocina_integral'),
  ('cocina integral', 'cocina_integral'),
  ('cofinavit', 'fin_infonavit'),
  ('conserje', 'portero'),
  ('control de acceso', 'acceso_controlado'),
  ('coto privado', 'fraccionamiento_privado'),
  ('credito bancario', 'fin_bancario'),
  ('credito hipotecario', 'fin_bancario'),
  ('creditos bancarios', 'fin_bancario'),
  ('cuarto de lavado', 'lavanderia'),
  ('cuarto de servicio', 'cuarto_servicio'),
  ('cuarto servicio', 'cuarto_servicio'),
  ('dos plantas', 'dos_plantas'),
  ('elevador', 'elevador'),
  ('estacionamiento de visitas', 'estacionamiento_visitas'),
  ('estacionamiento techado', 'estacionamiento_techado'),
  ('estacionamiento visitas', 'estacionamiento_visitas'),
  ('estudio', 'estudio'),
  ('facil estacionarse', 'facil_estacionarse'),
  ('facilidad para estacionarse', 'facil_estacionarse'),
  ('fibra optica', 'internet'),
  ('fin bancario', 'fin_bancario'),
  ('fin fovissste', 'fin_fovissste'),
  ('fin infonavit', 'fin_infonavit'),
  ('fin issfam', 'fin_issfam'),
  ('fin pemex', 'fin_pemex'),
  ('fogatero', 'fogatero'),
  ('fovissste', 'fin_fovissste'),
  ('fovisste', 'fin_fovissste'),
  ('fraccionamiento privado', 'fraccionamiento_privado'),
  ('frente a la playa', 'frente_playa'),
  ('frente agua', 'frente_agua'),
  ('frente al agua', 'frente_agua'),
  ('frente playa', 'frente_playa'),
  ('fumar no', 'fumar_no'),
  ('fumar si', 'fumar_si'),
  ('gas estacionario', 'gas_estacionario'),
  ('gas natural', 'gas_estacionario'),
  ('gimnasio', 'gimnasio'),
  ('golf', 'golf'),
  ('gym', 'gimnasio'),
  ('hidroneumatico', 'hidroneumatico'),
  ('infonavit', 'fin_infonavit'),
  ('infonavit cofinavit', 'fin_infonavit'),
  ('internet', 'internet'),
  ('internet fibra optica', 'internet'),
  ('issfam', 'fin_issfam'),
  ('issfam banjercito', 'fin_issfam'),
  ('jacuzzi', 'jacuzzi'),
  ('jardin', 'jardin'),
  ('juegos infantiles', 'juegos_infantiles'),
  ('lavanderia', 'lavanderia'),
  ('ludoteca', 'ludoteca'),
  ('mascotas no', 'mascotas_no'),
  ('mascotas permitidas', 'mascotas_si'),
  ('mascotas si', 'mascotas_si'),
  ('minisplit', 'aire_acondicionado'),
  ('no se aceptan mascotas', 'mascotas_no'),
  ('oficina', 'oficina'),
  ('padel', 'padel'),
  ('panel solar', 'panel_solar'),
  ('paneles solares', 'panel_solar'),
  ('patio', 'patio'),
  ('pemex', 'fin_pemex'),
  ('penthouse', 'penthouse'),
  ('permitido fumar', 'fumar_si'),
  ('pet friendly', 'mascotas_si'),
  ('pet friendly area', 'pet_friendly_area'),
  ('pet park', 'pet_friendly_area'),
  ('piscina', 'alberca'),
  ('planta baja', 'planta_baja'),
  ('planta electrica', 'planta_electrica'),
  ('portero', 'portero'),
  ('privada', 'fraccionamiento_privado'),
  ('prohibido fumar', 'fumar_no'),
  ('rampas', 'rampas'),
  ('recamara en planta baja', 'recamara_planta_baja'),
  ('recamara planta baja', 'recamara_planta_baja'),
  ('roof garden', 'roof_garden'),
  ('roofgarden', 'roof_garden'),
  ('sala de cine', 'cine'),
  ('salon de eventos', 'salon_usos_multiples'),
  ('salon de usos multiples', 'salon_usos_multiples'),
  ('salon usos multiples', 'salon_usos_multiples'),
  ('sauna', 'sauna'),
  ('se aceptan mascotas', 'mascotas_si'),
  ('seguridad', 'seguridad_24h'),
  ('seguridad 12 horas', 'seguridad_12h'),
  ('seguridad 12h', 'seguridad_12h'),
  ('seguridad 24 horas', 'seguridad_24h'),
  ('seguridad 24h', 'seguridad_24h'),
  ('sum', 'salon_usos_multiples'),
  ('tenis', 'tenis'),
  ('terraza', 'terraza'),
  ('una planta', 'una_planta'),
  ('una sola planta', 'una_planta'),
  ('vapor', 'sauna'),
  ('vestidor', 'vestidor'),
  ('vigilancia 24 horas', 'seguridad_24h'),
  ('vigilancia 24h', 'seguridad_24h'),
  ('vista agua', 'vista_agua'),
  ('vista al agua', 'vista_agua'),
  ('vista al mar', 'vista_mar'),
  ('vista mar', 'vista_mar'),
  ('vista panoramica', 'vista_panoramica'),
  ('wifi', 'internet')
on conflict do nothing;

with fuente as (
  select p.id, a.txt
    from public.propiedades p,
         lateral unnest(coalesce(p.amenidades, '{}'::text[])) as a(txt)
   where coalesce(array_length(p.caracteristicas, 1), 0) = 0
     and coalesce(array_length(p.amenidades, 1), 0) > 0
), clasif as (
  select f.id, f.txt, al.clave
    from fuente f
    left join _bk_alias al on al.nombre = public.bk_normaliza(f.txt)
), agrupado as (
  select id,
         array_remove(array_agg(distinct clave), null) as claves,
         string_agg(distinct btrim(txt), ', ') filter (where clave is null and btrim(txt) <> '') as otras
    from clasif
   group by id
)
update public.propiedades p
   set caracteristicas = coalesce(a.claves, '{}'::text[]),
       otras_caracteristicas = coalesce(p.otras_caracteristicas, a.otras)
  from agrupado a
 where p.id = a.id;

do $vista$
begin
  if not exists (select 1 from pg_views where schemaname = 'public' and viewname = 'propiedades_publicas_extra') then
    execute $sql$
create view public.propiedades_publicas_extra as
select p.id, p.subtipo,
       case when coalesce(p.mostrar_precio, true) then p.operaciones
            else coalesce((select jsonb_agg(o - 'precio') from jsonb_array_elements(p.operaciones) o), '[]'::jsonb)
       end as operaciones,
       coalesce(p.mostrar_precio, true) as mostrar_precio,
       p.precio_unidad, p.mantenimiento_incluido,
       p.antiguedad, p.condicion, p.disposicion, p.orientacion,
       p.pisos_edificio, p.caracteristicas, p.otras_caracteristicas,
       case when p.mostrar_ubicacion_exacta then p.lat end as lat,
       case when p.mostrar_ubicacion_exacta then p.lng end as lng
  from public.propiedades p
 where p.id in (select id from public.propiedades_publicas)
    $sql$;
  end if;
end $vista$;

grant select on public.propiedades_publicas_extra to anon, authenticated;



-- ════════════════════════════════════════════════════════════════════════
-- 13. Fase 2 — multimedia (ya corrida; se repite sin efecto)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-fase2-multimedia.sql)
alter table public.propiedades
  add column if not exists videos text[] not null default '{}'::text[],
  add column if not exists tours text[] not null default '{}'::text[],
  add column if not exists documentos jsonb not null default '[]'::jsonb;

alter table public.propiedades drop constraint if exists propiedades_documentos_es_arreglo;
alter table public.propiedades
  add constraint propiedades_documentos_es_arreglo check (jsonb_typeof(documentos) = 'array');

insert into storage.buckets (id, name, public)
select 'documentos-publicos', 'documentos-publicos', true
where not exists (select 1 from storage.buckets where id = 'documentos-publicos');

drop policy if exists "lectura publica de documentos de inmuebles" on storage.objects;
create policy "lectura publica de documentos de inmuebles"
  on storage.objects for select
  using (bucket_id = 'documentos-publicos');

drop policy if exists "usuarios autenticados suben documentos de inmuebles" on storage.objects;
create policy "usuarios autenticados suben documentos de inmuebles"
  on storage.objects for insert
  with check (bucket_id = 'documentos-publicos' and auth.role() = 'authenticated');

drop policy if exists "dueno borra sus documentos de inmuebles" on storage.objects;
create policy "dueno borra sus documentos de inmuebles"
  on storage.objects for delete
  using (bucket_id = 'documentos-publicos' and owner = auth.uid());

create or replace view public.propiedades_publicas_extra as
select p.id, p.subtipo,
       case when coalesce(p.mostrar_precio, true) then p.operaciones
            else coalesce((select jsonb_agg(o - 'precio') from jsonb_array_elements(p.operaciones) o), '[]'::jsonb)
       end as operaciones,
       coalesce(p.mostrar_precio, true) as mostrar_precio,
       p.precio_unidad, p.mantenimiento_incluido,
       p.antiguedad, p.condicion, p.disposicion, p.orientacion,
       p.pisos_edificio, p.caracteristicas, p.otras_caracteristicas,
       case when p.mostrar_ubicacion_exacta then p.lat end as lat,
       case when p.mostrar_ubicacion_exacta then p.lng end as lng,
       p.videos, p.tours, p.documentos
  from public.propiedades p
 where p.id in (select id from public.propiedades_publicas);

grant select on public.propiedades_publicas_extra to anon, authenticated;



-- ════════════════════════════════════════════════════════════════════════
-- 14. Fase 3 — contactos y pipeline (tolera las tablas viejas)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-fase3-contactos.sql)
do $$
declare r record;
begin
  for r in
    select c.relname as tabla, a.attname as columna
      from pg_attribute a
      join pg_class c on c.oid = a.attrelid
      join pg_namespace n on n.oid = c.relnamespace
      join (values
        ('pipeline_etapas',   array['id', 'nombre']),
        ('contacto_tipos',    array['id', 'org_id', 'clave', 'nombre']),
        ('fuentes_captacion', array['id', 'org_id', 'nombre', 'nombre_norm'])
      ) as t(tabla, nuestras) on t.tabla = c.relname
     where n.nspname = 'public' and a.attnum > 0 and not a.attisdropped
       and a.attnotnull and not a.atthasdef
       and a.attname <> all (t.nuestras)
       and not exists (select 1 from pg_index i
                        where i.indrelid = c.oid and i.indisprimary and a.attnum = any (i.indkey))
  loop
    execute format('alter table public.%I alter column %I drop not null', r.tabla, r.columna);
    raise notice '%.%: se quitó NOT NULL (columna vieja que Broquer ya no llena)', r.tabla, r.columna;
  end loop;
end $$;

create table if not exists public.pipeline_etapas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  nombre text not null,
  orden integer default 0,
  color text,
  created_at timestamptz default now()
);
alter table public.pipeline_etapas
  add column if not exists user_id uuid,
  add column if not exists nombre text,
  add column if not exists orden integer default 0,
  add column if not exists color text,
  add column if not exists created_at timestamptz default now(),
  add column if not exists org_id uuid,
  add column if not exists clave text,
  add column if not exists es_sistema boolean not null default false;
alter table public.pipeline_etapas alter column user_id drop not null;

update public.pipeline_etapas set clave = lower(btrim(nombre)) where clave is null;
update public.pipeline_etapas e
   set org_id = om.org_id
  from public.organizacion_miembros om
 where e.org_id is null and e.user_id is not null
   and om.user_id = e.user_id and om.activo = true;

insert into public.pipeline_etapas (org_id, clave, nombre, orden, color, es_sistema)
select o.id, d.clave, d.nombre, d.orden, d.color, true
  from public.organizaciones o
  cross join (values
    ('futuro',     'Futuro',      10, 'var(--etapa-futuro)'),
    ('nuevo',      'Nuevo',       20, 'var(--etapa-nuevo)'),
    ('activo',     'Activo',      30, 'var(--etapa-activo)'),
    ('contactado', 'Contactado',  40, 'var(--etapa-contactado)'),
    ('cerrado',    'Cerrado',     50, 'var(--etapa-cerrado)'),
    ('descartado', 'Descartado',  60, 'var(--etapa-descartado)')
  ) as d(clave, nombre, orden, color)
 where not exists (select 1 from public.pipeline_etapas e where e.org_id = o.id);

insert into public.pipeline_etapas (org_id, clave, nombre, orden, color, es_sistema)
select o.id, 'spam', 'Basura/Spam',
       coalesce((select max(orden) from public.pipeline_etapas e where e.org_id = o.id), 0) + 10,
       'var(--mute-2)', true
  from public.organizaciones o
 where not exists (select 1 from public.pipeline_etapas e where e.org_id = o.id and e.clave = 'spam');

create index if not exists idx_pipeline_etapas_org on public.pipeline_etapas (org_id, orden);

alter table public.pipeline_etapas enable row level security;
drop policy if exists "equipo ve etapas de su organizacion" on public.pipeline_etapas;
create policy "equipo ve etapas de su organizacion"
  on public.pipeline_etapas for select
  using (org_id in (select public.mis_org_ids()) or user_id = auth.uid());

create table if not exists public.contacto_tipos (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  clave text not null,
  nombre text not null,
  orden integer not null default 0,
  es_sistema boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index if not exists contacto_tipos_org_clave on public.contacto_tipos (org_id, clave);

insert into public.contacto_tipos (org_id, clave, nombre, orden, es_sistema)
select o.id, d.clave, d.nombre, d.orden, true
  from public.organizaciones o
  cross join (values
    ('arrendador',         'Propietario / Arrendador',  10),
    ('arrendatario',       'Inquilino / Arrendatario',  20),
    ('comprador',          'Comprador',                 30),
    ('vendedor',           'Vendedor',                  40),
    ('obligado_solidario', 'Obligado solidario',        50),
    ('colega',             'Colega / Agente',           60),
    ('notario',            'Notario',                   70),
    ('valuador',           'Valuador',                  80),
    ('juridico',           'Jurídico',                  90),
    ('agente_externo',     'Agente externo',           100),
    ('otro',               'Otro',                     110)
  ) as d(clave, nombre, orden)
on conflict (org_id, clave) do nothing;

alter table public.contacto_tipos enable row level security;
drop policy if exists "equipo ve tipos de su organizacion" on public.contacto_tipos;
create policy "equipo ve tipos de su organizacion"
  on public.contacto_tipos for select
  using (org_id in (select public.mis_org_ids()));

create table if not exists public.fuentes_captacion (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nombre text not null,
  nombre_norm text not null,
  created_at timestamptz not null default now()
);
alter table public.fuentes_captacion
  add column if not exists org_id uuid,
  add column if not exists nombre text,
  add column if not exists nombre_norm text,
  add column if not exists created_at timestamptz not null default now();
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'fuentes_captacion' and column_name = 'user_id') then
    alter table public.fuentes_captacion alter column user_id drop not null;
    update public.fuentes_captacion f
       set org_id = om.org_id
      from public.organizacion_miembros om
     where f.org_id is null and om.user_id = f.user_id and om.activo = true;
  end if;
end $$;
update public.fuentes_captacion set nombre_norm = public.bk_normaliza(nombre)
 where nombre_norm is null and nombre is not null;
create unique index if not exists fuentes_captacion_org_norm on public.fuentes_captacion (org_id, nombre_norm);

alter table public.contactos
  add column if not exists fuente_id uuid,
  add column if not exists telefonos jsonb not null default '[]'::jsonb,
  add column if not exists correos jsonb not null default '[]'::jsonb,
  add column if not exists puesto text,
  add column if not exists redes jsonb not null default '{}'::jsonb,
  add column if not exists etapa_cambiada_en timestamptz;

insert into public.fuentes_captacion (org_id, nombre, nombre_norm)
select org_id, nombre, norm
  from (
    select c.org_id, btrim(c.fuente) as nombre, public.bk_normaliza(c.fuente) as norm,
           row_number() over (partition by c.org_id, public.bk_normaliza(c.fuente)
                              order by count(*) desc, btrim(c.fuente)) as rn
      from public.contactos c
     where c.org_id is not null and coalesce(btrim(c.fuente), '') <> ''
     group by c.org_id, btrim(c.fuente), public.bk_normaliza(c.fuente)
  ) v
 where rn = 1 and norm <> ''
on conflict (org_id, nombre_norm) do nothing;

insert into public.fuentes_captacion (org_id, nombre, nombre_norm)
select o.id, d.nombre, public.bk_normaliza(d.nombre)
  from public.organizaciones o
  cross join (values ('Facebook'), ('Instagram'), ('WhatsApp'), ('Referido'),
                     ('Portal inmobiliario'), ('Sitio web'), ('Llamada directa'),
                     ('Bolsa Broquer'), ('EasyBroker')) as d(nombre)
on conflict (org_id, nombre_norm) do nothing;

update public.contactos c
   set fuente_id = f.id,
       fuente = f.nombre
  from public.fuentes_captacion f
 where c.fuente_id is null
   and c.org_id = f.org_id
   and coalesce(btrim(c.fuente), '') <> ''
   and public.bk_normaliza(c.fuente) = f.nombre_norm;

alter table public.fuentes_captacion enable row level security;
drop policy if exists "equipo ve fuentes de su organizacion" on public.fuentes_captacion;
create policy "equipo ve fuentes de su organizacion"
  on public.fuentes_captacion for select
  using (org_id in (select public.mis_org_ids()));

create or replace function public.bk_contacto_etapa_cambiada()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' or new.estatus is distinct from old.estatus then
    new.etapa_cambiada_en := now();
  end if;
  return new;
end $$;
drop trigger if exists trg_contacto_etapa_cambiada on public.contactos;
create trigger trg_contacto_etapa_cambiada
  before insert or update of estatus on public.contactos
  for each row execute function public.bk_contacto_etapa_cambiada();

create or replace function public.bk_filas_de_org(p_tabla text, p_org uuid)
returns text language sql immutable as $$
  select format(
    '(org_id = %L or (org_id is null and user_id in (select user_id from public.organizacion_miembros where org_id = %L and activo)))',
    p_org, p_org)
$$;

create or replace function public.bk_etiquetas_conteo(p_tabla text, p_org uuid)
returns table(etiqueta text, n bigint)
language plpgsql stable security definer set search_path = public as $$
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  return query execute format(
    'select t, count(*) from public.%I, unnest(coalesce(etiquetas, ''{}''::text[])) as t where %s group by t order by t',
    p_tabla, public.bk_filas_de_org(p_tabla, p_org));
end $$;

create or replace function public.bk_etiqueta_renombrar(p_tabla text, p_org uuid, p_de text, p_a text)
returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  if coalesce(btrim(p_a), '') = '' then raise exception 'nombre vacío'; end if;
  execute format(
    'update public.%I set etiquetas = (select array_agg(distinct x order by x) from unnest(array_replace(etiquetas, %L, %L)) as x)
      where %L = any(etiquetas) and %s',
    p_tabla, p_de, btrim(p_a), p_de, public.bk_filas_de_org(p_tabla, p_org));
  get diagnostics n = row_count;
  return n;
end $$;

create or replace function public.bk_etiqueta_eliminar(p_tabla text, p_org uuid, p_etiqueta text)
returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  execute format(
    'update public.%I set etiquetas = array_remove(etiquetas, %L) where %L = any(etiquetas) and %s',
    p_tabla, p_etiqueta, p_etiqueta, public.bk_filas_de_org(p_tabla, p_org));
  get diagnostics n = row_count;
  return n;
end $$;

revoke all on function public.bk_etiquetas_conteo(text, uuid) from public, anon, authenticated;
revoke all on function public.bk_etiqueta_renombrar(text, uuid, text, text) from public, anon, authenticated;
revoke all on function public.bk_etiqueta_eliminar(text, uuid, text) from public, anon, authenticated;



-- ════════════════════════════════════════════════════════════════════════
-- 15. Fase 4 — Buzón (tolera respuestas_guardadas vieja)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-fase4-buzon.sql)
do $$
declare r record;
begin
  for r in
    select c.relname as tabla, a.attname as columna
      from pg_attribute a
      join pg_class c on c.oid = a.attrelid
      join pg_namespace n on n.oid = c.relnamespace
      join (values
        ('buzon_leads',          array['id', 'org_id', 'canal']),
        ('respuestas_guardadas', array['id', 'org_id', 'titulo', 'texto']),
        ('buzon_reglas',         array['org_id']),
        ('buzon_guardias',       array['id', 'org_id', 'user_id', 'dia', 'hora_inicio', 'hora_fin'])
      ) as t(tabla, nuestras) on t.tabla = c.relname
     where n.nspname = 'public' and a.attnum > 0 and not a.attisdropped
       and a.attnotnull and not a.atthasdef
       and a.attname <> all (t.nuestras)
       and not exists (select 1 from pg_index i
                        where i.indrelid = c.oid and i.indisprimary and a.attnum = any (i.indkey))
  loop
    execute format('alter table public.%I alter column %I drop not null', r.tabla, r.columna);
    raise notice '%.%: se quitó NOT NULL (columna vieja que Broquer ya no llena)', r.tabla, r.columna;
  end loop;
end $$;

create table if not exists public.buzon_leads (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  user_id uuid,                    -- cuenta dueña (la del número/sitio/inventario)
  canal text not null,
  estado text not null default 'sin_atender',
  contacto_id text,
  propiedad_id uuid,
  fuente_id uuid,
  fuente text,
  nombre text,
  telefono text,
  email text,
  mensaje text,
  referencia text,                 -- id externo: conversación de WhatsApp, lead de Zapier…
  asignado_a uuid,
  asignado_en timestamptz,
  atendido_en timestamptz,
  primera_respuesta_en timestamptz,
  nota_interna text,
  datos jsonb not null default '{}'::jsonb,
  ultimo_mensaje_en timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.buzon_leads drop constraint if exists buzon_leads_estado_valido;
alter table public.buzon_leads add constraint buzon_leads_estado_valido
  check (estado in ('sin_atender', 'atendida', 'archivada', 'spam'));
create index if not exists idx_buzon_org_estado on public.buzon_leads (org_id, estado, ultimo_mensaje_en desc);
create index if not exists idx_buzon_asignado on public.buzon_leads (org_id, asignado_a);
create index if not exists idx_buzon_contacto on public.buzon_leads (contacto_id);
create unique index if not exists buzon_leads_referencia_uniq
  on public.buzon_leads (org_id, canal, referencia) where referencia is not null;

alter table public.buzon_leads enable row level security;
drop policy if exists "equipo ve el buzon de su organizacion" on public.buzon_leads;
create policy "equipo ve el buzon de su organizacion"
  on public.buzon_leads for select
  using (
    org_id in (select public.mis_org_ids())
    and (asignado_a = auth.uid() or asignado_a is null
         or public.org_permiso('ver_contactos_equipo'))
  );

create table if not exists public.respuestas_guardadas (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  titulo text not null,
  texto text not null,
  canal text not null default 'todos',      -- todos | whatsapp | correo
  creado_por uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.respuestas_guardadas
  add column if not exists org_id uuid,
  add column if not exists titulo text,
  add column if not exists texto text,
  add column if not exists canal text not null default 'todos',
  add column if not exists creado_por uuid,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'respuestas_guardadas' and column_name = 'contenido') then
    update public.respuestas_guardadas set texto = contenido where texto is null and contenido is not null;
  end if;
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'respuestas_guardadas' and column_name = 'user_id') then
    update public.respuestas_guardadas r
       set org_id = om.org_id, creado_por = coalesce(r.creado_por, r.user_id)
      from public.organizacion_miembros om
     where r.org_id is null and om.user_id = r.user_id and om.activo = true;
  end if;
end $$;
create index if not exists idx_respuestas_org on public.respuestas_guardadas (org_id, titulo);
alter table public.respuestas_guardadas enable row level security;
drop policy if exists "equipo ve respuestas de su organizacion" on public.respuestas_guardadas;
create policy "equipo ve respuestas de su organizacion"
  on public.respuestas_guardadas for select
  using (org_id in (select public.mis_org_ids()));

create table if not exists public.buzon_reglas (
  org_id uuid primary key,
  modo text not null default 'manual',      -- manual | agente_inmueble | ruleta | guardias
  ruleta_usuarios uuid[] not null default '{}'::uuid[],
  ruleta_ultimo integer not null default -1,
  token_entrada text,
  zona_horaria text not null default 'America/Mexico_City',
  updated_at timestamptz not null default now()
);
alter table public.buzon_reglas drop constraint if exists buzon_reglas_modo_valido;
alter table public.buzon_reglas add constraint buzon_reglas_modo_valido
  check (modo in ('manual', 'agente_inmueble', 'ruleta', 'guardias'));
alter table public.buzon_reglas enable row level security;

create table if not exists public.buzon_guardias (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  user_id uuid not null,
  dia smallint not null check (dia between 0 and 6),   -- 0 = domingo
  hora_inicio time not null,
  hora_fin time not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_guardias_org on public.buzon_guardias (org_id, dia);
alter table public.buzon_guardias enable row level security;
drop policy if exists "equipo ve guardias de su organizacion" on public.buzon_guardias;
create policy "equipo ve guardias de su organizacion"
  on public.buzon_guardias for select
  using (org_id in (select public.mis_org_ids()));

-- Tablas viejas pueden no tener created_at; el índice/la función lo usa.
alter table public.contactos add column if not exists created_at timestamptz not null default now();
create or replace function public.bk_buscar_contacto(p_org uuid, p_tel10 text, p_email text)
returns text
language sql stable security definer set search_path = public as $$
  select c.id
    from public.contactos c
   where (c.org_id = p_org
          or (c.org_id is null and c.user_id in (select user_id from public.organizacion_miembros where org_id = p_org and activo)))
     and (
       (coalesce(p_tel10, '') <> '' and (
          right(regexp_replace(coalesce(c.telefono, ''), '\D', '', 'g'), 10) = p_tel10
       or right(regexp_replace(coalesce(c.wa, ''), '\D', '', 'g'), 10) = p_tel10
       or exists (select 1 from jsonb_array_elements(coalesce(c.telefonos, '[]'::jsonb)) t
                   where right(regexp_replace(coalesce(t->>'numero', ''), '\D', '', 'g'), 10) = p_tel10)))
       or (coalesce(p_email, '') <> '' and (
          lower(c.email) = lower(p_email)
       or exists (select 1 from jsonb_array_elements(coalesce(c.correos, '[]'::jsonb)) m
                   where lower(m->>'correo') = lower(p_email))))
     )
   order by c.created_at asc nulls last
   limit 1
$$;
revoke all on function public.bk_buscar_contacto(uuid, text, text) from public, anon, authenticated;

insert into public.buzon_reglas (org_id, modo)
select id, 'manual' from public.organizaciones
on conflict (org_id) do nothing;



-- ════════════════════════════════════════════════════════════════════════
-- 16. Fase 5 — alertas de búsqueda (incluye las tablas del buscador)
-- ════════════════════════════════════════════════════════════════════════
-- (migracion-fase5-alertas.sql)
create table if not exists public.requerimientos_busqueda (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null,
  contacto_id         text not null,
  activo              boolean not null default true,
  operacion           text not null default 'venta',
  tipo_inmueble       text not null default 'casa',
  colonia             text,
  ciudad              text,
  estado              text,
  precio_min          numeric,
  precio_max          numeric,
  recamaras_min       integer,
  notas               text,
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now(),
  ultima_busqueda_en  timestamptz,
  unique (contacto_id)
);
create index if not exists requerimientos_busqueda_user_idx on public.requerimientos_busqueda (user_id);
create index if not exists requerimientos_busqueda_pendientes_idx on public.requerimientos_busqueda (activo, ultima_busqueda_en);
create table if not exists public.busqueda_resultados (
  id                  uuid primary key default gen_random_uuid(),
  requerimiento_id    uuid not null,
  user_id             uuid not null,
  contacto_id         text not null,
  titulo              text,
  url                 text not null,
  portal              text,
  precio              numeric,
  precio_confirmado   boolean not null default false,
  snippet             text,
  encontrado_en       timestamptz not null default now()
);
create index if not exists busqueda_resultados_requerimiento_idx on public.busqueda_resultados (requerimiento_id);
create index if not exists busqueda_resultados_contacto_idx on public.busqueda_resultados (contacto_id);
alter table public.requerimientos_busqueda enable row level security;
alter table public.busqueda_resultados enable row level security;

do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'requerimientos_busqueda'
                and column_name = 'contacto_id' and data_type = 'uuid') then
    alter table public.requerimientos_busqueda alter column contacto_id type text using contacto_id::text;
  end if;
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'busqueda_resultados'
                and column_name = 'contacto_id' and data_type = 'uuid') then
    alter table public.busqueda_resultados alter column contacto_id type text using contacto_id::text;
  end if;
end $$;

alter table public.requerimientos_busqueda
  add column if not exists org_id uuid,
  add column if not exists operaciones text[] not null default '{}'::text[],
  add column if not exists tipos text[] not null default '{}'::text[],
  add column if not exists zonas text[] not null default '{}'::text[],
  add column if not exists moneda text not null default 'MXN',
  add column if not exists banos_min numeric,
  add column if not exists estacionamientos_min integer,
  add column if not exists m2_construccion_min numeric,
  add column if not exists m2_construccion_max numeric,
  add column if not exists m2_terreno_min numeric,
  add column if not exists m2_terreno_max numeric,
  add column if not exists caracteristicas text[] not null default '{}'::text[],
  add column if not exists solo_comision_compartida boolean not null default false,
  add column if not exists ultima_alerta_en timestamptz;

update public.requerimientos_busqueda r
   set org_id = om.org_id
  from public.organizacion_miembros om
 where r.org_id is null and om.user_id = r.user_id and om.activo = true;
update public.requerimientos_busqueda
   set operaciones = array[operacion]
 where coalesce(array_length(operaciones, 1), 0) = 0 and operacion is not null;
update public.requerimientos_busqueda
   set tipos = array[tipo_inmueble]
 where coalesce(array_length(tipos, 1), 0) = 0 and tipo_inmueble is not null;
update public.requerimientos_busqueda
   set zonas = array_remove(array[nullif(btrim(colonia), ''), nullif(btrim(ciudad), '')], null)
 where coalesce(array_length(zonas, 1), 0) = 0 and (colonia is not null or ciudad is not null);

create index if not exists idx_req_org on public.requerimientos_busqueda (org_id, activo);

create table if not exists public.alertas_enviadas (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  requerimiento_id uuid not null,
  contacto_id text not null,
  propiedad_id uuid not null,
  origen text not null default 'propio',       -- propio | equipo | bolsa
  estado text not null default 'pendiente',    -- pendiente | enviada | descartada
  canal text,                                  -- whatsapp | correo
  detectada_en timestamptz not null default now(),
  enviada_en timestamptz,
  enviada_por uuid
);
create unique index if not exists alertas_req_prop_uniq on public.alertas_enviadas (requerimiento_id, propiedad_id);
create index if not exists idx_alertas_org on public.alertas_enviadas (org_id, estado);
alter table public.alertas_enviadas enable row level security;
drop policy if exists "equipo ve alertas de su organizacion" on public.alertas_enviadas;
create policy "equipo ve alertas de su organizacion"
  on public.alertas_enviadas for select
  using (org_id in (select public.mis_org_ids()));



commit;

-- ── Resumen (sólo lectura) ──────────────────────────────────────────────────
select t as tabla, to_regclass('public.' || t) is not null as existe
  from unnest(array[
    'actividades_historial', 'organizacion_categorias', 'tareas_categorias', 'actividades_categorias',
    'fin_cuentas', 'fin_categorias', 'fin_movimientos',
    'firma_documentos', 'firma_firmantes', 'firma_eventos', 'firma_campos', 'firma_paginas', 'firma_contrato_jobs',
    'video_jobs', 'avm_scrape_cache', 'correo_cuentas', 'demos_agendadas',
    'wa2_agenda', 'wa2_automatizaciones', 'wa2_campanas', 'wa2_campana_envios', 'wa2_flujo_estados',
    'requerimientos_busqueda', 'busqueda_resultados', 'alertas_enviadas',
    'contacto_tipos', 'fuentes_captacion', 'pipeline_etapas',
    'buzon_leads', 'buzon_reglas', 'buzon_guardias', 'respuestas_guardadas']) as t
 order by existe, tabla;
