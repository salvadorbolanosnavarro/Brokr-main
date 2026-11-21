-- Cuentas nuevas: organización personal automática y país editable.
-- Aplicada en broquer-redesign-staging. EN PRODUCCIÓN SE CORRE HASTA EL CAMBIO A + cierres.
-- Se puede correr dos veces sin efecto extra.
begin;

-- registro.html guarda el país con el usuario en sesión; faltaba este permiso.
grant update (pais) on public.usuarios to authenticated;

create or replace function public.handle_new_user()
 returns trigger
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare
  v_org uuid;
begin
  insert into public.usuarios (id, email, rol, activo)
  values (new.id, new.email, 'agente', true)
  on conflict (id) do update set
    email = excluded.email,
    updated_at = now();

  -- Buzón, Alertas y Ajustes de CRM necesitan una cuenta. Al aceptar una
  -- invitación, /org/aceptar-invitacion mueve al usuario a la empresa.
  if not exists (select 1 from public.organizacion_miembros m where m.user_id = new.id) then
    insert into public.organizaciones (nombre, owner_id, tipo)
    values (coalesce(nullif(new.email, ''), 'Mi cuenta'), new.id, 'personal')
    returning id into v_org;
    insert into public.organizacion_miembros (org_id, user_id, rol_org)
    values (v_org, new.id, 'owner');
  end if;
  return new;
end;
$function$;

revoke all on function public.handle_new_user() from public, anon, authenticated;
grant execute on function public.handle_new_user() to service_role;

-- Cuentas existentes sin ninguna membresía, ni siquiera dada de baja.
do $$
declare u record; v_org uuid;
begin
  for u in
    select x.id, x.email from public.usuarios x
    where not exists (select 1 from public.organizacion_miembros m where m.user_id = x.id)
  loop
    insert into public.organizaciones (nombre, owner_id, tipo)
    values (coalesce(nullif(u.email, ''), 'Mi cuenta'), u.id, 'personal')
    returning id into v_org;
    insert into public.organizacion_miembros (org_id, user_id, rol_org)
    values (v_org, u.id, 'owner');
  end loop;
end $$;

commit;
