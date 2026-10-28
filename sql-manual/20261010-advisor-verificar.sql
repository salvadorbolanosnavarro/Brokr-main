-- Verificación del Security Advisor (A, A4, B, C, E). Solo lectura.
-- La columna "ok" debe salir true en todos los renglones de las partes que ya aplicaste.
with f as (
  select p.oid, p.proname, p.proconfig, pg_get_functiondef(p.oid) as def
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
), chequeos(parte, chequeo, esperado, real) as (
  select 'A1', 'admin_update_usuario: anon/authenticated pueden ejecutar', false,
         bool_or(has_function_privilege('anon', oid, 'EXECUTE') or has_function_privilege('authenticated', oid, 'EXECUTE'))
    from f where proname = 'admin_update_usuario'
  union all
  select 'A2', proname || ': anon/authenticated pueden ejecutar', false,
         has_function_privilege('anon', oid, 'EXECUTE') or has_function_privilege('authenticated', oid, 'EXECUTE')
    from f where proname in ('handle_new_user', 'set_org_id', 'protect_usuarios_sensitive_fields',
                             'bk_contacto_cambio_estatus', 'rls_auto_enable')
  union all
  select 'A3', proname || ': anon puede ejecutar', false, has_function_privilege('anon', oid, 'EXECUTE')
    from f where proname in ('mis_org_ids', 'fila_de_mi_organizacion', 'contacto_en_mis_tareas',
                             'mi_org', 'es_admin_org', 'mi_rol_org', 'org_permiso')
  union all
  select 'A3', proname || ': authenticated puede ejecutar', true, has_function_privilege('authenticated', oid, 'EXECUTE')
    from f where proname in ('mis_org_ids', 'fila_de_mi_organizacion', 'contacto_en_mis_tareas',
                             'mi_org', 'es_admin_org', 'mi_rol_org', 'org_permiso')
  union all
  select 'A', proname || ': service_role puede ejecutar', true, has_function_privilege('service_role', oid, 'EXECUTE')
    from f where proname in ('admin_update_usuario', 'handle_new_user', 'mi_org', 'mis_org_ids')
  union all
  select 'A4', 'protect_usuarios_sensitive_fields protege acceso_completo_hasta', true,
         bool_or(def like '%NEW.acceso_completo_hasta = OLD.acceso_completo_hasta%')
    from f where proname = 'protect_usuarios_sensitive_fields'
  union all
  select 'B', 'regla vieja "' || nombre || '" existe', false,
         exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname = nombre)
    from unnest(array['fotos_propiedades_select_public', 'lectura publica de documentos de inmuebles',
                      'lectura publica de adjuntos de historial', 'usuarios pueden actualizar su avatar tk3snb_1']) nombre
  union all
  select 'B', 'regla nueva "' || nombre || '" existe y exige owner', true,
         exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname = nombre
                   and cmd = 'SELECT' and roles = array['authenticated']::name[] and qual like '%owner = auth.uid()%')
    from unnest(array['fotos_propiedades_ve_sus_archivos', 'documentos_publicos_ve_sus_archivos',
                      'adjuntos_historial_ve_sus_archivos', 'avatares_ve_sus_archivos']) nombre
  union all
  select 'C', proname || ': search_path fijo', true,
         coalesce('search_path=public, extensions, pg_temp' = any(proconfig), false)
    from f where proname in ('buscar_cercanos', 'bk_set_updated_at', 'tocar_updated_at', 'fb_touch_updated_at',
                             'bk_normaliza', 'bk_contacto_etapa_cambiada', 'bk_filas_de_org', 'bk_propiedad_publicada')
  union all
  select 'E', 'propiedades_publicas excluye ''ajena''', true,
         pg_get_viewdef('public.propiedades_publicas'::regclass) like '%''ajena''%'
  union all
  select 'E', 'anon puede leer propiedades_publicas', true,
         has_table_privilege('anon', 'public.propiedades_publicas', 'SELECT')
)
select parte, chequeo, esperado, real, (esperado = real) as ok
  from chequeos
 order by parte, chequeo;
