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
--     · El ciclo completo del aviso (subido, aceptado, rechazado, rehacer,
--       modificatorio) y las alertas al celular.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase ANTES de usar la versión
-- nueva del módulo de Cumplimiento.
-- ═══════════════════════════════════════════════════════════════════════════

alter table public.pld_config
  add column if not exists rfc_sujeto_obligado text,
  add column if not exists clave_entidad_colegiada text;

alter table public.pld_operaciones
  add column if not exists aviso_datos jsonb not null default '{}'::jsonb,
  -- Folio que la UIF le dio a la operación en el acuse (AAAA-999999999).
  -- Sin él no se puede presentar un aviso modificatorio.
  add column if not exists folio_uif text,
  add column if not exists modificado_at timestamptz;

-- ── Ciclo del aviso ─────────────────────────────────────────────────────────
--   generado  → «Por subir» (el agente lo descarga y lo sube al SPPLD)
--   subido    → «En revisión del SAT»
--   presentado→ «Aceptado» (acuse con folio)
--   rechazado → el SAT no lo aceptó; sus operaciones se liberan para corregir
--   descartado→ «Rehacer aviso»: se tiró sin presentar
alter table public.pld_avisos
  add column if not exists formato text,
  add column if not exists descargado_at timestamptz,
  add column if not exists subido_at timestamptz,
  add column if not exists rechazado_at timestamptz,
  add column if not exists motivo_rechazo text,
  add column if not exists aviso_origen_id uuid,
  add column if not exists operacion_id uuid,
  add column if not exists descripcion_modificacion text;

-- Si la tabla limitaba los valores de estatus o tipo, se amplían para los
-- estados nuevos (subido, descartado) y el tipo modificatorio. NOT VALID:
-- no revisa filas viejas, solo las que se escriban de aquí en adelante.
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

-- Alertas al celular: qué se avisó y cuándo, para no repetir el mismo día.
alter table public.pld_config
  add column if not exists alertas_enviadas jsonb not null default '{}'::jsonb;

-- ── Resultado ──
select table_name, column_name, data_type
  from information_schema.columns
 where table_schema = 'public'
   and ((table_name = 'pld_config' and column_name in ('rfc_sujeto_obligado', 'clave_entidad_colegiada'))
     or (table_name = 'pld_operaciones' and column_name in ('aviso_datos', 'folio_uif', 'modificado_at'))
   or (table_name = 'pld_avisos' and column_name in ('formato', 'subido_at', 'rechazado_at')));
