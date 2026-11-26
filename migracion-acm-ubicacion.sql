-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — ACM: ubicación confirmada de los comparables
--
-- Corrige un error real: un anuncio que no decía su colonia se guardaba con
-- la colonia que el asesor buscó, y así anuncios de cualquier zona de la
-- ciudad pasaban por "cercanos" (caso: Chapultepec Sur comparado con otra
-- zona). Desde ahora cada anuncio guarda si su colonia salió del propio
-- anuncio (ubicacion_confirmada = true) y sólo esos pueden entrar solos al
-- cálculo.
--
--   · Los anuncios ya guardados quedan como NO confirmados: no se puede saber
--     cuáles se atribuyeron mal. Cuando la búsqueda vuelve a leer un anuncio
--     que sí declara su colonia, se confirma solo.
--   · Se vacía la caché de coordenadas por colonia: con la regla anterior
--     Google pudo devolver el centro de la ciudad como si fuera una colonia.
--     Es sólo caché; se vuelve a llenar sola.
--
-- Idempotente. Correr en Supabase → SQL Editor → Run, ANTES de desplegar.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

alter table public.mercado_comparables
  add column if not exists ubicacion_confirmada boolean not null default false;

delete from public.mercado_colonias_geo;

commit;
