-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Cumplimiento: datos para el aviso oficial de inmuebles (INM)
--
-- QUÉ HACE
--   El aviso que se sube al SPPLD sigue el XSD oficial de la UIF para la
--   fracción V (core/pld/inm.xsd). Ese formato pide datos que antes no se
--   capturaban:
--     · pld_config.rfc_sujeto_obligado: la clave con la que el SAT identifica
--       al sujeto obligado es su RFC con homoclave (no el folio del padrón).
--     · pld_config.clave_entidad_colegiada: solo si reporta por medio de una
--       entidad colegiada (opcional).
--     · pld_operaciones.aviso_datos: figura del cliente y del agente, la otra
--       parte, características del inmueble, escritura o contrato y pagos.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase ANTES de usar la versión
-- nueva del módulo de Cumplimiento.
-- ═══════════════════════════════════════════════════════════════════════════

alter table public.pld_config
  add column if not exists rfc_sujeto_obligado text,
  add column if not exists clave_entidad_colegiada text;

alter table public.pld_operaciones
  add column if not exists aviso_datos jsonb not null default '{}'::jsonb;

-- ── Resultado ──
select table_name, column_name, data_type
  from information_schema.columns
 where table_schema = 'public'
   and ((table_name = 'pld_config' and column_name in ('rfc_sujeto_obligado', 'clave_entidad_colegiada'))
     or (table_name = 'pld_operaciones' and column_name = 'aviso_datos'));
