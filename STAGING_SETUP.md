# PR #180: activar los entornos de pruebas existentes

Rama: `work/redesign-preview-20261003`. No cambiar `main`, Railway producción ni el proyecto Cloudflare de producción. No crear otro backend ni otro frontend.

## 1. Supabase: conseguir el esquema correcto

**Bloqueo actual:** el repositorio contiene migraciones parciales, no el esquema completo de la base actual. No se puede certificar una copia exacta a partir de esos archivos. No ejecutar `schema.sql` como si fuera toda Broquer. No restaurar un backup completo: incluiría datos reales.

1. Abre Supabase y selecciona el proyecto de producción **solo para leer su esquema**.
2. En el menú izquierdo haz clic en **SQL Editor**, después **New query**.
3. Copia el contenido de `staging/00-schema-inventory.sql` y haz clic en **Run**. Solo lee definiciones; no modifica tablas ni lee filas de clientes.
4. En el resultado, haz clic en **Export > Download CSV**. Ese archivo permitirá preparar y contrastar la migración exacta. Contiene definiciones de funciones: revísalo antes de compartirlo por si alguien hubiera escrito secretos directamente en una función.
5. En otra consulta pega `staging/01-export-bucket-settings.sql`, pulsa **Run** y guarda el texto de `staging_bucket_sql`. Solo contiene ajustes de buckets, ningún archivo.
6. Selecciona una base **independiente y vacía**, llamada `broquer-redesign-staging`. Si no existe, crea únicamente este proyecto de base de datos. Nunca seleccionar producción ni `broquer-beta`.
7. **Todavía no ejecutar las migraciones parciales a ciegas.** Falta generar y validar el esquema exacto con la exportación del paso 4, incluidos RLS, funciones, triggers, permisos y políticas de Storage. El seed está preparado, pero no se ha ejecutado ni certificado contra el esquema real.
8. Cuando esté importado y contrastado el esquema completo, ejecuta aquí el SQL de buckets obtenido en el paso 5. No copiar archivos de producción.
9. En **Authentication > Users > Add user > Create new user**, crea `qa-broquer@example.test`. Pon tú la contraseña, activa **Auto confirm user** y usa **Create user**, no **Invite user**. No compartir la contraseña aquí.
10. En **Authentication > URL Configuration**, Site URL: `https://staging.broquer.app`. Añade a Redirect URLs `https://staging.broquer.app/**`. Guarda. No añadir URLs de producción.
11. En **SQL Editor > New query**, pega `staging/02-seed.sql` y pulsa **Run**. Aborta toda la transacción si faltan tablas/columnas obligatorias o hay otros usuarios de Auth. No concede rol administrador ni modifica reglas de permisos.
12. Revisa el resultado: dos clientes ficticios, una propiedad, una cita/tarea, un contrato borrador y una conversación ficticia con dos mensajes e IA apagada. Si hay error de esquema, no alterar la tabla para acomodar el seed: hay que corregir el seed contra el esquema real.
13. En **Settings > API** (o **Connect > App Frameworks**, según la versión del panel), guarda la **Project URL**, la clave **publishable/anon** y el **Project reference**. La clave **service_role/secret** va únicamente en Railway, nunca en Cloudflare ni en este chat.
14. Deja sin configurar SMTP propio, proveedores Meta y webhooks de producción en esta base. Las pruebas de recuperación no deben enviar correos reales.

## 2. Railway: usar el staging que ya existe

1. Abre el proyecto actual y selecciona **staging** en el selector de entorno de la parte superior. Comprueba que no diga **production**.
2. Abre el servicio que tiene `brokr-main-staging.up.railway.app`.
3. Ve a **Settings > Source**, selecciona el repositorio `Brokr-main` y la rama `work/redesign-preview-20261003`. No cambiar la rama del servicio de producción.
4. Ve a **Variables > Raw Editor** y pon estas variables en este servicio/entorno. No usar referencias compartidas que apunten a la base de producción:

| Variable | Valor |
| --- | --- |
| `BROQUER_ENV` | `staging` |
| `BROQUER_STAGING_PROJECT_NAME` | `broquer-redesign-staging` |
| `BROQUER_STAGING_DB_REF` | La referencia del proyecto Supabase limpio |
| `SUPABASE_URL` | URL del Supabase limpio |
| `SUPABASE_PUBLISHABLE_KEY` | Clave pública de ese mismo proyecto |
| `SUPABASE_SERVICE_KEY` | Clave service_role/secret de ese mismo proyecto; pegarla tú aquí |
| `APP_URL` | `https://staging.broquer.app` |
| `FRONTEND_URL` | `https://staging.broquer.app` |
| `API_BASE_URL` | `https://brokr-main-staging.up.railway.app` |
| `BROQUER_API_BASE` | `https://brokr-main-staging.up.railway.app` |
| `RECORDATORIOS_ACTIVOS` | `false` |
| `BUSCADOR_PROPIEDADES_ACTIVO` | `false` |
| `STRIPE_SECRET_KEY` | Clave `sk_test_…` de Stripe en modo prueba; nunca `sk_live_…` |
| `STRIPE_WEBHOOK_SECRET` | Secreto del webhook de Stripe **de prueba**; pegarlo tú aquí |

