-- ══════════════════════════════════════════════════════════════════════════
-- Archivos seguros · Parte B — adjuntos y WhatsApp pasan a PRIVADOS
-- ══════════════════════════════════════════════════════════════════════════
-- Hoy adjuntos-historial (identificaciones, comprobantes, contratos que se
-- adjuntan a notas y tareas) y wa-media (fotos, audios y documentos que
-- mandan los prospectos por WhatsApp) son buckets PÚBLICOS: quien tenga la
-- liga abre el archivo sin iniciar sesión. Es el mismo riesgo del incidente.
--
-- Después de esto, esas ligas viejas dejan de abrir el archivo por sí solas.
-- La app ya no las usa directamente:
--   · Historial/Tareas: historial-adjuntos.js pide ligas firmadas de 1 hora a
--     /adjuntos/ligas (solo si el usuario puede ver la nota o tarea).
--   · WhatsApp: /whatsapp2/mensajes regresa ligas firmadas de 1 hora, solo de
--     conversaciones que el usuario puede ver.
--   · Las fotos que llegan por WhatsApp para dar de alta un inmueble ahora se
--     COPIAN al bucket público de fotos (ya no se liga la del chat).
--
-- ⚠️  CORRER SOLO CUANDO:
--   1. El código de este cambio ya está publicado en producción (backend y web).
--   2. La app de iOS publicada ya incluye este cambio (las versiones viejas
--      abren las ligas públicas directamente y dejarían de ver adjuntos).
--   3. El reporte scripts/reporte_archivos.py no marca inmuebles cuyas fotos
--      apuntan a wa-media o adjuntos-historial (esas fotos dejarían de verse en
--      fichas públicas). Si los marca, primero hay que copiarlas.
--
-- No borra ni mueve archivos. Reversa: 20261106-archivos-privados-REVERSA.sql
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_archivos_20261106;
revoke all on schema respaldo_archivos_20261106 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_archivos_20261106.buckets_privados') is not null then
    raise exception 'La Parte B ya se aplicó. Corre la REVERSA antes de repetirla.';
  end if;
  create table respaldo_archivos_20261106.buckets_privados as
    select id, public from storage.buckets where id in ('adjuntos-historial', 'wa-media');
  revoke all on respaldo_archivos_20261106.buckets_privados from public, anon, authenticated;
end $$;

update storage.buckets set public = false where id in ('adjuntos-historial', 'wa-media');

-- Por si quedó alguna regla vieja de lectura pública (advisor B ya las quitó
-- para adjuntos-historial). Se guardan antes de quitarlas.
create table if not exists respaldo_archivos_20261106.politicas_lectura as
  select policyname, permissive, roles, cmd, qual, with_check
    from pg_policies
   where schemaname = 'storage' and tablename = 'objects' and cmd = 'SELECT'
     and policyname in ('lectura publica de adjuntos de historial', 'lectura publica wa-media');
revoke all on respaldo_archivos_20261106.politicas_lectura from public, anon, authenticated;
drop policy if exists "lectura publica de adjuntos de historial" on storage.objects;
drop policy if exists "lectura publica wa-media" on storage.objects;

commit;
