-- El token de Meta de cada número se guardaba sin que nada vigilara si seguía
-- sirviendo. Si Meta lo invalida (el agente revocó el permiso desde Facebook,
-- borró la app de su Business, o Meta lo caducó), los envíos empezaban a
-- fallar en silencio: la IA "contestaba", el mensaje nunca salía, y ni el
-- agente ni nosotros nos enterábamos hasta que el prospecto se quejaba.
--
-- Estas dos columnas dejan constancia de eso. El backend las marca en cuanto
-- Meta responde con un error de token (código 190), apaga la IA de ese número
-- y le manda una notificación al agente para que lo reconecte.
--
-- Cambio aditivo y seguro: no rompe filas existentes. Todos los números que ya
-- están conectados arrancan como válidos, que es lo correcto — si alguno tiene
-- el token muerto, se marcará solo en el primer envío que falle.

alter table wa2_numeros
  add column if not exists token_valido boolean not null default true;

alter table wa2_numeros
  add column if not exists token_error_at timestamptz;
