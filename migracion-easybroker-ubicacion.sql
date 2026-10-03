-- ============================================================================
-- Repara la ubicación de inmuebles importados de EasyBroker.
--
-- Bug: la API v1 de EasyBroker manda la ubicación como un solo texto
-- ("Ciudad Granja, Zapopan, Jalisco"). El importador guardaba ese texto
-- completo en `colonia` y dejaba `ciudad`='Morelia' / `estado`='Michoacán'
-- por default, así que en "Tus inmuebles" se veía
-- "Ciudad Granja, Zapopan, Jalisco, Morelia".
--
-- Esto parte la colonia en colonia / ciudad / estado. Solo toca filas que
-- vienen de EasyBroker (eb_public_id no nulo), cuya colonia trae comas y cuya
-- ciudad sigue en el default 'Morelia' (lo que dejó el bug). Es idempotente:
-- correrlo dos veces no cambia nada la segunda.
-- ============================================================================

-- 1) Vista previa (corre esto primero para ver qué se va a cambiar):
-- SELECT id, colonia, ciudad, estado FROM propiedades
--  WHERE eb_public_id IS NOT NULL AND colonia LIKE '%,%' AND ciudad = 'Morelia';

WITH partes AS (
  SELECT id,
         ARRAY(SELECT btrim(x) FROM unnest(string_to_array(colonia, ',')) AS x
               WHERE btrim(x) <> '') AS p
    FROM propiedades
   WHERE eb_public_id IS NOT NULL
     AND colonia LIKE '%,%'
     AND ciudad = 'Morelia'
)
UPDATE propiedades AS t
   SET colonia = CASE WHEN array_length(p, 1) >= 3
                      THEN array_to_string(p[1:array_length(p, 1) - 2], ', ')
                      ELSE p[1] END,
       ciudad  = CASE WHEN array_length(p, 1) >= 3
                      THEN p[array_length(p, 1) - 1]
                      ELSE p[2] END,
       estado  = CASE WHEN array_length(p, 1) >= 3
                      THEN p[array_length(p, 1)]
                      ELSE t.estado END,
       updated_at = now()
  FROM partes
 WHERE t.id = partes.id
   AND array_length(p, 1) >= 2;
