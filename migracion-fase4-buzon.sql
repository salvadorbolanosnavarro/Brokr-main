-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 4: Buzón (bandeja única de leads) y asignación
--
-- QUÉ AGREGA (sólo tablas nuevas; no toca datos existentes)
--   buzon_leads           una fila por lead o conversación que entra, venga
--                         de donde venga. El campo `canal` es texto libre
--                         ('whatsapp', 'sitio', 'bolsa', 'zapier', 'easybroker',
--                         'telefono', 'manual'…): Meta Lead Ads o portales se
--                         suman después sin cambiar la estructura.
--                         Ligado a contacto (contactos.id), inmueble de origen
--                         y fuente del catálogo. Estados: sin_atender,
--                         atendida, archivada, spam.
--   respuestas_guardadas  catálogo de respuestas por organización, con
--                         variables {nombre} e {inmueble}.
--   buzon_reglas          regla de asignación por organización: manual,
--                         agente_inmueble, ruleta o guardias; más el token
--                         secreto del webhook de entrada (Zapier/portales).
--   buzon_guardias        calendario de guardias (día y horario por usuario).
--
-- Lectura con RLS por organización (los agentes sin "ver contactos del
-- equipo" sólo ven sus leads y los sin asignar); escritura sólo por backend.
--
-- TOLERA TABLAS VIEJAS: en producción respuestas_guardadas ya existía con
-- otra forma (user_id y contenido NOT NULL, sin org_id/texto/canal). Aquí se
-- agregan las columnas que falten, se pasa contenido → texto y user_id →
-- org_id en filas viejas, y se quita el NOT NULL de columnas viejas que
-- Broquer ya no llena. No se borra ninguna fila ni columna.
--
-- Requiere: migracion-aislamiento-organizacion.sql y migracion-fase3-contactos.sql
-- (columnas telefonos/correos). Idempotente.
-- Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

-- ── Columnas viejas NOT NULL que Broquer ya no llena ────────────────────────
-- Va primero: si alguna de estas tablas ya existía con columnas obligatorias
-- que no son de este esquema (y sin valor por defecto), los guardados nuevos
-- fallarían. Se les quita el NOT NULL (no se borran ni se cambian los datos).
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
-- Tabla vieja (id, user_id, titulo, contenido, created_at, updated_at): se
-- completa con las columnas del Buzón y las filas viejas se pasan a su
-- organización (texto = contenido) para que aparezcan.
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
-- Sin políticas de lectura: el token es secreto; se lee/escribe por backend.

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

-- Busca un contacto de la organización por teléfono (10 dígitos MX) o
-- correo, para ligar el lead sin crear duplicados. Sólo backend.
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

-- Grupo Navarro trabaja hoy así: todo llega sin asignar.
insert into public.buzon_reglas (org_id, modo)
select id, 'manual' from public.organizaciones
on conflict (org_id) do nothing;

commit;
