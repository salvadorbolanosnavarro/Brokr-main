-- REVERSA de 20261010-advisor-A4-proteger-usuarios.sql
-- Pone la versión de protect_usuarios_sensitive_fields que había en producción
-- el 10 de octubre de 2026 (copiada tal cual del panel). Los permisos de la
-- función no cambian con esto.
begin;

CREATE OR REPLACE FUNCTION public.protect_usuarios_sensitive_fields()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions', 'pg_temp'
AS $function$
BEGIN
  -- Si quien hace el UPDATE no es el service_role (backend),
  -- ignoramos los cambios en rol, activo, stripe_customer_id y email.
  IF auth.role() <> 'service_role' THEN
    NEW.rol                = OLD.rol;
    NEW.activo             = OLD.activo;
    NEW.stripe_customer_id = OLD.stripe_customer_id;
    NEW.email              = OLD.email;
  END IF;
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

commit;
