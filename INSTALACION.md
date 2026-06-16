# Broquer · WhatsApp (Recepción + Bandeja) — Instalación

Cuatro archivos:
- `whatsapp.py` — el motor (webhook + Recepción IA + envío). Hecho con **tu** stack:
  httpx, Supabase por REST, Anthropic (`claude-sonnet-4-6`). **No instala nada nuevo.**
- `bandeja.html` — la bandeja (ver conversaciones, tomar el control, prender/apagar la IA).
- `schema.sql` — las tablas en Supabase.
- este `INSTALACION.md`.

> Sin dependencias nuevas: `httpx` ya está en tu `requirements.txt`, y el cerebro usa
> tu `ANTHROPIC_API_KEY` que ya tienes configurada.

---

## Paso 1 · Base de datos
Supabase → **SQL Editor** → pega `schema.sql` → **Run**. Crea las 4 tablas
(`wa_numbers`, `wa_contacts`, `wa_conversations`, `wa_messages`) con `user_id` y RLS,
igual que tu tabla `contactos`.

## Paso 2 · El backend
1. Copia `whatsapp.py` junto a tu `main.py`.
2. En `main.py`, debajo de donde creas `app = FastAPI(...)`, agrega:
```python
from whatsapp import router as whatsapp_router
app.include_router(whatsapp_router)
```
Tu webhook queda en: `https://TU-APP.railway.app/whatsapp/webhook`

## Paso 3 · La bandeja (frontend)
Copia `bandeja.html` a la raíz, junto a `contactos.html`. Ya usa tu `app-shell.js`,
tu `brokr-theme.css` y `window.brokrSb`, así que se ve idéntica a Broquer.
- Para que aparezca en el menú de todas las páginas, agrega el link **Bandeja**
  (`bandeja.html`) a la lista de navegación dentro de `app-shell.js`.

## Paso 4 · Variables de entorno (Railway → Variables)
Las de Supabase y Anthropic **ya las tienes**. Agrega solo las de WhatsApp:

| Variable | Qué es | De dónde sale |
|---|---|---|
| `WHATSAPP_TOKEN` | Token permanente para enviar | Meta → System User token |
| `WA_VERIFY_TOKEN` | Una palabra que tú inventas | la pones aquí Y en Meta (paso 5) |
| `WA_APP_SECRET` | Para validar la firma (opcional) | Meta → App Settings → Basic |
| `DEFAULT_USER_ID` | Tu `user_id` de Grupo Navarro (piloto) | Supabase → Authentication → Users |
| `DEFAULT_AGENCIA` | Nombre de la agencia | `Grupo Navarro` |
| `RECEPCION_MODEL` | Modelo del cerebro (opcional) | default `claude-sonnet-4-6` |

> Ya usa `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` y `ANTHROPIC_API_KEY`
> tal cual los tienes en `main.py`.

## Paso 5 · Conectar el webhook en Meta
developers.facebook.com → tu app → WhatsApp → **Configuration**:
1. **Callback URL:** `https://TU-APP.railway.app/whatsapp/webhook`
2. **Verify token:** la misma palabra de `WA_VERIFY_TOKEN`.
3. **Verify and Save.**
4. En **Webhook fields**, suscríbete a:
   - `messages` (entrantes del cliente) — el básico.
   - `smb_message_echoes` (**Coexistence**: lo que el agente manda desde su celular).
   - `history` y `smb_app_state_sync` (**Coexistence**, opcionales).

## Paso 6 · Probar
Manda un WhatsApp al número conectado desde tu celular personal. Recepción debe
contestar en segundos, y al abrir `bandeja.html` debe aparecer la conversación con
su calificación llenándose sola. Escribe tú un mensaje desde la bandeja: la IA se
apaga en esa conversación (tú tomaste el control) y la vuelves a prender con el switch.

---

## Coexistence (tu caso)
El número del agente sigue en su celular **y** conectado a Broquer al mismo tiempo:
- Recepción contesta al instante cuando el agente no puede.
- **En cuanto el agente responde desde su celular, la IA se apaga sola** en esa
  conversación (`smb_message_echoes` lo detecta). Sin encimarse.
- El agente la vuelve a prender desde la bandeja.

Detalles: usa dispositivos soportados (Windows/WearOS no generan echo); no hay
palomita azul bajo Coexistence (sería por Meta Verified); tope de 5 mensajes/seg.

## Lo que sigue
- Plantillas para los seguimientos fuera de la ventana de 24h.
- Embedded Signup para que cada agente conecte su número con un clic (post-piloto).

## Notas
- El JSON del `smb_message_echoes` puede variar un poquito; el código lo lee defensivo
  y, la primera vez, te lo deja en el log para confirmarlo. Si algo no cuadra, me pasas
  ese log y lo ajusto.
- No pude probar contra un WhatsApp real desde aquí. Súbelo a Railway y, si truena algo,
  me pasas el log.
