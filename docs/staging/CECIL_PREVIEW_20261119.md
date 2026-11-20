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

## Cuentas: ambos registros aceptados, confirmación de correo pendiente

El usuario autorizó explícitamente aceptar Términos, Contrato de suscripción y Aviso de Privacidad exclusivamente para A y B. Se aceptaron y se enviaron ambos registros mediante el formulario real del preview, con correo/contraseña y teléfono ficticio, sin Google.

- A: salvadorbolanosnavarro+cecila@gmail.com.
- B: salvadorbolanosnavarro+cecilb@gmail.com.

Para ambos, el formulario mostró que envió el correo de confirmación y que se necesita confirmarlo para entrar. Esto acredita la aceptación del registro por el flujo de la app; NO acredita que ya exista una sesión activa ni que el correo haya llegado a Gmail. El usuario debe confirmar los dos correos. No se desactivó la verificación ni se cambiaron variables.

Las contraseñas se conservaron únicamente en el archivo privado fuera de git; no se incluyen en informes ni capturas (los campos aparecen enmascarados). Evidencia sanitizada: account-registration-20261119.json y account-a/account-b-confirmation-20261119.jpg. Las pruebas CRUD, medios, documentos, A/B y WhatsApp autenticados continúan pendientes de estas confirmaciones.

Los controles GitHub Quality y Frontend Canon Quality del código fc4547ba terminaron en SUCCESS (runs 44641399624 y 44641399563).

## Tabla de cobertura actual

| Función | Broquer actual | Cecil | OK/Falla |
|---|---|---|---|
| Registro correo/contraseña A/B | Flujo de referencia | Ambos registros aceptados; falta confirmar correo | OK registro; sesión pendiente |
| Bloqueo Stripe | Sin ejecutar cobros prod | Staging real: 503, sin llamada externa | OK |
| Inicio: Instagram | Referencia de código | Navegador observa API staging | OK |
| Publicación sin referencias prod | Fuentes actuales no publicadas en preview | 342/342 archivos verificados por HTTP y hash | OK |
| ISR con mismos datos | Motor de main + fixtures sintéticos | Seis casos idénticos | OK offline; UI autenticada pendiente |
| Crear/editar/eliminar propiedad | Sin escrituras prod | Pendiente confirmar correos A/B | Pendiente |
| Crear/editar/eliminar contacto | Sin escrituras prod | Pendiente confirmar correos A/B | Pendiente |
| Crear/editar/eliminar lead | Sin escrituras prod | Pendiente confirmar correos A/B | Pendiente |
| Subir/borrar fotos | Sin escrituras prod | Pendiente confirmar correos A/B | Pendiente |
| Ficha técnica | Código actual de referencia | Pendiente prueba autenticada | Pendiente |
| Contrato | Código actual de referencia | Pendiente prueba autenticada | Pendiente |
| Opinión de valor | Código actual de referencia | Pendiente prueba autenticada | Pendiente |
| A no ve/edita B | Sin escrituras prod | Pendiente dos sesiones reales | Pendiente |
| Envío WhatsApp simulado | Sin mensajes prod | Pruebas mock; real anterior 401 sin sesión | Pendiente |
| Network dentro de módulos autenticados | Sin acceso prod | Pendiente sesión; CSP restringe destinos | Pendiente |
| Safari/WebView iPhone | Sin cambios | Usuario probará al final | Pendiente |

Un mock, 401, equivalencia offline o pantalla pública no se cuenta como una prueba funcional autenticada ni certificación de producción.
