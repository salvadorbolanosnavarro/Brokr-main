-- ══════════════════════════════════════════════════════════════════════════
-- Security Advisor · E) Vista propiedades_publicas: no mostrar inmuebles "ajena"
-- ══════════════════════════════════════════════════════════════════════════
-- Hallazgo: la vista ya excluye archivadas y 'no_activa', pero SÍ incluye
-- las propiedades con estatus 'ajena' (inmuebles de otro colega externo).
-- El micrositio las filtra él mismo, pero cualquiera que llame a la API sin
-- sesión podía pedirlas. Aquí la vista deja de mostrarlas.
-- Mismas columnas, mismo orden, mismos permisos: el micrositio no cambia.
-- propiedades_publicas_extra se apoya en esta vista y queda igual de cerrada.
-- Reversa: 20261010-advisor-E-vista-propiedades-publicas-REVERSA.sql
-- ══════════════════════════════════════════════════════════════════════════

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
  WHERE ((archivada IS NOT TRUE)
     AND (estatus IS DISTINCT FROM 'no_activa'::text)
     AND (estatus IS DISTINCT FROM 'ajena'::text)
     AND (user_id IN ( SELECT usuarios.id
           FROM usuarios
          WHERE (usuarios.sitio_activo = true))));

commit;
