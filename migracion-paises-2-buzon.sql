-- ══════════════════════════════════════════════════════════════════════════
-- Buzón: reconocer contactos por teléfono también en Perú y Chile
-- ══════════════════════════════════════════════════════════════════════════
-- Antes se comparaban siempre los últimos 10 dígitos; los celulares de Perú
-- y Chile tienen 9. Ahora se comparan tantos dígitos como trae el número
-- buscado (10 en México, Colombia y Argentina; 9 en Perú y Chile). Para
-- México no cambia nada.
--
-- Cómo correrlo: Supabase → SQL Editor → pega todo este archivo → Run.
-- Se puede correr más de una vez.

create or replace function public.bk_buscar_contacto(p_org uuid, p_tel10 text, p_email text)
returns text
language sql stable security definer set search_path = public as $$
  select c.id
    from public.contactos c
   where (c.org_id = p_org
          or (c.org_id is null and c.user_id in (select user_id from public.organizacion_miembros where org_id = p_org and activo)))
     and (
       (coalesce(p_tel10, '') <> '' and (
          right(regexp_replace(coalesce(c.telefono, ''), '\D', '', 'g'), length(p_tel10)) = p_tel10
       or right(regexp_replace(coalesce(c.wa, ''), '\D', '', 'g'), length(p_tel10)) = p_tel10
       or exists (select 1 from jsonb_array_elements(coalesce(c.telefonos, '[]'::jsonb)) t
                   where right(regexp_replace(coalesce(t->>'numero', ''), '\D', '', 'g'), length(p_tel10)) = p_tel10)))
       or (coalesce(p_email, '') <> '' and (
          lower(c.email) = lower(p_email)
       or exists (select 1 from jsonb_array_elements(coalesce(c.correos, '[]'::jsonb)) m
                   where lower(m->>'correo') = lower(p_email))))
     )
   order by c.created_at asc nulls last
   limit 1
$$;
revoke all on function public.bk_buscar_contacto(uuid, text, text) from public, anon, authenticated;
