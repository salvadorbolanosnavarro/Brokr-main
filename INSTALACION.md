# Broquer · WhatsApp (Recepción) — Instalación

Tres archivos:
- `whatsapp.py` — el motor (webhook + IA + envío).
- `schema.sql` — las tablas en Supabase.
- este `INSTALACION.md`.

---

## Paso 1 · Base de datos
Entra a Supabase → **SQL Editor** → pega todo `schema.sql` → **Run**.
Eso crea las 4 tablas (contactos, conversaciones, mensajes y mapeo de números).

## Paso 2 · El archivo
Copia `whatsapp.py` a la carpeta de tu backend (donde vive tu `main.py`).

Instala lo que falte:
```
pip install fastapi requests supabase openai
```

## Paso 3 · Conéctalo a tu app
En tu `main.py`, donde tienes tu `app = FastAPI()`, agrega:
```python
from whatsapp import router as whatsapp_router
app.include_router(whatsapp_router)
```
Eso deja tu webhook viviendo en:  `https://TU-APP.railway.app/whatsapp/webhook`

## Paso 4 · Variables de entorno (en Railway → Variables)

| Variable | Qué es | De dónde sale |
|---|---|---|
| `WHATSAPP_TOKEN` | Token permanente para enviar | Meta → System User token |
| `WA_VERIFY_TOKEN` | Una palabra que tú inventas | la pones aquí Y en Meta (paso 5) |
| `WA_APP_SECRET` | Para validar la firma (opcional) | Meta → App Settings → Basic |
| `SUPABASE_URL` | URL de tu proyecto | Supabase → Settings → API |
| `SUPABASE_SERVICE_KEY` | La **service_role** key | Supabase → Settings → API |
| `LLM_API_KEY` | Tu key del cerebro | Groq (o el que uses) |
| `LLM_BASE_URL` | Endpoint del LLM | `https://api.groq.com/openai/v1` (default) |
| `LLM_MODEL` | Modelo | `llama-3.3-70b-versatile` (default) |
| `DEFAULT_OWNER_ID` | El uuid de tu agente piloto | tu `auth.users` (Grupo Navarro) |
| `DEFAULT_AGENCIA` | Nombre de la agencia | `Grupo Navarro` |

> El cerebro está puesto en Groq para que pegue con tu stack. Si quieres que
> Recepción corra en Claude, cámbiame `LLM_BASE_URL`, `LLM_API_KEY` y `LLM_MODEL`
> (o te ajusto la función `recepcion_responde` para llamar a Anthropic directo).

## Paso 5 · Conectar el webhook en Meta
En tu app de Meta (developers.facebook.com) → WhatsApp → **Configuration**:
1. **Callback URL:** `https://TU-APP.railway.app/whatsapp/webhook`
2. **Verify token:** la misma palabra que pusiste en `WA_VERIFY_TOKEN`.
3. Da **Verify and Save** (si truena, revisa que la variable y la palabra sean idénticas).
4. En **Webhook fields**, suscríbete a:
   - `messages` (mensajes entrantes del cliente) — el básico.
   - `smb_message_echoes` (**Coexistence**: lo que el agente manda desde su celular).
   - `history` y `smb_app_state_sync` (**Coexistence**, opcionales: historial y contactos al conectar).

## Paso 6 · Probar
Manda un WhatsApp al número conectado (desde tu celular personal).
Debe contestarte Recepción en segundos, y en Supabase → Table Editor deben
aparecer el contacto, la conversación y los mensajes, con la calificación
llenándose sola.

---

## Coexistence (importante para tu caso)
Si el agente conecta su número con **Coexistence** (sigue usando su WhatsApp en el
cel + la API), el código ya lo contempla así:
- Cuando un cliente escribe, Recepción contesta al instante (como siempre).
- **En cuanto el agente contesta desde su celular, la IA se calla sola** en esa
  conversación (`ai_enabled` se apaga). Recepción es la red de seguridad que
  responde cuando tú no puedes, y se quita en cuanto tú entras. Sin encimarse.
- El agente puede volver a prender la IA desde la bandeja.

Detalles de Coexistence que conviene tener en mente:
- Usa dispositivos soportados; mensajes desde WhatsApp para Windows o WearOS no
  generan echo y no se sincronizan.
- No hay palomita azul (OBA) bajo Coexistence; si la quieres, es por Meta Verified.
- El número tiene un tope de 5 mensajes por segundo (de sobra para esto).

---

## Lo que falta (siguiente entrega)
- **La bandeja** (la pantalla donde tú ves las conversaciones y le quitas el
  control a la IA). Es rápida, pero la armo pegada a tu frontend para que se
  vea idéntica a Broquer — por eso necesito tu repo (ver nota abajo).
- **Plantillas** para los seguimientos fuera de la ventana de 24h.
- **Embedded Signup** para que cada agente conecte su número con un clic
  (esto es para cuando salgas del piloto).

## Notas honestas
- Tu zip no se pudo abrir de mi lado (error de lectura en la subida). Escribí
  esto para que pegue con tu stack de siempre, pero hay 2 puntos marcados en el
  código (`# usa tu cliente si ya tienes uno`) que conviene amarrar a tus
  helpers existentes. Si me lo re-subes, lo dejo exacto y de una vez te hago la
  bandeja.
- No pude probar este código contra un WhatsApp real desde aquí; déjalo correr
  en Railway y, si algo truena, me pasas el log y lo afino al toque.
