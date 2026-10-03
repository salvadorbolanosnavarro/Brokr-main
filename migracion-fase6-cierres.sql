-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 6: cierres y comisiones (paridad EasyBroker)
--
-- QUÉ AGREGA (sólo tablas/columnas nuevas con default; no borra nada)
--   cierres            reserva y cierre de cada operación: fechas, montos con
--                      moneda, comprador/arrendatario, comisión total (monto,
--                      % o meses de renta), de la inmobiliaria, del opcionador
--                      y del asesor (usuario del equipo o contacto/agencia
--                      externa), notas. Sólo lo lee quien tiene el permiso
--                      "Ver comisiones"; se escribe por el backend.
--   fin_movimientos    + estado (cobrado | por_cobrar), cierre_id, beneficiario:
--                      al guardar un cierre se crean solos los ingresos
--                      "Comisión por cobrar"; marcarlos cobrados actualiza el
--                      cierre. Los movimientos de siempre quedan 'cobrado'.
--   propiedades        + publicada_en (para "días publicada"); se rellena con
--                      la fecha de alta y se sella sola al publicar.
--
-- Requiere: migracion-finanzas.sql y migracion-fase1-inventario.sql.
-- Idempotente. Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

create table if not exists public.cierres (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  propiedad_id uuid not null,
  user_id uuid,                                   -- quien lo registró
  tipo_operacion text not null default 'venta',   -- venta | renta | preventa | renta_temporal | remate
  etapa text not null default 'cerrada',          -- reservada | cerrada
  fecha_reserva date,
  monto_reserva numeric,
  moneda_reserva text default 'MXN',
  fecha_cierre date,
  precio_cierre numeric,
  moneda_cierre text default 'MXN',
  comprador_contacto_id text,
  comision_tipo text default 'monto',             -- monto | pct | meses
  comision_valor numeric,
  comision_total numeric,
  moneda_comision text default 'MXN',
  comision_inmobiliaria numeric,
  opcionador_user_id uuid,
  opcionador_contacto_id text,
  opcionador_nombre text,
  opcionador_comision numeric,
  asesor_user_id uuid,
  asesor_contacto_id text,
  asesor_nombre text,
  asesor_comision numeric,
  precio_publicacion numeric,
  publicada_en timestamptz,
  notas text,
  cobrado boolean not null default false,
  origen text not null default 'broquer',         -- broquer | importado
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_cierres_org_fecha on public.cierres (org_id, fecha_cierre desc);
create index if not exists idx_cierres_prop on public.cierres (propiedad_id);

alter table public.cierres enable row level security;
drop policy if exists "comisiones visibles con permiso" on public.cierres;
create policy "comisiones visibles con permiso"
  on public.cierres for select
  using (org_id in (select public.mis_org_ids()) and public.org_permiso('ver_comisiones'));

alter table public.fin_movimientos
  add column if not exists estado text not null default 'cobrado',
  add column if not exists cierre_id uuid,
  add column if not exists beneficiario text;
create index if not exists fin_mov_cierre on public.fin_movimientos (cierre_id) where cierre_id is not null;

alter table public.propiedades add column if not exists publicada_en timestamptz;
update public.propiedades set publicada_en = created_at where publicada_en is null and created_at is not null;

create or replace function public.bk_propiedad_publicada()
returns trigger language plpgsql as $$
begin
  if new.publicada_en is null and coalesce(new.estatus, 'activa') = 'activa' then
    new.publicada_en := now();
  end if;
  return new;
end $$;
drop trigger if exists trg_propiedad_publicada on public.propiedades;
create trigger trg_propiedad_publicada
  before insert or update of estatus on public.propiedades
  for each row execute function public.bk_propiedad_publicada();

commit;
