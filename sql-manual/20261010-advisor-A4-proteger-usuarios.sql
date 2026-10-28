-- ══════════════════════════════════════════════════════════════════════════
-- Security Advisor · A4) Proteger más columnas de "usuarios"
-- ══════════════════════════════════════════════════════════════════════════
-- Hallazgo: desde el navegador cada usuario puede editar su propia fila de
-- "usuarios" (así guarda su nombre y teléfono). El trigger
-- protect_usuarios_sensitive_fields ya impide que cambie rol, activo,
-- stripe_customer_id y email, pero NO protege:
--   · acceso_completo_hasta  → el backend la usa para dar acceso completo sin pagar
--   · modulos_desactivados   → módulos que el admin le apagó
--   · plan, modulos, exento, notas → columnas de administración
-- Ninguna pantalla escribe esas columnas desde el navegador (el panel de
-- admin las cambia por el backend con service_role), así que protegerlas no
-- rompe nada. El backend (service_role) las sigue pudiendo cambiar.
-- La reversa (…-A4-proteger-usuarios-REVERSA.sql) pone la versión de hoy.
-- ══════════════════════════════════════════════════════════════════════════

begin;

CREATE OR REPLACE FUNCTION public.protect_usuarios_sensitive_fields()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'extensions', 'pg_temp'
AS $function$
BEGIN
  -- Si quien hace el UPDATE no es el service_role (backend),
  -- ignoramos los cambios en las columnas que solo administra Broquer.
  IF auth.role() <> 'service_role' THEN
    NEW.rol                   = OLD.rol;
    NEW.activo                = OLD.activo;
    NEW.stripe_customer_id    = OLD.stripe_customer_id;
    NEW.email                 = OLD.email;
    NEW.acceso_completo_hasta = OLD.acceso_completo_hasta;
    NEW.modulos_desactivados  = OLD.modulos_desactivados;
    NEW.plan                  = OLD.plan;
    NEW.modulos               = OLD.modulos;
    NEW.exento                = OLD.exento;
    NEW.notas                 = OLD.notas;
  END IF;
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

commit;
