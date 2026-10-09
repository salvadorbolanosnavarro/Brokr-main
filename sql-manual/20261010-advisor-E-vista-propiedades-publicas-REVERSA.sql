-- REVERSA de 20261010-advisor-E-vista-propiedades-publicas.sql
-- Definición de la vista tal como estaba en producción el 10 de octubre de 2026.
begin;

create or replace view public.propiedades_publicas as
 SELECT id,
    user_id,
    titulo,
    tipo,
    operacion,
        CASE
            WHEN (mostrar_precio IS NOT FALSE) THEN precio
            ELSE NULL::numeric
        END AS precio,
        CASE
            WHEN (mostrar_precio IS NOT FALSE) THEN precio_renta
            ELSE NULL::numeric
        END AS precio_renta,
    colonia,
    ciudad,
    recamaras,
    banos,
    m2_terreno,
    m2_construccion,
    m2_superficie_no_cubierta,
    fotos,
    descripcion,
        CASE
            WHEN (mostrar_ubicacion_exacta IS TRUE) THEN lat
            ELSE NULL::numeric
        END AS lat,
        CASE
            WHEN (mostrar_ubicacion_exacta IS TRUE) THEN lng
            ELSE NULL::numeric
        END AS lng,
    created_at,
    updated_at,
    estatus
   FROM propiedades p
  WHERE ((archivada IS NOT TRUE) AND (estatus IS DISTINCT FROM 'no_activa'::text) AND (user_id IN ( SELECT usuarios.id
           FROM usuarios
          WHERE (usuarios.sitio_activo = true))));

commit;
