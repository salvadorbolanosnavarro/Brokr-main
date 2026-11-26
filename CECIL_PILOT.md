# Cecil: piloto privado sobre Broquer

Autorizado por Salvador el22/nov/2026 exclusivamente para salvadorbolanosnavarro@gmail.com. No ampliar a otros usuarios. Antes de activar deben estar verificadas las copias y el regreso a Broquer.

## Infraestructura comprobada

GitHub Settings → Pages publica producción en broquer.app desde main, carpeta raíz. Railway proyecto brokr-api-railway, servicio brokrebapi, entorno production, publica api.broquer.app y despliega main automáticamente esperando CI. Cloudflare Pages broquer-staging es exclusivamente staging: no cambiarlo ni usar su compilador en producción.

El piloto incorpora un workflow Pages pilot que prepara los archivos web originales, sin alterar sus bytes, y añade /cecil/ con servicios reales. Excluye backend, SQL, tests y respaldos. El dominio y DNS se conservan. GitHub Pages debe usar Source: GitHub Actions para evitar que el publicador automático de la raíz compita con este artefacto. El job deploy solo se ejecuta desde main; los PR solo construyen el artefacto, nunca lo publican.

## Respaldo autorizado y verificado

- Copia física de producción disponible22/nov/2026 08:35:51UTC. Su mecanismo fue restaurado en staging:4min36s,124tablas. No se restauró producción.
-476archivos de Salvador,202006523bytes, copiados al bucket PRIVADO adjuntos-historial, carpeta cecil-pilot-backup-20261122 dentro de su UUID. Original/copia SHA256 idénticos476/476; originales intactos. Conteo/tamaño confirmados desde la base.
-28622filas en15tablas exportadas privadamente; conteos e IDs cotejados15/15. Incluye propiedades/contactos/leads/tareas, documentos y machotes de contratos y relaciones/eventos. JSON exacto de PostgreSQL y manifiestos SHA256. No incorporar datos privados al repositorio ni al frontend.
- Respaldo integral externo de Storage diferido explícitamente al issue225. La copia en el mismo proyecto no protege ante pérdida total del proyecto.

## Publicación y activación

1. Confirmar que main permanece en la base 0fc8733 (26/nov/2026: integra el módulo ACM «Análisis comparativo», que reemplaza en el menú a la Estimación de valor; diseño d5b6234c = 66a8ed2e + solo el ACM con las hojas de estilo del diseño, rama cecil/diseno-impuestos; base anterior 9378291); si avanzó, integrar y repetir pruebas. No desactivar la protección del constructor.
2. Preparar en Railway únicamente CECIL_UI_ENABLED=false y CECIL_UI_USER_IDS con el UUID real verificado de Salvador. No usar A3/B2 ni correo editable del cliente. No cambiar otras variables.
3. Con los checks y la construcción Pages en verde, seleccionar GitHub Pages Source: GitHub Actions, conservando broquer.app y HTTPS.
4. Fusionar PR217 a main con el SHA revisado y observar ambos despliegues. Mantener el flag apagado. Verificar Broquer habitual, /ui/cecil rechazando solicitudes sin sesión, artefacto Cecil real y ausencia de configuración staging.
5. Revisar elegibilidad por servidor, allowlist de exactamente una cuenta y sesión válida. Cambiar solo CECIL_UI_ENABLED=true cuando las verificaciones anteriores pasen.
6. En la cuenta de Salvador, pulsar Probar el diseño Cecil, Volver a Broquer y volver a entrar; conservar la sesión. Verificar que otras cuentas no reciben el botón ni elegibilidad.
7. En Cecil, Probar registro de errores envía un evento fijo sin usuario, petición ni breadcrumbs. Solo muestra Sentry aceptó cuando el transporte devuelve2xx para ese event_id; no confundir SDK invocado o cola vacía con aceptación. Registrar event_id/estado; la indexación en el panel Sentry es una comprobación distinta.
8. No ampliar a nadie más sin nueva aprobación.

## Reversión

Primero apagar CECIL_UI_ENABLED y desplegar. Revalidación cada15s/al recuperar visibilidad; ante fallo de elegibilidad Cecil vuelve a Broquer sin borrar tokens. Si el frontend está bloqueado, abrir la ruta habitual y restaurar la publicación anterior.

Versión anterior de main: dac7118c952deeda4f6b9160c05f19b0a42ca8a0. Railway deployment previo4ada004a-4ae6-4ad2-93dc-a43b705d26be. GitHub Pages deployment previo actions/runs/42901159196. Si hace falta revertir el merge, crear revert revisable y publicar main con GitHub Pages Source: Deploy from a branch, main /root, conservando dominio/HTTPS. No forzar historial ni borrar commits.

Un fallo visual se revierte por flag/artefacto, no restaurando toda la base. Recuperación de filas/archivos exige conciliar escrituras posteriores y limitarse al UUID de Salvador. Nunca tocar filas de otra cuenta ni restaurar datos sobre producción sin evaluar el daño real.
