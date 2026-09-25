-- ═══════════════════════════════════════════════════════════════════════════
-- Diagnóstico: por qué no se ve "asignado a" ni funciona el filtro en Tareas
-- Solo LECTURA — no cambia nada. Correr en el SQL Editor de Supabase y
-- copiar el resultado de cada bloque.
-- ═══════════════════════════════════════════════════════════════════════════

-- 1) Tu organización: ¿tipo = 'empresa'? Si dice otra cosa (o está vacío/NULL),
--    ahí está el problema — toda la función se apaga si esto no es 'empresa'.
select id as org_id, nombre, tipo, activo
  from public.organizaciones
 where id in (
   select org_id from public.organizacion_miembros
    where user_id = auth.uid() and activo = true
 );

-- 2) Miembros activos de esa organización — necesitas más de uno (tú +
--    colaboradores) para que el filtro tenga sentido.
select om.user_id, om.rol_org, om.activo, u.nombre, u.email
  from public.organizacion_miembros om
  left join public.usuarios u on u.id = om.user_id
 where om.org_id in (
   select org_id from public.organizacion_miembros
    where user_id = auth.uid() and activo = true
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
where org_id in (
  select org_id from public.organizacion_miembros
   where user_id = auth.uid() and activo = true
) or org_id is null;

-- 4) ¿Existen de verdad las políticas de RLS que agrega la migración? Si
--    faltan filas aquí (deberían aparecer "equipo ve tareas de su empresa" y
--    "equipo edita tareas de su empresa"), la migración no se completó del
--    todo — algo la cortó a medias.
select polname, polcmd
  from pg_policy
 where polrelid = 'public.tareas'::regclass
 order by polname;
