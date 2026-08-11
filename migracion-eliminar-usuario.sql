-- migracion-eliminar-usuario.sql
-- ─────────────────────────────────────────────────────────────────────
-- Eliminación total de un usuario desde la consola admin.
--
-- Crea la función admin_eliminar_usuario_total(p_user_id) que borra:
--   1. Sus membresías de organización y las organizaciones que él posee
--      (incluyendo las membresías de otros miembros de esas orgs).
--   2. TODA fila en CUALQUIER tabla de `public` que tenga una columna
--      uuid llamada `user_id` u `owner_id` con su id. El escaneo es
--      dinámico contra information_schema: las tablas que se creen en
--      el futuro quedan cubiertas automáticamente, sin mantener listas.
--   3. (Los archivos de Storage NO se borran aquí: Supabase lo prohíbe
--      por SQL. Los borra el backend vía Storage API tras llamar esta
--      función — ver /admin/user/eliminar en main.py.)
--   4. Su fila en public.usuarios.
--   5. Su cuenta en auth.users (con esto el correo puede re-registrarse).
--
-- Los borrados por tabla se hacen en hasta 3 pasadas: si una tabla falla
-- por una FK que depende de otra, se reintenta cuando la otra ya se vació.
-- Devuelve un JSON con el conteo de filas borradas por tabla.
--
-- SECURITY DEFINER: solo la llama el backend con el service key vía RPC.
-- Se revoca EXECUTE a anon/authenticated para que nadie la invoque desde
-- el frontend.
-- Idempotente: se puede correr las veces que sea.
-- ─────────────────────────────────────────────────────────────────────

create or replace function public.admin_eliminar_usuario_total(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_email      text;
  v_resumen    jsonb := '{}'::jsonb;
  v_filas      bigint;
  v_tabla      record;
  v_pendientes text[];
  v_fallidas   text[];
  v_pasada     int;
  v_col        text;
begin
  select email into v_email from auth.users where id = p_user_id;
  if v_email is null then
    return jsonb_build_object('ok', false, 'error', 'El usuario no existe.');
  end if;

  -- ── 1) Organizaciones que el usuario posee ──────────────────────────
  -- Primero las membresías de TODOS los miembros de sus orgs (si no,
  -- la FK de organizacion_miembros → organizaciones bloquea el borrado).
  if to_regclass('public.organizacion_miembros') is not null
     and to_regclass('public.organizaciones') is not null then
    delete from public.organizacion_miembros
     where org_id in (select id from public.organizaciones where owner_id = p_user_id);
    get diagnostics v_filas = row_count;
    if v_filas > 0 then
      v_resumen := v_resumen || jsonb_build_object('organizacion_miembros (de sus empresas)', v_filas);
    end if;
  end if;

  -- ── 2) Escaneo dinámico: toda tabla public con user_id u owner_id ───
  -- Se reintenta en pasadas para resolver dependencias entre tablas.
  for v_pasada in 1..3 loop
    v_fallidas := '{}';
    for v_tabla in
      select c.table_name, c.column_name
        from information_schema.columns c
        join information_schema.tables t
          on t.table_schema = c.table_schema and t.table_name = c.table_name
       where c.table_schema = 'public'
         and t.table_type   = 'BASE TABLE'
         and c.column_name in ('user_id', 'owner_id')
         and c.data_type    = 'uuid'
         and c.table_name  <> 'usuarios'
       order by c.table_name
    loop
      -- En pasadas posteriores solo se reintentan las que fallaron.
      if v_pasada > 1 and not (v_tabla.table_name || '.' || v_tabla.column_name) = any(v_pendientes) then
        continue;
      end if;
      begin
        execute format('delete from public.%I where %I = $1',
                       v_tabla.table_name, v_tabla.column_name)
          using p_user_id;
        get diagnostics v_filas = row_count;
        if v_filas > 0 then
          v_col := v_tabla.table_name
                   || case when v_tabla.column_name = 'owner_id' then ' (owner)' else '' end;
          v_resumen := v_resumen
            || jsonb_build_object(v_col, coalesce((v_resumen->>v_col)::bigint, 0) + v_filas);
        end if;
      exception when others then
        v_fallidas := v_fallidas || (v_tabla.table_name || '.' || v_tabla.column_name);
      end;
    end loop;
    exit when coalesce(array_length(v_fallidas, 1), 0) = 0;
    v_pendientes := v_fallidas;
  end loop;

  if coalesce(array_length(v_fallidas, 1), 0) > 0 then
    return jsonb_build_object(
      'ok', false,
      'error', 'No se pudieron limpiar estas tablas: ' || array_to_string(v_fallidas, ', '),
      'borrado_parcial', v_resumen
    );
  end if;

  -- ── 3) Archivos en Storage ──────────────────────────────────────────
  -- Supabase prohíbe borrar storage.objects con SQL directo (error 42501:
  -- "Use the Storage API instead"). Los archivos los borra el backend vía
  -- Storage API justo después de llamar esta función. Aquí no se toca nada.

  -- ── 4) Perfil ───────────────────────────────────────────────────────
  delete from public.usuarios where id = p_user_id;
  get diagnostics v_filas = row_count;
  if v_filas > 0 then
    v_resumen := v_resumen || jsonb_build_object('usuarios', v_filas);
  end if;

  -- ── 5) Cuenta de autenticación ──────────────────────────────────────
  delete from auth.users where id = p_user_id;

  return jsonb_build_object('ok', true, 'email', v_email, 'borrado', v_resumen);
end;
$$;

-- Nadie desde el frontend puede ejecutar esto. Solo el backend (service key).
revoke execute on function public.admin_eliminar_usuario_total(uuid) from public;
revoke execute on function public.admin_eliminar_usuario_total(uuid) from anon;
revoke execute on function public.admin_eliminar_usuario_total(uuid) from authenticated;
grant  execute on function public.admin_eliminar_usuario_total(uuid) to service_role;
