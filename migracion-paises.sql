-- ══════════════════════════════════════════════════════════════════════════
-- Broquer en 5 países: México, Colombia, Perú, Argentina y Chile
-- ══════════════════════════════════════════════════════════════════════════
-- Qué hace:
--   1. Agrega la columna "pais" a usuarios (MX, CO, PE, AR o CL).
--   2. Todas las cuentas que ya existen quedan en México (MX).
--   3. La cuenta elige su país UNA vez (al crearse). Después, desde el
--      navegador ya no se puede cambiar; solo el backend (service_role),
--      por ejemplo cuando alguien se une al equipo de una empresa y hereda
--      el país del dueño, o si Broquer lo corrige a mano.
--
-- Cómo correrlo: Supabase → SQL Editor → pega todo este archivo → Run.
-- Se puede correr más de una vez sin romper nada.
-- ══════════════════════════════════════════════════════════════════════════

begin;

alter table public.usuarios add column if not exists pais text;

update public.usuarios set pais = 'MX' where pais is null;

alter table public.usuarios drop constraint if exists usuarios_pais_valido;
alter table public.usuarios add constraint usuarios_pais_valido
  check (pais is null or pais in ('MX', 'CO', 'PE', 'AR', 'CL'));

-- Misma función que sql-manual/20261010-advisor-A4-proteger-usuarios.sql,
-- más el candado del país.
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
    -- El país se elige una sola vez: si ya tiene, no se cambia.
    IF OLD.pais IS NOT NULL THEN
      NEW.pais                = OLD.pais;
    END IF;
  END IF;
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

commit;

-- Comprobación (debe regresar una fila por país con su número de cuentas):
-- select pais, count(*) from public.usuarios group by pais order by 1;
