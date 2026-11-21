# Respaldo y recuperación: ensayo PostgreSQL completado

## Resultado actualizado del ensayo autorizado

El usuario autorizó expresamente el proyecto temporal de USD10/mes facturado por hora. Se ejecutó Supabase Dashboard → Database → Backups → Restore to new project, con la copia física COMPLETED del21/11/2026 07:05:17UTC de staging tymhlvawnqadqgwnpruk. Destino cecil-restore-drill-20261121-delete, ref hdpstaqcswrdcrozcxrq. El staging activo nunca se sobrescribió.

Inicio07:59:33.778UTC; primer ACTIVE_HEALTHY observado08:04:10.176UTC: **276.398segundos (4min36s)**, incluyendo aprovisionamiento e intervalo de observación. Validación terminada08:07:38UTC. **Proyecto temporal ELIMINADO**, confirmado por API list_projects y Dashboard a las08:09UTC. Cotización Dashboard USD9.68/mes compute y USD0disco; no se verificó importe final facturado.

124tablas,1759columnas,196políticas,780funciones,33triggers,381constraints,454índices,124estadosRLS,6extensiones y30roles sin diferencias de esquema.115tablas coinciden íntegramente en conteo/hash; las9 restantes coinciden al punto temporal del backup excluyendo campos mutables de actividad. A3 y dos tablas de piloto son posteriores al backup y correctamente no están en el clon. B2 ve su propiedad y ninguna ajena; A2 no ve la propiedad de B2. Inventarios agregados, hashes, SQL, comparación y tiempos: restore-20261121/. Sin filas de negocio ni credenciales en Git.

**Alcance:** recuperación de PostgreSQL probada.10buckets y5objetos conservan metadatos; los bytes de Storage NO forman parte de la copia física y no se restauraron. Falta el ensayo separado de archivos para declarar recuperación integral. No se midió tiempo de respaldo automático ni tiempo de producción.

## Procedimiento futuro para producción

Responsable: administrador Supabase designado por Salvador (o agente con acceso y autorización explícitos). Salvador autoriza ventana, coste y cualquier recuperación sobre la base activa. Herramienta ensayada: Dashboard, Database → Backups → Scheduled backups → Restore to new project. Elegir copia COMPLETED inmediatamente previa al piloto y destino aislado autorizado; registrar inicio y ACTIVE_HEALTHY; comparar esquema, hashes, RLS y pruebas de negocio. Exportar/restaurar Storage aparte con manifiesto de tamaño/SHA256, y conservar configuración Auth/SMTP/EdgeFunctions/Realtime mediante sus gestores. Borrar el clon al terminar y verificar su ausencia.

No se conoce cuánto tardará producción: el único tiempo observado es4min36s para staging, más la validación. Ante un fallo visual apagar el flag y volver a Broquer; NO restaurar toda la base por un problema UI. Solo ante daño de datos y aprobación explícita se suspenden escrituras, se selecciona el punto de recuperación, se restaura al destino aprobado, se reponen Storage/configuración y se concilian operaciones posteriores antes de reabrir. Una restauración puede perder escrituras posteriores y no revierte cobros/envíos. No se ejecutó nada de esto en producción.

## Alternativa lógica preparada, no ejecutada

scripts/staging_backup_drill.sh usa pg_dump custom y pg_dumpall --roles-only --no-role-passwords con PostgreSQL17, conexiones privadas vía PGSERVICEFILE/PGPASSFILE y permisos600. pg_restore conserva ownership/ACL con roles preparados; rechaza producción y nunca restaura encima del staging activo. Esta alternativa no fue el método ensayado y no hereda su tiempo medido.

## Ensayo de archivos completado

Se completó copia→borrado de foto ficticia→restauración al mismo nombre→SHA256idéntico en staging,7comprobaciones OK,32.606s. Ver STORAGE_BACKUP_RUNBOOK_20261121.md y storage-restore-20261121.json. Esto sustituye el pendiente de ensayo funcional de un archivo; el respaldo integral de TODOS los buckets de producción sigue siendo obligatorio antes de activar.
