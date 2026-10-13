-- REVERSA de 20261013-bitacora-sin-cambios-de-etapa-duplicados.sql
-- Deja bk_contacto_cambio_estatus() exactamente como estaba en producción el
-- 13-oct-2026 (vuelve a escribir "Estatus cambiado de…" en la bitácora).
-- Las líneas repetidas que se borraron no regresan.
create or replace function public.bk_contacto_cambio_estatus()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $function$
BEGIN
  IF NEW.estatus IS DISTINCT FROM OLD.estatus THEN
    NEW.fecha_cambio_estatus := now();
    INSERT INTO public.actividades (user_id, tipo, texto, contacto_id, meta)
    VALUES (
      NEW.user_id,
      'cambio_estatus',
      format('Estatus cambiado de "%s" a "%s"',
             COALESCE(OLD.estatus, 'sin estatus'), NEW.estatus),
      NEW.id,
      jsonb_build_object('de', OLD.estatus, 'a', NEW.estatus)
    );
  END IF;
  RETURN NEW;
END;
$function$;
