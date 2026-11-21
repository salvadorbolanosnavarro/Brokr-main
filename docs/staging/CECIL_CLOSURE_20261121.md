# Cierre de staging: estado comprobado y pendientes reales

No se cambió main, producción ni variables de Railway/Cloudflare. PR220 y PR217 siguen draft y sin merge. Preparación del piloto no equivale a aprobación de activarlo.

## Cuenta A3

El usuario creó A3 y proporcionó su nueva contraseña exclusiva de staging. Se actualizó solo el archivo privado fuera de git. Se observó inicialmente la sesión iniciada; se cerró para verificar reingreso y el flujo seguro del navegador devolvió «Correo o contraseña incorrectos». No se volvió a intentar automáticamente ni se inyectaron tokens al navegador. Una prueba independiente de la API sí autentica con la contraseña guardada. **El reingreso UI y los cuatro recorridos NO están aprobados.** No se recuperó A2.

A3 conserva rol agente y plan free; acceso funcional temporal7d para probar documentos sin cobros. UUID staging bd7e565d-c0c7-46d1-9cc2-70399ed97a91. Nunca usar este UUID en producción.

## Piloto: pruebas de servidor

El preview tiene Broquer original en raíz y Cecil en /cecil/, ambos contra la API/BD aisladas. El worker de Cloudflare valida la sesión con Auth de staging y lee una tabla RLS de solo lectura para el cliente. Solo A3 tiene flag activo. GET /ui/cecil comprueba identidad; las pantallas HTML Cecil también se protegen en el servidor mediante cookie HttpOnly/Secure/SameSite. API/Supabase mantienen sus propios permisos de negocio.

No se cambiaron variables. Se crearon dos tablas exclusivamente en staging: cecil_staging_pilot y cecil_staging_error_receipts, con RLS y sin permiso de cliente para modificar flags. SQL exacto: pilot-schema-20261121.sql. Esta implementación de control del worker NO se copia a producción; PR217 conserva el flag autenticado del backend Railway.

- A3: flag200 true y HTML Cecil200.
- B2: flag200 false; HTML Cecil302 a Broquer; POST de error403.
- Anónimo: endpoint de flag401.
- B2 intentando modificar el flag de A3:403.
- Apagado temporal: A3 flagfalse, HTML302; el mismo token sigue accediendo a su perfil200. Flag restaurado atrue solo para A3.
- Cliente: pruebas de estado de ida, vuelta y revocación conservan la sesión; revalida cada15s y al volver a la pestaña. Esto es prueba unitaria, **no certificación de clics en navegador real**.

## Errores

CSP permite únicamente el host de ingestión Sentry observado en la configuración pública, además de los servicios de staging. Se retira de la compilación de staging el loader heredado de producción y se envían eventos sanitizados a través del worker, con environment=staging. No se envían correos, tokens, cookies, mensajes arbitrarios o stacks con datos de clientes. Errores runtime se limitan a3 por página del piloto; el probe controlado requiere flag activo.

POST autenticado A3 /__staging/error-probe devolvió200, sentry_status200, sentry_accepted=true y receipt_saved=true. Event ID565301cf-35f2-4654-b484-e41dc7d4fc6b, confirmado después por SQL en la tabla de acuses. Esto demuestra aceptación por ingestión de Sentry y recepción del servidor; no se abrió el dashboard de incidencias de Sentry ni se verificó el botón mediante clic UI. El proyecto Sentry es el existente y el evento se etiqueta staging.

## Cobertura final de esta sesión

| Requisito | Evidencia | Estado |
|---|---|---|
| A3 sale y vuelve a entrar por UI | Salida observada; reingreso seguro rechazado | Pendiente |
| Contactos por interfaz | No se ejecutó tras el bloqueo de acceso | Pendiente |
| Leads por interfaz | No se ejecutó tras el bloqueo de acceso | Pendiente |
| Contratos por interfaz | No se ejecutó tras el bloqueo de acceso | Pendiente |
| Opinión de valor por interfaz | No se ejecutó tras el bloqueo de acceso | Pendiente |
| A3 dentro/B2 fuera por servidor | pilot-server-live-20261121.json | OK |
| Cliente no puede modificar flag | pilot-client-write-denied-20261121.json | OK |
| Revocación conservando sesión API | pilot-revocation-live-20261121.json | OK servidor |
| Ida/vuelta y revocación por botones reales | Implementados; contrato de estado pasa | Pendiente UI |
| Error de prueba recibido | Sentry200 + acuse SQL, environment staging | OK servidor; botón UI pendiente |
| Publicación aislada |304 archivos HTTP/hash exactos, cero refs producción | OK |
| ISR seis casos contra main | Mismos46 campos numéricos/booleanos; fixtures iguales | OK offline |
| Respaldo/restauración completa medida | Copias físicas observadas; ensayo no ejecutado | Pendiente |
| Procedimiento de recuperación | BACKUP_RUNBOOK_20261121.md y script con preflight | Preparado; no ensayado |
| PR piloto producción | #217 con checklist, guardado corregido, revocación, flag apagado | Preparado, sin publicar |
| iPhone Safari/WebView | Dispositivo físico del usuario | Pendiente |

## Veredicto

**NO activar producción todavía.** Las cuatro pruebas UI, el regreso real por botones y una restauración completa con Storage/timing siguen abiertos. Copias automáticas existentes y unit tests no sustituyen esos ensayos. Un rollback visual apaga el flag; no restaura toda la base ni borra escrituras de otros usuarios. PR217 no resuelve el UUID real de Salvador hasta que un administrador lo confirme por el correo objetivo.

La intervención pendiente se concentra al final: recuperar el acceso A3 en el navegador seguro y habilitar un destino de restauración aislado (aprobación expresa del coste cotizado o conexión/destino privados existentes). No poner secretos en chat.

Evidencia visual del proyecto de staging: staging-backups-20261121.jpg. La etiqueta main/PRODUCTION de Supabase se refiere a la rama interna de ESTE proyecto de pruebas, no al proyecto de producción urtgysmtnvoqaljuhntz.
