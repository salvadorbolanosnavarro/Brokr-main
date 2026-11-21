# Respaldo y recuperación: procedimiento pendiente de ensayo completo

No se accedió a producción. El proyecto staging confirmado es `tymhlvawnqadqgwnpruk`, PostgreSQL17.11, base26MB según consulta del21/11. Eso NO permite estimar ni prometer cuánto tardará producción. El entorno de trabajo no dispone de conexión privada libpq ni de un destino PostgreSQL/Supabase desechable. La conexión OAuth del plugin permite SQL, pero no entrega una conexión utilizable por pg_dump. **No hay un respaldo completo ni una restauración medidos.**

## Herramienta, responsable y duración

- Operador: administrador de la base designado por Salvador (o el agente, cuando se disponga de la conexión privada y destino de ensayo autorizados). Salvador aprueba cualquier intervención futura de producción. No se requieren llaves en el chat.
- Herramienta de respaldo lógico: PostgreSQL17 `pg_dump` formato custom y `pg_dumpall --roles-only --no-role-passwords`. Alternativa oficial administrada: Supabase CLI `supabase db dump` para roles, schema y datos, usando Docker. No intercambiar los dos formatos de restauración.
- Restauración del custom dump: PostgreSQL17 `pg_restore` sobre un destino aislado compatible, `--exit-on-error`, transacción y sin `--clean` implícito. Roles/extensiones se preparan antes. No declarar éxito solo porque terminó el comando: verificar después contenido y comportamiento.
- Duración: se medirá en el ensayo, por separado para exportación, transferencia, restauración, Storage y validación. Nunca usar los26MB de staging como tiempo de recuperación de producción. RTO/RPO quedan pendientes de medición y de confirmar la política de backups/PITR del plan de producción.

## Ensayo exclusivamente de staging

1. Preparar PostgreSQL17 y un destino vacío, aislado, compatible con extensiones de Supabase. No se usará broquer-beta, ni se restaurará encima del staging activo. No se creó infraestructura facturable.
2. Guardar dos conexiones libpq en un archivo privado `PGSERVICEFILE`, contraseñas en `PGPASSFILE` modo600. Fuente contiene ref `tymhlvawnqadqgwnpruk`. Destino distinto, con `application_name=cecil-disposable-restore`. Sin credenciales en argumentos, Git o evidencias.
3. Configurar solo el proceso local: `STAGING_SOURCE_SERVICE`, `STAGING_RESTORE_SERVICE`, `STAGING_BACKUP_DIR` apuntando a esas conexiones/directorio privado. Estas NO son variables de Railway/Cloudflare.
4. Ejecutar `bash scripts/staging_backup_drill.sh`. Rechaza producción, fuente inesperada, destino staging activo o herramientas ausentes. Es un script preparado, no un ensayo ya realizado.
5. Comparar inventario de tablas, conteos por tabla, extensiones, definiciones de funciones, triggers, índices, políticas/RLS y buckets. Comparar hashes/contenido de fixtures A/B; probar login, CRUD y aislamiento en el destino con efectos externos bloqueados. Revisar publicaciones Realtime y permisos.
6. Exportar y restaurar por separado los bytes de Supabase Storage; el dump contiene metadatos, **no las imágenes/documentos del bucket**. Verificar listado y SHA256 de cada objeto copiado. No reemplazar esto por comprobar solo storage.objects.
7. Firmar informe de resultado y tiempos medidos. Conservar dump cifrado, checksum y registro de validación fuera del repositorio; borrar el destino desechable solo después de conservar evidencia y autorización.

## Producción: checklist futuro, no ejecutado

