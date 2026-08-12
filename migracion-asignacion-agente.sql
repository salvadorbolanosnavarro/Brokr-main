-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Asignación de agente responsable (Broquer para Empresas)
--
-- Qué hace:
--   Agrega la columna asignado_a a contactos y propiedades: el user_id del
--   agente de la empresa responsable de ese cliente o inmueble.
--
-- Qué NO hace (a propósito):
--   · NO cambia user_id (el creador sigue siendo el creador).
--   · NO toca RLS ni visibilidad: quién ve qué sigue exactamente igual.
--   · Asignar es una etiqueta de responsabilidad, no una transferencia.
--
-- Quién puede asignar: solo owner o admin de la empresa. El candado real
-- está en el backend (POST /org/asignar valida rol y org antes de escribir
-- con la service key); esta columna no es editable de forma directa más
-- allá de lo que ya permitan las políticas existentes de cada tabla.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

alter table public.contactos
  add column if not exists asignado_a uuid;

alter table public.propiedades
  add column if not exists asignado_a uuid;

-- Índices para el filtro "por agente" en empresas con miles de registros
create index if not exists idx_contactos_asignado_a
  on public.contactos (org_id, asignado_a);

create index if not exists idx_propiedades_asignado_a
  on public.propiedades (org_id, asignado_a);

-- Verificación
select 'contactos' as tabla,
       count(*) filter (where asignado_a is not null) as asignados,
       count(*) as total
  from public.contactos
union all
select 'propiedades',
       count(*) filter (where asignado_a is not null),
       count(*)
  from public.propiedades;
