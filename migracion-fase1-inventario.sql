-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 1: inventario completo (paridad EasyBroker)
--
-- QUÉ AGREGA (sólo columnas nuevas con default; no borra ni cambia nada)
--   propiedades.operaciones      jsonb  — varias operaciones, cada una con su
--                                         precio/moneda/unidad/periodo:
--                                         [{"tipo":"venta","precio":2500000,
--                                           "moneda":"MXN","unidad":"total"},
--                                          {"tipo":"renta_temporal","precio":1800,
--                                           "moneda":"MXN","periodo":"noche"}]
--                                         Las columnas viejas operacion/precio/
--                                         moneda se siguen llenando con la
--                                         operación principal (la primera) para
--                                         que Bolsa, WhatsApp y búsquedas sigan
--                                         funcionando sin cambios.
--   subtipo                      text   — tipo detallado del catálogo
--                                         (casa_condominio, nave_industrial…);
--                                         la columna tipo sigue con la familia
--                                         de siempre (casa, terreno, bodega…).
--   precio_unidad                text   — total | m2 | ha
--   mantenimiento_incluido       text   — si | no | no_indicado
--   antiguedad                   int    — años (alternativa al año)
--   condicion, disposicion, orientacion  text
--   pisos_edificio               int
--   caracteristicas              text[] — claves del catálogo (casillas)
--   otras_caracteristicas        text   — lo que no coincidió con el catálogo
--   lat, lng                     double precision — para el mapa
--   fecha_cierre                 timestamptz
--
-- Además:
--   · Rellena operaciones con la operación vieja de cada inmueble.
--   · Convierte el texto viejo de amenidades en casillas; lo que no coincide
--     va a otras_caracteristicas. La columna amenidades NO se borra.
--   · Vista propiedades_publicas_extra para que el micrositio lea los campos
--     nuevos sólo de inmuebles que ya son públicos.
--
-- Idempotente. Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

alter table public.propiedades
  add column if not exists subtipo text,
  add column if not exists operaciones jsonb not null default '[]'::jsonb,
  add column if not exists precio_unidad text not null default 'total',
  add column if not exists mantenimiento_incluido text not null default 'no_indicado',
  add column if not exists antiguedad integer,
  add column if not exists condicion text,
  add column if not exists disposicion text,
  add column if not exists orientacion text,
  add column if not exists pisos_edificio integer,
  add column if not exists caracteristicas text[] not null default '{}'::text[],
  add column if not exists otras_caracteristicas text,
  add column if not exists lat double precision,
  add column if not exists lng double precision,
  add column if not exists fecha_cierre timestamptz;

create index if not exists idx_propiedades_caracteristicas on public.propiedades using gin (caracteristicas);
create index if not exists idx_propiedades_operaciones on public.propiedades using gin (operaciones);

-- ── Subtipo: el tipo detallado (la columna tipo queda como familia) ──
update public.propiedades set subtipo = tipo
 where subtipo is null and tipo in ('casa','departamento','terreno','local','oficina','bodega');

-- ── Operaciones: una por inmueble viejo ──
update public.propiedades
   set operaciones = jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
         'tipo', operacion,
         'precio', precio,
         'moneda', coalesce(nullif(moneda, ''), 'MXN'),
         'unidad', 'total')))
 where operaciones = '[]'::jsonb
   and operacion in ('venta', 'renta');

-- ── Amenidades de texto → casillas ──
create or replace function public.bk_normaliza(t text)
returns text language sql immutable as $$
  select btrim(regexp_replace(
           lower(translate(coalesce(t, ''), 'áéíóúüñÁÉÍÓÚÜÑàèìòùÀÈÌÒÙ', 'aeiouunaeiouunaeiouaeiou')),
           '[^a-z0-9]+', ' ', 'g'))
$$;

