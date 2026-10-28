-- REVERSA de 20261016-solo-admin-borra.sql
-- Quita los tres candados de borrado y la función. Las reglas que ya había
-- nunca se tocaron, así que todo queda exactamente como estaba.
begin;

drop policy if exists "solo dueno o admin borra" on public.contactos;
drop policy if exists "solo dueno o admin borra" on public.propiedades;
drop policy if exists "solo dueno o admin borra" on public.actividades;
drop function if exists public.soy_agente_de_empresa();

commit;
