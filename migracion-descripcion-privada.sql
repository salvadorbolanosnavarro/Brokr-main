-- Agrega "descripción privada" a Contactos: un snapshot del estado de
-- calificación (temperatura, score, presupuesto, forma de pago, qué busca,
-- resumen) que la IA de WhatsApp mantiene actualizado. Se SOBRESCRIBE cada
-- vez (es una foto del momento), a diferencia de "notas" que es historial
-- acumulado. También editable a mano desde Contactos/Leads.
-- Cambio aditivo y seguro: no rompe filas existentes.

alter table contactos
  add column if not exists descripcion_privada text;
