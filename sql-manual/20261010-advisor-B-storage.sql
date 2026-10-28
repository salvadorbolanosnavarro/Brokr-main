-- ══════════════════════════════════════════════════════════════════════════
-- Security Advisor · B) Buckets públicos que dejan listar todos sus archivos
-- ══════════════════════════════════════════════════════════════════════════
-- Hoy cualquiera puede LISTAR todos los archivos de fotos-propiedades,
-- documentos-publicos, adjuntos-historial y avatares. Se cambia la regla de
-- "ver" por "cada usuario con sesión solo ve los archivos que él subió".
--   · Las ligas públicas (/object/public/...) siguen funcionando igual: no
--     usan esta regla.
--   · Las subidas siguen funcionando: usan "upsert", que necesita ver el
--     propio archivo, y eso se conserva.
--   · El backend (service_role) no usa estas reglas.
-- No toca storage.buckets. La foto de las reglas viejas queda en
-- respaldo_advisor_20261010 para 20261010-advisor-B-storage-REVERSA.sql.
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_advisor_20261010;
revoke all on schema respaldo_advisor_20261010 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_advisor_20261010.storage_politicas') is not null then
    raise notice 'La foto de reglas de storage ya existe; no se vuelve a tomar.';
    return;
  end if;
  create table respaldo_advisor_20261010.storage_politicas (
    nombre     name primary key,
    permissive text,
    roles      name[],
    cmd        text,
    qual       text,
    with_check text
  );
  revoke all on respaldo_advisor_20261010.storage_politicas from public, anon, authenticated;
  insert into respaldo_advisor_20261010.storage_politicas
  select policyname, permissive, roles, cmd, qual, with_check
    from pg_policies
   where schemaname = 'storage' and tablename = 'objects'
     and policyname in ('fotos_propiedades_select_public',
                        'lectura publica de documentos de inmuebles',
                        'lectura publica de adjuntos de historial',
                        'usuarios pueden actualizar su avatar tk3snb_1');
end $$;

drop policy if exists "fotos_propiedades_select_public"               on storage.objects;
drop policy if exists "lectura publica de documentos de inmuebles"    on storage.objects;
drop policy if exists "lectura publica de adjuntos de historial"      on storage.objects;
drop policy if exists "usuarios pueden actualizar su avatar tk3snb_1" on storage.objects;

drop policy if exists "fotos_propiedades_ve_sus_archivos" on storage.objects;
create policy "fotos_propiedades_ve_sus_archivos" on storage.objects
  for select to authenticated
  using (bucket_id = 'fotos-propiedades' and owner = auth.uid());

drop policy if exists "documentos_publicos_ve_sus_archivos" on storage.objects;
create policy "documentos_publicos_ve_sus_archivos" on storage.objects
  for select to authenticated
  using (bucket_id = 'documentos-publicos' and owner = auth.uid());

drop policy if exists "adjuntos_historial_ve_sus_archivos" on storage.objects;
create policy "adjuntos_historial_ve_sus_archivos" on storage.objects
  for select to authenticated
  using (bucket_id = 'adjuntos-historial' and owner = auth.uid());

drop policy if exists "avatares_ve_sus_archivos" on storage.objects;
create policy "avatares_ve_sus_archivos" on storage.objects
  for select to authenticated
  using (bucket_id = 'avatares' and owner = auth.uid());

commit;
