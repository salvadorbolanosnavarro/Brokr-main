-- ============================================================
-- Cuentas de acceso sin perfil en `usuarios` ("huérfanas")
-- ============================================================
-- Una cuenta en auth.users sin fila en public.usuarios puede iniciar
-- sesión, pero NO aparece en la consola admin y NO tiene acceso a
-- funciones de pago (has_paid_feature_access exige la fila).
--
-- Causa histórica (corregida en routers/account_delete.py, 2026-11-28):
-- "Eliminar mi cuenta" borraba tablas sueltas + `usuarios` y luego
-- intentaba borrar auth.users, que fallaba para todo dueño de
-- organización (organizaciones.owner_id es ON DELETE RESTRICT). Ahora
-- usa admin_eliminar_usuario_total, que es atómica.
--
-- 1) Diagnóstico: debe devolver 0 filas.
select a.id, a.email, a.created_at, a.last_sign_in_at
  from auth.users a
  left join public.usuarios u on u.id = a.id
 where u.id is null
 order by a.created_at desc;

-- 2) Reparación (solo si el diagnóstico devolvió filas). Recrea el perfil
--    mínimo, igual que handle_new_user. No otorga acceso de pago: eso se
--    hace desde la consola (Acceso completo) o con la suscripción real.
-- insert into public.usuarios (id, email, rol, activo, created_at)
-- select a.id, a.email, 'agente', true, a.created_at
--   from auth.users a
--   left join public.usuarios u on u.id = a.id
--  where u.id is null
-- on conflict (id) do nothing;