5. Si existen `SUPABASE_ANON_KEY` o `SUPABASE_KEY`, elimínalas de staging o reemplázalas por la misma clave pública de staging; no conservar valores de producción. Revisa también las variables heredadas/compartidas.
6. Para suscripciones, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_AMPI`, `STRIPE_PRICE_EMPRESA_MENSUAL`, `STRIPE_PRICE_EMPRESA_ANUAL`, `STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL` y `STRIPE_PRICE_EMPRESA_EXTRA_ANUAL` deben tener IDs de precios creados en modo test; el código de Stripe define estos nombres en `core/stripe.py`. No copiar IDs live ni promociones de producción.
7. Deja vacías/elimina **en staging** `META_APP_SECRET`, `FB_APP_SECRET`, `WA_APP_SECRET`, `RESEND_API_KEY`, `CORREO_SECRET`, `CORREO_WEBHOOK_TOKEN`, `APNS_KEY_P8`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `EB_API_KEY` y `FIRMAME_API_KEY`. No registrar webhooks Meta/WhatsApp de clientes ni importar tokens reales. No hace falta poner estas llaves para probar el rediseño.
8. Haz clic en **Deploy** para aplicar los cambios pendientes. Abre **Deployments > último despliegue > View logs**. Si falla por una variable de aislamiento, corrige esa variable; no desactives la protección.
9. En **Settings > Networking**, conserva el dominio existente `brokr-main-staging.up.railway.app`. No crear otro servicio.

En staging el backend permite HTTPX solo al Supabase aprobado y a Stripe con credenciales test; bloquea SMTP y las demás integraciones. El bloqueo devuelve error real: **no simula que un mensaje fue enviado**. IA externa, EasyBroker y otras integraciones también quedan pendientes de pruebas independientes. Las redirecciones HTTP externas no se siguen. Producción conserva su comportamiento si `BROQUER_ENV` no es `staging`.

## 3. Cloudflare Pages: publicar en broquer-staging

1. Abre **Workers & Pages > broquer-staging**. Comprueba el nombre antes de cambiar ajustes.
2. En **Settings > Builds & deployments** (en algunas versiones **Settings > Build**), abre la configuración Git.
3. Para este proyecto de pruebas, establece **Production branch** en `work/redesign-preview-20261003`. Aquí “Production” significa el despliegue principal de **broquer-staging**, que sirve su dominio personalizado; no es la rama `main` ni el proyecto productivo de Broquer.
4. Framework preset: **None**. Root directory: raíz del repositorio. Build command: `python3 scripts/build_staging.py`. Build output directory: `dist`. Guarda.
5. En **Settings > Variables and Secrets** (o **Environment variables**), selecciona **Production** del proyecto **broquer-staging** y agrega:

| Variable | Valor |
| --- | --- |
| `BROQUER_STAGING_API_URL` | `https://brokr-main-staging.up.railway.app` |
| `BROQUER_STAGING_SUPABASE_URL` | URL del Supabase limpio |
| `BROQUER_STAGING_SUPABASE_KEY` | Solo clave pública publishable/anon de ese mismo Supabase |
| `SKIP_DEPENDENCY_INSTALL` | `1` |

6. Si quieres usar los despliegues Preview de la misma rama, agrega las mismas variables en **Preview**. Nunca introducir service_role, Stripe, Meta, Resend o EasyBroker en Cloudflare Pages.
7. En **Custom domains**, comprueba que `staging.broquer.app` esté asociado a **broquer-staging**. Conserva esa asociación.
8. En **Deployments**, ejecuta **Retry deployment** para el último commit de esta rama, o espera el despliegue automático por Git. Comprueba rama, commit y resultado **Success**.
9. Abre `https://staging.broquer.app` desde Safari de tu iPhone e inicia sesión con el usuario QA. La compilación reemplaza las URLs/clave pública en los archivos servidos; el código fuente de producción sigue conservado para su despliegue normal.

La compilación falla si falta configuración, se usa `main`, la API productiva, la base productiva conocida o una clave secreta. La política del navegador restringe las conexiones al backend y Supabase de pruebas. Publica solo archivos estáticos; excluye backend, SQL, scripts, tests y archivos secretos.

## 4. Prueba de aceptación pendiente

- Crear, editar y borrar solo registros ficticios; recargar y confirmar persistencia.
- Probar datos/vacío/error/cargando en cada flujo, además de sus validaciones y adjuntos.
- Probar agente, administrador y equipo con usuarios QA distintos; verificar que un agente no pueda leer/escribir registros ajenos. El seed inicial crea una sola identidad; no certifica la matriz de roles.
- Abrir formularios, enfocar inputs y cerrar teclado en iPhone/Safari y en el WebView real. La regla compartida impone mínimo 16px; aún falta comprobar la escala en el dispositivo.
- Confirmar Stripe modo test; no usar tarjetas reales. Verificar que WhatsApp, push y correo no entregan nada.
- Registrar cada resultado en `REDESIGN_COVERAGE.md`. “Probado con mock: superficie” no demuestra guardado ni permisos reales.
- Revisar los fallos de calidad existentes documentados en `REDESIGN_VALIDATION.md`: expectativas antiguas de fuente y tamaño del vendor ReactDOM. No se han eludido esas comprobaciones.
- Solo después de tu revisión y aprobación se podrá mergear el PR. Actualmente sigue siendo borrador.

Fuentes de paneles: https://developers.cloudflare.com/pages/configuration/build-configuration/ · https://docs.railway.com/variables · https://docs.railway.com/services · https://supabase.com/docs/guides/local-development/database-migrations
