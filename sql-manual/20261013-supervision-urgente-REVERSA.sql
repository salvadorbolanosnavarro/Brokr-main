-- REVERSA de 20261013-supervision-urgente.sql
-- Quita el candado, el índice y las cuatro columnas. Las notas urgentes que
-- existan se quedan en la bitácora como notas normales (pierden la marca).
begin;

drop trigger if exists actividades_candado_supervision on public.actividades;
drop function if exists public.actividades_candado_supervision();
drop index if exists public.idx_actividades_urgentes_pendientes;

alter table public.actividades drop column if exists atendido_por;
alter table public.actividades drop column if exists atendido_en;
alter table public.actividades drop column if exists para_usuario;
alter table public.actividades drop column if exists urgente;

commit;