create temporary table _bk_alias(nombre text primary key, clave text) on commit drop;
insert into _bk_alias(nombre, clave) values
  ('a c', 'aire_acondicionado'),
  ('accesibilidad', 'rampas'),
  ('acceso a la playa', 'acceso_playa'),
  ('acceso controlado', 'acceso_controlado'),
  ('acceso playa', 'acceso_playa'),
  ('aire acondicionado', 'aire_acondicionado'),
  ('alberca', 'alberca'),
  ('amueblada', 'amueblado'),
  ('amueblado', 'amueblado'),
  ('anden', 'anden'),
  ('area comun', 'area_comun'),
  ('area de asador', 'asador'),
  ('area de juegos infantiles', 'juegos_infantiles'),
  ('area de lavado', 'lavanderia'),
  ('area infantil', 'juegos_infantiles'),
  ('area para mascotas', 'pet_friendly_area'),
  ('areas comunes', 'area_comun'),
  ('areas verdes', 'area_comun'),
  ('asador', 'asador'),
  ('ascensor', 'elevador'),
  ('azotea', 'roof_garden'),
  ('balcon', 'balcon'),
  ('banjercito', 'fin_issfam'),
  ('bbq', 'asador'),
  ('bodega', 'bodega_interna'),
  ('bodega cuarto de guardado', 'bodega_interna'),
  ('bodega interna', 'bodega_interna'),
  ('business center', 'business_center'),
  ('calefaccion', 'calefaccion'),
  ('calentador solar', 'panel_solar'),
  ('campo de golf', 'golf'),
  ('cancha basquetbol', 'cancha_basquetbol'),
  ('cancha de basquetbol', 'cancha_basquetbol'),
  ('cancha de futbol', 'cancha_futbol'),
  ('cancha de padel', 'padel'),
  ('cancha de tenis', 'tenis'),
  ('cancha futbol', 'cancha_futbol'),
  ('casa club', 'casa_club'),
  ('caseta de vigilancia', 'acceso_controlado'),
  ('centro de negocios', 'business_center'),
  ('chimenea', 'chimenea'),
  ('cine', 'cine'),
  ('cisterna', 'cisterna'),
  ('clima', 'aire_acondicionado'),
  ('closets', 'closets'),
  ('club house', 'casa_club'),
  ('cochera techada', 'estacionamiento_techado'),
  ('cocina equipada', 'cocina_integral'),
  ('cocina integral', 'cocina_integral'),
  ('cofinavit', 'fin_infonavit'),
  ('conserje', 'portero'),
  ('control de acceso', 'acceso_controlado'),
  ('coto privado', 'fraccionamiento_privado'),
  ('credito bancario', 'fin_bancario'),
  ('credito hipotecario', 'fin_bancario'),
  ('creditos bancarios', 'fin_bancario'),
  ('cuarto de lavado', 'lavanderia'),
  ('cuarto de servicio', 'cuarto_servicio'),
  ('cuarto servicio', 'cuarto_servicio'),
  ('dos plantas', 'dos_plantas'),
  ('elevador', 'elevador'),
  ('estacionamiento de visitas', 'estacionamiento_visitas'),
  ('estacionamiento techado', 'estacionamiento_techado'),
  ('estacionamiento visitas', 'estacionamiento_visitas'),
  ('estudio', 'estudio'),
  ('facil estacionarse', 'facil_estacionarse'),
  ('facilidad para estacionarse', 'facil_estacionarse'),
  ('fibra optica', 'internet'),
  ('fin bancario', 'fin_bancario'),
  ('fin fovissste', 'fin_fovissste'),
  ('fin infonavit', 'fin_infonavit'),
  ('fin issfam', 'fin_issfam'),
  ('fin pemex', 'fin_pemex'),
  ('fogatero', 'fogatero'),
  ('fovissste', 'fin_fovissste'),
  ('fovisste', 'fin_fovissste'),
  ('fraccionamiento privado', 'fraccionamiento_privado'),
  ('frente a la playa', 'frente_playa'),
  ('frente agua', 'frente_agua'),
  ('frente al agua', 'frente_agua'),
  ('frente playa', 'frente_playa'),
  ('fumar no', 'fumar_no'),
  ('fumar si', 'fumar_si'),
  ('gas estacionario', 'gas_estacionario'),
  ('gas natural', 'gas_estacionario'),
  ('gimnasio', 'gimnasio'),
  ('golf', 'golf'),
  ('gym', 'gimnasio'),
  ('hidroneumatico', 'hidroneumatico'),
  ('infonavit', 'fin_infonavit'),
  ('infonavit cofinavit', 'fin_infonavit'),
  ('internet', 'internet'),
  ('internet fibra optica', 'internet'),
  ('issfam', 'fin_issfam'),
  ('issfam banjercito', 'fin_issfam'),
  ('jacuzzi', 'jacuzzi'),
  ('jardin', 'jardin'),
  ('juegos infantiles', 'juegos_infantiles'),
  ('lavanderia', 'lavanderia'),
  ('ludoteca', 'ludoteca'),
  ('mascotas no', 'mascotas_no'),
  ('mascotas permitidas', 'mascotas_si'),
  ('mascotas si', 'mascotas_si'),
  ('minisplit', 'aire_acondicionado'),
  ('no se aceptan mascotas', 'mascotas_no'),
  ('oficina', 'oficina'),
  ('padel', 'padel'),
  ('panel solar', 'panel_solar'),
  ('paneles solares', 'panel_solar'),
  ('patio', 'patio'),
  ('pemex', 'fin_pemex'),
  ('penthouse', 'penthouse'),
  ('permitido fumar', 'fumar_si'),
  ('pet friendly', 'mascotas_si'),
  ('pet friendly area', 'pet_friendly_area'),
  ('pet park', 'pet_friendly_area'),
  ('piscina', 'alberca'),
  ('planta baja', 'planta_baja'),
  ('planta electrica', 'planta_electrica'),
  ('portero', 'portero'),
  ('privada', 'fraccionamiento_privado'),
  ('prohibido fumar', 'fumar_no'),
  ('rampas', 'rampas'),
  ('recamara en planta baja', 'recamara_planta_baja'),
  ('recamara planta baja', 'recamara_planta_baja'),
  ('roof garden', 'roof_garden'),
  ('roofgarden', 'roof_garden'),
  ('sala de cine', 'cine'),
  ('salon de eventos', 'salon_usos_multiples'),
  ('salon de usos multiples', 'salon_usos_multiples'),
  ('salon usos multiples', 'salon_usos_multiples'),
  ('sauna', 'sauna'),
  ('se aceptan mascotas', 'mascotas_si'),
  ('seguridad', 'seguridad_24h'),
  ('seguridad 12 horas', 'seguridad_12h'),
  ('seguridad 12h', 'seguridad_12h'),
  ('seguridad 24 horas', 'seguridad_24h'),
  ('seguridad 24h', 'seguridad_24h'),
  ('sum', 'salon_usos_multiples'),
  ('tenis', 'tenis'),
  ('terraza', 'terraza'),
  ('una planta', 'una_planta'),
  ('una sola planta', 'una_planta'),
  ('vapor', 'sauna'),
  ('vestidor', 'vestidor'),
  ('vigilancia 24 horas', 'seguridad_24h'),
  ('vigilancia 24h', 'seguridad_24h'),
  ('vista agua', 'vista_agua'),
  ('vista al agua', 'vista_agua'),
  ('vista al mar', 'vista_mar'),
  ('vista mar', 'vista_mar'),
  ('vista panoramica', 'vista_panoramica'),
  ('wifi', 'internet')
