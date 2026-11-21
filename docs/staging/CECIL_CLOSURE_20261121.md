# Cierre de staging: evidencia del 21/11/2026

No se modificaron main, producción ni variables de Railway/Cloudflare. PR220 y PR217 siguen draft, sin merge. No se recuperó A2. A3 entró mediante intervención del usuario y su sesión se conservó durante los recorridos.

## Pruebas por interfaz con A3

| Función | Recorrido observado | Resultado |
|---|---|---|
| Contactos | Crear contacto ficticio, recargar, editar, recargar y verificar, eliminar; estado vacío | OK UI |
| Leads | Crear oportunidad ficticia, recargar, mover Nuevo→Activo, editar nombre/notas, recargar y verificar, eliminar; pipeline vacío | OK UI |
| Contrato | Llenar arrendamiento con tres partes/direcciones ficticias, fechas, renta/deposito10000, generar y descargar Word | OK UI; DOCX45490bytes, partes/dirección verificadas en XML |
| Opinión de valor | Casa Altozano/Morelia,220m²terreno/180m²construcción,3recámaras/2baños/2estacionamientos | Falla: dos intentos UI terminan en Error en el análisis |
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

Los metadatos de10buckets/5objetos están en la copia, **los bytes de Storage no**. Falta un ensayo separado de archivos para declarar recuperación integral. El tiempo de producción no se conoce y no se infiere del staging. BACKUP_RUNBOOK_20261121.md documenta responsable, herramienta, pasos y límites.

## Piloto de producción: preparado, no autorizado ni activado

PR217 conserva flag de servidor apagado/allowlist vacía y checklist de activación/reversión, guardado de propiedades corregido, retorno y revocación. No recibe tablas/worker de staging. El UUID real de Salvador debe verificarse por administrador; nunca copiar el UUID de A3 a producción.

Antes de activar: resolver AVM y repetir su recorrido UI, ensayo Storage, revisión iPhone Safari/WebView por usuario y respaldo previo verificable del proyecto real, con ventana/custodio/aprobación. Issue221 (URLs Auth staging) sigue pendiente antes de probar flujos por correo. Fallos visuales se revierten apagando el flag, sin restaurar toda la base.
