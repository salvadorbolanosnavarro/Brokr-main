-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 7: sitio web del agente o de la inmobiliaria
--
-- QUÉ AGREGA (sólo tablas nuevas; el sitio de siempre broquer.app/tu-nombre
-- sigue funcionando igual)
--   sitios          un sitio por agente o por organización: slug, plantilla,
--                   logo, favicon, colores, WhatsApp flotante, redes, GA4,
--                   Meta Pixel, código propio en HEAD/BODY (sólo admin),
--                   mostrar perfil del asesor, incluir la Bolsa, traductor,
--                   textos de Acerca/Contacto, SEO y dominio propio con su
--                   estado (Cloudflare for SaaS).
--   sitio_paginas   páginas personalizadas: título, slug, contenido (texto
--                   enriquecido, se guarda ya limpio), meta SEO, publicada,
--                   si sale en el menú y orden.
--
-- El backend sirve el sitio como HTML con Open Graph (api.broquer.app/s/slug
-- o el dominio propio); lectura pública sólo por el backend.
--
-- Requiere: migracion-aislamiento-organizacion.sql. Idempotente.
-- Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

create table if not exists public.sitios (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  tipo text not null default 'organizacion',      -- organizacion | agente
  user_id uuid,                                    -- para sitios de agente
  slug text not null,
  activo boolean not null default false,
  nombre text,
  eslogan text,
  plantilla text not null default 'clasica',      -- clasica | moderna
  logo_url text,
  favicon_url text,
  hero_url text,
  color_primario text not null default '#0b2545',
  color_secundario text not null default '#13a89e',
  whatsapp text,
  telefono text,
  email text,
  direccion text,
  redes jsonb not null default '{}'::jsonb,
  ga4_id text,
  meta_pixel_id text,
  codigo_head text,
  codigo_body text,
  mostrar_asesor boolean not null default true,
  incluir_bolsa boolean not null default false,
  traductor boolean not null default false,
  acerca_html text,
  seo_titulo text,
  seo_descripcion text,
  dominio text,
  dominio_estado text not null default 'sin_dominio',   -- sin_dominio | pendiente | activo | error
  dominio_detalle text,
  cf_hostname_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists sitios_slug_uniq on public.sitios (lower(slug));
create unique index if not exists sitios_dominio_uniq on public.sitios (lower(dominio)) where dominio is not null;
create unique index if not exists sitios_org_tipo_user on public.sitios (org_id, tipo, coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid));

alter table public.sitios enable row level security;
drop policy if exists "equipo ve los sitios de su organizacion" on public.sitios;
create policy "equipo ve los sitios de su organizacion"
  on public.sitios for select
  using (org_id in (select public.mis_org_ids()));

create table if not exists public.sitio_paginas (
  id uuid primary key default gen_random_uuid(),
  sitio_id uuid not null references public.sitios(id) on delete cascade,
  titulo text not null,
  slug text not null,
  contenido_html text not null default '',
  meta_titulo text,
  meta_descripcion text,
  publicada boolean not null default false,
  en_menu boolean not null default false,
  orden integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists sitio_paginas_slug_uniq on public.sitio_paginas (sitio_id, lower(slug));
alter table public.sitio_paginas enable row level security;
drop policy if exists "equipo ve las paginas de sus sitios" on public.sitio_paginas;
create policy "equipo ve las paginas de sus sitios"
  on public.sitio_paginas for select
  using (sitio_id in (select id from public.sitios where org_id in (select public.mis_org_ids())));

commit;
