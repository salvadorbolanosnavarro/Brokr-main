# Cecil staging preview — 19 noviembre 2026

PR de origen: #217 (sin merge a main). Rama exclusiva: work/cecil-staging-preview-20261119.

Se reutiliza el compilador del #217 y su snapshot de diseño 086fd40e. El modo staging exige la rama de preview, la API Railway staging y la BD tymhlvawnqadqgwnpruk; elimina el guard de piloto de producción porque este preview completo ya está aislado. El modo original de piloto permanece sin activar. Las variables públicas existentes de Cloudflare deben estar disponibles en Preview; si faltan, el build falla y no se cambian variables.

Build existente: python scripts/build_staging.py; salida dist. Usa BROQUER_STAGING_API_URL, BROQUER_STAGING_SUPABASE_URL y BROQUER_STAGING_SUPABASE_KEY públicos existentes. No incluye runtime demo. CSP restringe conexiones a staging. 53 pantallas bajo /cecil y rutas públicas equivalentes en raíz. Release auditable: /preview-release.json.

Validación local: 6 pruebas Cecil correctas (incluidas 2 nuevas de compilación/configuración). Se comprueban todos los HTML/JS/CSS/JSON/SVG compilados: sin API/base/llave pública de producción ni demo-runtime; rechaza main, API de producción, BD equivocada, llave secreta y modo demo. El test de navegador check_cecil_rollout.cjs no se ejecutó: falta Chromium del runner; no se cuenta como prueba pasada.

## Evidencia backend

#218 mergeado SOLO a work/redesign-preview-20261003 en 343defd4d57efe71268be2617d5afb668e254bd5. Railway reporta deploy success. Evidencia HTTP exacta en live-safety-20261119.json: checkout devuelve 503 STAGING_STRIPE_TEST_KEY_REQUIRED / external_call_performed=false. WhatsApp devuelve 401 sin sesión; esto NO acredita la simulación de envío. Requiere iniciar sesión con cuenta staging y un número/conversación ficticios vinculados. No se envió ningún mensaje autenticado.

## Cobertura funcional — resultados reales pendientes de autenticación

| Función | Broquer actual | Cecil | OK/Falla |
|---|---|---|---|
| Stripe: impedir cobro con llave inválida staging | No se ejecuta cobro en producción | API staging real 503, sin llamada externa | OK |
| WhatsApp: simular envío | No se envían mensajes en producción | Backend probado con mocks; API real 401 sin sesión | Pendiente |
| Crear, editar y eliminar propiedad | Referencia código actual; sin escrituras prod | Pendiente cuenta staging | Pendiente |
| Crear, editar y eliminar contacto | Referencia código actual; sin escrituras prod | Pendiente cuenta staging | Pendiente |
| Crear, editar y eliminar lead | Referencia código actual; sin escrituras prod | Pendiente cuenta staging | Pendiente |
| Subir y borrar fotos | Sin escrituras prod | Pendiente cuenta staging | Pendiente |
| Generar ficha técnica | Código de referencia actual | Pendiente datos y cuenta staging | Pendiente |
| Generar contrato | Código de referencia actual | Pendiente datos y cuenta staging | Pendiente |
| Opinión de valor | Código de referencia actual | Pendiente datos y cuenta staging | Pendiente |
| ISR: comparar mismos casos | Pendiente ejecutar casos comparativos | Pendiente ejecutar casos comparativos | Pendiente |
| A no ve ni edita datos de B | Sin escrituras prod | Requiere dos cuentas staging | Pendiente |
| API/BD exclusivamente staging | API/base de producción como referencia prohibida | Build sin referencias de producción, CSP restrictiva | OK local; Network autenticado pendiente |
| Safari iPhone | No se modifica | Requiere dispositivo real | Pendiente |
| WebView iPhone | No se modifica | Requiere app/dispositivo real | Pendiente |

No se interpreta una prueba local, un mock, un 401 ni una vista responsive de escritorio como certificación real de producción o iPhone.
