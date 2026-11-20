# Cecil staging: publicación y cobertura — 19 noviembre 2026

Preview real: https://work-cecil-staging-preview-2.broquer-staging.pages.dev
PR #220 sigue draft, sin merge al #217 ni main. Backend staging conserva #218. main permanece en dac7118c952deeda4f6b9160c05f19b0a42ca8a0. No se cambiaron variables ni configuración de producción.

## Fuga corregida en la publicación real

El proyecto Pages publica desde la raíz, no desde dist. La compilación anterior estaba validada pero no era lo que se servía: landing y acceso aún conservaban conexiones de producción. Se añadió routing avanzado _worker.js en el MISMO proyecto: solo sirve los archivos de preview-public permitidos por preview-public-manifest.json; las fuentes raíz/backend quedan fuera del routing. No hay un proyecto ni servicio nuevo ni cambios de variables. El paquete se genera con scripts/build_staging.py + scripts/package_cecil_preview.py. Quedan 53 pantallas, en raíz y /cecil, con la misma API staging y BD tymhlvawnqadqgwnpruk. Los HTML/JS y todos los demás archivos publicados se revisan byte a byte contra referencias prohibidas, incluso binarios. Se excluyen archivos Python, SQL y cachés del paquete.

CSP efectiva: connect-src self + API Railway staging + Supabase staging (HTTPS/WSS). El worker añade X-Cecil-Preview: staging-only. Se rechaza cualquier host ajeno al proyecto staging y todo método distinto de GET/HEAD. No se utiliza proxy hacia producción. Las solicitudes de la app usan directamente staging.

La llamada de inicio instagram/feed está reescrita a https://brokr-main-staging.up.railway.app/instagram/feed. Se observó completada en navegador, a través de PerformanceObserver (no es una captura de DevTools Network). Para reproducir evidencia pública: /landing.html?qa=network. El panel QA solo aparece con ese parámetro y muestra origen/ruta, sin queries, credenciales, cuerpos ni cabeceras. Captura: network-staging-20261119.jpg.

## Evidencias y pruebas

- Cloudflare bot confirma deploy de 54cff5f en https://bea9c3cb.broquer-staging.pages.dev y el alias estable de preview.
- published-files-live-20261119.json: 342/342 archivos servidos con HTTP200, SHA256 idéntico al manifiesto, encabezado staging-only y cero referencias prohibidas. _headers es archivo de control de Cloudflare: se escanea localmente, no se sirve por HTTP.
- Suite #220: 1,152 pruebas OK, 4 omitidas. Incluye prueba que falla si cualquier archivo publicado contiene api.broquer.app o urtgysmtnvoqaljuhntz (incluso binarios y mayúsculas).
- 13 comprobaciones Node de routing: archivos permitidos, fuentes privadas denegadas, host no staging denegado y POST denegado. Sintaxis JS correcta.
- ISR: seis casos coinciden con main para todos los campos numéricos y booleanos, con datos e índices sintéticos idénticos. No hubo llamadas a producción ni se afirma validación fiscal con Banxico real. Evidencia: isr-parity-20261119.json; runner tests/check_cecil_isr_parity.cjs.
- Golden HTTP actualizado exclusivamente con GET /ui/cecil, endpoint intencional heredado del #217; ningún otro contrato cambió. El constructor de producción rechaza esta rama con cambios de preview. El inventario de deuda excluye exclusivamente directorios de salida dist/preview-public; su contenido se verifica con manifiesto y auditoría. El comentario inicial de app-shell se acortó sin cambiar instrucciones JS ni elevar límites.
- Stripe staging ya verificado: HTTP503/STAGING_STRIPE_TEST_KEY_REQUIRED/external_call_performed=false, en live-safety-20261119.json.

## Pruebas conectadas A2/B2 — 19 de noviembre, actualización final

El usuario desactivó Confirm email en Supabase staging. Las cuentas antiguas A/B se ignoraron sin modificarlas. Se registraron mediante el formulario real del preview A2 y B2 (aliases +cecila2 y +cecilb2) con los acuerdos expresamente autorizados: ambas entraron directamente. Contraseñas y sesiones permanecen fuera de git y de estos informes.

El conector Supabase confirmó proyecto broquer-redesign-staging, ref tymhlvawnqadqgwnpruk, ACTIVE_HEALTHY. Se concedió acceso funcional temporal hasta 2026-11-26 20:31:16 hora Ciudad de México únicamente a esos dos UUID/correos. Ambas conservan rol agente y plan free; no se cambiaron RLS, schema, claves, variables ni suscripciones Stripe. El SQL exacto está en qa-access-seed-20261119.sql; no debe ejecutarse contra otro proyecto.

Para probar el envío autenticado se creó un wac_numbers de A2 con ID y token manifiestamente inválidos. POST /whatsapp-chatgpt/send-test devolvió HTTP409, simulated=true, external_call_performed=false, code=SIDE_EFFECTS_DISABLED, provider=meta, method=POST. Se eliminó después ese fixture exacto. No se utilizó ningún número real ni token Meta real.

