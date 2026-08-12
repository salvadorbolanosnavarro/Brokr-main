-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Módulo de correo electrónico (cuentas IMAP/SMTP)
--
-- Guarda la conexión de correo de cada usuario. La contraseña de aplicación
-- viaja y se guarda CIFRADA por el backend (Fernet); esta tabla nunca ve la
-- contraseña en claro.
--
-- SEGURIDAD: RLS activo y SIN políticas a propósito. Eso significa que ni
-- el propio usuario puede leer esta tabla desde el frontend — solo la
-- service key del backend. Es la tabla más sensible de Broquer y así debe
-- quedarse. NO agregar políticas de lectura.
--
-- Idempotente. Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

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

-- Una cuenta de correo por usuario
create unique index if not exists idx_correo_cuentas_user
  on public.correo_cuentas (user_id);

-- RLS sin políticas: solo la service key del backend puede tocarla
alter table public.correo_cuentas enable row level security;

-- Verificación
select count(*) as cuentas_conectadas from public.correo_cuentas;
