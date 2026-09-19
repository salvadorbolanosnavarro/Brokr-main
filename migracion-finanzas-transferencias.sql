-- =============================================================================
-- Broquer · Finanzas — Transferencias entre cuentas
-- Pégala COMPLETA en Supabase > SQL Editor y dale Run.
-- Aditiva: no borra ni modifica datos existentes.
-- =============================================================================
-- Qué hace:
--   Agrega cuenta_destino_id a fin_movimientos para poder mover dinero de una
--   cuenta a otra sin que cuente como ingreso o gasto real (ej. sacar de
--   Efectivo y meterlo a BBVA). El movimiento sigue siendo una sola fila:
--     tipo = 'transferencia', cuenta_id = origen, cuenta_destino_id = destino.
--   El saldo de cada cuenta (calculado en vivo por el backend) resta del
--   origen y suma al destino. No se toca categoria_id/propiedad_id/
--   contacto_id: una transferencia no es categorizable ni ligada a una
--   propiedad, así que el backend los deja en null.
-- =============================================================================

ALTER TABLE fin_movimientos
  ADD COLUMN IF NOT EXISTS cuenta_destino_id uuid REFERENCES fin_cuentas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS fin_mov_cuenta_destino
  ON fin_movimientos (cuenta_destino_id) WHERE cuenta_destino_id IS NOT NULL;
