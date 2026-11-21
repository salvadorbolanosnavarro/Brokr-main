# Cierre de staging: evidencia del 21/11/2026

No se modificaron main, producción ni variables de Railway/Cloudflare. PR220 y PR217 siguen draft, sin merge. No se recuperó A2. A3 entró mediante intervención del usuario y su sesión se conservó durante los recorridos.

## Pruebas por interfaz con A3

| Función | Recorrido observado | Resultado |
|---|---|---|
| Contactos | Crear contacto ficticio, recargar, editar, recargar y verificar, eliminar; estado vacío | OK UI |
| Leads | Crear oportunidad ficticia, recargar, mover Nuevo→Activo, editar nombre/notas, recargar y verificar, eliminar; pipeline vacío | OK UI |
| Contrato | Llenar arrendamiento con tres partes/direcciones ficticias, fechas, renta/deposito10000, generar y descargar Word | OK UI; DOCX45490bytes, partes/dirección verificadas en XML |
| Opinión de valor | Casa Altozano/Morelia,220m²terreno/180m²construcción,3recámaras/2baños/2estacionamientos;7comparables,$5,530,000;PDF25891bytes/2páginas descargado y verificado | OK UI después de #224 |
| Botones del piloto | Volver a Broquer → avatar Salvador Pruebas Cecil A3; Probar el diseño Cecil → Cecil, sin login | OK UI |
| Error controlado | Clic Probar registro de errores, mensaje recibido; acuse SQL sentry_accepted=true | OK UI/servidor, f6149a79-a96a-4958-ab34-1bc164c02d92 |
| Revocación en interfaz | Flag A3false → recarga vuelve a Broquer con avatar A3 y sin botón; reactivar soloA3 y entrar con botón real | OK UI; no acredita el tiempo de revocación sin recarga |

Contacto y lead ficticios eliminados por sus botones reales. No se enviaron contratos a firma, correo o WhatsApp. Word de prueba en ui-a3-20261121/; no es un contrato celebrado. La prueba acredita generación técnica, no revisión jurídica.

## Controles de servidor y aislamiento

Worker valida bearer con Auth de staging y flag RLS de solo lectura para clientes. A3flag200true/HTML200; B2flag200false/HTML302 a Broquer, error403; anónimo401; cliente no puede escribir flags403. Revocación API conservó el mismo token/perfil200. Solo A3 habilitada. Estas pruebas B2 son de servidor: no se atribuyen a un recorrido UI de B2.

Sentry usa el host exacto permitido por CSP, environment staging y códigos sanitizados sin PII/tokens. La ingestión aceptó el evento y el acuse SQL quedó guardado; no se abrió el Dashboard de Sentry para validar su agrupación.

304archivos publicados comprobados200/hash exacto y sin api.broquer.app ni ref de producción. ISR:6casos con46campos numéricos/booleanos idénticos a main, datos ficticios offline.7tests focales Python,13checks routing y máquina de estados Node pasan.

## Restauración y borrado

Copia física de staging21/11 07:05:17UTC restaurada en proyecto temporal separado, autorizado hastaUSD10/mes por horas. Primer estado saludable en276.398s (4min36s).124tablas del punto temporal validadas:115hashes íntegros y9conteos/hashes al punto del respaldo; esquema, RLS, funciones, triggers, índices, roles y extensiones sin diferencias. Aislamiento RLS probado. Destino hdpstaqcswrdcrozcxrq **borrado**, confirmado por API y Dashboard; ver restore-20261121/timing.json y summary.json.

Los metadatos de10buckets/5objetos están en la copia de base, **los bytes de Storage no**. Se completó el ensayo separado: una foto ficticia propia copiada a carpeta de respaldo, borrada y restaurada a su ruta original con SHA256/tamaño idénticos;7checks,32.606s. No equivale a un backup integral de producción. Ver STORAGE_BACKUP_RUNBOOK_20261121.md y storage-restore-20261121.json. El tiempo de producción no se conoce y no se infiere del staging. BACKUP_RUNBOOK_20261121.md documenta responsable, herramienta, pasos y límites.

## Piloto de producción: preparado, no autorizado ni activado

PR217 conserva flag de servidor apagado/allowlist vacía y checklist de activación/reversión, guardado de propiedades corregido, retorno y revocación. No recibe tablas/worker de staging. El UUID real de Salvador debe verificarse por administrador; nunca copiar el UUID de A3 a producción.

Antes de activar: revisión iPhone Safari/WebView por usuario y respaldo previo verificable de base Y todos los bytes de Storage del proyecto real, con ventana/custodio/aprobación. Los cuatro recorridos UI y recuperación de un archivo están cerrados. Ver CECIL_PILOT_FINAL_CHECKLIST_20261121.md. Issue221 (URLs Auth staging) sigue pendiente antes de probar flujos por correo. Fallos visuales se revierten apagando el flag, sin restaurar toda la base.

## Cierre de AVM y listas de seguridad

Diagnóstico conectado antes del arreglo:409 SIDE_EFFECTS_DISABLED por dos GET a EasyBroker. PR224 fusionado SOLO a work/redesign-preview-20261003, merge e7ca1c4868d36f905f75c06d6e416873406b4a7b; Railway staging informa despliegue success. El lector omite fuentes de integraciones bloqueadas antes de HTTP/Firecrawl y en redirects; EasyBroker NO queda autorizado. Se permiten rutas de consultas Firecrawl,SerpAPI,GooglePlaces/geocode/customsearch,Banxico,Groq/Anthropic/Gemini-texto. Operaciones distintas a esas consultas y todos los métodos de Stripe,Meta/WhatsApp,Instagram/Facebook,Resend/SMTP,APNs,EasyBroker continúan bloqueados.

40tests focales y1174locales (4omitidos) pasan. CI backend reporta1172pruebas, sin fallos unitarios; Quality solo falla por los dos preexistentes del #219. Después del deploy: Stripe503/external_call_performedfalse y envíoWhatsApp409/simulatedtrue/external_call_performedfalse con conexión ficticia inválida de A3; fixture eliminado. No se envió nada a contactos reales. Evidencia avm-readonly-policy-tests-20261121.json y avm-live-safety-20261121.json.

Resultado A3 UI después del deploy:18:30:04UTC inicio,18:32:28UTC resultado observado,7comparables,$5,530,000 y PDF2páginas/25891bytes. Evidencia UI/PDF/hash en ui-a3-20261121/avm-ui-success-20261121.json. Firecrawl se muestra inactivo por configuración y varias fuentes con lectura bloqueada; el éxito funcional no certifica la exactitud de una valuación ni la configuración de esos proveedores. No se cambiaron variables para ocultar esa limitación.
