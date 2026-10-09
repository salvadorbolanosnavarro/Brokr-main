-- Cuántos tokens de WhatsApp están cifrados y cuántos no (solo lectura).
-- No muestra ningún token. Después de WA_TOKENS_ACCION=cifrar, la columna
-- "sin_cifrar" debe quedar en 0 en las dos tablas.
select 'wa2_numeros' as tabla,
       count(*) filter (where access_token like 'enc:wa1:%')                         as cifrados,
       count(*) filter (where access_token is not null and access_token <> ''
                          and access_token not like 'enc:wa1:%')                    as sin_cifrar,
       count(*) filter (where access_token is null or access_token = '')            as sin_token
  from public.wa2_numeros
union all
select 'wac_numbers',
       count(*) filter (where access_token like 'enc:wa1:%'),
       count(*) filter (where access_token is not null and access_token <> ''
                          and access_token not like 'enc:wa1:%'),
       count(*) filter (where access_token is null or access_token = '')
  from public.wac_numbers;
