-- Trial de bienvenida: 7 días de Broquer Max sin costo, una sola vez por cuenta.
-- Se marca al completarse un checkout con trial (webhook de Stripe) y ya no se
-- vuelve a ofrecer aunque la fila de suscripciones se borre.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS trial_max_usado boolean DEFAULT false;