Se corrigió un defecto real de la UI: Guardar inmueble buscaba el botón dentro del formulario aunque el nuevo footer está fuera. Ahora utiliza SubmitEvent.submitter y fallback explícito. Commit e322d335 ya publicado en el preview; creación y edición por interfaz verificadas después del deploy. Prueba de regresión en el constructor.

| Función | Broquer actual | Cecil | OK/Falla |
|---|---|---|---|
| Registro A2/B2 | Flujo de referencia, sin registrar en producción | Dos registros UI y sesiones reales sin correo | OK |
| Propiedad: crear/editar/eliminar | Contrato actual de API; sin escrituras prod | API y BD reales, ambas cuentas; crear/editar también UI | OK |
| Contacto: crear/editar/eliminar | Contrato actual de API; sin escrituras prod | API/BD reales, ambas cuentas | OK API; UI completa no recorrida |
| Lead: crear/editar/eliminar | Contactos con es_potencial=true | API/BD reales, ambas cuentas | OK API; UI completa no recorrida |
| Subir/borrar fotos | Storage actual | Bytes reales upload/read/delete; UI subir/quitar/guardar | OK |
| Ficha técnica | Renderizador backend actual | HTTP200, descarga PDF200 y texto del inmueble ficticio comprobado | OK API; generación UI no certificada |
| Contrato | Generador backend actual | HTTP200 DOCX, XML contiene las dos partes ficticias | OK API; UI completa no recorrida |
| Opinión de valor | Endpoint backend actual | HTTP200, valor y 13 comparables reales de mercado, inmueble de prueba | OK API; UI completa no recorrida |
| ISR mismos datos | Fuente main dac7118, seis escenarios | 46 campos numéricos/booleanos por caso idénticos con índices sintéticos; UI calculó además con Banxico real | OK equivalencia; ver límites abajo |
| A no ve/edita/elimina B y viceversa | Modelo de ownership actual | Lectura cruzada vacía, edición 403/404; borrado cruzado no elimina, ownership de fotos conservado | OK |
| WhatsApp desde A2 | Endpoint real, sin mensajes de producción | POST autenticado409 simulated=true y external_call_performed=false | OK |
| Stripe | Sin cobros producción | Evidencia previa HTTP503 STAGING_STRIPE_TEST_KEY_REQUIRED | OK |
| Network autenticado sin producción | No se navegó producción | Inventario autenticado: solo API/DB de staging; CSP restrictiva. Inicio Instagram ya corregido | OK en tráfico observado |
| Archivos publicados | Fuentes producción no servidas | 342/342 auditados HTTP/hash y prueba de todos los bytes del paquete | OK |
| Safari / WebView iPhone | Sin cambios producción | Lo comprobará el usuario en dispositivo real | Pendiente usuario |

### Evidencias y límites

- connected-tests-20261119.json y delete-tests-20261119.json: CRUD, lectura/edición/borrado cruzados. Los seis registros creados por API fueron eliminados. Queda un inmueble B2 claramente QA, creado/editado en UI, para revisión; su foto retirada y el objeto huérfano se limpiaron.
- whatsapp-storage-tests-20261119.json conserva el intento inicial de sembrar WhatsApp por REST que RLS rechazó403 y el envío404 sin número conectado; NO se cuentan como simulación. La evidencia válida posterior está en whatsapp-simulated-20261119.json.
- Las funciones pagadas rechazaron inicialmente las cuentas free con402. Después del acceso temporal se generaron ficha y contrato: document-tests-20261119.json, document-download-tests-20261119.json, QA-A2-ficha.pdf y QA-A2-contract.docx. Ningún token de descarga se publica.
- AVM agotó la primera espera cliente100s. Reintento con300s acorde al timeout180s del modelo terminó200: avm-connected-20261119.json y QA-A2-opinion-valor.json. No se certifica precisión de mercado ni rendimiento de producción; la latencia es una observación a revisar.
- ISR: isr-parity-20261119.json y screenshot isr-live-20261119.jpg. UI: terreno, venta2,800,000, compra1,350,000, noviembre2005, firma20/11/2026, comisión112,000, escritura20,000. INPC63.577256 y147.014044; costo actualizado3,337,890; pérdida669,890; ISR0. Comparación de seis casos es offline con fixtures iguales, no pruebas HTTP contra producción ni certificación fiscal.
- authenticated-network-20261119.txt y capturas account-a2-signed-in.jpg / account-b2-connected-inventory.jpg documentan sesiones y orígenes observados. Observar inventario no equivale a recorrer cada pantalla ni cada endpoint.
- Issue #221 abierto para Site URL/Redirect URLs de Supabase staging. No se modificó Auth URL; antes de flujos de correo debe corregirse y probarse. https://github.com/salvadorbolanosnavarro/Brokr-main/issues/221

No se declara listo para producción. Falta iPhone real y recorrido UI integral de contactos, leads, contratos y AVM. #217 y #220 siguen sin mergear; main, infraestructura y variables de producción intactas.
