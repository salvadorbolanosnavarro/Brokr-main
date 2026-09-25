-- ═══════════════════════════════════════════════════════════════════════════
-- Diagnóstico: por qué no se ve "asignado a" ni funciona el filtro en Tareas
-- Solo LECTURA — no cambia nada. Correr en el SQL Editor de Supabase y
-- copiar el resultado de cada bloque.
--
-- OJO: el SQL Editor de Supabase corre como superusuario (postgres), no
-- como tu usuario logueado en la app — ahí auth.uid() siempre da NULL, así
-- que estas consultas usan tu correo directamente en vez de auth.uid().
-- Cambia 'TU_CORREO_AQUI' por tu correo real de Broquer antes de correr
-- cada bloque.
-- ═══════════════════════════════════════════════════════════════════════════

-- 0) Tu user_id (lo necesitan los bloques siguientes).
select id as mi_user_id, nombre, email
  from public.usuarios
 where email = 'TU_CORREO_AQUI';

-- 1) Tu organización: ¿tipo = 'empresa'? Si dice otra cosa (o está vacío/NULL),
--    ahí está el problema — toda la función se apaga si esto no es 'empresa'.
select o.id as org_id, o.nombre, o.tipo, o.activo
  from public.organizaciones o
  join public.organizacion_miembros om on om.org_id = o.id
  join public.usuarios u on u.id = om.user_id
 where u.email = 'TU_CORREO_AQUI'
   and om.activo = true;

-- 2) Miembros activos de esa organización — necesitas más de uno (tú +
--    colaboradores) para que el filtro tenga sentido.
select om.user_id, om.rol_org, om.activo, u.nombre, u.email
  from public.organizacion_miembros om
  left join public.usuarios u on u.id = om.user_id
 where om.org_id = (
   select om2.org_id
     from public.organizacion_miembros om2
     join public.usuarios u2 on u2.id = om2.user_id
    where u2.email = 'TU_CORREO_AQUI' and om2.activo = true
    limit 1
 );

-- 3) ¿Las tareas ya tienen org_id? Si "sin_org" no es 0, hay tareas que la
--    migración no pudo backfillear (típicamente de un usuario que ya no
--    tiene membresía activa).
select
  count(*) filter (where org_id is not null) as con_org,
  count(*) filter (where org_id is null) as sin_org,
  count(*) filter (where asignado_a is not null) as ya_asignadas,
  count(*) as total
from public.tareas
where org_id = (
  select om.org_id
    from public.organizacion_miembros om
    join public.usuarios u on u.id = om.user_id
   where u.email = 'TU_CORREO_AQUI' and om.activo = true
   limit 1
) or org_id is null;

-- 3b) Si el bloque 3 sale con total=0, es que NINGUNA tarea en toda la tabla
--     quedó ligada a tu organización (ni siquiera las tuyas). Esto compara
--     contra el total real de "tareas" que existen en la base, sin filtrar
--     por org, para confirmarlo.
select count(*) as total_tareas_en_toda_la_base from public.tareas;

-- 4) Políticas de RLS de "tareas" (ya confirmado que existen y son
--    PERMISSIVE — no hace falta volver a correr esto, se deja de
--    referencia).
select polname, polcmd
  from pg_policy
 where polrelid = 'public.tareas'::regclass
 order by polname;
