-- ═══════════════════════════════════════════════════════════════════════
-- BROQUER · Consola de dueño — tablas nuevas
-- Correr una sola vez en Supabase → SQL Editor.
--
-- Crea dos tablas:
--   correos        · bandeja de entrada y enviados del panel de admin
--   facturas_cfdi  · control de CFDI por cada cobro de Stripe
--
-- Ambas quedan CERRADAS con RLS: solo el backend (service key) las toca.
-- Ningún usuario, ni siquiera un admin desde el navegador, puede leerlas
-- directo desde Supabase. Todo pasa por api.broquer.app.
-- ═══════════════════════════════════════════════════════════════════════

-- ── 1. Correos ─────────────────────────────────────────────────────────
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

create index if not exists correos_direccion_fecha_idx
  on public.correos (direccion, created_at desc);
create index if not exists correos_leido_idx
  on public.correos (leido) where leido = false;
create index if not exists correos_user_idx
  on public.correos (user_id);

alter table public.correos enable row level security;
-- Sin políticas a propósito: RLS activo y cero policies = nadie entra con
-- llave pública. La service key del backend ignora RLS y es la única vía.

-- ── 2. Facturas CFDI ───────────────────────────────────────────────────
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

create index if not exists facturas_cfdi_estado_idx
  on public.facturas_cfdi (estado, created_at desc);
create index if not exists facturas_cfdi_user_idx
  on public.facturas_cfdi (user_id);

alter table public.facturas_cfdi enable row level security;
-- Igual que arriba: cerrada a llave pública, abierta solo al backend.

-- ── 3. Mantener updated_at al día en facturas ──────────────────────────
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
