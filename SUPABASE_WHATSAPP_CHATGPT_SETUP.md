# Setup de Supabase para WhatsApp de ChatGPT

Este módulo usa tablas **independientes** del WhatsApp legacy. Antes de abrir el pull request o desplegar el backend, aplica la migración `whatsapp_chatgpt_schema.sql` en el proyecto de Supabase que usa Broquer.

## 1. Ejecutar la migración

1. Abre Supabase.
2. Entra a **SQL Editor**.
3. Crea un query nuevo.
4. Copia y ejecuta completo el contenido de `whatsapp_chatgpt_schema.sql`.
5. Confirma que exista la tabla `public.wac_numbers`.

La tabla guarda los números conectados por usuario, el WABA, el `phone_number_id`, el token de Meta y el estado operativo del número.

## 2. Variables requeridas en el backend

Configura estas variables en Railway o en el entorno donde corre `main.py`:

| Variable | Uso |
| --- | --- |
| `SUPABASE_URL` | URL del proyecto Supabase. |
| `SUPABASE_ANON_KEY` | Llave anon para validar la sesión del usuario. |
| `SUPABASE_SERVICE_KEY` | Llave service role para guardar el número conectado. |
| `META_APP_ID` | App ID de Meta/Facebook Login for Business. |
| `META_APP_SECRET` | App secret para intercambiar el `code` por token. |
| `META_LOGIN_CONFIG_ID` | ID del login configuration de Embedded Signup. |
| `WA_EMBEDDED_SIGNUP_CONFIG_ID` | Alias aceptado si no se usa `META_LOGIN_CONFIG_ID`. |
| `WA_REGISTER_PIN` | PIN de registro del número; por defecto usa `123456`. |
| `META_GRAPH_VERSION` | Versión de Graph API; por defecto `v23.0`. |

## 3. Checklist en Meta

- El dominio público de Broquer debe estar permitido en la configuración de Facebook Login / JavaScript SDK.
- El Login Configuration debe ser de **WhatsApp Embedded Signup**.
- La app debe tener permisos de WhatsApp Business Management y WhatsApp Business Messaging.
- El webhook de la app debe estar configurado en Meta para recibir eventos de WhatsApp cuando se active la automatización completa.

## 4. Validación rápida

Con una sesión iniciada en Broquer, abre directamente:

```text
/whatsapp-chatgpt.html
```

Si falta alguna variable, la pantalla muestra cuáles faltan antes de iniciar Meta Embedded Signup. Si todo está configurado, el botón **Conectar mi número ahora** abre Meta y, al terminar, guarda el número en `public.wac_numbers`.