1. Salvador autoriza la ventana y el operador. Identificar el proyecto por ref y cuenta verificados; verificar backups administrados/PITR y retención en Dashboard. Nunca desactivar servicios de producción por este documento sin autorización.
2. Tomar respaldo inmediatamente previo al piloto con el mismo método ya ensayado y exportación separada de Storage; registrar instante, versión, tamaño, SHA256, cifrado, ubicación y custodio. Guardar también configuración Auth, URLs, SMTP, secretos mediante el gestor apropiado, Edge Functions, Realtime, dominios y configuración externa: no todo está incluido en el dump.
3. Verificar restauración en destino aislado antes de activar. Los tiempos de ese ensayo determinan la ventana, no una cifra inventada. Una copia sin prueba de restauración no es respaldo verificado.
4. Activar únicamente la interfaz para el UUID real de Salvador. No aplicar las tablas/worker de staging a producción. No cambiar schema ni servicios del negocio para el piloto visual.
5. Ante un fallo visual, apagar el flag y volver a Broquer: esto conserva escrituras correctas y sesión. **No restaurar toda la base automáticamente por un fallo de UI**: una restauración puede borrar operaciones posteriores de otros usuarios y no revierte mensajes, cargos ni publicaciones externas.
6. Solo si hubo daño de datos, detener escrituras según el plan aprobado, documentar el punto de recuperación, validar respaldo, restaurar con el procedimiento ensayado y conciliar operaciones posteriores. El operador ejecuta; Salvador autoriza el impacto y la reapertura.

Fuentes oficiales consultadas: https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore y https://supabase.com/docs/guides/platform/migrating-within-supabase/dashboard-restore . Documentan configuración adicional y copia separada de Storage. Este documento identifica límites de acceso y no afirma una restauración inexistente.


## Comprobación adicional del Dashboard (staging solamente)

Se abrió el proyecto **broquer-redesign-staging**, ref tymhlvawnqadqgwnpruk, Database → Backups → Scheduled backups. Hay copias físicas diarias COMPLETED. La más reciente visible es21/11/2026 07:05:17UTC (01:05:17 Ciudad de México). A3 se creó a las07:14:15UTC: restaurar esa copia encima del staging activo eliminaría A3 y los controles recién preparados. No se ejecutó esa restauración.

Point in time muestra que es un add-on aún no activado. No se contrató. Restore to new project ofrece copiar schema, datos, índices, roles/permisos y usuarios; requiere reconfigurar Storage, Auth/API keys, Edge Functions, extensiones y réplicas. Se dejó sin confirmar y no se creó proyecto. El conector get_cost para un proyecto adicional de la organización verificada devuelve 10USD/mes (compute por horas, según la tarifa oficial) y recurrence monthly; se necesita aprobación expresa del coste y verificar el importe/moneda final del panel antes de crear un destino facturable. No se asumió autorización de gasto por el OK general de staging.

Alternativa sin servicio cloud adicional: conexión privada de solo respaldo y un PostgreSQL/Supabase desechable compatible del operador; no existe aún en este entorno. No se pedirán contraseñas en el chat. El ensayo y su duración siguen pendientes; la existencia de copias COMPLETED no demuestra una restauración correcta.

### Ruta por panel para el operador, cuando esté autorizado

1. Abrir Supabase → organización Broquer → proyecto correcto por ref → Database → Backups.
2. Scheduled backups: comprobar fecha, estado COMPLETED y que incluya los datos objetivo. Para ensayo, ir a Restore to new project y elegir la copia; el staging original permanece intacto.
3. Revisar qué se copia y qué se reconfigura. Antes de Continue/confirmación final, revisar coste, nombre/ref, región y destinatario. No seleccionar producción ni activar PITR como parte de este ensayo.
4. Registrar hora de inicio en UTC y hora de finalización cuando el nuevo proyecto esté saludable. Usar esas marcas para medir restauración administrada; no equivale al tiempo de hacer el respaldo, que fue automático y no se midió.
5. Verificar los objetos, permisos, datos y acceso del clon; copiar y comprobar Storage por separado. Solo entonces calificar el ensayo como OK.
6. En producción se haría el mismo procedimiento después de autorización explícita y respaldo previo verificable, con el UUID/refs de producción comprobados por el operador. No usar las fechas ni tiempos de staging como garantía de producción.

Tarifa oficial comprobada el21/11/2026: https://supabase.com/pricing — Micro10USD/mes, facturación de compute por horas. La cotización del conector no autoriza contratarlo ni incluye posibles consumos extra.
