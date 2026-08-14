-- =============================================================================
-- Broquer · Finanzas — Migración de base de datos
-- Pégala COMPLETA en Supabase > SQL Editor y dale Run.
-- Correr ANTES de subir routers/finanzas.py y finanzas.html.
-- =============================================================================
-- Qué crea:
--   · fin_cuentas       — las cuentas del usuario (banco, efectivo, tarjeta…)
--   · fin_categorias    — categorías de ingreso/gasto (el backend siembra las
--                         del gremio en el primer uso; aquí solo va la tabla)
--   · fin_movimientos   — cada ingreso o gasto. Puede ligarse a una propiedad
--                         y a un contacto para calcular rentabilidad real.
--   · bucket fin-comprobantes — tickets y facturas, privado, dueño-only.
--
-- Diseño clave:
--   · Los SALDOS NUNCA SE GUARDAN. Se calculan siempre en vivo como
--     saldo_inicial + suma de movimientos. Editar o borrar cualquier
--     movimiento recalcula todo sin inconsistencias.
--   · TODO es editable después de creado (regla del módulo).
--   · team_id existe desde hoy (nullable) para no migrar cuando lleguen
--     las finanzas por equipo. Hoy no se usa.
--   · RLS estricto igual que propiedades: cada quien ve solo lo suyo.
--     El backend usa service key DESPUÉS de validar el JWT del usuario.
-- =============================================================================

-- ── Cuentas ─────────────────────────────────────────────────────────────────
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

-- ── Categorías ──────────────────────────────────────────────────────────────
-- Por usuario. El backend siembra las del gremio (comisión de venta, Meta Ads,
-- fotografía, gasolina…) en el primer GET si la lista está vacía. Sembrarlas
-- desde el backend y no aquí evita triggers sobre auth.users y deja al
-- usuario renombrar o borrar las que no use.
CREATE TABLE IF NOT EXISTS fin_categorias (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL,
  team_id     uuid,
  nombre      text NOT NULL,
  tipo        text NOT NULL DEFAULT 'gasto',    -- ingreso | gasto
  clave       text,                             -- clave interna de las sembradas
                                                -- ("comision_venta"…); NULL en las
                                                -- creadas por el usuario. Sirve para
                                                -- no re-sembrar y para ligar la
                                                -- comisión automática aunque el
                                                -- usuario la renombre.
  orden       int NOT NULL DEFAULT 100,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fin_categorias_user ON fin_categorias (user_id);

ALTER TABLE fin_categorias ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fin_categorias_owner ON fin_categorias;
CREATE POLICY fin_categorias_owner ON fin_categorias
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- ── Movimientos ─────────────────────────────────────────────────────────────
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
  contacto_id    uuid,                          -- liga opcional a contactos.id
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

-- ── Bucket de comprobantes (privado, dueño-only) ────────────────────────────
-- Mismo patrón que el bucket 'firmas': privado, y solo el dueño (primera
-- carpeta = su uid) puede leer y escribir. El backend sube con service key
-- después de validar el JWT, y las lecturas van por liga firmada corta.
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
