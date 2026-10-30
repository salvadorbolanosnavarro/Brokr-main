-- ============================================================
-- Teléfono obligatorio en el perfil de usuarios
-- ============================================================
-- La fila de `usuarios` la crea handle_new_user al darse de alta en
-- auth.users, antes de que la persona capture su teléfono; por eso no se
-- puede poner NOT NULL. Lo que sí garantiza la base:
--   1. Nadie completa su perfil (guarda o cambia su nombre) sin teléfono.
--   2. Nadie borra el teléfono una vez capturado.
-- Las altas nuevas y las actualizaciones de otros campos de cuentas viejas
-- sin teléfono siguen funcionando; la app las manda a registro.html.
-- Idempotente: se puede correr varias veces.
-- ============================================================

create or replace function public.usuarios_exigir_telefono()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  sin_tel boolean := nullif(btrim(coalesce(new.telefono, '')), '') is null;
begin
  if sin_tel and nullif(btrim(coalesce(old.telefono, '')), '') is not null then
    raise exception 'El teléfono es obligatorio y no se puede borrar.'
      using errcode = 'check_violation';
  end if;
  if sin_tel and new.nombre is distinct from old.nombre
     and nullif(btrim(coalesce(new.nombre, '')), '') is not null then
    raise exception 'Ingresa tu teléfono para completar tu perfil.'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_usuarios_exigir_telefono on public.usuarios;
create trigger trg_usuarios_exigir_telefono
  before update of nombre, telefono on public.usuarios
  for each row execute function public.usuarios_exigir_telefono();

-- Cuentas que hoy no tienen teléfono (se les pedirá al iniciar sesión):
-- select id, email, nombre
--   from public.usuarios
--  where nullif(btrim(coalesce(telefono, '')), '') is null
--  order by email;