on conflict do nothing;

with fuente as (
  select p.id, a.txt
    from public.propiedades p,
         lateral unnest(coalesce(p.amenidades, '{}'::text[])) as a(txt)
   where coalesce(array_length(p.caracteristicas, 1), 0) = 0
     and coalesce(array_length(p.amenidades, 1), 0) > 0
), clasif as (
  select f.id, f.txt, al.clave
    from fuente f
    left join _bk_alias al on al.nombre = public.bk_normaliza(f.txt)
), agrupado as (
  select id,
         array_remove(array_agg(distinct clave), null) as claves,
         string_agg(distinct btrim(txt), ', ') filter (where clave is null and btrim(txt) <> '') as otras
    from clasif
   group by id
)
update public.propiedades p
   set caracteristicas = coalesce(a.claves, '{}'::text[]),
       otras_caracteristicas = coalesce(p.otras_caracteristicas, a.otras)
  from agrupado a
 where p.id = a.id;

-- ── Campos públicos nuevos para el micrositio ──
-- Sólo inmuebles que ya expone propiedades_publicas (mismas reglas que hoy).
create or replace view public.propiedades_publicas_extra as
select p.id, p.subtipo,
       -- Si el agente ocultó el precio, las operaciones salen sin monto.
       case when coalesce(p.mostrar_precio, true) then p.operaciones
            else coalesce((select jsonb_agg(o - 'precio') from jsonb_array_elements(p.operaciones) o), '[]'::jsonb)
       end as operaciones,
       coalesce(p.mostrar_precio, true) as mostrar_precio,
       p.precio_unidad, p.mantenimiento_incluido,
       p.antiguedad, p.condicion, p.disposicion, p.orientacion,
       p.pisos_edificio, p.caracteristicas, p.otras_caracteristicas,
       case when p.mostrar_ubicacion_exacta then p.lat end as lat,
       case when p.mostrar_ubicacion_exacta then p.lng end as lng
  from public.propiedades p
 where p.id in (select id from public.propiedades_publicas);

grant select on public.propiedades_publicas_extra to anon, authenticated;

commit;

select count(*) filter (where jsonb_array_length(operaciones) > 0) as con_operaciones,
       count(*) filter (where coalesce(array_length(caracteristicas, 1), 0) > 0) as con_caracteristicas,
       count(*) as total
  from public.propiedades;
