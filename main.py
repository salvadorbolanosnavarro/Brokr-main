from fastapi import (FastAPI, HTTPException, Query, Request, UploadFile, File,
                     BackgroundTasks, Response)
from fastapi.middleware.cors import CORSMiddleware
from limites import exigir_cupo, exigir_sesion
from pydantic import BaseModel
from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_public_rows, get_rows, patch_rows, post_rows
from core.legacy_main_config import legacy_main_settings
import httpx
import os
import time
import re
import asyncio
import logging
import base64
import hmac
import hashlib
import uuid as _uuid
import io
import json
import concurrent.futures
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Pillow
try:
    from PIL import Image, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# OpenCV
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# ════════════════════════════════════════════════════════════════
# SISTEMA DE DISEÑO — fuente única de color para los PDFs
# ════════════════════════════════════════════════════════════════
# Los PDFs (Ficha técnica, AVM, ISR) los renderiza Playwright de forma
# aislada: no cargan brokr-theme.css por <link>, así que sus tokens
# vivían COPIADOS A MANO en tres archivos. Se desincronizaron dos
# ediciones seguidas —se quedaron en la paleta "Sky" cuando la app ya
# iba en "Premium"— y nadie lo notó porque nada lo verificaba.
#
# Ahora se leen del theme real. Un solo lugar donde cambiar un color.
# brokr-theme.css viaja en la imagen de Railway porque el Dockerfile
# hace COPY . . — queda junto a main.py.
#
# Lo que un documento impreso SÍ puede sobrescribir (y por qué), va
# como `extra` en theme_css_for_pdf(): el papel es blanco, no el canvas
# azul de la app; y los radios son de documento, no de interfaz.

_THEME_PATH = Path(__file__).parent / "brokr-theme.css"
_theme_tokens_cache: Optional[str] = None

# Respaldo por si el CSS no se puede leer (archivo movido, permisos).
# Un PDF que no se genera es peor que un PDF con el color de ayer.
# Espejo del :root de la edición "Canon".
_THEME_TOKENS_FALLBACK = """
  --paper:#FFFFFF; --paper-2:#F4F6FB; --bone:#FFFFFF; --shell:#F5F7FC;
  --ink:#0B0B0F; --ink-2:#2A3142; --ink-3:#57607A;
  --mute:#57607A; --mute-2:#8A93A9; --mute-3:#C6CCDA;
  --line:#E7EBF4; --line-2:#DBE1EE; --line-3:#BEC7DA;
  --forest:#0A5DE0; --forest-2:#084BB8; --forest-soft:rgba(10,93,224,0.10);
  --sky-navy:#081C4E; --sky-navy-mid:#10307E; --sky-navy-deep:#050F2E;
  --sky-blue:#0A5DE0; --sky-blue-press:#084BB8; --sky-blue-lift:#6F9FF2;
  --sky-canvas:#E9F0FD; --sky-blue-on-dark:#8FB0F5;
  --warn:#B34E0B; --warn-soft:rgba(243,116,13,0.14);
  --danger:#D42A62; --danger-soft:rgba(212,42,98,0.12);
  --success:#0E9F6E; --success-soft:rgba(14,159,110,0.12);
  --info:#0A5DE0; --info-soft:rgba(10,93,224,0.10);
  --r-xs:8px; --r-sm:12px; --r:14px; --r-lg:22px; --r-xl:26px; --r-pill:999px;
  --font-sans:'Inter',-apple-system,BlinkMacSystemFont,system-ui,Roboto,'Helvetica Neue',sans-serif;
  --font-display:'Inter',-apple-system,BlinkMacSystemFont,system-ui,Roboto,sans-serif;
"""


def _theme_tokens() -> str:
    """Declaraciones de todos los bloques :root de brokr-theme.css,
    listas para inyectarse dentro de un :root{}. Se lee una vez por
    proceso; si falla, cae al respaldo sin tumbar la generación."""
    global _theme_tokens_cache
    if _theme_tokens_cache is not None:
        return _theme_tokens_cache
    try:
        css = _THEME_PATH.read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # fuera comentarios
        blocks = re.findall(r":root\s*\{([^{}]*)\}", css)
        decls = "\n".join(b.strip() for b in blocks if b.strip())
        # Si el theme cambia de forma y ya no trae lo esperado, mejor el
        # respaldo conocido que un PDF sin colores.
        for required in ("--ink", "--sky-navy", "--sky-blue", "--font-sans"):
            if required not in decls:
                raise ValueError(f"brokr-theme.css sin {required}")
        _theme_tokens_cache = decls
    except Exception as e:
        print(f"[theme] no se pudo leer {_THEME_PATH}: {e} — usando respaldo")
        _theme_tokens_cache = _THEME_TOKENS_FALLBACK
    return _theme_tokens_cache


def theme_css_for_pdf(extra: str = "") -> str:
    """CSS base de un documento PDF: los tokens del theme, más los
    overrides que un impreso legítimamente necesita. `extra` se aplica
    al final, así que gana sobre todo lo anterior."""
    return (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Inter:opsz,wght@14..32,400..800&display=swap');\n"
        ":root{\n" + _theme_tokens() + "\n}\n"
        "/* Overrides del documento impreso: el papel es blanco (el canvas\n"
        "   azul de la app no aplica) y los radios son de documento. */\n"
        ":root{\n  --paper:#FFFFFF;\n  " + extra + "\n}\n"
    )


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# whatsapp.py es el módulo de WhatsApp (multi-número, IA de recepción, webhook
# propio bajo /whatsapp2 — el prefijo interno del router no cambió aunque el
# archivo ya se llama whatsapp.py). Import defensivo: si algo le falta, el
# resto del backend sigue vivo.
try:
    from whatsapp import router as whatsapp_router
    app.include_router(whatsapp_router)
except Exception as _e:
    import logging as _logging
    _logging.getLogger("broquer.main").error("No se pudo cargar whatsapp: %s", _e)

# Motor agéntico de Broq (tool-use nativo + loop de varios pasos + voz Whisper).
# Import defensivo: si por cualquier razón fallara la carga, el resto del backend
# sigue funcionando con normalidad.
try:
    from routers.agente import router as agente_router
    app.include_router(agente_router)
except Exception as _e:
    print(f"[agente] No se pudo montar el router agéntico: {_e}")

# Broquer para empresas: miembros, invitaciones, roles y permisos.
# Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.organizaciones import router as org_router
    app.include_router(org_router)
except Exception as _e:
    print(f"[org] No se pudo montar el router de organizaciones: {_e}")

# WhatsApp de ChatGPT: onboarding real por Meta Embedded Signup, separado del módulo legacy.
try:
    from routers.whatsapp_chatgpt import router as whatsapp_chatgpt_router
    app.include_router(whatsapp_chatgpt_router)
except Exception as _e:
    print(f"[whatsapp-chatgpt] No se pudo montar el router: {_e}")
# Cumplimiento PLD/UIF: expediente único, umbrales, avisos y bitácora.
# Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.cumplimiento import router as pld_router
    app.include_router(pld_router)
except Exception as _e:
    print(f"[pld] No se pudo montar el router de cumplimiento: {_e}")

# Firma electrónica: documentos, firmantes, código de verificación, constancia
# y verificación pública por folio. Mismo import defensivo: si falla, el resto
# del backend sigue vivo.
try:
    from routers.firmas import router as firmas_router
    app.include_router(firmas_router)
except Exception as _e:
    print(f"[firmas] No se pudo montar el router de firma electrónica: {_e}")

# Video de ficha: arma un recorrido con ffmpeg a partir de las fotos que ya
# viven en la propiedad. Mismo import defensivo: si falla, el resto del
# backend sigue vivo.
try:
    from routers.video import router as video_router
    app.include_router(video_router)
except Exception as _e:
    print(f"[video] No se pudo montar el router de video: {_e}")

# Correo electrónico: conexión IMAP/SMTP, bandeja, lectura, respuesta y
# envío. Mismo import defensivo: si falla, el resto del backend sigue vivo.
try:
    from routers.correo import router as correo_router
    app.include_router(correo_router)
except Exception as _e:
    print(f"[correo] No se pudo montar el router de correo: {_e}")

# Bolsa inmobiliaria: inventario compartido entre agentes Broquer con
# comisión compartida. Mismo import defensivo: si falla, el resto del
# backend sigue vivo.
try:
    from routers.bolsa import router as bolsa_router
    app.include_router(bolsa_router)
except Exception as _e:
    print(f"[bolsa] No se pudo montar el router de la bolsa: {_e}")

# Finanzas: cuentas, ingresos, gastos, rentabilidad por propiedad, lectura
# de tickets con Broq y reportes PDF/CSV. Mismo import defensivo: si falla,
# el resto del backend sigue vivo.
try:
    from routers.finanzas import router as finanzas_router
    app.include_router(finanzas_router)
except Exception as _e:
    print(f"[finanzas] No se pudo montar el router de finanzas: {_e}")

CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}

def save_config(data: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass

_config = load_config()

# Compatibility aliases while main.py is progressively decomposed. All runtime
# environment names and public/privileged Supabase key policy live in Core.
EB_API_KEY       = settings.easybroker_api_key or _config.get("eb_api_key", "")
GROQ_API_KEY     = settings.groq_api_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
GEMINI_API_KEY    = settings.gemini_api_key
EB_BASE          = "https://api.easybroker.com/v1"
GROQ_BASE        = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE   = "https://api.anthropic.com/v1"
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta"
APIFY_API_KEY = settings.apify_api_key
GOOGLE_PLACES_KEY = settings.google_places_key
SUPABASE_URL      = settings.supabase_url
SUPABASE_KEY      = settings.supabase_anon_key
FB_APP_ID     = settings.legacy_main_fb_app_id
FB_APP_SECRET = settings.legacy_main_fb_app_secret
FRONTEND_URL  = settings.legacy_main_frontend_url
# Banxico SIE — INPC + UDIS para calculadora ISR
BANXICO_TOKEN     = settings.banxico_token
BANXICO_BASE      = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = settings.banxico_series_udis  # Valor de UDIS (diaria)
BANXICO_SERIE_INPC = settings.banxico_series_inpc  # INPC mensual base 2Q-jul-2018=100
# service_role key — bypasea RLS. Solo para operaciones del backend en nombre
# del usuario, DESPUÉS de validar su JWT con get_user_id_from_token().
# NUNCA expongas esta variable al frontend.
SUPABASE_SERVICE_KEY = settings.supabase_service_key
# Pagos — Stripe

# In-memory PDF store: token → (bytes, filename). Max 50 entradas.
_pdf_store: dict = {}

# ── CACHE EN MEMORIA (TTL 6h) ──
_cache: dict = {}
CACHE_TTL = 21600  # 6 hours default
_cache_ttl: dict = {}  # per-key TTL overrides

def cache_get(key):
    if key in _cache:
        data, ts = _cache[key]
        ttl = _cache_ttl.get(key, CACHE_TTL)
        if time.time() - ts < ttl:
            return data
        del _cache[key]
        _cache_ttl.pop(key, None)
    return None

def cache_set(key, data, ttl=None):
    _cache[key] = (data, time.time())
    if ttl is not None:
        _cache_ttl[key] = ttl

def eb_headers(key: str = None):
    k = key or EB_API_KEY
    return {"X-Authorization": k, "accept": "application/json"}

# ────────────────────────────────────────────
# EASYBROKER — BASE ENDPOINTS
# ────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Brokr API activa", "version": "4.8"}

# Endpoint para keep-alive (UptimeRobot u otro monitor cada 4 minutos).
# No hace queries, no toca DB — solo evita que Railway duerma el servidor.
@app.get("/ping")
def ping():
    return {"ok": True}

# ────────────────────────────────────────────
# BANXICO SIE — INPC mensual + UDIS diaria
# Series: SP74625 (INPC base 2Q-jul-2018=100), SP68257 (UDIS)
# Token gratuito: banxico.org.mx/SieAPIRest
# Cache: meses/fechas pasadas 30 días; corrientes 6h
# ────────────────────────────────────────────
async def _banxico_fetch(serie: str, fecha_ini: str = None, fecha_fin: str = None) -> list:
    """
    Consulta una serie de Banxico SIE.
    Fechas en formato YYYY-MM-DD (formato esperado por Banxico SIE).
    Si no se pasan fechas, usa /datos/oportuno (último valor publicado).
    Devuelve lista de {fecha: 'DD/MM/YYYY', dato: 'valor'}.
    """
    if not BANXICO_TOKEN:
        raise HTTPException(status_code=503, detail="BANXICO_TOKEN no configurado en el backend")
    if fecha_ini and fecha_fin:
        url = f"{BANXICO_BASE}/{serie}/datos/{fecha_ini}/{fecha_fin}"
    else:
        url = f"{BANXICO_BASE}/{serie}/datos/oportuno"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url, params={"token": BANXICO_TOKEN},
                                 headers={"Accept": "application/json"})
            if r.status_code in (401, 403):
                raise HTTPException(status_code=502, detail="Token Banxico rechazado")
            if r.status_code == 400:
                raise HTTPException(status_code=400, detail=f"Banxico rechazó request: {r.text[:200]}")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Banxico devolvió HTTP {r.status_code}")
            data = r.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Error consultando Banxico: {e}")
    series = (data.get("bmx") or {}).get("series") or []
    if not series:
        return []
    datos = series[0].get("datos") or []
    # Filtra "N/E" (no existe ese día — feriados/no publicado)
    return [d for d in datos if d.get("dato") and d["dato"] != "N/E"]

@app.get("/api/inpc/{anio}/{mes}")
async def api_inpc(anio: int, mes: int):
    """
    INPC mensual de Banxico SIE (serie SP74625, base 2Q jul 2018 = 100).
    Devuelve {anio, mes, valor, fecha_publicacion, fuente}.
    """
    if not (1969 <= anio <= 2099):
        raise HTTPException(status_code=400, detail="Año fuera de rango (1969-2099)")
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mes debe ser 1-12")
    key = f"inpc:{anio}-{mes:02d}"
    cached = cache_get(key)
    if cached:
        return cached
    # Banxico requiere fechas YYYY-MM-DD
    if mes == 12:
        last_day = 31
    else:
        last_day = (date(anio, mes + 1, 1) - timedelta(days=1)).day
    fecha_ini = f"{anio}-{mes:02d}-01"
    fecha_fin = f"{anio}-{mes:02d}-{last_day:02d}"
    datos = await _banxico_fetch(BANXICO_SERIE_INPC, fecha_ini, fecha_fin)
    fallback = False
    anio_real, mes_real = anio, mes
    if not datos:
        # Art. 17-A CFF (sexto parrafo): cuando el INPC del mes mas reciente aun no
        # se publica (INEGI lo libera ~dia 9-10 del mes siguiente), se aplica el
        # ULTIMO indice mensual publicado. Retrocedemos hasta 3 meses buscandolo.
        for _ in range(3):
            mes_real -= 1
            if mes_real < 1:
                mes_real = 12
                anio_real -= 1
            if mes_real == 12:
                ld = 31
            else:
                ld = (date(anio_real, mes_real + 1, 1) - timedelta(days=1)).day
            datos = await _banxico_fetch(
                BANXICO_SERIE_INPC,
                f"{anio_real}-{mes_real:02d}-01",
                f"{anio_real}-{mes_real:02d}-{ld:02d}")
            if datos:
                fallback = True
                break
    if not datos:
        raise HTTPException(status_code=404, detail=f"INPC no publicado para {anio}-{mes:02d}")
    valor = float(str(datos[-1]["dato"]).replace(",", ""))
    fecha_pub = datos[-1]["fecha"]
    result = {"anio": anio_real, "mes": mes_real, "valor": valor,
              "fecha_publicacion": fecha_pub, "fuente": "banxico_sie",
              "fallback": fallback,
              "anio_solicitado": anio, "mes_solicitado": mes}
    now = datetime.now()
    is_past = (anio < now.year) or (anio == now.year and mes < now.month)
    # Un resultado fallback caduca pronto: en cuanto INEGI publique, se toma el real.
    cache_set(key, result, ttl=6 * 3600 if fallback else (30 * 86400 if is_past else 6 * 3600))
    return result

@app.get("/api/udis/{fecha}")
async def api_udis(fecha: str):
    """
    Valor de UDIS de Banxico SIE (serie SP68257) para una fecha específica.
    fecha en formato YYYY-MM-DD. Devuelve {fecha, valor, fecha_publicacion, fuente}.
    Si la fecha es muy reciente y aún no publicada, devuelve el último valor disponible.
    """
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha debe ser YYYY-MM-DD")
    key = f"udis:{fecha}"
    cached = cache_get(key)
    if cached:
        return cached
    datos = await _banxico_fetch(BANXICO_SERIE_UDIS, fecha, fecha)
    if not datos:
        # Fallback: rango de 14 días hacia atrás (UDIS se publican diariamente
        # pero en feriados raros puede haber gaps)
        fecha_ini = (fecha_obj - timedelta(days=14)).isoformat()
        datos = await _banxico_fetch(BANXICO_SERIE_UDIS, fecha_ini, fecha)
    if not datos:
        raise HTTPException(status_code=404, detail=f"UDIS no publicadas para {fecha}")
    valor = float(str(datos[-1]["dato"]).replace(",", ""))
    fecha_pub = datos[-1]["fecha"]
    result = {"fecha": fecha, "valor": valor,
              "fecha_publicacion": fecha_pub, "fuente": "banxico_sie"}
    is_past = fecha_obj < datetime.now().date()
    cache_set(key, result, ttl=7 * 86400 if is_past else 12 * 3600)
    return result

# ────────────────────────────────────────────
# CONFIG — EB API KEY POR USUARIO (Supabase)
# ────────────────────────────────────────────
class EbKeyRequest(BaseModel):
    key: str

# Helper: compara dos secretos en tiempo constante (evita adivinarlos byte a
# byte midiendo cuánto tarda la respuesta). Devuelve False si alguno va vacío.
def hmac_compare(recibido: str, esperado: str) -> bool:
    import hmac as _h
    if not recibido or not esperado:
        return False
    return _h.compare_digest(str(recibido), str(esperado))


# ════════════════════════════════════════════════════════════════
# CONTEXTO DE ORGANIZACIÓN (Broquer para empresas)
# Tras la migración, la RLS filtra por org_id — NO por user_id. Todo registro
# que cree el backend debe llevar org_id o queda huérfano e invisible para
# todos. El backend usa service key y se brinca la RLS, así que un olvido aquí
# no truena: silenciosamente crea basura. Por eso va explícito en cada INSERT.
# ════════════════════════════════════════════════════════════════
from routers.organizaciones import (
    get_org_id_for_user, get_org_context, permiso_efectivo,
    exigir_gestion_integraciones,
)


# Helper: obtiene la EB key de un usuario desde Supabase
# IMPORTANTE: NO hace fallback al EB_API_KEY global. Si el usuario no tiene
# su propia key configurada, devuelve None. Esto blinda multi-tenant: ningún
# usuario puede usar la cuenta de EasyBroker de otro.
async def get_eb_key_for_user(user_id: str) -> str:
    # Acordado con Chava: la cuenta de EasyBroker es UNA por empresa, no por
    # agente. Buscamos por org_id para que todo el equipo use la misma.
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return None
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "org_id": f"eq.{org_id}",
                "provider": "eq.easybroker",
                "select": "api_key",
                "limit": "1",
            },
            timeout=8,
        )
        return (rows[0].get("api_key") or "").strip() or None if rows else None
    except Exception:
        return None

# Helper: obtiene el rol del usuario desde la tabla usuarios
async def get_user_rol(user_id: str) -> str:
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return "agente"
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol", "limit": "1"},
            timeout=8,
        )
        if rows:
            return rows[0].get("rol") or "agente"
    except Exception:
        pass
    return "agente"

# Helper: obtiene rol + activo en una sola llamada
async def get_user_access_state(user_id: str) -> dict:
    """
    Devuelve {'rol': str, 'activo': bool} para verificar acceso de un usuario.
    Si la cuenta está desactivada (activo=False), ningún rol da acceso.
    """
    default = {"rol": "agente", "activo": True}
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return default
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol,activo", "limit": "1"},
            timeout=8,
        )
        if rows:
            return {
                "rol": rows[0].get("rol") or "agente",
                "activo": rows[0].get("activo") if rows[0].get("activo") is not None else True,
            }
    except Exception:
        pass
    return default

# ─────────────────────────────────────────────
# TELEMETRÍA — uso de IA y tiempo por módulo
# Tablas: usage_logs, module_sessions (ver migracion-telemetria.sql)
# Nunca rompen el endpoint principal: todos los errores se silencian.
# ─────────────────────────────────────────────

# Precios públicos por modelo (USD por token, salvo Gemini image-gen que es por imagen).
# Si un modelo no está aquí, usa el fallback del proveedor.
# Fuentes: anthropic.com/pricing, groq.com/pricing, ai.google.dev/pricing.
PRICING = {
    # Anthropic — por token
    "claude-sonnet-4-6":           {"in": 3.0  / 1_000_000, "out": 15.0 / 1_000_000},
    "claude-opus-4-7":             {"in": 15.0 / 1_000_000, "out": 75.0 / 1_000_000},
    "claude-haiku-4-5-20251001":   {"in": 1.0  / 1_000_000, "out": 5.0  / 1_000_000},
    # Groq — por token
    "llama-3.3-70b-versatile":     {"in": 0.59 / 1_000_000, "out": 0.79 / 1_000_000},
    "llama-3.1-8b-instant":        {"in": 0.05 / 1_000_000, "out": 0.08 / 1_000_000},
}
PRICING_FALLBACK_BY_PROVIDER = {
    "anthropic": {"in": 3.0  / 1_000_000, "out": 15.0 / 1_000_000},
    "groq":      {"in": 0.59 / 1_000_000, "out": 0.79 / 1_000_000},
    "gemini":    {"in": 0.30 / 1_000_000, "out": 2.50 / 1_000_000},
}
# Gemini image generation se cobra por imagen, no por token.
GEMINI_IMAGE_USD_PER_UNIT = 0.039  # Nano Banana 2 — precio público aproximado.


def _cost_for(proveedor: str, modelo: str, tokens_in: int, tokens_out: int, unidades: int) -> float:
    """Calcula costo en USD para una llamada. Tolerante a modelos desconocidos."""
    try:
        if proveedor == "gemini" and unidades > 0:
            return round(float(unidades) * GEMINI_IMAGE_USD_PER_UNIT, 6)
        rate = PRICING.get(modelo) or PRICING_FALLBACK_BY_PROVIDER.get(proveedor) or {"in": 0, "out": 0}
        return round(float(tokens_in) * rate["in"] + float(tokens_out) * rate["out"], 6)
    except Exception:
        return 0.0


async def track_usage(
    user_id: str,
    modulo: str,
    herramienta: str,
    proveedor: str,
    modelo: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    unidades: int = 0,
):
    """Inserta una fila en usage_logs. Fire-and-forget: nunca lanza."""
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    costo = _cost_for(proveedor, modelo, tokens_in, tokens_out, unidades)
    payload = {
        "user_id":     user_id,
        "modulo":      (modulo or "desconocido")[:80],
        "herramienta": (herramienta or "")[:120],
        "proveedor":   (proveedor or "")[:40],
        "modelo":      (modelo or "")[:80],
        "tokens_in":   int(tokens_in or 0),
        "tokens_out":  int(tokens_out or 0),
        "unidades":    int(unidades or 0),
        "costo_usd":   costo,
    }
    try:
        await post_rows(
            "usage_logs", payload, prefer="return=minimal", timeout=6
        )
    except Exception:
        pass


def _track_anthropic(user_id: str, modulo: str, herramienta: str, response_json: dict, modelo: str = "claude-sonnet-4-6"):
    """Helper sync: extrae usage del response de Anthropic y dispara track_usage en background."""
    if not user_id:
        return
    try:
        usage = (response_json or {}).get("usage") or {}
        ti = int(usage.get("input_tokens") or 0)
        to = int(usage.get("output_tokens") or 0)
        # Cache read/creation también consumen — los sumamos al input si están.
        ti += int(usage.get("cache_read_input_tokens") or 0)
        ti += int(usage.get("cache_creation_input_tokens") or 0)
        asyncio.create_task(track_usage(
            user_id=user_id, modulo=modulo, herramienta=herramienta,
            proveedor="anthropic", modelo=modelo, tokens_in=ti, tokens_out=to,
        ))
    except Exception:
        pass


def _track_groq(user_id: str, modulo: str, herramienta: str, response_json: dict, modelo: str = "llama-3.3-70b-versatile"):
    """Helper sync: extrae usage del response de Groq (formato OpenAI) y trackea en background."""
    if not user_id:
        return
    try:
        usage = (response_json or {}).get("usage") or {}
        ti = int(usage.get("prompt_tokens") or 0)
        to = int(usage.get("completion_tokens") or 0)
        asyncio.create_task(track_usage(
            user_id=user_id, modulo=modulo, herramienta=herramienta,
            proveedor="groq", modelo=modelo, tokens_in=ti, tokens_out=to,
        ))
    except Exception:
        pass


def _track_gemini_image(user_id: str, modulo: str, herramienta: str, unidades: int = 1, modelo: str = "gemini-image"):
    """Helper sync: trackea generación de imagen con Gemini (cobro por unidad)."""
    if not user_id:
        return
    try:
        asyncio.create_task(track_usage(
            user_id=user_id, modulo=modulo, herramienta=herramienta,
            proveedor="gemini", modelo=modelo, unidades=int(unidades or 0),
        ))
    except Exception:
        pass


# Módulos válidos para el heartbeat. Mantener sincronizado con los `data-app`
# de los HTML del frontend (búsqueda rápida: grep -h "data-app=" *.html).
MODULOS_VALIDOS = {
    "home", "props", "contactos", "contratos", "avm", "valor", "ficha",
    "ficha-manual", "isr", "image-cleaner", "facebook-ads", "guia",
    "solicitud-arr", "admin", "blog", "verificador", "equipo",
}


def _request_modulo(request: Request, fallback: str) -> str:
    """Lee el módulo activo del header X-Brokr-Module (puesto por app-shell.js).
    Permite que /chat-claude o /chat (genéricos) atribuyan al módulo correcto."""
    try:
        m = (request.headers.get("X-Brokr-Module") or "").strip().lower()[:40]
        if m and m in MODULOS_VALIDOS:
            return m
    except Exception:
        pass
    return fallback


class TelemetriaSesionModuloReq(BaseModel):
    modulo: str
    segundos: int


@app.post("/telemetria/sesion-modulo")
async def telemetria_sesion_modulo(req: TelemetriaSesionModuloReq, request: Request):
    """Heartbeat del frontend: registra segundos activos de un usuario en un módulo.
    Silenciosamente ignora payloads inválidos o usuarios anónimos — no es crítico.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        return {"ok": False}
    modulo = (req.modulo or "").strip().lower()[:40]
    if modulo not in MODULOS_VALIDOS:
        return {"ok": False, "razon": "modulo_invalido"}
    segs = int(req.segundos or 0)
    # Anti-abuso: ignorar valores absurdos. Cap 1h por heartbeat.
    if segs <= 0 or segs > 3600:
        return {"ok": False, "razon": "segundos_invalidos"}
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"ok": False}
    try:
        await post_rows(
            "module_sessions",
            {"user_id": user_id, "modulo": modulo, "segundos": segs},
            prefer="return=minimal",
            timeout=5,
        )
    except Exception:
        pass
    return {"ok": True}


@app.post("/config/eb-key")
async def set_eb_key(req: EbKeyRequest, request: Request):
    # La cuenta de EasyBroker es de la EMPRESA. Solo el dueño o quien él designe.
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    # Validar la key contra EasyBroker antes de guardar
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            test = await client.get(
                f"{EB_BASE}/properties?limit=1",
                headers={"X-Authorization": req.key.strip(), "accept": "application/json"}
            )
            print(f"[set_eb_key] EasyBroker validation status: {test.status_code}, body[:200]: {test.text[:200]}")
            if test.status_code == 401:
                raise HTTPException(status_code=400, detail="API key de EasyBroker invalida. Verifica que la copiaste correctamente.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[set_eb_key] Excepcion en validacion: {type(e).__name__}: {e}")
        pass

    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "easybroker",
        "api_key": req.key.strip(),
        "updated_at": datetime.utcnow().isoformat()
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        err_body = e.response.text or ""
        print(f"[set_eb_key] Supabase respondió {status}: {err_body}")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo guardar la API key (Supabase {status}). Reintenta o avisa a soporte si persiste."
        )
    return {"ok": True, "saved": True, "scope": "user"}

# Endpoint para desconectar EasyBroker (borrar la API key del usuario)
@app.delete("/config/eb-key")
async def delete_eb_key(request: Request):
    # Desconectar deja SIN INVENTARIO a todo el equipo. Solo el dueño o designado.
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")
    try:
        await delete_rows(
            "user_integrations",
            {
                "org_id": f"eq.{await get_org_id_for_user(user_id)}",
                "provider": "eq.easybroker",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Compatibilidad: históricamente los status HTTP de Supabase se ignoraban.
        pass
    return {"ok": True, "deleted": True}

@app.get("/config/eb-key")
async def get_eb_key(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        # Sin sesión, devolvemos "no configurada" sin error para no tirar la UI
        return {"configured": False, "masked": ""}
    key = await get_eb_key_for_user(user_id)
    if key and len(key) > 4:
        masked = "*" * (len(key) - 4) + key[-4:]
    else:
        masked = ""
    return {"configured": bool(key), "masked": masked}

@app.get("/config/public")
async def get_public_config():
    """Devuelve configuración pública que el frontend necesita al arrancar.
    FB_APP_ID es un ID de app de Meta — no es secreto, puede exponerse al cliente."""
    return {"fb_app_id": FB_APP_ID}

# ════════════════════════════════════════════════════════════════
# Endpoint unificado para el perfil del usuario.
# Devuelve estado de EasyBroker + Facebook en UNA sola llamada
# con UNA sola query a Supabase. Reduce 2 peticiones HTTP a 1
# (elimina un CORS preflight) y 2 queries a Supabase a 1.
# ════════════════════════════════════════════════════════════════
@app.get("/profile/status")
async def get_profile_status(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}

    # Una sola query trae AMBAS integraciones (EB + FB) del usuario.
    # Core conserva el acceso privilegiado en un solo lugar; este endpoint
    # sigue siendo fail-soft ante cualquier rechazo o fallo de transporte.
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "in.(easybroker,facebook)",
                "select": "provider,api_key,meta",
            },
            timeout=8,
        )
    except Exception:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}

    # Parsear cada provider
    eb_state = {"configured": False, "masked": ""}
    fb_state = {"connected": False}

    for row in rows:
        provider = row.get("provider")
        api_key = row.get("api_key", "")
        if provider == "easybroker" and api_key:
            masked = "*" * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else ""
            eb_state = {"configured": True, "masked": masked}
        elif provider == "facebook" and api_key:
            meta_str = row.get("meta", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else (meta_str or {})
            except Exception:
                meta = {}
            # El token NO viaja al navegador: solo se dice si existe. (Además,
            # ahora está cifrado en reposo, así que mandarlo tampoco serviría
            # de nada al frontend.)
            fb_state = {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "tiene_token_ads": bool(meta.get("user_token")),
                "token": _fb_estado_token(meta),
            }

    # Suscripcion
    sub_state = {"active": False, "plan": None, "status": "sin_suscripcion"}
    try:
        # Equipo interno y admin siempre tienen acceso activo
        rol_val = None
        for row in rows:
            pass  # rows ya fue procesado arriba
        rol_val = await get_user_rol(user_id)
        if rol_val in ("equipo", "admin"):
            sub_state = {
                "active": True,
                "plan": "Equipo Interno" if rol_val == "equipo" else "Admin",
                "status": "active",
            }
        else:
            # La suscripción cuelga de la ORG: en una empresa la paga el
            # titular y la heredan todos sus agentes.
            _oid = await get_org_id_for_user(user_id)
            sub_rows = await get_rows(
                "suscripciones",
                {"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"},
                timeout=6,
            )
            if sub_rows:
                row = sub_rows[0]
                _st = row.get("status")
                _act = _st in ("active", "trialing")
                if _st == "trialing" and row.get("trial_hasta") and _trial_ya_vencio(row.get("trial_hasta")):
                    _act = False
                    _st = "trial_vencido"
                    asyncio.create_task(_expirar_trial_suscripcion(row.get("id")))
                sub_state = {
                    "active": _act,
                    "plan": row.get("plan_nombre"),
                    "status": _st,
                }
    except Exception:
        pass

    if sub_state.get("status") == "sin_suscripcion":
        try:
            sub_state["trial_disponible"] = await _trial_max_disponible(user_id)
        except Exception:
            sub_state["trial_disponible"] = False

    return {"eb": eb_state, "fb": fb_state, "sub": sub_state}

# ────────────────────────────────────────────
# GROQ CHAT PROXY
# ────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list
    model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1024
    temperature: float = 0.7

@app.post("/chat")
async def chat_proxy(req: ChatRequest, request: Request):
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY no configurada en el servidor")
    user_id = await get_user_id_from_token(request)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model":       req.model,
                "messages":    req.messages,
                "max_tokens":  req.max_tokens,
                "temperature": req.temperature,
            }
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code,
                detail=f"Error Groq: {r.text}")
        data = r.json()
        _track_groq(user_id, _request_modulo(request, "chat"), "/chat", data,
                    modelo=req.model or "llama-3.3-70b-versatile")
        return data


# ────────────────────────────────────────────
# CLAUDE CHAT PROXY — BROQ IA SUPERINTELIGENTE
# ────────────────────────────────────────────
SHAARK_SYSTEM_PROMPT = """Eres Broq, el asistente de inteligencia artificial de la plataforma Broquer — el copiloto operativo para agentes inmobiliarios de México, especializada en Morelia y Michoacán.

IDENTIDAD:
- Tu nombre es Broq. Si el usuario dice "broq", "broker", "Broker", "broquer" o variantes, siempre escríbelo como "Broq" en tu respuesta.
- Eres el copiloto del agente. Puedes hacer casi todo lo que el agente haría manualmente en la plataforma — y lo haces por él cuando te lo pide.
- Eres especialmente útil cuando el agente va manejando, está en una cita, o no puede escribir. Si habla por voz, respondes con oraciones cortas y directas.
- Llamas al usuario por su nombre de pila cuando lo conoces (lo recibes en el contexto).

PERSONALIDAD:
- Hablas español mexicano, natural, cercano y profesional.
- Eres directo y preciso. Sin relleno. Sin redundancia.
- Nunca inventas cifras, leyes, artículos o datos que no existen.
- Si no sabes algo con certeza, lo dices y ofreces buscar o recomendar dónde verificar.

CONOCIMIENTO EXPERTO QUE DOMINAS:

DERECHO INMOBILIARIO MEXICANO:
- Código Civil Federal y de Michoacán: compraventa, arrendamiento, promesa de venta, comodato, cesión de derechos.
- Cuándo se requiere escritura pública ante notario y cuándo basta un contrato privado.
- Registro Público de la Propiedad: cómo registrar, por qué importa, tiempos y costos.
- Ley Federal de Protección de Datos Personales (LFPDPPP) — obligaciones del agente.
- Ley Federal para la Prevención e Identificación de Operaciones con Recursos de Procedencia Ilícita (LFPIORPI) — PLD para agentes inmobiliarios: reportes, aviso SAT, umbrales.
- Diferencias entre promesa de compraventa y contrato de compraventa definitivo.
- Derechos y obligaciones de arrendador y arrendatario: depósito, fianza, rescisión.
- Régimen de propiedad en condominio en Michoacán.
- Fideicomiso inmobiliario básico.
- Reglamentos de construcción de Morelia.

FISCAL E ISR:
- LISR artículos 119 y 120 — enajenación de inmuebles, exención 700,000 UDIS para casa habitación.
- Deducciones: precio de compra actualizado con INPC, mejoras, escrituración, comisiones.
- Retención del notario, declaración anual del vendedor.
- Régimen de arrendamiento en SAT: pagos provisionales, deducción ciega del 35%.
- ISAI (Impuesto Sobre Adquisición de Inmuebles) — quién lo paga, cuánto, dónde.
- IVA en operaciones comerciales e industriales.

VALUACIÓN Y MERCADO:
- Método de mercado (comparables), método físico (costo), capitalización de rentas.
- Cap rate, precio por m², análisis hedónico.
- Mercado de Morelia: Chapultepec, Altozano, Félix Ireta, Lomas del Estadio, Santa María, Lomas de Tzompantle, Vistas del Campestre, Villas del Pedregal, Bosques de Tariacuri, Torremolinos, Las Américas, Jardines del Rincón, y más.
- Factores de plusvalía: vialidades, equipamiento urbano, densidad, tendencia de zona.

MARKETING INMOBILIARIO:
- Facebook Ads e Instagram Ads para inmuebles: objetivos, presupuestos, públicos, creativos.
- Cómo redactar una ficha técnica que vende.
- Estrategia de precios: precio de lista vs precio de mercado.
- Cómo manejar la objeción de precio con el propietario.
- Técnicas de captación de exclusivas.
- Script de llamada en frío para propietarios.
- Presentación de servicios ante propietario.
- Marketing de contenidos: LinkedIn, Instagram, TikTok para agentes.

TECNOLOGÍA PARA AGENTES:
- EasyBroker: cómo conectar, importar propiedades, subir propiedades, el CRM.
- Portales: Inmuebles24, Vivanuncios, Lamudi, MercadoLibre Inmuebles.
- Firma electrónica en México: validez legal, Mifiel, Docusign.
- WhatsApp Business, Google Business Profile, Google Meet para agentes.
- Cómo usar Broquer al 100%: todos los módulos, cómo pedir ayuda por voz, etc.

CÓMO CONECTAR EASYBROKER (respuesta exacta cuando te pregunten):
1. En EasyBroker, haz clic en tu nombre (esquina superior derecha) → "Configuración de cuenta".
2. En el menú izquierdo, busca "Integraciones" o "API".
3. Copia tu API Key personal (código alfanumérico largo).
4. En Broquer, abre tu perfil haciendo clic en tus iniciales (esquina inferior izquierda del sidebar en desktop, o el avatar en móvil).
5. En la sección "EasyBroker", pega tu API Key y haz clic en "Conectar EasyBroker".
6. Broquer valida la conexión en segundos.
Nota: cada agente debe usar su propia API Key personal. No la compartas.

REGLA DE ORO PARA ACCIONES:
Cuando el usuario pide ejecutar una tarea, recopila los datos OBLIGATORIOS de UNO EN UNO, conversacionalmente. NUNCA ejecutes la acción con datos incompletos. Cuando tengas todo, di un resumen breve y ejecuta. Los opcionales que el usuario no conozca: usa 0 o "".

═══════════════════════════════════════════════════════════════
MODO ASISTENTE EJECUTOR — PRIORIDAD #1
═══════════════════════════════════════════════════════════════
Eres un ASISTENTE que EJECUTA, no un chatbot que sugiere. Cuando el usuario
pide algo que puedes hacer DIRECTAMENTE, HAZLO. No le digas "ve a tal módulo
y dale al botón X". TÚ lo haces y le entregas el resultado.

PREFIERE SIEMPRE LAS ACCIONES DIRECTAS sobre las que navegan:
  • `calcular_isr_directo`     → genera y descarga el PDF de ISR en el chat
  • `estimar_valor_directo`    → genera y descarga el PDF de estimación de valor
  • `agregar_contacto`         → agrega contacto al CRM sin salir del chat
  • `generar_contrato_directo` → descarga DOCX del contrato sin salir del chat

Solo navega (`llenar_isr`, `llenar_avm`, `llenar_contrato`, `navegar`) cuando:
  - El usuario explícitamente lo pide ("llévame a", "abre", "muéstrame el módulo de").
  - Faltan datos críticos y necesita editar a mano.

Tono: decidido, breve, fáctico. Di "Listo, lo hago." en lugar de "Voy a llevarte
a la pantalla de…". El usuario está manejando, dándote órdenes por voz; tú
ejecutas como una secretaria experta que conoce su trabajo.

══════════════════════════════════════════════════
ACCIÓN 1: CALCULAR ISR POR ENAJENACIÓN
══════════════════════════════════════════════════
Datos OBLIGATORIOS (pregunta uno por uno):
1. Tipo de inmueble: casa habitación, terreno, o comercial
2. Precio de venta (MXN)
3. Mes y año de la venta
4. Precio de compra original (MXN)
5. Mes y año de la compra
6. Si es casa: ¿usó la exención en los últimos 3 años? (sí / no / no sabe)
7. ¿Mejoras o ampliaciones? (monto o "no")
8. ¿Escrituración al comprar? (monto o "no sé")
9. ¿Comisión del agente en esta venta? (monto o "no aplica")

La pregunta 6 SOLO aplica a casa/departamento. Para terrenos y comerciales usa "no" automáticamente.

Cuando tengas todo:
[ACCION]{"tipo":"llenar_isr","precio_venta":NUMERO,"precio_compra":NUMERO,"anio_venta":NUMERO,"mes_venta":NUMERO,"anio_compra":NUMERO,"mes_compra":NUMERO,"inmueble":"casa","exencion":"no","mejoras":NUMERO,"escrituracion":NUMERO,"comision":NUMERO}[/ACCION]

Valores "inmueble": "casa" | "terreno" | "comercial"
Valores "exencion": "no" | "si" | "nose"
mes_venta y mes_compra son números 1-12. Datos opcionales desconocidos = 0.

══════════════════════════════════════════════════
ACCIÓN 2: OPINIÓN DE VALOR CON BÚSQUEDA WEB
══════════════════════════════════════════════════
Datos OBLIGATORIOS (pregunta uno por uno si faltan):
1. Colonia o fraccionamiento
2. Tipo de inmueble: casa, departamento, terreno, local, oficina, bodega
3. Operación: venta o renta
4. Superficie: m² construcción (casas/deptos/locales) o m² terreno (terrenos)
Opcionales: recámaras, baños, estacionamientos, condición terreno, ciudad (default Morelia).

[ACCION]{"tipo":"opinion_valor_web","colonia":"Vistas Altozano","tipo_inmueble":"terreno","operacion":"venta","m2_terreno":183,"m2_construccion":0,"recamaras":0,"banos":0,"ciudad":"Morelia","condicion_terreno":"plano"}[/ACCION]

Valores "tipo_inmueble": "casa" | "departamento" | "terreno" | "local" | "oficina" | "bodega"
Valores "operacion": "venta" | "renta"
Valores "condicion_terreno": "plano" | "pendiente" | "irregular" | "" (solo terrenos)

══════════════════════════════════════════════════
ACCIÓN 3: GENERAR CONTRATO DE ARRENDAMIENTO
══════════════════════════════════════════════════
Datos OBLIGATORIOS:
1. Calle del inmueble arrendado
2. Número exterior
3. Colonia
4. C.P.
5. Municipio y estado (ej: "Morelia, Michoacán")
6. Nombre completo del arrendador (dueño) — EN MAYÚSCULAS
7. Nombre completo del arrendatario (inquilino) — EN MAYÚSCULAS
8. Renta mensual (MXN)
9. Depósito en garantía (si no sabe, usa el mismo valor que la renta)
10. Fecha de inicio (día/mes/año)

[ACCION]{"tipo":"llenar_contrato","subtipo":"arrendamiento","calle_inmueble":"AV. CAMELINAS","num_ext":"123","num_int":"","colonia":"CHAPULTEPEC","cp":"58260","municipio_estado":"MORELIA, MICHOACÁN","arrendador":"SALVADOR BOLAÑOS NAVARRO","arrendatario":"GABRIELA NAVARRO PÉREZ","renta":8500,"deposito":8500,"dia_pago":5,"fecha_inicio":"2026-05-01"}[/ACCION]

dia_pago: día límite del mes para pagar (default 5). fecha_inicio en formato YYYY-MM-DD.

══════════════════════════════════════════════════
ACCIÓN 4: GENERAR PROMESA DE COMPRAVENTA
══════════════════════════════════════════════════
Datos OBLIGATORIOS:
1. Dirección del inmueble (calle y número)
2. Colonia
3. C.P.
4. Nombre del vendedor
5. Nombre del comprador
6. Precio total de venta
7. Monto de arras/enganche
8. Fecha límite para escriturar

[ACCION]{"tipo":"llenar_contrato","subtipo":"promesa","dir":"Cipres 167","colonia":"Melchor Ocampo","cp":"58160","vendedor":"JUAN PÉREZ GARCÍA","comprador":"MARÍA LÓPEZ HERNÁNDEZ","precio":2500000,"arras":250000,"fecha_limite":"2026-06-30"}[/ACCION]

fecha_limite en formato YYYY-MM-DD.

══════════════════════════════════════════════════
ACCIÓN 5: FICHA TÉCNICA DESDE EASYBROKER
══════════════════════════════════════════════════
[ACCION]{"tipo":"crear_ficha","id_easybroker":"EB-KH4322"}[/ACCION]
Si el usuario no da el ID: [ACCION]{"tipo":"navegar","modulo":"ficha"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 6: FICHA TÉCNICA MANUAL
══════════════════════════════════════════════════
Datos mínimos: tipo, operación, precio, colonia.
[ACCION]{"tipo":"crear_ficha_manual","tipo_inmueble":"casa","operacion":"venta","precio":3500000,"colonia":"Chapultepec","ciudad":"Morelia","calle":"Av. Madero 123","recamaras":3,"banos":2,"m2_construccion":180,"m2_terreno":220,"estacionamientos":2,"descripcion":""}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 7: BUSCAR PROPIEDAD EN MIS INMUEBLES
══════════════════════════════════════════════════
[ACCION]{"tipo":"buscar_propiedad","query":"Chapultepec"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 8: CREAR CAMPAÑA DE META ADS
══════════════════════════════════════════════════
Datos OBLIGATORIOS:
1. ¿Para qué propiedad? (nombre o descripción breve)
2. ¿Presupuesto diario en pesos? (mínimo $50)
3. Objetivo — ofrece opciones: a) Conseguir leads  b) Llevar tráfico a web  c) Reconocimiento

[ACCION]{"tipo":"confirmar_campana","nombre":"NOMBRE","objetivo":"OUTCOME_LEADS","presupuesto_diario_mxn":150,"ciudad":"Morelia","edad_min":25,"edad_max":55,"url_destino":"","texto_anuncio":""}[/ACCION]

Valores "objetivo": "OUTCOME_LEADS" | "OUTCOME_TRAFFIC" | "OUTCOME_AWARENESS"
NUNCA ejecutes sin confirmación explícita.

══════════════════════════════════════════════════
ACCIÓN 9: NAVEGAR A UN MÓDULO
══════════════════════════════════════════════════
[ACCION]{"tipo":"navegar","modulo":"isr"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"contratos"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"avm"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"props"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"ficha"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"ficha-manual"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"facebook-ads"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"contactos"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"image-cleaner"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 10: AGREGAR CONTACTO DIRECTAMENTE (sin navegar)
══════════════════════════════════════════════════
Cuando el usuario pide agregar un contacto/prospecto/cliente, captura los datos y lánzalo directo. NO navegues. El contacto se crea en el CRM y aparece la confirmación en el chat.

Datos OBLIGATORIOS: nombre. Opcionales: telefono, email, empresa, tipo_contacto (prospecto|vendedor|comprador|arrendatario), notas.

[ACCION]{"tipo":"agregar_contacto","nombre":"María López","telefono":"4431234567","email":"maria@example.com","tipo_contacto":"prospecto","notas":"Interesada en Chapultepec, presupuesto 4M"}[/ACCION]

Ejemplo:
Usuario: "agrega a María López, su tel es 443 123 4567, le interesa una casa en Chapultepec con presupuesto de 4 millones"
Broq: "Listo, lo agrego."
[ACCION]{"tipo":"agregar_contacto","nombre":"María López","telefono":"4431234567","tipo_contacto":"prospecto","notas":"Interesada en Chapultepec, presupuesto 4M"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 11A: CALCULAR ISR Y DESCARGAR PDF DIRECTAMENTE (preferida)
══════════════════════════════════════════════════
Cuando tengas TODOS los datos del ISR y el usuario quiere el resultado YA,
usa esta acción. El PDF se descarga directo en su dispositivo sin sacarlo
del chat. Es la acción DEFAULT para "calcular ISR" / "dame el ISR de…".

Mismos campos que `llenar_isr`, solo cambia el tipo.

[ACCION]{"tipo":"calcular_isr_directo","precio_venta":3200000,"precio_compra":1000000,"anio_venta":2026,"mes_venta":3,"anio_compra":2015,"mes_compra":1,"inmueble":"casa","exencion":"no","mejoras":0,"escrituracion":0,"comision":96000}[/ACCION]

Ejemplo:
Usuario: "calcula el ISR y mándame el PDF"
Broq: "Listo, calculando y descargando."
[ACCION]{"tipo":"calcular_isr_directo",...}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 11B: ESTIMAR VALOR Y DESCARGAR PDF DIRECTAMENTE (preferida)
══════════════════════════════════════════════════
Cuando tengas los datos para una estimación de valor y el usuario quiere el
PDF YA, usa esta acción. Busca comparables, hace el cálculo y descarga el PDF
directo en el chat. Tarda 30s–2 min porque consulta portales en vivo.

Mismos campos que `opinion_valor_web`.

[ACCION]{"tipo":"estimar_valor_directo","colonia":"Vistas Altozano","tipo_inmueble":"casa","operacion":"venta","m2_construccion":180,"m2_terreno":220,"recamaras":3,"banos":2,"ciudad":"Morelia","condicion_terreno":""}[/ACCION]

Ejemplo:
Usuario: "estima el valor de una casa de 180m² en Vistas Altozano y mándame el PDF"
Broq: "Voy a buscar comparables y prepararte el PDF. Tarda un poco."
[ACCION]{"tipo":"estimar_valor_directo",...}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 12: GENERAR Y DESCARGAR CONTRATO DIRECTAMENTE
══════════════════════════════════════════════════
Cuando ya tienes TODOS los datos obligatorios y el usuario CONFIRMA que quiere descargar el contrato, usa esta acción. El DOCX se descarga directo en su dispositivo, sin navegar.

Si faltan datos: usa "llenar_contrato" (acción 4) en su lugar — eso navega y deja el form pre-llenado para que complete.

Datos: TODOS los del contrato. subtipo: "arrendamiento" | "promesa".

[ACCION]{"tipo":"generar_contrato_directo","subtipo":"arrendamiento","datos":{...}}[/ACCION]

Ejemplo:
Usuario: "ya tengo todo, descárgame el contrato ya"
Broq: "Listo, lo genero y se descarga."
[ACCION]{"tipo":"generar_contrato_directo","subtipo":"arrendamiento","datos":{"fecha_contrato":"2026-05-21","calle_inmueble":"Av. Camelinas","num_ext_inmueble":"123","colonia_inmueble":"CHAPULTEPEC","cp_inmueble":"58260","municipio_estado_inmueble":"MORELIA, MICHOACAN","nombre_arrendador":"SALVADOR BOLAÑOS","nombre_arrendatario":"GABRIELA NAVARRO","renta_mensual":8500,"deposito_garantia":8500,"dia_pago":5,"fecha_inicio":"2026-06-01","fecha_fin":"2027-05-31"}}[/ACCION]

══════════════════════════════════════════════════
EJEMPLOS DE CONVERSACIÓN
══════════════════════════════════════════════════

EJEMPLO ISR:
Usuario: "calcula el ISR de una casa que vendí en 3.2 millones en marzo 2026, la compré en un millón en enero 2015, comisión 96 mil"
Broq: "Venta $3,200,000 en marzo 2026, compra $1,000,000 en enero 2015, comisión $96,000. ¿Usaste la exención de casa habitación en los últimos 3 años?"
Usuario: "no"
Broq: "Listo, calculando."
[ACCION]{"tipo":"llenar_isr","precio_venta":3200000,"precio_compra":1000000,"anio_venta":2026,"mes_venta":3,"anio_compra":2015,"mes_compra":1,"inmueble":"casa","exencion":"no","mejoras":0,"escrituracion":0,"comision":96000}[/ACCION]

EJEMPLO CONTRATO:
Usuario: "necesito un contrato de renta para Av. Camelinas 123, Chapultepec, Morelia, el dueño es Salvador Bolaños y el inquilino es Gabriela Navarro, renta 8,500"
Broq: "¿Cuál es el código postal?"
Usuario: "58260"
Broq: "¿Desde qué fecha empieza?"
Usuario: "1 de mayo de 2026"
Broq: "Generando contrato."
[ACCION]{"tipo":"llenar_contrato","subtipo":"arrendamiento","calle_inmueble":"AV. CAMELINAS","num_ext":"123","num_int":"","colonia":"CHAPULTEPEC","cp":"58260","municipio_estado":"MORELIA, MICHOACÁN","arrendador":"SALVADOR BOLAÑOS NAVARRO","arrendatario":"GABRIELA NAVARRO PÉREZ","renta":8500,"deposito":8500,"dia_pago":5,"fecha_inicio":"2026-05-01"}[/ACCION]

EJEMPLO EASYBROKER:
Usuario: "¿cómo conecto mi EasyBroker?"
Broq: "En EasyBroker, haz clic en tu nombre (arriba a la derecha) → Configuración de cuenta → Integraciones o API → copia tu API Key. Luego en Broquer, abre tu perfil (tus iniciales abajo a la izquierda del sidebar) → sección EasyBroker → pega la key y haz clic en Conectar. Queda listo en segundos."

EJEMPLO ASESORÍA LEGAL:
Usuario: "¿puedo rentar sin contrato escrito?"
Broq: "Técnicamente sí — el Código Civil de Michoacán permite arrendamiento verbal. Pero sin contrato escrito, si hay conflicto, la ley presume que el plazo es mensual y que no hay depósito, lo que te deja sin herramienta legal. Siempre conviene tener el contrato firmado."

Responde siempre en español. Sin markdown en respuestas conversacionales (sin **, sin #, sin listas con guiones). Usa oraciones naturales y cortas cuando el usuario habla por voz."""

class ClaudeChatRequest(BaseModel):
    messages: list
    max_tokens: int = 1200
    temperature: float = 0.7
    context: str = ""  # Módulo/pantalla activa — se inyecta al system prompt

@app.post("/chat-claude")
async def chat_claude_proxy(req: ClaudeChatRequest, request: Request):
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")
    user_id = await get_user_id_from_token(request)

    # Construir system prompt con contexto dinámico del módulo activo
    system_content = SHAARK_SYSTEM_PROMPT
    if req.context:
        system_content += f"\n\n═══════════════════════════════════════\nCONTEXTO ACTUAL DEL USUARIO\n═══════════════════════════════════════\nEl usuario está en: {req.context}\nAdapta tu respuesta y acciones a este módulo cuando sea relevante."

    user_messages = [m for m in req.messages if m.get("role") != "system"]

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": req.max_tokens,
                "system": system_content,
                "messages": user_messages,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            }
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code,
                detail=f"Error Claude: {r.text}")

        data = r.json()
        _track_anthropic(user_id, _request_modulo(request, "chat"), "/chat-claude", data,
                         modelo=data.get("model") or "claude-sonnet-4-6")
        # Extraer texto ignorando bloques tool_use (web_search)
        blocks = data.get("content", [])
        text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        reply_text = "".join(text_parts).strip() or "Sin respuesta."
        return {
            "choices": [
                {"message": {"role": "assistant", "content": reply_text}}
            ]
        }


# ──────────────────────────────────────────────────────────────
# SOLICITUD DE ARRENDAMIENTO — Análisis con Claude (vision/PDF/DOCX)
# ──────────────────────────────────────────────────────────────
@app.post("/solicitud-arrendamiento/analizar")
async def analizar_solicitud_arrendamiento(
    request: Request,
    file: UploadFile = File(...),
    documentos: List[UploadFile] = File(default=[]),
):
    """
    Lee una solicitud de arrendamiento (PDF, imagen JPG/PNG/WEBP o DOCX) más
    hasta 5 documentos de respaldo opcionales (comprobantes de ingresos, escrituras
    del aval, INE, estados de cuenta, etc.) y los cruza todos con Claude Sonnet 4.6.
    Devuelve JSON estructurado con puntaje, riesgo, hallazgos y recomendaciones.
    Solicitud principal: máx 15 MB. Documentos adicionales: máx 8 MB c/u.
    Requiere usuario autenticado.
    """
    # Auth
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión para usar este módulo.")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor.")

    # Leer archivo y validar tamaño
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 15 MB).")
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Archivo vacío o corrupto.")

    fname = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()

    is_pdf = ctype == "application/pdf" or fname.endswith(".pdf")
    is_docx = "wordprocessingml" in ctype or fname.endswith(".docx")
    is_image = (
        ctype.startswith("image/")
        or any(fname.endswith(x) for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"])
    )

    # System prompt: rúbrica de evaluación + formato JSON estricto
    SYSTEM_PROMPT = """Eres un perito experto en evaluación de solicitudes de arrendamiento inmobiliario en México. Analizas con el rigor de un banco o inmobiliaria seria. Detectas inconsistencias, riesgos de impago y posibles fraudes.

Envuelve tu respuesta SIEMPRE entre las etiquetas <output> y </output>. Dentro de esas etiquetas coloca ÚNICAMENTE el JSON, sin texto adicional, sin bloques de markdown, sin comentarios. Así:
<output>
{ ... tu JSON aquí ... }
</output>

La estructura del JSON debe ser:
{
  "puntaje": <entero 0-100>,
  "nivel_riesgo": "verde" | "amarillo" | "rojo",
  "veredicto_corto": "<1-2 líneas resumiendo el caso>",
  "datos_extraidos": {
    "nombre_solicitante": "<string o null>",
    "edad": "<string o null>",
    "ocupacion": "<string o null>",
    "ingresos_mensuales_mxn": <número o null>,
    "renta_solicitada_mxn": <número o null>,
    "ratio_ingreso_renta": <número o null>,
    "tiene_aval": <true | false | null>,
    "tiene_referencias": <true | false | null>
  },
  "secciones": [
    {"categoria": "Identificación", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Domicilio", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Empleo e ingresos", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Estabilidad y referencias", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Fiador o garantía", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Indicadores PLD", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]},
    {"categoria": "Coherencia documental", "estatus": "ok"|"atencion"|"critico"|"faltante", "puntos": ["..."]}
  ],
  "banderas_rojas": ["..."],
  "recomendaciones": ["..."]
}

Rúbrica de puntaje:
- 90-100 (verde): completo, coherente, ratio ingreso/renta >= 3x, aval sólido con propiedad libre de gravamen
- 75-89 (verde): mayoritariamente completo, ratio 2.5-3x, mínimas faltantes
- 60-74 (amarillo): incompleto pero rescatable, ratio 2-2.5x o aval débil
- 40-59 (amarillo/rojo): faltan elementos críticos, ratio 1.5-2x, o referencias no verificables
- 0-39 (rojo): inconsistencias graves, posibles indicios de falsificación, datos críticos ausentes, ratio < 1.5x

Reglas estrictas:
1. Si no puedes extraer un dato, ponlo en null. NUNCA inventes información.
2. Calcula ratio_ingreso_renta = ingresos_mensuales_mxn / renta_solicitada_mxn cuando ambos estén presentes. Devuélvelo con 2 decimales.
3. En "secciones" SIEMPRE devuelve las 7 categorías en ese orden, aunque alguna esté "faltante".
4. estatus "faltante" = la solicitud simplemente no incluyó esa información (no es necesariamente malo, pero hay que pedirla).
5. estatus "critico" = riesgo grave detectado (no solo "falta", sino algo activamente alarmante).
6. Los "puntos" deben ser observaciones CONCRETAS, no generalidades. Cita datos específicos del documento cuando puedas.
7. "banderas_rojas" solo si hay riesgos genuinos: inconsistencias entre secciones, ratio < 2x sin aval, datos manipulados, referencias laborales sospechosas, fecha de emisión muy antigua, etc.
8. "recomendaciones" son acciones concretas que el agente debe hacer ANTES de firmar: verificar X comprobante con el patrón, confirmar Y referencia, pedir Z documento faltante, etc.
9. Indicadores PLD: revisa si hay coincidencias con criterios de actividad vulnerable de LFPIORPI (renta mensual >= 1,605 UMA = $188,282.55 MXN en 2026 obliga identificación del cliente; >= 3,210 UMA = $376,565 MXN obliga aviso al SAT)."""

    # ── Helper: convierte un UploadFile a bloque(s) de contenido para Claude ──
    async def archivo_a_bloques(uf: UploadFile, etiqueta: str, max_bytes: int = 8 * 1024 * 1024):
        """Devuelve lista de bloques content para Claude según tipo de archivo."""
        raw = await uf.read()
        if len(raw) > max_bytes or len(raw) < 50:
            return []  # omitir silenciosamente si excede límite o está vacío
        n = (uf.filename or "").lower()
        ct = (uf.content_type or "").lower()
        bloques = []
        bloques.append({"type": "text", "text": f"\n--- {etiqueta} ({uf.filename}) ---"})
        if ct == "application/pdf" or n.endswith(".pdf"):
            bloques.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(raw).decode("utf-8")
                }
            })
        elif "wordprocessingml" in ct or n.endswith(".docx"):
            try:
                from docx import Document as _DocxDocument
                _doc = _DocxDocument(io.BytesIO(raw))
                _parts = []
                for _p in _doc.paragraphs:
                    if _p.text and _p.text.strip():
                        _parts.append(_p.text.strip())
                for _tbl in _doc.tables:
                    for _row in _tbl.rows:
                        for _cell in _row.cells:
                            for _p in _cell.paragraphs:
                                if _p.text and _p.text.strip():
                                    _parts.append(_p.text.strip())
                _txt = "\n".join(_parts)[:10000]
                if _txt.strip():
                    bloques.append({"type": "text", "text": _txt})
            except Exception:
                pass  # omitir si no se puede leer
        elif ct.startswith("image/") or any(n.endswith(x) for x in [".jpg", ".jpeg", ".png", ".webp"]):
            _mt = "image/jpeg"
            if n.endswith(".png") or "png" in ct:
                _mt = "image/png"
            elif n.endswith(".webp") or "webp" in ct:
                _mt = "image/webp"
            bloques.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _mt,
                    "data": base64.standard_b64encode(raw).decode("utf-8")
                }
            })
        return bloques

    # ── Construir user_content: solicitud principal ──────────────────────────
    user_content = []

    if is_pdf:
        b64 = base64.standard_b64encode(content).decode("utf-8")
        user_content.append({"type": "text", "text": "--- SOLICITUD DE ARRENDAMIENTO (documento principal) ---"})
        user_content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64}
        })

    elif is_docx:
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(io.BytesIO(content))
            parts = []
            for p in doc.paragraphs:
                if p.text and p.text.strip():
                    parts.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            if p.text and p.text.strip():
                                parts.append(p.text.strip())
            extracted = "\n".join(parts)[:18000]
            if not extracted.strip():
                raise HTTPException(status_code=400, detail="El DOCX no contiene texto legible.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el DOCX: {e}")
        user_content.append({
            "type": "text",
            "text": "--- SOLICITUD DE ARRENDAMIENTO (documento principal, formato Word) ---\n\n" + extracted
        })

    elif is_image:
        media_type = "image/jpeg"
        if fname.endswith(".png") or "png" in ctype:
            media_type = "image/png"
        elif fname.endswith(".webp") or "webp" in ctype:
            media_type = "image/webp"
        elif fname.endswith(".gif") or "gif" in ctype:
            media_type = "image/gif"
        b64 = base64.standard_b64encode(content).decode("utf-8")
        user_content.append({"type": "text", "text": "--- SOLICITUD DE ARRENDAMIENTO (documento principal) ---"})
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64}
        })

    else:
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Sube PDF, imagen (JPG/PNG/WEBP) o DOCX."
        )

    # ── Documentos adicionales (hasta 5) ─────────────────────────────────────
    docs_validos = (documentos or [])[:5]
    nombres_extra = []
    for i, doc_extra in enumerate(docs_validos, start=1):
        etiqueta = f"DOCUMENTO DE RESPALDO #{i}"
        bloques = await archivo_a_bloques(doc_extra, etiqueta)
        if bloques:
            user_content.extend(bloques)
            nombres_extra.append(doc_extra.filename or f"documento_{i}")

    # ── Instrucción final con contexto de documentos enviados ─────────────────
    if nombres_extra:
        USER_INSTRUCTION = (
            f"Se adjuntan {len(nombres_extra)} documento(s) de respaldo además de la solicitud principal: "
            + ", ".join(nombres_extra) + ".\n"
            "Cruza la información de todos los documentos entre sí:\n"
            "- Verifica que los ingresos declarados en la solicitud coincidan con los comprobantes.\n"
            "- Verifica que el aval tenga solvencia real según su escritura u otro documento.\n"
            "- Detecta inconsistencias entre lo declarado en la solicitud y lo que muestran los respaldos.\n"
            "- Menciona discrepancias específicas en la sección 'Coherencia documental' y en banderas_rojas si aplica.\n\n"
            "Devuelve tu evaluación ÚNICAMENTE dentro de etiquetas <output></output>, "
            "como se indica en el system prompt. Solo JSON entre esas etiquetas."
        )
    else:
        USER_INSTRUCTION = (
            "Analiza esta solicitud de arrendamiento. "
            "Devuelve tu evaluación ÚNICAMENTE dentro de etiquetas <output></output>, "
            "como se indica en el system prompt. Solo JSON entre esas etiquetas, nada más."
        )

    user_content.append({"type": "text", "text": USER_INSTRUCTION})

    # Llamada a Claude
    try:
        async with httpx.AsyncClient(timeout=150) as client:
            r = await client.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 4096,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_content}]
                }
            )
        if r.status_code != 200:
            err_txt = (r.text or "")[:300]
            raise HTTPException(
                status_code=502,
                detail=f"Error Claude {r.status_code}: {err_txt}"
            )

        data = r.json()
        _track_anthropic(user_id, "solicitud-arr", "/solicitud-arrendamiento/analizar",
                         data, modelo=data.get("model") or "claude-sonnet-4-6")
        reply_text = ""
        try:
            reply_text = data.get("content", [{}])[0].get("text", "")
        except Exception:
            pass
        if not reply_text:
            raise HTTPException(status_code=502, detail="Claude devolvió respuesta vacía.")

        # ── Extracción robusta del JSON ──────────────────────────────────
        # Prioridad 1: contenido entre <output>...</output>
        json_str = None
        tag_match = re.search(r'<output>\s*(.*?)\s*</output>', reply_text, re.DOTALL | re.IGNORECASE)
        if tag_match:
            json_str = tag_match.group(1).strip()
        else:
            # Prioridad 2: primer bloque { ... } del texto
            brace_match = re.search(r'\{.*\}', reply_text, re.DOTALL)
            if brace_match:
                json_str = brace_match.group().strip()

        if not json_str:
            raise HTTPException(status_code=502, detail="Claude no devolvió JSON válido.")

        # Limpiar caracteres de control que vienen de PDFs (null bytes, BOM, etc.)
        # Conservamos \n \r \t que son válidos en JSON.
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)
        # Quitar BOM si quedó al inicio
        json_str = json_str.lstrip('\ufeff')

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Segundo intento: escapar comillas dobles problemáticas dentro de valores string.
            # Reemplaza secuencias tipo :" texto "con comillas" ": con versión escapada.
            try:
                json_str2 = re.sub(
                    r'(?<=[:{,\[])\s*"((?:[^"\\]|\\.)*)"\s*(?=[,}\]:])',
                    lambda m: '"' + m.group(1).replace('"', '\\"') + '"',
                    json_str
                )
                parsed = json.loads(json_str2)
            except Exception:
                raise HTTPException(
                    status_code=502,
                    detail=f"JSON inválido de Claude: {str(e)[:120]}"
                )

        # Validación ligera del shape
        if "puntaje" not in parsed or "nivel_riesgo" not in parsed:
            raise HTTPException(status_code=502, detail="Respuesta sin estructura esperada.")

        # Asegurar que datos_extraidos y secciones existan (aunque vacías)
        parsed.setdefault("datos_extraidos", {})
        parsed.setdefault("secciones", [])
        parsed.setdefault("banderas_rojas", [])
        parsed.setdefault("recomendaciones", [])
        parsed.setdefault("veredicto_corto", "")

        return parsed

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="El análisis tardó demasiado. Intenta de nuevo.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando: {str(e)[:200]}")


@app.post("/isr-pdf")
async def generar_isr_pdf(p: dict, request: Request):
    """Recibe HTML del cálculo ISR y lo convierte a PDF con Playwright."""
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    from playwright.async_api import async_playwright  # noqa: re-import ok here (lazy)
    html = p.get("html", "")
    if not html:
        raise HTTPException(status_code=400, detail="HTML vacío")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(300)
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "right": "20mm", "bottom": "20mm", "left": "20mm"}
        )
        await browser.close()
    token = str(_uuid.uuid4()).replace("-","")[:16]
    filename = p.get("filename", "ISR_Brokr.pdf")
    _pdf_store[token] = (pdf_bytes, filename)
    if len(_pdf_store) > 50:
        oldest = list(_pdf_store.keys())[0]
        del _pdf_store[oldest]
    from fastapi.responses import JSONResponse
    return JSONResponse({"token": token, "filename": filename})


@app.get("/propiedad/{property_id}")
async def get_propiedad(property_id: str, request: Request):
    # Multi-tenant blindado: identificar al usuario por su token de Supabase
    # y sacar SU EB key del backend. La API key nunca toca el frontend.
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    user_key = await get_eb_key_for_user(user_id)
    if not user_key:
        raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker para usar este módulo.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{EB_BASE}/properties/{property_id}",
                             headers=eb_headers(user_key))
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil → Integración EasyBroker.")
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()

# ════════════════════════════════════════════════════════════════
# IMPORTACIÓN MASIVA DESDE EASYBROKER
# Trae TODAS las propiedades del agente desde su cuenta de EasyBroker
# y las inserta en Supabase (tabla propiedades) bajo SU user_id.
# Deduplicación por eb_public_id: si ya existe, la salta.
# ════════════════════════════════════════════════════════════════

# Mapeo: tipo EasyBroker → tipo Brokr
_EB_TIPO_MAP = {
    "Casa": "casa",
    "Casa en condominio": "casa",
    "Departamento": "departamento",
    "Departamento en condominio": "departamento",
    "Terreno": "terreno",
    "Terreno comercial": "terreno",
    "Local comercial": "local",
    "Local en centro comercial": "local",
    "Oficina": "oficina",
    "Edificio": "oficina",
    "Bodega comercial": "bodega",
    "Bodega industrial": "bodega",
    "Nave industrial": "bodega",
    "Rancho": "terreno",
    "Quinta": "casa",
    "Villa": "casa",
    "Loft": "departamento",
    "Penthouse": "departamento",
    "Casa uso de suelo": "casa",
}

# Mapeo: estatus EasyBroker → estatus Broquer.
# Solo migramos estos cuatro: publicadas, apartadas, vendidas y rentadas
# (las que ya cerraron cuentan como cerradas). El resto (no publicadas,
# suspendidas, rechazadas) NO se importa.
_EB_STATUS_MAP = {
    "published":     "activa",
    "not_published": "suspendida",
    "reserved":      "reservada",
    "sold":          "vendida",
    "rented":        "rentada",
}

# Estatus que se importan cuando el usuario no elige ninguno (apps viejas
# que todavía no mandan la selección). Se conserva el comportamiento previo:
# no se traen las no publicadas si nadie las pidió.
_EB_STATUS_DEFAULT = ["published", "reserved", "sold", "rented"]

# Tope de propiedades por importación.
_EB_LIMITE_PROPIEDADES = 1000

def _eb_to_brokr(prop_full: dict, user_id: str) -> dict:
    """Mapea una propiedad de EasyBroker al esquema de la tabla propiedades de Brokr."""
    # Conversiones numéricas defensivas
    def _to_int(v):
        try:    return int(float(v)) if v not in (None, "", 0) else None
        except: return None
    def _to_float(v):
        try:    return float(v) if v not in (None, "", 0) else None
        except: return None

    # Tipo
    tipo_eb = prop_full.get("property_type", "")
    tipo = _EB_TIPO_MAP.get(tipo_eb, tipo_eb.lower() if tipo_eb else None)

    # Operación + precio (EB tiene array de operations con price)
    operaciones = prop_full.get("operations", []) or []
    operacion = None
    precio = None
    moneda = "MXN"
    if operaciones:
        op_venta = next((o for o in operaciones if o.get("type") == "sale"), None)
        op_renta = next((o for o in operaciones if o.get("type") == "rental"), None)
        op = op_venta or op_renta or operaciones[0]
        if op.get("type") == "sale":
            operacion = "venta"
        elif op.get("type") == "rental":
            operacion = "renta"
        amount = op.get("amount") or 0
        precio = float(amount) if amount else None
        moneda = (op.get("currency") or "MXN").upper()

    # Ubicación — EasyBroker la manda como objeto:
    # {region, city, city_area, street, postal_code, latitude, longitude}
    # Soportamos también el formato viejo de string defensivamente.
    location_raw = prop_full.get("location") or ""
    colonia = None
    ciudad  = "Morelia"
    estado  = "Michoacán"
    cp_from_loc = None
    if isinstance(location_raw, dict):
        colonia = location_raw.get("city_area") or location_raw.get("name") or location_raw.get("neighborhood") or None
        ciudad  = location_raw.get("city") or location_raw.get("municipality") or "Morelia"
        estado  = location_raw.get("region") or location_raw.get("state") or "Michoacán"
        cp_from_loc = location_raw.get("postal_code") or None
    elif isinstance(location_raw, str) and location_raw:
        parts = [p.strip() for p in location_raw.split(",")]
        colonia = parts[0] if parts else None
        ciudad  = parts[1] if len(parts) > 1 else "Morelia"
        estado  = parts[2] if len(parts) > 2 else "Michoacán"

    # Calle, num_ext, num_int — EB las pone juntas en "street" (ej. "Av. Madero 123 Int 4")
    # Intentamos separar con un regex sencillo; si no se puede, todo va a "calle".
    street_raw = prop_full.get("street") or ""
    # En la API moderna street también puede venir dentro de location.street
    if not street_raw and isinstance(location_raw, dict):
        street_raw = location_raw.get("street") or ""
    calle, num_ext, num_int = _split_street(street_raw)

    # CP — preferir el de la raíz, si no, el de location
    cp = prop_full.get("postal_code") or cp_from_loc or None

    # Fotos — property_images[].url (la API moderna usa "url", no "title_image_full")
    property_images = prop_full.get("property_images", []) or []
    fotos = []
    title_img = prop_full.get("title_image_full") or prop_full.get("title_image_thumb")
    if title_img:
        fotos.append(title_img)
    for img in property_images:
        url = img.get("url") or img.get("title_image_full") or img.get("image_url")
        if url and url not in fotos:
            fotos.append(url)

    # Amenidades (features[] en EB)
    features = prop_full.get("features") or []
    amenidades = [f for f in features if isinstance(f, str) and f.strip()] or None

    return {
        "user_id":            user_id,
        "eb_public_id":       prop_full.get("public_id"),
        "titulo":             prop_full.get("title") or "Propiedad",
        "tipo":               tipo,
        "operacion":          operacion,
        "estatus":            "activa",
        "precio":             precio,
        "moneda":             moneda,
        "calle":              calle or street_raw or None,
        "num_exterior":       num_ext,
        "num_interior":       num_int,
        "colonia":            colonia,
        "ciudad":             ciudad,
        "estado":             estado,
        "cp":                 cp,
        "m2_construccion":    _to_float(prop_full.get("construction_size")),
        "m2_terreno":         _to_float(prop_full.get("lot_size")),
        "recamaras":          _to_int(prop_full.get("bedrooms")),
        "banos":              _to_float(prop_full.get("bathrooms")),
        "medio_bano":         _to_int(prop_full.get("half_bathrooms")),
        "estacionamientos":   _to_int(prop_full.get("parking_spaces")),
        "nivel":              str(prop_full.get("floor")) if prop_full.get("floor") not in (None, "") else None,
        "mantenimiento":      _to_float(prop_full.get("expenses")),
        "anio_construccion":  _to_int(prop_full.get("age")),
        "descripcion":        prop_full.get("description") or None,
        "amenidades":         amenidades,
        "fotos":              fotos,
        "updated_at":         datetime.utcnow().isoformat()
    }


def _split_street(s: str):
    """Separa 'Av. Madero 123 Int 4' en (calle, num_ext, num_int).
    Tolerante: si no encuentra patrón, devuelve (s, None, None)."""
    import re
    if not s or not isinstance(s, str):
        return (None, None, None)
    s = s.strip()
    # Buscar "Int 4", "Int. 4", "interior 4", "#4 int 5" al final
    int_match = re.search(r'[\s,]+(?:int\.?|interior|depto\.?|departamento)\s*([0-9A-Za-z\-]+)\s*$', s, re.IGNORECASE)
    num_int = None
    if int_match:
        num_int = int_match.group(1)
        s = s[:int_match.start()].strip()
    # Buscar último número como num_ext: "Av. Madero 123" → calle="Av. Madero", ext="123"
    ext_match = re.search(r'^(.+?)[\s,#]+([0-9]+[A-Za-z\-]?)\s*$', s)
    if ext_match:
        return (ext_match.group(1).strip(), ext_match.group(2).strip(), num_int)
    return (s, None, num_int)

# EasyBroker limita su API a 20 peticiones por segundo. Si nos pasamos,
# responde 429 y las propiedades se pierden. Estos valores nos dejan por
# debajo del límite con margen.
_EB_LOTE          = 8     # peticiones simultáneas
_EB_PAUSA_LOTE    = 0.5   # segundos mínimos entre lotes → máx ~16 req/s
_EB_REINTENTOS    = 5
_EB_ESPERA_BASE   = 1.5   # segundos; se duplica en cada reintento
_EB_ESPERA_MAX    = 20.0


async def _eb_get_reintentos(client: httpx.AsyncClient, url: str,
                             headers: dict, params: dict = None,
                             timeout: float = 20.0):
    """
    GET a EasyBroker que reintenta cuando la API rechaza por exceso de
    peticiones (429) o falla del lado de ellos (5xx). Respeta la cabecera
    Retry-After si viene. Devuelve la respuesta, o None si nunca respondió.
    """
    ultimo = None
    for intento in range(_EB_REINTENTOS):
        try:
            r = await client.get(url, headers=headers, params=params, timeout=timeout)
            ultimo = r
            if r.status_code == 429 or r.status_code >= 500:
                try:
                    espera = float(r.headers.get("Retry-After") or 0)
                except (TypeError, ValueError):
                    espera = 0.0
                if espera <= 0:
                    espera = _EB_ESPERA_BASE * (2 ** intento)
                await asyncio.sleep(min(espera, _EB_ESPERA_MAX))
                continue
            return r
        except Exception:
            ultimo = None
            await asyncio.sleep(min(_EB_ESPERA_BASE * (2 ** intento), _EB_ESPERA_MAX))
    return ultimo


@app.get("/easybroker/diagnostico")
async def easybroker_diagnostico(request: Request):
    """
    Herramienta de diagnóstico. Le hace a EasyBroker las mismas preguntas que
    hace la importación y reporta EXACTAMENTE qué contesta, para saber si
    respeta el filtro de estatus y con qué nombre manda cada dato.
    No guarda nada.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    user_key = await get_eb_key_for_user(user_id)
    if not user_key:
        raise HTTPException(status_code=400, detail="No tienes API key de EasyBroker configurada.")

    out = {"version_api": "4.8"}

    def _total(d):
        pag = d.get("pagination") or {}
        return pag.get("total") or pag.get("total_entries") or pag.get("count")

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) Sin ningún filtro
        try:
            r0 = await client.get(f"{EB_BASE}/properties",
                                  headers=eb_headers(user_key),
                                  params={"limit": 50, "page": 1})
            d0 = r0.json() if r0.status_code == 200 else {}
            out["sin_filtro_http"] = r0.status_code
            out["sin_filtro_total"] = _total(d0)
            contenido = d0.get("content") or []
            out["sin_filtro_en_pagina"] = len(contenido)
            if contenido:
                primera = contenido[0]
                out["campos_del_listado"] = sorted(primera.keys())
                out["status_en_listado"] = primera.get("status")
                out["primer_public_id"] = primera.get("public_id")
                # Qué valores de estatus aparecen en esta página
                vistos = {}
                for p in contenido:
                    v = str(p.get("status"))
                    vistos[v] = vistos.get(v, 0) + 1
                out["status_vistos_en_pagina"] = vistos
        except Exception as e:
            out["sin_filtro_error"] = str(e)[:200]

        # 2) Con filtro, probando las dos formas de escribirlo
        for etiqueta, params in (
            ("corchetes", [("limit", 50), ("page", 1), ("search[statuses][]", "published")]),
            ("sin_corchetes", [("limit", 50), ("page", 1), ("search[statuses]", "published")]),
        ):
            try:
                r1 = await client.get(f"{EB_BASE}/properties",
                                      headers=eb_headers(user_key), params=params)
                d1 = r1.json() if r1.status_code == 200 else {}
                out[f"filtro_{etiqueta}_http"] = r1.status_code
                out[f"filtro_{etiqueta}_total"] = _total(d1)
            except Exception as e:
                out[f"filtro_{etiqueta}_error"] = str(e)[:200]

        # 3) Filtro por vendidas, para comparar contra el total
        try:
            r2 = await client.get(f"{EB_BASE}/properties",
                                  headers=eb_headers(user_key),
                                  params=[("limit", 50), ("page", 1),
                                          ("search[statuses][]", "sold")])
            d2 = r2.json() if r2.status_code == 200 else {}
            out["filtro_vendidas_http"] = r2.status_code
            out["filtro_vendidas_total"] = _total(d2)
        except Exception as e:
            out["filtro_vendidas_error"] = str(e)[:200]

        # 4) Detalle de una propiedad: qué campos trae y cómo llama al estatus
        pid = out.get("primer_public_id")
        if pid:
            try:
                rd = await client.get(f"{EB_BASE}/properties/{pid}",
                                      headers=eb_headers(user_key))
                out["detalle_http"] = rd.status_code
                if rd.status_code == 200:
                    det = rd.json()
                    out["campos_del_detalle"] = sorted(det.keys())
                    out["status_en_detalle"] = det.get("status")
            except Exception as e:
                out["detalle_error"] = str(e)[:200]

    return out


@app.post("/easybroker/import-all")
async def easybroker_import_all(request: Request):
    """
    Importa propiedades PUBLICADAS del agente desde su cuenta de EasyBroker
    a Mis Inmuebles. Upsert por eb_public_id: si ya existe, actualiza datos
    de EB pero PRESERVA notas internas y estatus que el usuario haya cambiado.

    Optimizaciones:
    - Filtra solo published con search[statuses][]=published
    - Procesa detalles en paralelo (lotes de 10)
    - Inserta en lotes a Supabase (1 POST por lote, no 1 por propiedad)
    - Preserva notas y estatus del usuario en filas existentes
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    user_key = await get_eb_key_for_user(user_id)
    if not user_key:
        raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker antes de importar.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    # ─── Estatus elegidos por el usuario ───
    # Body opcional: {"statuses": ["published", "sold", ...]}
    try:
        body_imp = await request.json()
    except Exception:
        body_imp = {}
    # Con fotos_diferidas=true NO se lanza la copia de fotos al terminar.
    # La migración completa lo usa para que la copia (pesada) no compita con
    # los pasos de contactos e historial en el mismo worker.
    fotos_diferidas = bool((body_imp or {}).get("fotos_diferidas"))
    pedidos = (body_imp or {}).get("statuses")
    if isinstance(pedidos, str):
        pedidos = [pedidos]
    if isinstance(pedidos, list):
        statuses_elegidos = [s for s in _EB_STATUS_MAP if s in pedidos]
    else:
        statuses_elegidos = []
    if not statuses_elegidos:
        statuses_elegidos = list(_EB_STATUS_DEFAULT)

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # ─── Paso 1: leer filas existentes del usuario (para preservar notas/estatus) ───
    existentes_por_eb_id = {}  # eb_public_id → {notas, estatus}
    try:
        try:
            filas_existentes = await get_rows(
                "propiedades",
                {"user_id": f"eq.{user_id}",
                 "eb_public_id": "not.is.null",
                 "select": "eb_public_id,notas,estatus"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            filas_existentes = []
        for row in filas_existentes:
            eb_id = row.get("eb_public_id")
            if eb_id:
                existentes_por_eb_id[eb_id] = {
                    "notas":   row.get("notas"),
                    "estatus": row.get("estatus"),
                }
    except Exception as e:
        print(f"[import-all] Error leyendo existentes: {e}")

    # ─── Paso 2: paginar el listado de EasyBroker, un estatus a la vez ───
    # IMPORTANTE: EasyBroker NO incluye el estatus dentro de cada propiedad,
    # ni en el listado ni en el detalle. La única forma de saber de qué estatus
    # es una propiedad es preguntarle por ese estatus y etiquetar lo que venga.
    # Por eso paginamos un estatus a la vez. (Verificado con /easybroker/diagnostico)
    estatus_por_pid = {}     # public_id → estatus Broquer
    conteo_por_estatus = {}  # estatus EB → cuántas llegaron
    ids_published = []       # orden de llegada (nombre histórico, se conserva)
    limite_alcanzado = False
    descartadas_estatus = 0  # repetidas entre estatus (ya contadas en otro)
    for s in statuses_elegidos:
        conteo_por_estatus[s] = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for eb_status in statuses_elegidos:
            if limite_alcanzado:
                break
            brokr_status = _EB_STATUS_MAP[eb_status]
            pagina = 1
            while pagina <= 400:  # tope duro de seguridad
                r = await _eb_get_reintentos(
                    client,
                    f"{EB_BASE}/properties",
                    eb_headers(user_key),
                    [("limit", 50), ("page", pagina),
                     ("search[statuses][]", eb_status)],
                    timeout=30.0,
                )
                if r is None:
                    break
                if r.status_code == 401:
                    raise HTTPException(status_code=401, detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil.")
                if r.status_code != 200:
                    break
                data = r.json()
                content = data.get("content", []) or []
                if not content:
                    break
                for p in content:
                    if len(ids_published) >= _EB_LIMITE_PROPIEDADES:
                        limite_alcanzado = True
                        break
                    pid = p.get("public_id")
                    if not pid:
                        continue
                    if pid in estatus_por_pid:
                        descartadas_estatus += 1
                        continue
                    estatus_por_pid[pid] = brokr_status
                    conteo_por_estatus[eb_status] = conteo_por_estatus.get(eb_status, 0) + 1
                    ids_published.append(pid)
                if limite_alcanzado:
                    break
                if not data.get("pagination", {}).get("next_page"):
                    break
                pagina += 1

    total_eb = len(ids_published)

    # ─── Paso 3: traer detalle de TODAS las published en paralelo (lotes de 10) ───
    # Aún las que ya existen las re-procesamos para que el upsert actualice precio,
    # fotos, descripción, amenidades, etc. (Decisión D2).
    errores: list = []
    inmuebles_listos: list = []

    # La empresa comparte UNA cuenta de EasyBroker. Sin esto, cada agente que
    # importara crearía su propia copia del mismo inventario.
    org_id_import = await get_org_id_for_user(user_id)
    if not org_id_import:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")

    async def fetch_one(client: httpx.AsyncClient, pid: str):
        try:
            rd = await _eb_get_reintentos(
                client,
                f"{EB_BASE}/properties/{pid}",
                eb_headers(user_key),
                timeout=20.0,
            )
            if rd is None:
                return ("err", {"id": pid, "error": "EasyBroker no respondió tras varios intentos"})
            if rd.status_code != 200:
                return ("err", {"id": pid, "error": f"EB status {rd.status_code}"})
            prop_full = rd.json()
            inmueble = _eb_to_brokr(prop_full, user_id)
            inmueble["org_id"] = org_id_import
            # EasyBroker no manda el estatus dentro de la propiedad. Usamos el
            # estatus por el que preguntamos para traerla.
            eb_estatus = estatus_por_pid.get(pid)
            if eb_estatus:
                inmueble["estatus"] = eb_estatus
            # Preservar notas y estatus del usuario si la fila ya existe
            prev = existentes_por_eb_id.get(pid)
            if prev:
                if prev.get("notas"):
                    inmueble["notas"] = prev["notas"]
                if prev.get("estatus"):
                    inmueble["estatus"] = prev["estatus"]
            return ("ok", inmueble)
        except Exception as e:
            return ("err", {"id": pid, "error": str(e)[:120]})

    BATCH = _EB_LOTE
    lotes_fallidos_seguidos = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(ids_published), BATCH):
            chunk = ids_published[i:i+BATCH]
            _prog(user_id, f"propiedades {min(i + BATCH, len(ids_published))} de {len(ids_published)}")
            inicio_lote = time.monotonic()
            results = await asyncio.gather(*[fetch_one(client, pid) for pid in chunk])
            # Mantener el ritmo por debajo del límite de EasyBroker: si el lote
            # tardó menos que la pausa mínima, esperamos la diferencia.
            resto = _EB_PAUSA_LOTE - (time.monotonic() - inicio_lote)
            if resto > 0 and i + BATCH < len(ids_published):
                await asyncio.sleep(resto)
            fallos_lote = 0
            for status, payload in results:
                if status == "ok":
                    inmuebles_listos.append(payload)
                else:
                    errores.append(payload)
                    fallos_lote += 1
            # Cortacircuito: si EasyBroker rechaza TODO durante varios lotes
            # seguidos (429 sostenido), no tiene caso moler reintentos media
            # hora. Se aborta con mensaje claro.
            lotes_fallidos_seguidos = (lotes_fallidos_seguidos + 1
                                       if fallos_lote == len(chunk) else 0)
            if lotes_fallidos_seguidos >= 4:
                raise HTTPException(status_code=429, detail="EasyBroker está limitando las peticiones de tu cuenta (429 sostenido). Espera 10-15 minutos y vuelve a correr la migración: lo ya importado no se pierde ni se duplica.")

    # ─── Paso 4: UPSERT en lotes a Supabase (50 por POST) ───
    # Necesita el índice único (user_id, eb_public_id) en Supabase para que
    # on_conflict funcione.
    upserted = 0
    UPSERT_BATCH = 50
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(inmuebles_listos), UPSERT_BATCH):
            chunk = inmuebles_listos[i:i+UPSERT_BATCH]
            ultimo_fallo = "sin respuesta"
            guardado = False
            for intento in range(3):
                try:
                    ri = await client.post(
                        f"{SUPABASE_URL}/rest/v1/propiedades",
                        headers={**sb_headers,
                                 "Prefer": "resolution=merge-duplicates,return=minimal"},
                        params={"on_conflict": "org_id,eb_public_id"},
                        json=chunk
                    )
                    if ri.status_code in (200, 201, 204):
                        upserted += len(chunk)
                        guardado = True
                        break
                    ultimo_fallo = f"Supabase {ri.status_code}: {ri.text[:200]}"
                except Exception as e:
                    ultimo_fallo = str(e)[:200]
                await asyncio.sleep(1.5 * (2 ** intento))
            if not guardado:
                errores.append({
                    "id": f"lote_{i // UPSERT_BATCH}",
                    "error": ultimo_fallo
                })

    nuevas      = sum(1 for inm in inmuebles_listos if inm["eb_public_id"] not in existentes_por_eb_id)
    actualizadas = upserted - nuevas if upserted >= nuevas else 0

    # Guardar las fotos en Broquer, solo, sin que el usuario espere ni deje
    # la pestaña abierta. Si ya hay un proceso corriendo para esta empresa,
    # el propio trabajador se ignora a sí mismo.
    fotos_lanzado = False
    if org_id_import and upserted and not fotos_diferidas:
        try:
            asyncio.create_task(_migrar_fotos_org(org_id_import))
            fotos_lanzado = True
        except Exception as e:
            print(f"[import-all] No se pudo lanzar el guardado de fotos: {e}")

    return {
        "total_easybroker": total_eb,
        "importadas":       nuevas,           # nuevas filas creadas
        "actualizadas":     actualizadas,     # ya existían y se actualizaron
        "ya_existian":      actualizadas,     # backward-compat con frontend viejo
        "por_estatus":      conteo_por_estatus,  # cuántas de cada estatus EB
        "statuses":         statuses_elegidos,   # estatus que se importaron
        "descartadas":      descartadas_estatus, # EB las mandó pero no se pidieron
        "limite":           _EB_LIMITE_PROPIEDADES,
        "limite_alcanzado": limite_alcanzado,
        "fotos_en_proceso": fotos_lanzado,
        "errores":          errores
    }


# ════════════════════════════════════════════════════════════════
# MIGRACIÓN DE FOTOS A STORAGE PROPIO
# Baja las fotos que hoy viven en los servidores de EasyBroker (o cualquier
# otro externo) y las re-sube al bucket fotos-propiedades del propio Broquer,
# dejando en la columna `fotos` las URLs públicas de Broquer. Así las fotos
# siguen funcionando aunque se cancele la cuenta de EasyBroker.
#
# Se procesa en TANDAS: el frontend llama en bucle mostrando progreso, con un
# cursor (id de la última propiedad revisada). Es IDEMPOTENTE: una foto que ya
# vive en Broquer se salta, y si una falla se conserva la URL original para
# reintentarla en la próxima pasada. Sube de a poco (concurrencia baja) para
# no saturar los IOPS de la instancia.
# ════════════════════════════════════════════════════════════════

_FOTOS_BUCKET = "fotos-propiedades"

_EXT_POR_MIME = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
    "image/webp": "webp", "image/gif": "gif", "image/heic": "heic",
}

def _foto_ya_es_de_broquer(url) -> bool:
    """True si la foto ya vive en el Storage de Broquer (no hay que migrarla)."""
    return isinstance(url, str) and bool(SUPABASE_URL) and SUPABASE_URL in url

def _foto_migrable(url) -> bool:
    """True si es una URL http externa que conviene bajar a Broquer."""
    return (isinstance(url, str)
            and url.startswith("http")
            and not _foto_ya_es_de_broquer(url))


# ── Compresión ──────────────────────────────────────────────────
# Las fotos de EasyBroker vienen a resolución completa (1-3 MB cada una).
# A 1600 px de lado mayor se ven idénticas en pantalla y en los PDFs, pero
# pesan una fracción. Esto baja el almacenamiento y, sobre todo, el tráfico,
# que es el recurso que primero se agota.
_FOTO_MAX_LADO = 1600
_FOTO_CALIDAD  = 82

def _comprimir_imagen(raw: bytes):
    """
    Devuelve (bytes, mime, ext) ya optimizado, o (None, None, None) si no se
    pudo mejorar. Es CPU-intensivo: llamar siempre con asyncio.to_thread.
    """
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((_FOTO_MAX_LADO, _FOTO_MAX_LADO), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=_FOTO_CALIDAD,
                optimize=True, progressive=True)
        datos = buf.getvalue()
        if datos and len(datos) < len(raw):
            return (datos, "image/jpeg", "jpg")
    except Exception:
        pass
    return (None, None, None)


async def _foto_a_storage(client: httpx.AsyncClient, url: str, sb_headers: dict):
    """
    Baja una foto externa, la comprime y la sube al Storage de Broquer.
    Devuelve la URL pública nueva, o None si algo falló (se conserva la
    original para reintentarla en la siguiente pasada).
    """
    try:
        rd = await client.get(url, timeout=30.0, follow_redirects=True)
        if rd.status_code != 200 or not rd.content:
            return None
        mime = (rd.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
        raw = rd.content
    except Exception:
        return None

    ext = _EXT_POR_MIME.get(mime, "jpg")
    comp, mime_c, ext_c = await asyncio.to_thread(_comprimir_imagen, raw)
    if comp:
        raw, mime, ext = comp, mime_c, ext_c

    nombre = f"{_uuid.uuid4().hex}.{ext}"
    try:
        ru = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}",
            headers={**sb_headers, "Content-Type": mime},
            content=raw, timeout=60.0,
        )
    except Exception:
        return None
    if ru.status_code not in (200, 201):
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{_FOTOS_BUCKET}/{nombre}"


# ── Trabajador en segundo plano ─────────────────────────────────
# Arranca solo al terminar una importación. El usuario no tiene que apretar
# nada ni dejar la pestaña abierta. Es idempotente y reanudable: si el
# servidor se reinicia a medias, la siguiente importación retoma lo que faltó.
_fotos_en_proceso = set()   # org_id que ya tienen un trabajador corriendo

async def _migrar_fotos_org(org_id: str):
    """Recorre todas las propiedades de la empresa y guarda sus fotos externas."""
    if not org_id or org_id in _fotos_en_proceso:
        return
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    _fotos_en_proceso.add(org_id)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    cursor = None
    total_fotos = 0
    total_props = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                params = {
                    "org_id": f"eq.{org_id}",
                    "select": "id,fotos",
                    "order":  "id.asc",
                    "limit":  "10",
                }
                if cursor:
                    params["id"] = f"gt.{cursor}"
                try:
                    filas = await get_rows("propiedades", params, timeout=30.0)
                except Exception:
                    break
                if not filas:
                    break

                for fila in filas:
                    cursor = fila.get("id")
                    fotos = fila.get("fotos") or []
                    if not isinstance(fotos, list) or not any(_foto_migrable(f) for f in fotos):
                        continue
                    nuevas = []
                    subidas = 0
                    for f in fotos:
                        if not _foto_migrable(f):
                            nuevas.append(f)
                            continue
                        nueva = await _foto_a_storage(client, f, sb_headers)
                        if nueva:
                            nuevas.append(nueva)
                            subidas += 1
                        else:
                            nuevas.append(f)  # se reintenta la próxima vez
                    if not subidas:
                        continue
                    try:
                        await client.patch(
                            f"{SUPABASE_URL}/rest/v1/propiedades",
                            headers={**sb_headers, "Content-Type": "application/json",
                                     "Prefer": "return=minimal"},
                            params={"id": f"eq.{fila.get('id')}"},
                            json={"fotos": nuevas}, timeout=30.0,
                        )
                        total_props += 1
                        total_fotos += subidas
                    except Exception:
                        pass
                    # Respiro para no saturar la instancia con IOPS de Storage
                    await asyncio.sleep(0.3)
    except Exception as e:
        print(f"[fotos] Error en segundo plano para org {org_id}: {e}")
    finally:
        _fotos_en_proceso.discard(org_id)
        print(f"[fotos] org {org_id}: {total_fotos} fotos guardadas en {total_props} propiedades")


@app.get("/easybroker/fotos-pendientes")
async def easybroker_fotos_pendientes(request: Request):
    """Cuántas propiedades de la empresa siguen con fotos fuera de Broquer."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return {"pendientes": 0, "en_proceso": False}
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    pendientes = 0
    try:
        filas_pendientes = await get_rows(
            "propiedades",
            {"org_id": f"eq.{org_id}", "select": "fotos"},
            timeout=30,
        )
        for fila in filas_pendientes:
            fotos = fila.get("fotos") or []
            if isinstance(fotos, list) and any(_foto_migrable(f) for f in fotos):
                pendientes += 1
    except Exception:
        pass
    return {"pendientes": pendientes, "en_proceso": org_id in _fotos_en_proceso}


@app.post("/easybroker/migrar-fotos")
async def easybroker_migrar_fotos(request: Request):
    """
    Baja a Storage propio las fotos externas de las propiedades de la empresa.
    Se llama por TANDAS desde el frontend (con cursor) para mostrar progreso
    y no exceder tiempos. Devuelve cuántas propiedades quedan por revisar.

    Body JSON opcional: { "cursor": <id de la última propiedad procesada> }
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    cursor = (body or {}).get("cursor")

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    CHUNK = 10  # propiedades por tanda

    # ─── Traer una tanda de propiedades de la empresa (keyset por id) ───
    params = {
        "org_id": f"eq.{org_id}",
        "select": "id,fotos",
        "order":  "id.asc",
        "limit":  str(CHUNK),
    }
    if cursor:
        params["id"] = f"gt.{cursor}"
    try:
        filas = await get_rows("propiedades", params, timeout=30)
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")

    propiedades_ok = 0
    fotos_subidas  = 0
    errores        = 0
    ultimo_id      = cursor

    async def _subir_una(client, url):
        """Baja una foto externa y la sube a Storage. Devuelve la URL nueva o None."""
        try:
            rd = await client.get(url, timeout=30.0, follow_redirects=True)
            if rd.status_code != 200 or not rd.content:
                return None
            mime = (rd.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
            raw = rd.content
        except Exception:
            return None
        ext = _EXT_POR_MIME.get(mime, "jpg")
        nombre = f"{_uuid.uuid4().hex}.{ext}"
        try:
            ru = await client.post(
                f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}",
                headers={**sb_headers, "Content-Type": mime},
                content=raw, timeout=60.0,
            )
        except Exception:
            return None
        if ru.status_code not in (200, 201):
            return None
        return f"{SUPABASE_URL}/storage/v1/object/public/{_FOTOS_BUCKET}/{nombre}"

    async def _resolver(client, f):
        if _foto_migrable(f):
            return (f, await _subir_una(client, f))
        return (f, None)

    async with httpx.AsyncClient(timeout=60) as client:
        for fila in filas:
            pid = fila.get("id")
            ultimo_id = pid
            fotos = fila.get("fotos") or []
            if not isinstance(fotos, list) or not any(_foto_migrable(f) for f in fotos):
                continue

            nuevas = []
            subidas_prop = 0
            # Subir de a poco (concurrencia 4) para no saturar la instancia
            i = 0
            while i < len(fotos):
                lote = fotos[i:i+4]
                resultados = await asyncio.gather(*[_resolver(client, f) for f in lote])
                for original, nueva in resultados:
                    if _foto_migrable(original) and nueva:
                        nuevas.append(nueva)
                        subidas_prop += 1
                    else:
                        # No migrable, o falló (se conserva para reintentar)
                        nuevas.append(original)
                i += 4

            if subidas_prop == 0:
                continue

            # Guardar el array nuevo (solo se toca esta propiedad)
            try:
                rp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers={**sb_headers, "Content-Type": "application/json",
                             "Prefer": "return=minimal"},
                    params={"id": f"eq.{pid}"},
                    json={"fotos": nuevas},
                )
                if rp.status_code in (200, 204):
                    propiedades_ok += 1
                    fotos_subidas += subidas_prop
                else:
                    errores += 1
            except Exception:
                errores += 1

    hay_mas = len(filas) == CHUNK

    return {
        "propiedades_actualizadas": propiedades_ok,
        "fotos_subidas":            fotos_subidas,
        "errores":                  errores,
        "cursor":                   ultimo_id,
        "hay_mas":                  hay_mas,
    }


# ════════════════════════════════════════════════════════════════
# BORRADO MASIVO
# Permite vaciar el inventario o el directorio de contactos de un jalón.
# Reglas de seguridad:
#  - Un agente normal solo puede borrar SUS propios registros.
#  - Solo el dueño o un administrador de la empresa puede borrar los de
#    todo el equipo.
#  - Al borrar propiedades se borran también sus fotos del almacenamiento,
#    porque si no seguiríamos pagando archivos que ya no le sirven a nadie.
# ════════════════════════════════════════════════════════════════

async def _alcance_borrado(user_id: str):
    """
    Decide si este usuario puede borrar y qué.
    Devuelve (filtro_supabase, alcance) o (None, None) si no puede borrar nada.

    Regla, decidida por Chava y sin excepciones:
      - En una EMPRESA, un agente NO puede borrar nada. Ni lo que él capturó.
        Solo el dueño o un administrador.
      - En una cuenta personal (un agente por su cuenta), esa organización es
        suya y él es su propio dueño, así que sí puede borrar lo suyo.
    """
    ctx = await get_org_context(user_id)
    if not ctx:
        return (None, None)
    org_id = ctx.get("org_id")
    if not org_id:
        return (None, None)
    es_admin = ctx.get("rol_org") in ("owner", "admin")
    es_empresa = (ctx.get("org_tipo") or "personal") == "empresa"

    if es_empresa and not es_admin:
        return (None, None)          # agente en empresa: no borra NADA
    return ({"org_id": f"eq.{org_id}"}, "empresa" if es_empresa else "personal")


_MSG_SIN_PERMISO = ("No tienes permiso para eliminar. En Broquer para Empresas solo "
                    "el dueño de la cuenta o un administrador puede eliminar registros. "
                    "Si necesitas quitar algo, pídeselo a quien administra tu cuenta.")


def _nombre_archivo_foto(url: str):
    """De una URL pública de Broquer saca el nombre del archivo en el bucket."""
    marca = f"/object/public/{_FOTOS_BUCKET}/"
    if isinstance(url, str) and marca in url:
        return url.split(marca, 1)[1].split("?")[0]
    return None


async def _borrar_fotos_storage(nombres: list):
    """Borra archivos del bucket en lotes. Se ejecuta en segundo plano."""
    if not nombres or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    borradas = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(nombres), 100):
                lote = nombres[i:i+100]
                try:
                    r = await client.request(
                        "DELETE",
                        f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}",
                        headers=sb_headers,
                        json={"prefixes": lote},
                    )
                    if r.status_code in (200, 204):
                        borradas += len(lote)
                except Exception:
                    pass
                await asyncio.sleep(0.2)
    finally:
        print(f"[borrado] {borradas} fotos eliminadas del almacenamiento")


@app.post("/propiedades/eliminar-masivo")
async def propiedades_eliminar_masivo(request: Request):
    """
    Borra varias propiedades de un jalón.
    Body: {"ids": ["...", "..."]}  o  {"todos": true}
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = (body or {}).get("ids") or []
    todos = bool((body or {}).get("todos"))
    if not todos and not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste ninguna propiedad.")
    if not todos and len(ids) > 2000:
        raise HTTPException(status_code=400, detail="Demasiadas propiedades a la vez. Hazlo en partes.")

    filtro, alcance = await _alcance_borrado(user_id)
    if not filtro:
        raise HTTPException(status_code=403, detail=_MSG_SIN_PERMISO)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # 1) Leer lo que sí se puede borrar (el filtro ya limita el alcance).
    # En LOTES: con cientos de IDs la URL rebasa el límite de longitud de
    # Supabase y el GET falla completo.
    filas: list = []
    try:
        if todos:
            filas = await get_rows(
                "propiedades",
                {**filtro, "select": "id,fotos", "limit": "10000"},
                timeout=60,
            )
        else:
            for i in range(0, len(ids), 200):
                lote = ids[i:i+200]
                lista = ",".join(f'"{str(x)}"' for x in lote)
                filas.extend(await get_rows(
                    "propiedades",
                    {**filtro, "select": "id,fotos", "id": f"in.({lista})"},
                    timeout=60,
                ))
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")

    if not filas:
        return {"eliminadas": 0, "fotos_programadas": 0, "alcance": alcance}

    # 2) Juntar los nombres de archivo de las fotos que viven en Broquer
    nombres = []
    for fila in filas:
        for f in (fila.get("fotos") or []):
            n = _nombre_archivo_foto(f)
            if n:
                nombres.append(n)

    # 3) Borrar las filas, en lotes, respetando siempre el alcance
    ids_reales = [str(fila.get("id")) for fila in filas if fila.get("id")]
    eliminadas = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(ids_reales), 200):
                lote = ids_reales[i:i+200]
                lista = ",".join(f'"{x}"' for x in lote)
                rd = await client.delete(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers={**sb_headers, "Prefer": "return=minimal"},
                    params={**filtro, "id": f"in.({lista})"},
                )
                if rd.status_code in (200, 204):
                    eliminadas += len(lote)
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudieron borrar todas las propiedades.")

    # 4) Las fotos se borran en segundo plano: son miles y no vale la pena
    #    hacer esperar al usuario por archivos que ya nadie va a ver.
    if nombres:
        try:
            asyncio.create_task(_borrar_fotos_storage(nombres))
        except Exception:
            pass

    return {
        "eliminadas":        eliminadas,
        "fotos_programadas": len(nombres),
        "alcance":           alcance,
    }


@app.post("/contactos/eliminar-masivo")
async def contactos_eliminar_masivo(request: Request):
    """
    Borra varios contactos de un jalón.
    Body: {"ids": ["...", "..."]}  o  {"todos": true}
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = (body or {}).get("ids") or []
    todos = bool((body or {}).get("todos"))
    if not todos and not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste ningún contacto.")

    filtro, alcance = await _alcance_borrado(user_id)
    if not filtro:
        raise HTTPException(status_code=403, detail=_MSG_SIN_PERMISO)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # Verificar en LOTES: con cientos de IDs la URL rebasa el límite de
    # longitud de Supabase y el GET falla completo. (Bug real con 599.)
    filas: list = []
    try:
        if todos:
            filas = await get_rows(
                "contactos",
                {**filtro, "select": "id", "limit": "10000"},
                timeout=60,
            )
        else:
            for i in range(0, len(ids), 200):
                lote = ids[i:i+200]
                lista = ",".join(f'"{str(x)}"' for x in lote)
                filas.extend(await get_rows(
                    "contactos",
                    {**filtro, "select": "id", "id": f"in.({lista})"},
                    timeout=60,
                ))
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")

    ids_reales = [str(fila.get("id")) for fila in filas if fila.get("id")]
    if not ids_reales:
        return {"eliminados": 0, "alcance": alcance}

    eliminados = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(ids_reales), 200):
                lote = ids_reales[i:i+200]
                lista = ",".join(f'"{x}"' for x in lote)
                rd = await client.delete(
                    f"{SUPABASE_URL}/rest/v1/contactos",
                    headers={**sb_headers, "Prefer": "return=minimal"},
                    params={**filtro, "id": f"in.({lista})"},
                )
                if rd.status_code in (200, 204):
                    eliminados += len(lote)
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudieron borrar todos los contactos.")

    return {"eliminados": eliminados, "alcance": alcance}


@app.get("/propiedades")
async def get_propiedades(page: int = 1, limit: int = 20):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{EB_BASE}/properties", headers=eb_headers(),
                             params={"page": page, "limit": limit})
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()

# ────────────────────────────────────────────
# COLONIAS AUTOCOMPLETE
# ────────────────────────────────────────────
async def fetch_all_properties() -> list:
    """Fetch all properties from EB and cache them."""
    cached = cache_get("all_properties")
    if cached is not None:
        return cached

    all_props = []
    page = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(f"{EB_BASE}/properties", headers=eb_headers(),
                                 params={"limit": 50, "page": page})
            if r.status_code != 200:
                break
            data = r.json()
            props = data.get("content", [])
            if not props:
                break
            all_props.extend(props)
            # Stop if we have enough or no more pages
            total = data.get("pagination", {}).get("total", 0)
            if len(all_props) >= min(total, 3000):  # cap at 3000 for speed
                break
            if not data.get("pagination", {}).get("next_page"):
                break
            page += 1
            if page > 60:  # safety cap
                break

    cache_set("all_properties", all_props)
    return all_props

def extract_colonia(location_str: str) -> str:
    """Extract colonia from 'Colonia, Ciudad, Estado' string."""
    if not location_str:
        return ""
    parts = [p.strip() for p in location_str.split(",")]
    return parts[0] if parts else location_str.strip()

def normalize(s: str) -> str:
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
        s = s.lower().replace(a, b)
    return s

@app.get("/colonias")
async def get_colonias(q: str = Query("", min_length=2), ciudad: str = "Morelia"):
    """Return unique colonias matching search query — fast direct EB search."""
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")

    cache_key = f"colonias_{normalize(ciudad)}"
    colonias_map = cache_get(cache_key)

    if colonias_map is None:
        # Build index: paginate EB and collect all colonias
        colonias_map = {}
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while page <= 80:  # up to 4000 properties
                r = await client.get(
                    f"{EB_BASE}/properties",
                    headers=eb_headers(),
                    params={"limit": 50, "page": page}
                )
                if r.status_code != 200:
                    break
                data = r.json()
                props = data.get("content", [])
                if not props:
                    break
                for p in props:
                    loc = p.get("location", "")
                    if not loc or normalize(ciudad) not in normalize(loc):
                        continue
                    # Status field empty in this EB plan — no filter
                    # Date: January 2025 onwards
                    # No date filter — all properties included
                    col = extract_colonia(loc)
                    if col and len(col) > 2:
                        colonias_map[col] = colonias_map.get(col, 0) + 1
                if not data.get("pagination",{}).get("next_page"):
                    break
                page += 1
        cache_set(cache_key, colonias_map)

    q_norm = normalize(q)
    matches = [
        {"colonia": col, "count": cnt}
        for col, cnt in colonias_map.items()
        if q_norm in normalize(col)
    ]
    matches.sort(key=lambda x: -x["count"])
    return {"colonias": matches[:12], "total_colonias": len(colonias_map)}

# ────────────────────────────────────────────
# AVM — HELPERS
# ────────────────────────────────────────────
class AVMRequest(BaseModel):
    colonia: str
    ciudad: str
    tipo: str
    operacion: str
    m2_construccion: Optional[float] = None
    m2_terreno:      Optional[float] = None
    recamaras:       Optional[int]   = None
    banos:           Optional[float] = None
    estado:          Optional[str]   = "bueno"
    anio_construccion: Optional[int] = None

def parse_price(val) -> Optional[float]:
    if not val:
        return None
    try:
        v = float(str(val).replace(",", ""))
        if 50_000 <= v <= 999_000_000:
            return v
    except:
        pass
    return None

TIPO_MAP = {
    "casa":          ["Casa"],
    "departamento":  ["Departamento"],
    "terreno":       ["Terreno"],
    "local":         ["Local comercial"],
    "comercial":     ["Local comercial","Oficina","Bodega"],
    "oficina":       ["Oficina"],
    "bodega":        ["Bodega"],
}
OP_MAP = {
    "venta": "sale",
    "renta": "rental",
}


TIPO_SIMILAR = {
    "casa":         ["Casa","Departamento"],
    "departamento": ["Departamento","Casa"],
    "terreno":      ["Terreno"],
    "local":        ["Local comercial","Oficina","Bodega"],
    "comercial":    ["Local comercial","Oficina","Bodega"],
    "oficina":      ["Oficina","Local comercial"],
    "bodega":       ["Bodega","Local comercial"],
}

async def get_comparables_eb(colonia: str, ciudad: str,
                              tipo: str, operacion: str) -> list:
    cache_key = f"comp_{colonia}_{ciudad}_{tipo}_{operacion}".lower().replace(" ","_")
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Map tipo to EB property_type values
    tipo_labels = TIPO_MAP.get(tipo.lower(), [tipo.capitalize()])
    op_type     = OP_MAP.get(operacion.lower(), "sale")

    comparables = []
    page = 1

    def norm(s):
        for a,b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
            s = s.lower().replace(a,b)
        return re.sub(r"[^a-z0-9 ]", "", s).strip()

    async with httpx.AsyncClient(timeout=60) as client:
        while len(comparables) < 50 and page <= 160:
            r = await client.get(
                f"{EB_BASE}/properties",
                headers=eb_headers(),
                params={"limit": 50, "page": page}
            )
            if r.status_code != 200:
                break
            data = r.json()
            props = data.get("content", [])
            if not props:
                break

            for p in props:
                # ── 1. COLONIA FILTER (strict) ──
                loc = p.get("location", "")
                if not loc:
                    continue
                if colonia and norm(colonia) not in norm(loc):
                    continue
                if norm(ciudad) not in norm(loc):
                    continue

                # ── 2. TIPO FILTER ──
                prop_type = p.get("property_type", "")
                tipo_match = any(norm(t) in norm(prop_type) for t in tipo_labels)
                if not tipo_match:
                    continue

                # ── 3. OPERATION FILTER (strict) ──
                ops = p.get("operations", [])
                matching_op = None
                for op in ops:
                    if op.get("type") == op_type:
                        matching_op = op
                        break
                if not matching_op:
                    continue  # wrong operation type — skip

                # ── 4. DATE: use created_at for appreciation calculation ──
                created_at   = p.get("created_at", "")
                published_at = p.get("published_at", "") or p.get("updated_at", "")
                # created_at = when property was first entered in EB (true age)
                pub_year = 2026  # default
                if created_at:
                    try:
                        pub_year = int(created_at[:4])
                    except:
                        pass

                # ── 5. PRICE ──
                price = parse_price(matching_op.get("amount"))
                if not price:
                    continue

                col_prop = extract_colonia(loc)
                comparables.append({
                    "precio":          price,
                    "titulo":          p.get("title", "")[:80],
                    "m2_construccion": p.get("construction_size"),
                    "m2_terreno":      p.get("lot_size"),
                    "recamaras":       p.get("bedrooms"),
                    "banos":           p.get("bathrooms"),
                    "colonia":         col_prop,
                    "fuente":          "EasyBroker",
                    "public_id":       p.get("public_id", ""),
                    "publicado":       created_at[:10] if created_at else (published_at[:10] if published_at else ""),
                    "pub_year":        pub_year,
                    "tipo_exacto":     norm(tipo_labels[0]) in norm(prop_type),
                })

            if not data.get("pagination", {}).get("next_page"):
                break
            page += 1

    # Remove outliers
    if len(comparables) >= 3:
        prices = sorted(c["precio"] for c in comparables)
        median = prices[len(prices)//2]
        comparables = [c for c in comparables
                       if median * 0.25 <= c["precio"] <= median * 4.0]

    cache_set(cache_key, comparables[:30])
    return comparables[:30]


# ────────────────────────────────────────────
# HEDONIC MODEL
# ────────────────────────────────────────────
APRECIACION_ANUAL = 0.04  # 4% annual real estate appreciation in Morelia
ANIO_ACTUAL = 2026

def ajuste_hedonico(comp: dict, sujeto: dict) -> dict:
    precio_base = comp["precio"]
    ajustes = []
    factor  = 1.0

    # ── 0. PRICE UPDATE BY APPRECIATION (4% annual) ──
    pub_year = comp.get("pub_year", ANIO_ACTUAL)
    anos_transcurridos = max(0, ANIO_ACTUAL - pub_year)
    if anos_transcurridos > 0:
        factor_apreciacion = (1 + APRECIACION_ANUAL) ** anos_transcurridos
        factor *= factor_apreciacion
        ajustes.append(f"actualización {anos_transcurridos} año{'s' if anos_transcurridos>1 else ''} "
                       f"(+{round((factor_apreciacion-1)*100,1)}% a 4%/año)")

    # m² construction (sqrt scaling)
    m2s = sujeto.get("m2_construccion")
    m2c = comp.get("m2_construccion")
    if m2s and m2c and m2c > 0 and abs(m2s - m2c) > 5:
        ratio = (m2s / m2c) ** 0.5
        factor *= ratio
        diff = m2s - m2c
        ajustes.append(f"m² ({'+' if diff>0 else ''}{diff:.0f}): "
                       f"{'+' if ratio>1 else ''}{(ratio-1)*100:.1f}%")

    # Bedrooms (4% per room)
    rs = sujeto.get("recamaras")
    rc = comp.get("recamaras")
    if rs and rc and rs != rc:
        diff = rs - rc
        factor *= (1 + diff * 0.04)
        ajustes.append(f"recámaras ({'+' if diff>0 else ''}{diff}): "
                       f"{'+' if diff>0 else ''}{diff*4}%")

    # Conservation state
    estado_adj = {"malo":-0.15,"regular":-0.07,"bueno":0.0,"excelente":0.08}
    adj_e = estado_adj.get(sujeto.get("estado","bueno"), 0.0)
    if adj_e != 0:
        factor *= (1 + adj_e)
        ajustes.append(f"estado ({sujeto.get('estado')}): "
                       f"{'+' if adj_e>0 else ''}{adj_e*100:.0f}%")

    # Age (1.5% per decade over 10 years)
    anio = sujeto.get("anio_construccion")
    if anio:
        anos = datetime.now().year - anio
        age_adj = max(-0.20, min(0.15, -0.015 * ((anos - 10) / 10)))
        if abs(age_adj) > 0.01:
            factor *= (1 + age_adj)
            ajustes.append(f"antigüedad ({anos} años): "
                           f"{'+' if age_adj>0 else ''}{age_adj*100:.1f}%")

    # EB properties are already real transaction prices
    # No offer-to-close discount needed (unlike portal listings)
    if not ajustes:
        ajustes.append("sin ajustes — comparable directo")

    return {
        **comp,
        "precio_ajustado": round(precio_base * factor, -3),
        "factor_total":    round(factor, 4),
        "ajustes":         ajustes,
    }

# ────────────────────────────────────────────
# AVM ENDPOINT
# ────────────────────────────────────────────


@app.post("/avm")
async def calcular_avm(req: AVMRequest):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")

    comparables_raw = await get_comparables_eb(
        req.colonia, req.ciudad, req.tipo, req.operacion
    )

    nivel = 1
    nivel_msg = ""

    # If < 3 exact tipo matches, try similar tipos in same colonia
    exact_matches = [c for c in comparables_raw if c.get("tipo_exacto", True)]
    if len(exact_matches) < 3 and req.tipo.lower() in TIPO_SIMILAR:
        similar_tipos = TIPO_SIMILAR[req.tipo.lower()]
        for tipo_alt in similar_tipos[1:]:  # skip first (same as original)
            alt_comps = await get_comparables_eb(
                req.colonia, req.ciudad, tipo_alt.lower(), req.operacion
            )
            for c in alt_comps:
                if c not in comparables_raw:
                    comparables_raw.append(c)
        if len(comparables_raw) >= 3:
            nivel_msg = (f"{len(exact_matches)} comparables exactos en {req.colonia}. "
                         f"Se complementó con tipos similares en la misma colonia.")

    if len(comparables_raw) < 3:
        nivel = 2
        comparables_raw = await get_comparables_eb(
            "", req.ciudad, req.tipo, req.operacion
        )
        nivel_msg = (f"Pocos comparables en {req.colonia} con datos ene 2025–mar 2026. "
                     f"Se amplió a {req.ciudad} — filtrado por precio/m².")

    if len(comparables_raw) < 2:
        raise HTTPException(
            status_code=422,
            detail=(f"No se encontraron comparables de {req.tipo} en {req.operacion} "
                    f"en {req.ciudad}. Verifica el tipo de operación e inmueble.")
        )

    sujeto = {
        "m2_construccion":   req.m2_construccion,
        "m2_terreno":        req.m2_terreno,
        "recamaras":         req.recamaras,
        "banos":             req.banos,
        "estado":            req.estado,
        "anio_construccion": req.anio_construccion,
    }

    # Apply hedonic adjustments
    ajustados = []
    for comp in comparables_raw:
        try:
            ajustados.append(ajuste_hedonico(comp, sujeto))
        except:
            continue

    if not ajustados:
        raise HTTPException(status_code=422, detail="Error procesando comparables")

    # Filter by price/m² if we have m2 data (nivel 2 only)
    if nivel == 2 and req.m2_construccion and req.m2_construccion > 0:
        pm2s = [(c, c["precio_ajustado"] / req.m2_construccion)
                for c in ajustados]
        if len(pm2s) >= 5:
            vals = sorted(p for _, p in pm2s)
            median_pm2 = vals[len(vals)//2]
            ajustados = [c for c, pm2 in pm2s
                         if median_pm2 * 0.65 <= pm2 <= median_pm2 * 1.35]

    # Calculate value range
    precios = sorted(c["precio_ajustado"] for c in ajustados)
    n       = len(precios)
    trim    = max(1, n // 10)
    p_trim  = precios[trim: n-trim] if n > 4 else precios

    valor_minimo   = round(min(p_trim), -3)
    valor_probable = round(sum(p_trim) / len(p_trim), -3)
    valor_maximo   = round(max(p_trim), -3)

    # Price per m²
    pm2_list = []
    for c in ajustados:
        m2 = c.get("m2_construccion") or req.m2_construccion
        if m2 and m2 > 0:
            pm2_list.append(c["precio_ajustado"] / m2)
    pm2_prom = round(sum(pm2_list) / len(pm2_list)) if pm2_list else None

    nivel_labels = {
        1: f"Alta confianza — {len(ajustados)} comparables en {req.colonia}",
        2: f"Confianza media — {len(ajustados)} comparables en {req.ciudad} (filtrado por precio/m²)",
    }

    return {
        "colonia":            req.colonia,
        "ciudad":             req.ciudad,
        "tipo":               req.tipo,
        "operacion":          req.operacion,
        "nivel":              nivel,
        "nivel_mensaje":      nivel_labels.get(nivel, nivel_msg),
        "fuentes":            ["EasyBroker"],
        "num_comparables":    len(ajustados),
        "valor_minimo":       valor_minimo,
        "valor_probable":     valor_probable,
        "valor_maximo":       valor_maximo,
        "precio_m2_promedio": pm2_prom,
        "comparables":        ajustados[:10],
        "nota": ("Valores calculados con base en propiedades publicadas en la bolsa "
                 "EasyBroker — comparables actualizados al 2026 con apreciación del 4% anual, más ajustes hedónicos por m², recámaras, "
                 "estado y antigüedad. El valor definitivo requiere inspección física "
                 "y avalúo formal."),
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
    }


# ────────────────────────────────────────────
# AVM — CLAUDE AI OPINION DE VALOR
# ────────────────────────────────────────────

class AvmClaudeRequest(BaseModel):
    # Ubicación
    estado: str
    ciudad: str
    colonia: str = ""
    direccion: str = ""
    tipo_zona: str = ""      # residencial, comercial, industrial, mixta, turistica
    nse: str = ""            # A, B, C+, C, D+, D, E
    # Inmueble
    tipo: str                # casa, departamento, terreno, local, oficina, bodega, edificio
    operacion: str = "venta" # venta | renta
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos_completos: float = 0
    medios_banos: int = 0
    estacionamientos: int = 0
    nivel_piso: int = 0
    # Estado y acabados
    antiguedad: int = 0
    conservacion: str = "bueno"  # excelente, bueno, regular, malo
    acabados: str = "medio"      # lujo, residencial_plus, residencial, medio, economico
    remodelado: bool = False
    descripcion_remodelacion: str = ""
    # Amenidades
    amenidades: list = []        # alberca, jardin, bodega, cuarto_servicio, elevador, seguridad, gimnasio, salon
    # Contexto
    precio_lista: float = 0
    motivo_valuacion: str = ""
    comentarios: str = ""

@app.post("/api/avm-claude")
async def avm_claude(req: AvmClaudeRequest, request: Request):
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")
    user_id = await get_user_id_from_token(request)

    # Construir descripción detallada de la propiedad
    tipo_labels = {
        "casa": "Casa habitación", "departamento": "Departamento/Condominio",
        "terreno": "Terreno", "local": "Local comercial",
        "oficina": "Oficina", "bodega": "Bodega/Nave industrial", "edificio": "Edificio"
    }
    conservacion_labels = {
        "excelente": "Excelente / Como nuevo", "bueno": "Bueno",
        "regular": "Regular / Necesita detalles", "malo": "Malo / Requiere remodelación"
    }
    acabados_labels = {
        "lujo": "Lujo / Residencial Plus", "residencial_plus": "Residencial Plus",
        "residencial": "Residencial", "medio": "Estándar / Medio", "economico": "Económico / Interés social"
    }

    partes = []
    partes.append(f"TIPO DE INMUEBLE: {tipo_labels.get(req.tipo, req.tipo)}")
    partes.append(f"OPERACIÓN: {req.operacion.upper()}")
    partes.append(f"\nUBICACIÓN:")
    partes.append(f"  - Estado: {req.estado}")
    partes.append(f"  - Ciudad/Municipio: {req.ciudad}")
    if req.colonia: partes.append(f"  - Colonia/Fraccionamiento: {req.colonia}")
    if req.direccion: partes.append(f"  - Dirección: {req.direccion}")
    if req.tipo_zona: partes.append(f"  - Tipo de zona: {req.tipo_zona}")
    if req.nse: partes.append(f"  - Nivel socioeconómico de la zona: {req.nse}")

    partes.append(f"\nDIMENSIONES:")
    if req.m2_construccion > 0: partes.append(f"  - Superficie construida: {req.m2_construccion} m²")
    if req.m2_terreno > 0: partes.append(f"  - Superficie de terreno: {req.m2_terreno} m²")
    if req.recamaras > 0: partes.append(f"  - Recámaras: {req.recamaras}")
    if req.banos_completos > 0: partes.append(f"  - Baños completos: {req.banos_completos}")
    if req.medios_banos > 0: partes.append(f"  - Medios baños: {req.medios_banos}")
    if req.estacionamientos > 0: partes.append(f"  - Estacionamientos: {req.estacionamientos}")
    if req.nivel_piso > 0: partes.append(f"  - Piso/Nivel: {req.nivel_piso}")

    partes.append(f"\nESTADO DEL INMUEBLE:")
    partes.append(f"  - Antigüedad aproximada: {req.antiguedad} años")
    partes.append(f"  - Estado de conservación: {conservacion_labels.get(req.conservacion, req.conservacion)}")
    partes.append(f"  - Calidad de acabados: {acabados_labels.get(req.acabados, req.acabados)}")
    if req.remodelado:
        partes.append(f"  - Remodelado recientemente: SÍ")
        if req.descripcion_remodelacion:
            partes.append(f"  - Descripción remodelación: {req.descripcion_remodelacion}")

    if req.amenidades:
        amenidad_labels = {
            "alberca": "Alberca/Pool", "jardin": "Jardín", "bodega": "Bodega",
            "cuarto_servicio": "Cuarto de servicio", "elevador": "Elevador",
            "seguridad": "Seguridad/Vigilancia 24h", "gimnasio": "Gimnasio",
            "salon": "Salón de eventos", "roof_garden": "Roof garden",
            "terraza": "Terraza", "vista": "Vista panorámica", "acceso_playa": "Acceso a playa",
        }
        am_list = [amenidad_labels.get(a, a) for a in req.amenidades]
        partes.append(f"\nAMENIDADES: {', '.join(am_list)}")

    if req.precio_lista > 0:
        partes.append(f"\nPRECIO DE LISTA ACTUAL: ${req.precio_lista:,.0f} MXN")
    if req.motivo_valuacion:
        partes.append(f"MOTIVO DE LA VALUACIÓN: {req.motivo_valuacion}")
    if req.comentarios:
        partes.append(f"COMENTARIOS ADICIONALES: {req.comentarios}")

    descripcion = "\n".join(partes)

    system_prompt = """Eres el mejor perito valuador de bienes raíces de México, certificado por la Sociedad Hipotecaria Federal y el INDAABIN, con 30 años de experiencia valuando propiedades en todo el territorio nacional. Tu análisis es utilizado por bancos, notarías y juzgados para transacciones de millones de pesos. La vida financiera del usuario que solicita esta estimación de valor depende de la precisión de tu análisis.

Tu misión: proporcionar la estimación de valor más precisa, fundamentada y útil posible basándote en:
1. Tu conocimiento profundo del mercado inmobiliario mexicano por región, ciudad y colonia
2. Tendencias y precios actuales del mercado (hasta tu fecha de corte de conocimiento)
3. Factores macroeconómicos: inflación, tasas de interés, INPP, INPC
4. El Método Comparativo de Mercado (enfoque principal)
5. El Enfoque Físico o de Costos (edificaciones)
6. El Enfoque de Capitalización de Rentas (cuando aplique)
7. Ajustes hedónicos por ubicación, características, estado y acabados

IMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido (sin texto antes ni después, sin markdown, sin ```json), con exactamente esta estructura:
{
  "valor_estimado": <número en pesos MXN sin comas ni signos>,
  "valor_minimo": <número>,
  "valor_maximo": <número>,
  "valor_por_m2_construccion": <número o 0 si no aplica>,
  "valor_por_m2_terreno": <número o 0 si no aplica>,
  "nivel_confianza": "<alta|media|baja>",
  "razon_confianza": "<por qué ese nivel>",
  "resumen_ejecutivo": "<2-3 oraciones concretas sobre el valor>",
  "analisis_ubicacion": "<análisis del valor de la zona y su impacto>",
  "analisis_propiedad": "<análisis de las características físicas y su impacto>",
  "factores_positivos": ["<factor 1>", "<factor 2>", ...],
  "factores_negativos": ["<factor 1>", "<factor 2>", ...],
  "recomendaciones": ["<recomendación 1>", "<recomendación 2>", ...],
  "mercado_actual": "<descripción del mercado actual en esa zona>",
  "metodologia": "<metodología aplicada y justificación>",
  "advertencias": "<advertencias o limitaciones de esta estimación>"
}"""

    user_msg = f"""Por favor valúa la siguiente propiedad y proporciona tu estimación de valor profesional:

{descripcion}

Recuerda: responde ÚNICAMENTE con el JSON, sin ningún texto adicional."""

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": user_msg}],
                "system": system_prompt,
            },
        )

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:300]}")

    _resp_json = r.json()
    _track_anthropic(user_id, "avm", "/api/avm-claude", _resp_json,
                     modelo=_resp_json.get("model") or "claude-sonnet-4-6")
    raw = _resp_json.get("content", [{}])[0].get("text", "")
    # Limpiar posibles markdown wrappers
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        resultado = _json.loads(raw)
    except Exception:
        raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")

    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")
    resultado["propiedad_descripcion"] = f"{tipo_labels.get(req.tipo, req.tipo)} en {req.colonia or req.ciudad}, {req.estado}"
    return resultado


# ────────────────────────────────────────────
# AVM — OPINIÓN DE VALOR CON INVESTIGACIÓN CONTROLADA DE COMPARABLES
# ────────────────────────────────────────────

class AvmWebSearchRequest(BaseModel):
    colonia: str
    tipo_inmueble: str          # casa | departamento | terreno | local | oficina | bodega
    operacion: str = "venta"    # venta | renta
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos: float = 0
    estacionamientos: int = 0
    condicion_terreno: str = "" # plano | pendiente | irregular
    ciudad: str = "Morelia"
    estado: str = "Michoacán"
    comentarios: str = ""

SEARCH_TIMEOUT = legacy_main_settings.avm_search_timeout
FETCH_TIMEOUT = legacy_main_settings.avm_fetch_timeout
MAX_SEARCH_RESULTS = legacy_main_settings.avm_max_search_results
MAX_URLS_TO_FETCH = legacy_main_settings.avm_max_urls_to_fetch
MAX_TEXT_CHARS_PER_URL = legacy_main_settings.avm_max_text_chars_per_url

PORTAL_HINTS = {
    "inmuebles24.com": "Inmuebles24",
    "lamudi.com.mx": "Lamudi",
    "propiedades.com": "Propiedades.com",
    "vivanuncios.com.mx": "Vivanuncios",
    "icasas.mx": "iCasas",
    "trovit.com.mx": "Trovit",
    "easybroker.com": "EasyBroker",
    "metroscubicos.com": "Metros Cúbicos",
    "nestoria.mx": "Nestoria",
    "mercadolibre.com.mx": "Mercado Libre Inmuebles",
}

BLOCKED_FETCH_DOMAINS = {
    "google.com", "google.com.mx", "facebook.com", "instagram.com", "tiktok.com",
    "youtube.com", "maps.google.com", "googleusercontent.com"
}

# ── Firecrawl: scraping con bypass de anti-bot para dominios complejos ──
FIRECRAWL_API_KEY = legacy_main_settings.firecrawl_api_key
FIRECRAWL_CONCURRENCY = legacy_main_settings.firecrawl_concurrency
FIRECRAWL_TIMEOUT = legacy_main_settings.firecrawl_timeout

# Dominios que requieren Firecrawl (DataDome / Cloudflare / antibot fuerte).
# Si no hay API key, se intenta httpx directo y los 403 se reportan como antes.
PREMIUM_FETCH_DOMAINS = {
    "inmuebles24.com",
    "lamudi.com.mx",
    "lamudi.com",
    "propiedades.com",
    "metroscubicos.com",
    "mercadolibre.com.mx",
}


async def _firecrawl_scrape(url: str) -> Dict[str, Any]:
    """
    Llama Firecrawl /v1/scrape en modo proxy=auto: cobra 1 crédito si pasa con
    proxy básico, 5 créditos si necesita escalar a enhanced. Devuelve un dict
    con `ok`, `page_text` y `credits` para logging.
    """
    if not FIRECRAWL_API_KEY:
        return {"ok": False, "error": "no_api_key", "page_text": "", "credits": 0}
    payload = {
        "url": url,
        "formats": ["markdown"],
        "proxy": "auto",
        "onlyMainContent": True,
        "timeout": int(FIRECRAWL_TIMEOUT * 1000),
    }
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT + 5) as client:
            r = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                json=payload, headers=headers,
            )
        if r.status_code != 200:
            return {"ok": False, "error": f"http_{r.status_code}", "page_text": "", "credits": 0}
        d = r.json() or {}
        if not d.get("success"):
            return {"ok": False, "error": d.get("error") or "no_success", "page_text": "", "credits": 0}
        data = d.get("data") or {}
        # Firecrawl devuelve markdown limpio; lo recortamos al mismo límite que httpx.
        text = (data.get("markdown") or "")[:MAX_TEXT_CHARS_PER_URL]
        meta = data.get("metadata") or {}
        credits = int(meta.get("creditsUsed") or d.get("creditsUsed") or 1)
        return {"ok": True, "page_text": text, "credits": credits}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "page_text": "", "credits": 0}


def _today_mx() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def _round_mxn(n: float, base: int = 1000) -> int:
    try:
        return int(round(float(n) / base) * base)
    except Exception:
        return 0


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        h = (urlparse(url).netloc or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _portal_name(url: str) -> str:
    h = _host(url)
    for domain, name in PORTAL_HINTS.items():
        if domain in h:
            return name
    return h or "Fuente web"


def _canonical_url(url: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/'), '', ''))
    except Exception:
        return url


def _sameish_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _build_search_queries(req: AvmWebSearchRequest) -> List[str]:
    tipo = {
        "terreno": "terreno", "casa": "casa", "departamento": "departamento",
        "local": "local comercial", "oficina": "oficina", "bodega": "bodega"
    }.get(req.tipo_inmueble, req.tipo_inmueble)
    op = "venta" if req.operacion == "venta" else "renta"
    base = f'{tipo} en {op} "{req.colonia}" "{req.ciudad}" precio m2'
    q = [
        base,
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:inmuebles24.com',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:lamudi.com.mx',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:propiedades.com',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:vivanuncios.com.mx',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:easybroker.com',
    ]
    if req.estado:
        q.append(f'{tipo} {op} "{req.colonia}" "{req.ciudad}" "{req.estado}"')
    return q


async def _search_google_cse(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.google_cse_api_key
    cx = legacy_main_settings.google_cse_id
    if not key or not cx:
        return []
    r = await client.get("https://www.googleapis.com/customsearch/v1", params={"key": key, "cx": cx, "q": query, "num": 10})
    if r.status_code != 200:
        return []
    out = []
    for item in r.json().get("items", []) or []:
        link = item.get("link")
        if link:
            out.append({"title": item.get("title", ""), "url": link, "snippet": item.get("snippet", ""), "provider": "google_cse"})
    return out


async def _search_serpapi(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.serpapi_api_key
    if not key:
        return []
    r = await client.get("https://serpapi.com/search.json", params={"engine": "google", "q": query, "api_key": key, "num": 10, "hl": "es", "gl": "mx"})
    if r.status_code != 200:
        return []
    out = []
    for item in r.json().get("organic_results", []) or []:
        link = item.get("link")
        if link:
            out.append({"title": item.get("title", ""), "url": link, "snippet": item.get("snippet", ""), "provider": "serpapi"})
    return out


async def _search_brave(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.brave_search_api_key
    if not key:
        return []
    r = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 10, "country": "MX", "search_lang": "es"},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    if r.status_code != 200:
        return []
    out = []
    for item in ((r.json().get("web") or {}).get("results") or []):
        link = item.get("url")
        if link:
            out.append({"title": item.get("title", ""), "url": link, "snippet": item.get("description", ""), "provider": "brave"})
    return out


async def _search_tavily(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.tavily_api_key
    if not key:
        return []
    r = await client.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "search_depth": "basic", "max_results": 10, "include_raw_content": False},
    )
    if r.status_code != 200:
        return []
    out = []
    for item in r.json().get("results", []) or []:
        link = item.get("url")
        if link:
            out.append({"title": item.get("title", ""), "url": link, "snippet": item.get("content", ""), "provider": "tavily"})
    return out


async def _collect_search_candidates(req: AvmWebSearchRequest) -> Dict[str, Any]:
    queries = _build_search_queries(req)
    providers_configured = {
        "google_cse": bool(legacy_main_settings.google_cse_api_key and legacy_main_settings.google_cse_id),
        "serpapi": bool(legacy_main_settings.serpapi_api_key),
        "brave": bool(legacy_main_settings.brave_search_api_key),
        "tavily": bool(legacy_main_settings.tavily_api_key),
    }
    if not any(providers_configured.values()):
        raise HTTPException(
            status_code=500,
            detail="Configura al menos una API de búsqueda: GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID, SERPAPI_API_KEY, BRAVE_SEARCH_API_KEY o TAVILY_API_KEY."
        )

    results: List[Dict[str, Any]] = []
    seen = set()
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
        for query in queries:
            batches = await asyncio.gather(
                _search_google_cse(client, query),
                _search_serpapi(client, query),
                _search_brave(client, query),
                _search_tavily(client, query),
                return_exceptions=True,
            )
            for batch in batches:
                if isinstance(batch, Exception):
                    continue
                for item in batch:
                    url = item.get("url", "")
                    canon = _canonical_url(url)
                    if not url or canon in seen:
                        continue
                    h = _host(url)
                    if any(bad in h for bad in BLOCKED_FETCH_DOMAINS):
                        continue
                    item["portal"] = _portal_name(url)
                    item["query"] = query
                    seen.add(canon)
                    results.append(item)
                    if len(results) >= MAX_SEARCH_RESULTS:
                        return {"queries": queries, "results": results, "providers_configured": providers_configured}
    return {"queries": queries, "results": results, "providers_configured": providers_configured}


def _extract_json_from_text(raw: str) -> Dict[str, Any]:
    """Extrae un objeto JSON de la respuesta del modelo aunque venga envuelto en
    cercas de markdown (```json ... ```), con texto antes o despues, o con la
    llave de apertura pegada a la cerca. Solo lanza error si de plano no hay un
    objeto JSON parseable (p. ej. respuesta truncada)."""
    text = (raw or "").strip()

    def _try(s: str):
        try:
            return json.loads(s)
        except Exception:
            return None

    # 1) Tal cual: por si ya viene como JSON limpio.
    out = _try(text)
    if out is not None:
        return out

    # 2) Quitando cercas de markdown en cualquier posicion.
    nofence = text
    if "```" in nofence:
        first = re.search(r"```(?:json|JSON)?", nofence)
        if first:
            inner = nofence[first.end():]
            last = inner.rfind("```")
            nofence = (inner[:last] if last != -1 else inner).strip()
            out = _try(nofence)
            if out is not None:
                return out

    # 3) Primer objeto {...} balanceado (ignora llaves dentro de cadenas).
    for source in (nofence, text):
        start = source.find("{")
        if start == -1:
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(source)):
            ch = source[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    out = _try(source[start:i + 1])
                    if out is not None:
                        return out
                    break

    # 4) Ultimo recurso: regex codicioso (comportamiento previo).
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        out = _try(m.group())
        if out is not None:
            return out

    raise ValueError("No se encontro un objeto JSON valido en la respuesta del modelo.")


def _extract_visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "header", "footer", "nav"]):
            tag.decompose()
        # conservar datos útiles que a veces vienen en JSON-LD sin copiar toda la página
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            meta_desc = meta.get("content")
        text = soup.get_text(" ", strip=True)
        return _sameish_text(f"{title} {meta_desc} {text}")[:MAX_TEXT_CHARS_PER_URL]
    except Exception:
        return _sameish_text(re.sub(r"<[^>]+>", " ", html or ""))[:MAX_TEXT_CHARS_PER_URL]


async def _fetch_candidate_pages(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
    }
    sem_http = asyncio.Semaphore(3)
    sem_fc   = asyncio.Semaphore(FIRECRAWL_CONCURRENCY)
    stats = {"firecrawl_calls": 0, "firecrawl_credits": 0}

    async def _try_httpx(url: str) -> Dict[str, Any]:
        async with sem_http:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
                r = await client.get(url)
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code >= 400 or "text/html" not in ctype:
            return {"ok": False, "status": r.status_code, "text": ""}
        return {"ok": True, "status": r.status_code, "text": _extract_visible_text(r.text)}

    async def _try_firecrawl(url: str) -> Dict[str, Any]:
        async with sem_fc:
            res = await _firecrawl_scrape(url)
        if res.get("ok"):
            stats["firecrawl_calls"] += 1
            stats["firecrawl_credits"] += int(res.get("credits") or 0)
        return res

    async def one(item: Dict[str, Any]) -> Dict[str, Any]:
        url = item.get("url", "")
        h = _host(url)
        if any(bad in h for bad in BLOCKED_FETCH_DOMAINS):
            return {**item, "fetch_status": "skipped_domain", "page_text": ""}

        is_premium = any(p in h for p in PREMIUM_FETCH_DOMAINS)

        # Estrategia:
        #   - Premium domains → Firecrawl primero (httpx siempre fallaría con 403).
        #   - Resto → httpx primero, fallback a Firecrawl si responde 403/429/5xx.
        try:
            if is_premium and FIRECRAWL_API_KEY:
                fc = await _try_firecrawl(url)
                if fc.get("ok"):
                    return {**item, "fetch_status": "ok_firecrawl",
                            "page_text": fc["page_text"]}
                # Si Firecrawl falla, intento httpx como último recurso.
                try:
                    h_res = await _try_httpx(url)
                    if h_res["ok"]:
                        return {**item, "fetch_status": "ok_httpx_fallback",
                                "page_text": h_res["text"]}
                    return {**item, "fetch_status": f"firecrawl_{fc.get('error','err')}__http_{h_res.get('status')}",
                            "page_text": ""}
                except Exception as e:
                    return {**item, "fetch_status": f"firecrawl_{fc.get('error','err')}__httpx_err",
                            "fetch_error": str(e)[:120], "page_text": ""}

            # Camino directo (gratis) primero.
            h_res = await _try_httpx(url)
            if h_res["ok"]:
                return {**item, "fetch_status": "ok", "page_text": h_res["text"]}

            # Si el sitio devolvió 403/429/5xx y hay Firecrawl, reintento allí.
            status = h_res.get("status") or 0
            if FIRECRAWL_API_KEY and (status in (403, 429) or status >= 500):
                fc = await _try_firecrawl(url)
                if fc.get("ok"):
                    return {**item, "fetch_status": f"ok_firecrawl_retry_{status}",
                            "page_text": fc["page_text"]}
                return {**item, "fetch_status": f"http_{status}__firecrawl_{fc.get('error','err')}",
                        "page_text": ""}
            return {**item, "fetch_status": f"http_{status}", "page_text": ""}
        except Exception as e:
            return {**item, "fetch_status": "error", "fetch_error": str(e)[:120], "page_text": ""}

    tasks = [one(c) for c in candidates[:MAX_URLS_TO_FETCH]]
    fetched = await asyncio.gather(*tasks) if tasks else []

    # Log telemetría de Firecrawl por opinión (lo verás en Railway logs).
    if stats["firecrawl_calls"]:
        print(f"[firecrawl] calls={stats['firecrawl_calls']} credits={stats['firecrawl_credits']}")

    return fetched


def _subject_summary(req: AvmWebSearchRequest, tipo_label: str) -> str:
    partes = [f"{tipo_label} en {req.operacion.upper()}", f"Ubicación: {req.colonia}, {req.ciudad}, {req.estado}"]
    if req.m2_terreno > 0:
        partes.append(f"Terreno: {req.m2_terreno} m²" + (f" ({req.condicion_terreno})" if req.condicion_terreno else ""))
    if req.m2_construccion > 0:
        partes.append(f"Construcción: {req.m2_construccion} m²")
    if req.recamaras > 0:
        partes.append(f"Recámaras: {req.recamaras}")
    if req.banos > 0:
        partes.append(f"Baños: {req.banos}")
    if req.estacionamientos > 0:
        partes.append(f"Estacionamientos: {req.estacionamientos}")
    if req.comentarios:
        partes.append(f"Comentarios del usuario: {req.comentarios}")
    return "\n".join(partes)


async def _claude_extract_and_value(req: AvmWebSearchRequest, tipo_label: str, evidence: List[Dict[str, Any]], queries: List[str], user_id: str = None) -> Dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    es_terreno = req.tipo_inmueble == "terreno"
    superficie_sujeto = req.m2_terreno if es_terreno else (req.m2_construccion or req.m2_terreno)
    evidence_compact = []
    for i, e in enumerate(evidence, 1):
        evidence_compact.append({
            "id": i,
            "titulo": e.get("title", ""),
            "url": e.get("url", ""),
            "portal": e.get("portal", ""),
            "snippet": e.get("snippet", ""),
            "fetch_status": e.get("fetch_status", ""),
            "texto_visible_limitado": e.get("page_text", "")[:MAX_TEXT_CHARS_PER_URL],
        })

    system_prompt = f"""Eres un analista valuador inmobiliario mexicano. Tu trabajo NO es inventar comparables: debes usar únicamente la evidencia web entregada por el servidor.

Objetivo: limpiar, clasificar y calcular una estimación de valor por método comparativo de mercado.

Reglas duras:
1. No inventes precios, superficies, colonias ni URLs.
2. Si un anuncio no muestra precio y superficie suficientes, márcalo como descartado.
3. Si detectas que una misma propiedad aparece duplicada, conserva una sola.
4. No uses fotos, teléfonos, nombres de asesores ni datos personales.
5. Prioriza comparables de la misma colonia/fraccionamiento; después zonas adyacentes y similares.
6. Para terrenos usa m² de terreno. Para casas/departamentos usa m² de construcción como base principal; si no hay construcción, descarta o márcalo como baja confianza.
7. Aplica factor negociación de -5% a precios de oferta en venta. En renta usa -3% si aplica.
8. Penaliza comparables sospechosos: anuncio viejo, datos incompletos, precio/m² extremo, ubicación poco clara, submercado distinto.
9. Si hay menos de 3 comparables útiles, entrega rango conservador y nivel_confianza='baja'.
10. Esta salida es una estimación de valor, no avalúo certificado.

Responde ÚNICAMENTE JSON válido con esta estructura:
{{
  "valor_estimado": 0,
  "valor_minimo": 0,
  "valor_maximo": 0,
  "valor_por_m2": 0,
  "precio_m2_base": 0,
  "nivel_confianza": "alta|media|baja",
  "razon_confianza": "",
  "resumen_ejecutivo": "",
  "comparables": [
    {{
      "descripcion": "",
      "superficie_m2": 0,
      "precio": 0,
      "precio_m2": 0,
      "fuente": "",
      "url": "",
      "incluido_en_promedio": true,
      "motivo_inclusion_o_descarte": ""
    }}
  ],
  "comparables_descartados": [
    {{"descripcion":"", "fuente":"", "url":"", "motivo":""}}
  ],
  "factores_ajuste": [
    {{"factor":"", "descripcion":"", "porcentaje":0, "impacto":"positivo|negativo|neutro"}}
  ],
  "precio_m2_ajustado_calculo": "",
  "analisis_zona": "",
  "recomendaciones": [""],
  "advertencias": "",
  "fecha": "{_today_mx()}"
}}
"""

    user_msg = {
        "inmueble_sujeto": _subject_summary(req, tipo_label),
        "superficie_relevante_sujeto_m2": superficie_sujeto,
        "queries_utilizadas": queries,
        "evidencia_web": evidence_compact,
        "instruccion_calculo": "Extrae comparables reales de la evidencia; calcula precio/m²; descarta duplicados/outliers; promedia solo incluidos; aplica ajustes; calcula valor estimado y rango."
    }

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": legacy_main_settings.anthropic_avm_model,
                "max_tokens": 8000,
                "temperature": 0.05,
                "system": system_prompt,
                "messages": [{"role": "user", "content": json.dumps(user_msg, ensure_ascii=False)}],
            },
        )

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:500]}")

    _resp_json = r.json()
    _track_anthropic(user_id, "avm", "/api/avm-websearch", _resp_json,
                     modelo=_resp_json.get("model") or legacy_main_settings.anthropic_avm_model)
    raw = ""
    for block in _resp_json.get("content", []) or []:
        if block.get("type") == "text":
            raw += block.get("text", "")
    try:
        return _extract_json_from_text(raw)
    except Exception:
        raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:700]}")


@app.post("/api/avm-websearch")
async def avm_websearch(req: AvmWebSearchRequest, request: Request):
    """Opinión de valor con búsqueda web controlada: search API → URLs candidatas → extracción mínima → IA limpia y calcula."""
    user_id = await get_user_id_from_token(request)
    exigir_cupo(request, user_id)
    exigir_sesion(request, user_id)
    tipo_labels = {
        "casa": "Casa habitación", "departamento": "Departamento/Condominio",
        "terreno": "Terreno", "local": "Local comercial",
        "oficina": "Oficina", "bodega": "Bodega/Nave industrial",
    }
    tipo_label = tipo_labels.get(req.tipo_inmueble, req.tipo_inmueble)

    busqueda = await _collect_search_candidates(req)
    candidatos = busqueda["results"]
    if not candidatos:
        raise HTTPException(status_code=404, detail="No encontré URLs candidatas con las APIs de búsqueda configuradas. Prueba con otra colonia/zona o configura otra API de búsqueda.")

    paginas = await _fetch_candidate_pages(candidatos)
    resultado = await _claude_extract_and_value(req, tipo_label, paginas, busqueda["queries"], user_id=user_id)

    # Metadata útil para depuración y transparencia del frontend/PDF
    resultado["tipo_inmueble"] = tipo_label
    resultado["operacion"] = req.operacion
    resultado["colonia"] = req.colonia
    resultado["ciudad"] = req.ciudad
    resultado["estado"] = req.estado
    resultado["m2_construccion"] = req.m2_construccion
    resultado["m2_terreno"] = req.m2_terreno
    resultado["recamaras"] = req.recamaras
    resultado["banos"] = req.banos
    resultado["condicion_terreno"] = req.condicion_terreno
    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")
    resultado["metodologia"] = "Búsqueda web por API configurada, lectura limitada de URLs públicas, extracción mínima de datos visibles, deduplicación y clasificación por IA, cálculo comparativo con ajustes."
    resultado["fuentes_consultadas"] = [{
        "titulo": p.get("title", ""),
        "url": p.get("url", ""),
        "portal": p.get("portal", ""),
        "estado_lectura": p.get("fetch_status", ""),
        "provider": p.get("provider", ""),
    } for p in paginas]
    resultado["queries_utilizadas"] = busqueda["queries"]
    resultado["proveedores_busqueda_configurados"] = busqueda["providers_configured"]

    # Fallback numérico si Claude devolvió comparables pero omitió algún cálculo básico.
    try:
        comps = [c for c in resultado.get("comparables", []) if c.get("incluido_en_promedio") and c.get("precio_m2")]
        if comps and not resultado.get("precio_m2_base"):
            resultado["precio_m2_base"] = _round_mxn(sum(float(c["precio_m2"]) for c in comps) / len(comps), 100)
        sup = req.m2_terreno if req.tipo_inmueble == "terreno" else (req.m2_construccion or req.m2_terreno)
        if sup and resultado.get("valor_por_m2") and not resultado.get("valor_estimado"):
            resultado["valor_estimado"] = _round_mxn(float(resultado["valor_por_m2"]) * sup)
        if resultado.get("valor_estimado"):
            v = float(resultado["valor_estimado"])
            resultado["valor_minimo"] = resultado.get("valor_minimo") or _round_mxn(v * 0.92)
            resultado["valor_maximo"] = resultado.get("valor_maximo") or _round_mxn(v * 1.08)
    except Exception:
        pass

    return resultado


# ────────────────────────────────────────────
# AVM — PDF DE OPINIÓN DE VALOR
# ────────────────────────────────────────────

@app.post("/avm-pdf")
async def generar_avm_pdf(p: dict):
    """Recibe el resultado del AVM websearch y genera un PDF profesional con Playwright.

    Sistema de diseño: los mismos tokens de brokr-theme.css (navy, azul,
    Manrope, radios, sombras) que usa el resto de Broquer — para que este
    documento se sienta hermano de la Ficha técnica y del ISR, no un
    invitado con otra identidad visual.
    """
    from playwright.async_api import async_playwright

    resultado = p.get("resultado", {})
    agente = p.get("agente", "Agente Broquer")

    if not resultado:
        raise HTTPException(status_code=400, detail="Resultado vacío")

    def fmt_mx(n):
        try:
            return "${:,.0f}".format(float(n))
        except Exception:
            return str(n)

    def _esc(s):
        return (str(s) if s is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

    # Comparables
    comps_html = ""
    for c in resultado.get("comparables", []):
        fuente = c.get("fuente","—") or "—"
        url = c.get("url","") or ""
        src_cell = (
            f'<a href="{_esc(url)}" target="_blank" rel="noopener" class="link">{_esc(fuente)}</a>'
            if url else _esc(fuente)
        )
        comps_html += f"""
        <tr>
          <td>{_esc(c.get('descripcion','—'))}</td>
          <td class="num">{_esc(c.get('superficie_m2','—'))} m²</td>
          <td class="num">{fmt_mx(c.get('precio',0))}</td>
          <td class="num">{fmt_mx(c.get('precio_m2',0))}/m²</td>
          <td class="src">{src_cell}</td>
        </tr>"""

    # Factores de ajuste — badge con punto, mismo patrón que .bk-badge del app
    factores_html = ""
    for f in resultado.get("factores_ajuste", []):
        imp = f.get("impacto", "neutro")
        badge_cls = "badge--success" if imp == "positivo" else "badge--danger" if imp == "negativo" else "badge--mute"
        etiqueta = "Favorable" if imp == "positivo" else "Desfavorable" if imp == "negativo" else "Neutro"
        factores_html += f"""
        <tr>
          <td>
            <div class="factor-nombre">{_esc(f.get('factor','—'))}</div>
            <span class="badge {badge_cls}"><span class="dot"></span>{etiqueta}</span>
          </td>
          <td class="factor-desc">{_esc(f.get('descripcion','—'))}</td>
        </tr>"""

    recs_html = "".join(f"<li>{_esc(r)}</li>" for r in resultado.get("recomendaciones", []))

    m2c = resultado.get("m2_construccion", 0)
    m2t = resultado.get("m2_terreno", 0)
    sup_parts = []
    if m2t: sup_parts.append(f"{m2t} m² terreno")
    if m2c: sup_parts.append(f"{m2c} m² construcción")
    superficie_str = " · ".join(sup_parts) if sup_parts else "—"

    fecha_hoy = resultado.get("fecha", time.strftime("%d/%m/%Y"))
    operacion = (resultado.get('operacion','venta') or 'venta').capitalize()

    # Tokens desde brokr-theme.css. Radios propios del documento.
    _AVM_TOKENS = theme_css_for_pdf(
        "--r-xs:4px; --r-sm:8px; --r:14px; --r-lg:28px; --r-pill:999px;"
    )
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<style>
{_AVM_TOKENS}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font-sans); color: var(--ink); background: var(--paper); font-size: 13px; line-height: 1.55; -webkit-font-smoothing: antialiased; letter-spacing: -0.01em; }}
  .page {{ padding: 48px 52px 40px; max-width: 780px; margin: 0 auto; }}

  /* ── Encabezado de documento ── */
  .doc-head {{ display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 20px; border-bottom: 1px solid var(--line); margin-bottom: 28px; }}
  .doc-head__brand {{ font-size: 15px; font-weight: 700; color: var(--sky-navy); letter-spacing: -0.01em; }}
  .doc-head__title {{ font-size: 12px; color: var(--mute); margin-top: 2px; }}
  .doc-head__date {{ font-size: 11px; color: var(--mute); }}

  /* ── Bloque de valor — tarjeta navy, no negro genérico ── */
  .valor-card {{
    background: linear-gradient(155deg, var(--sky-navy), var(--sky-navy-mid));
    border-radius: var(--r-lg);
    padding: 26px 28px 22px;
    margin-bottom: 22px;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }}
  .valor-lbl {{ font-size: 11px; color: rgba(255,255,255,.65); font-weight: 600; letter-spacing: 0.02em; margin-bottom: 6px; }}
  .valor-num {{ font-family: var(--font-sans); font-size: 34px; font-weight: 700; color: #fff; line-height: 1.05; letter-spacing: -0.02em; }}
  .valor-meta {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 18px; margin-top: 20px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.14); }}
  .meta-item .meta-lbl {{ font-size: 10px; color: rgba(255,255,255,.55); font-weight: 600; letter-spacing: 0.02em; margin-bottom: 4px; }}
  .meta-item .meta-val {{ font-size: 13px; font-weight: 700; color: #fff; letter-spacing: -0.005em; }}

  /* ── Secciones ── */
  .seccion {{ margin-bottom: 26px; }}
  .sec-titulo {{ font-size: 11px; font-weight: 700; color: var(--mute); letter-spacing: 0.02em; margin-bottom: 12px; }}
  .resumen {{ font-size: 12.5px; color: var(--ink-2); line-height: 1.7; text-align: justify; }}

  /* ── Badge con punto — idéntico a .bk-badge del app ── */
  .badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: var(--r-pill);
    font-size: 11px; font-weight: 700; letter-spacing: 0.02em;
    background: var(--paper-2); color: var(--mute);
  }}
  .badge .dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
  .badge--success {{ background: var(--success-soft); color: var(--success); }}
  .badge--danger  {{ background: var(--danger-soft);  color: var(--danger); }}
  .badge--mute    {{ background: var(--paper-2);       color: var(--mute); }}

  /* ── Tablas ── */
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ font-weight: 700; color: var(--mute); text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line-2); font-size: 10px; letter-spacing: 0.02em; }}
  td {{ padding: 12px 6px; border-bottom: 1px solid var(--line); color: var(--ink); vertical-align: top; }}
  td.num {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); }}
  .link {{ color: var(--forest); text-decoration: underline; }}
  tr:last-child td {{ border-bottom: none; }}

  .factor-nombre {{ font-weight: 700; font-size: 12.5px; margin-bottom: 5px; }}
  .factor-desc {{ color: var(--mute); font-size: 11.5px; line-height: 1.5; }}

  .recs {{ padding-left: 18px; }}
  .recs li {{ font-size: 12.5px; color: var(--ink-2); line-height: 1.7; margin-bottom: 4px; }}

  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line); text-align: center; font-size: 10px; color: var(--mute-2); letter-spacing: 0.02em; }}
</style>
</head>
<body>
<div class="page">

  <div class="doc-head">
    <div>
      <div class="doc-head__brand">Broquer</div>
      <div class="doc-head__title">Estimación de valor</div>
    </div>
    <div class="doc-head__date">{fecha_hoy}</div>
  </div>

  <div class="valor-card">
    <div class="valor-lbl">Valor estimado</div>
    <div class="valor-num">{fmt_mx(resultado.get('valor_estimado',0))}</div>
    <div class="valor-meta">
      <div class="meta-item">
        <div class="meta-lbl">Inmueble</div>
        <div class="meta-val">{_esc(resultado.get('tipo_inmueble','—'))}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Superficie</div>
        <div class="meta-val">{_esc(superficie_str)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Ubicación</div>
        <div class="meta-val">{_esc(resultado.get('colonia','—'))}, {_esc(resultado.get('ciudad','Morelia'))}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Operación</div>
        <div class="meta-val">{_esc(operacion)}</div>
      </div>
    </div>
  </div>

  <div class="seccion">
    <div class="sec-titulo">Análisis</div>
    <div class="resumen">{_esc(resultado.get('resumen_ejecutivo','—'))}</div>
  </div>

  <div class="seccion">
    <div class="sec-titulo">Comparables de mercado</div>
    <table>
      <thead>
        <tr>
          <th>Propiedad</th>
          <th style="text-align:right">Superficie</th>
          <th style="text-align:right">Precio</th>
          <th style="text-align:right">$/m²</th>
          <th>Fuente</th>
        </tr>
      </thead>
      <tbody>{comps_html}</tbody>
    </table>
  </div>

  {"" if not factores_html else f'''
  <div class="seccion">
    <div class="sec-titulo">Factores de ajuste</div>
    <table>
      <tbody>{factores_html}</tbody>
    </table>
  </div>
  '''}

  {"" if not recs_html else f'''
  <div class="seccion">
    <div class="sec-titulo">Recomendaciones</div>
    <ul class="recs">{recs_html}</ul>
  </div>
  '''}

  <div class="footer">Powered by Broquer</div>

</div>
</body>
</html>"""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(400)
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
        )
        await browser.close()

    token = str(_uuid.uuid4()).replace("-", "")[:16]
    colonia_slug = resultado.get("colonia", "propiedad").replace(" ", "_")[:20]
    filename = f"Estimacion_Valor_{colonia_slug}_{time.strftime('%Y%m%d')}.pdf"
    _pdf_store[token] = (pdf_bytes, filename)
    if len(_pdf_store) > 50:
        oldest = list(_pdf_store.keys())[0]
        del _pdf_store[oldest]

    from fastapi.responses import JSONResponse
    return JSONResponse({"token": token, "filename": filename})


@app.get("/avm-pdf/{token}")
async def descargar_avm_pdf(token: str):
    from fastapi.responses import StreamingResponse
    import io as _io
    if token not in _pdf_store:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
        }
    )


@app.get("/isr-pdf/{token}")
async def descargar_isr_pdf(token: str):
    from fastapi.responses import StreamingResponse
    import io as _io
    if token not in _pdf_store:
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
        }
    )


# ────────────────────────────────────────────
# CONTRATOS
# ────────────────────────────────────────────
from fastapi.responses import FileResponse
import tempfile, os, subprocess, json as _json

class ContratoRequest(BaseModel):
    tipo: str   # arrendamiento | promesa
    datos: dict
    clausulas_especiales: list = []  # plain-language clauses to be drafted by AI


# El proxy abierto /img se eliminó por seguridad. Bajaba CUALQUIER dirección que
# le pasaran, así que servía para usar nuestro servidor como escondite y para
# alcanzar servicios internos de Railway desde fuera. Ya no lo llamaba nadie:
# las fichas en PDF bajan las fotos directo desde el propio backend.

@app.post("/contrato")
async def generar_contrato(req: ContratoRequest, request: Request):
    """Generate a DOCX contract from form data, with AI-drafted special clauses."""
    user_id = await get_user_id_from_token(request)

    # ── STEP 1: Draft special clauses with AI (abogado mexicano) ──
    clausulas_redactadas = []
    if req.clausulas_especiales:
        tipo_label = "arrendamiento" if req.tipo == "arrendamiento" else "promesa de compraventa"
        lista_clausulas = "\n".join(
            f"{i+1}. {c}" for i, c in enumerate(req.clausulas_especiales)
        )
        prompt_clausulas = (
            "Eres un abogado especialista en derecho inmobiliario mexicano con 20 años de experiencia "
            "redactando contratos conforme al Código Civil Federal y los códigos civiles estatales.\n\n"
            f"El usuario quiere incluir las siguientes cláusulas especiales en un contrato de {tipo_label}. "
            "Para cada una, redacta una cláusula jurídicamente correcta, con lenguaje formal, precisa y "
            "ejecutable ante tribunales mexicanos. Usa numeración romana (PRIMERA ESPECIAL, SEGUNDA ESPECIAL, etc.).\n\n"
            "No incluyas explicaciones ni comentarios — solo la cláusula redactada lista para insertarse en el contrato.\n\n"
            "Cláusulas a redactar:\n"
            + lista_clausulas
        )

        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt_clausulas}],
                "max_tokens": 2000,
                "temperature": 0.3
            }
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=payload
                )
            if r.status_code == 200:
                _resp_json = r.json()
                _track_groq(user_id, "contratos", "/contrato", _resp_json,
                            modelo=payload.get("model") or "llama-3.3-70b-versatile")
                ai_text = _resp_json["choices"][0]["message"]["content"].strip()
                clausulas_redactadas = [ai_text]
        except Exception as e:
            print(f"AI clause drafting error: {e}")
            # Fallback: use plain text
            clausulas_redactadas = req.clausulas_especiales

    # ── STEP 2: Write datos + clausulas to temp JSON ──
    datos_completos = dict(req.datos)
    datos_completos["clausulas_especiales"] = clausulas_redactadas

    # Write datos to temp JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        _json.dump(datos_completos, f, ensure_ascii=False)
        json_path = f.name

    output_path = json_path.replace('.json', '.docx')

    try:
        script = os.path.join(os.path.dirname(__file__), 'generar_contrato.py')
        result = subprocess.run(
            ['python3', script, req.tipo, json_path, output_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500,
                detail=f"Error generando contrato: {result.stderr}")

        nombres = {
            'arrendamiento': 'Contrato_Arrendamiento.docx',
            'promesa': 'Promesa_Compraventa.docx',
        }
        filename = nombres.get(req.tipo, 'Contrato.docx')

        return FileResponse(
            output_path,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=filename,
            background=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try: os.unlink(json_path)
        except: pass


# ── CONTRATOS PERSONALIZADOS (MACHOTES) ─────────────────────────

from fastapi import Form as FastAPIForm

# ── MI PROPIO MACHOTE ─────────────────────────────────────────────
# El usuario sube su contrato (marcado con {{campo}} o un contrato real ya
# lleno). machotes.py lo convierte en una plantilla normalizada y detecta los
# campos; aquí solo persistimos y servimos. Ver machotes.py para el motor.
# ──────────────────────────────────────────────────────────────────
import machotes as _mach

MACHOTES_BUCKET = "machotes-contrato"
MACHOTE_MAX_BYTES = 12 * 1024 * 1024


def _sb_headers(extra: dict = None) -> dict:
    h = {"apikey": SUPABASE_SERVICE_KEY,
         "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    if extra:
        h.update(extra)
    return h


# =============================================================================
# RECORDATORIOS DE TAREAS/CITAS
# -----------------------------------------------------------------------------
# Cada 5 minutos revisa las tareas con fecha_entrega próxima y manda UN push
# por tarea (se marca recordatorio_enviado para no repetirlo). No depende de
# ningún módulo específico: aplica a cualquier tarea, la haya creado el
# usuario a mano, Broq, o WhatsApp 2.0 al agendar una visita.
# =============================================================================
_recordatorios_log = logging.getLogger("broquer.recordatorios")


async def _revisar_recordatorios():
    try:
        from push import enviar_push
    except Exception:
        return  # sin push.py configurado no hay nada que hacer aquí

    ahora = datetime.now(timezone.utc)
    try:
        try:
            tareas = await get_rows(
                "tareas",
                {
                    "select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes",
                    "completada": "eq.false", "recordatorio_enviado": "eq.false",
                    "fecha_entrega": "not.is.null", "limit": "200",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError as e:
            texto = e.response.text if e.response is not None else ""
            _recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", texto[:200])
            return
    except Exception as e:
        _recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)
        return

    for t in tareas:
        try:
            fecha = datetime.fromisoformat(str(t["fecha_entrega"]).replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if fecha < ahora:
            continue  # ya pasó y nadie la marcó — no tiene caso avisar tarde
        minutos_antes = t.get("recordatorio_minutos_antes") or 60
        disparo = fecha - timedelta(minutes=minutos_antes)
        if disparo > ahora:
            continue  # todavía no toca avisar de esta

        cuerpo = f"{t['titulo']} — en {minutos_antes} minutos" if minutos_antes >= 15 else f"{t['titulo']} — está por comenzar"
        try:
            await enviar_push(t["user_id"], "Recordatorio de cita", cuerpo,
                              datos={"tipo": "tarea", "tarea_id": t["id"]})
        except Exception as e:
            _recordatorios_log.warning("No se pudo mandar el push de la tarea %s: %s", t["id"], e)
            continue

        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.patch(f"{SUPABASE_URL}/rest/v1/tareas",
                              headers=_sb_headers({"Content-Type": "application/json"}),
                              params={"id": f"eq.{t['id']}"}, json={"recordatorio_enviado": True})
        except Exception as e:
            _recordatorios_log.warning("No se pudo marcar recordatorio_enviado de %s: %s", t["id"], e)


async def _recordatorios_loop():
    while True:
        try:
            await _revisar_recordatorios()
        except Exception as e:
            _recordatorios_log.error("Fallo el ciclo de recordatorios: %s", e)
        await asyncio.sleep(300)  # cada 5 minutos


@app.on_event("startup")
async def _iniciar_recordatorios():
    asyncio.create_task(_recordatorios_loop())


_MACHOTE_SELECT = ("id,titulo,tipo,campos,motor,patron_usado,descartados,"
                   "storage_path,texto_preview,created_at,updated_at")

_CAMPO_EDITABLE = ("label", "tipo_input", "grupo", "ayuda", "default",
                   "fijo", "obligatorio", "orden")


async def _machote_o_404(machote_id: str, user_id: str, select: str = _MACHOTE_SELECT) -> dict:
    try:
        rows = await get_rows(
            "machotes_contrato",
            {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}",
             "select": select, "limit": "1"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    if not rows:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    return rows[0]


async def _descargar_plantilla(storage_path: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{storage_path}",
            headers=_sb_headers(),
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudo leer el archivo de tu machote.")
    return r.content


async def _subir_a_storage(client: httpx.AsyncClient, path: str, content: bytes):
    r = await client.post(
        f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{path}",
        headers=_sb_headers({
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "x-upsert": "true",
        }),
        content=content,
    )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"No se pudo guardar el archivo: {r.text[:200]}")


def _leer_docx_subido(file: UploadFile, content: bytes):
    if not content:
        raise HTTPException(status_code=400, detail="El archivo llegó vacío. Vuelve a seleccionarlo.")
    if len(content) > MACHOTE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Tu contrato pesa más de 12 MB. Quítale las imágenes pesadas y vuelve a subirlo.")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Solo aceptamos archivos .docx (Word).")


@app.post("/contrato/machote/abrir")
async def abrir_machote(request: Request, file: UploadFile = File(...)):
    """Devuelve el contrato párrafo por párrafo para pintarlo en pantalla y que
    el usuario señale ahí mismo qué datos cambian. No guarda nada."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    content = await file.read()
    _leer_docx_subido(file, content)
    try:
        return await asyncio.get_event_loop().run_in_executor(
            _thread_pool, _mach.abrir, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[machotes] error al abrir: {e}")
        raise HTTPException(status_code=400, detail="No pudimos leer tu archivo. Ábrelo en Word y guárdalo otra vez como .docx.")


@app.post("/contrato/machote/sugerir")
async def sugerir_campos_machote(
    request: Request,
    file: UploadFile = File(...),
    tipo: str = FastAPIForm(default=""),
):
    """Acelerador opcional: la IA propone marcas. No guarda nada; todo aterriza
    en la pantalla para que el usuario lo revise, corrija o borre."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    content = await file.read()
    _leer_docx_subido(file, content)
    try:
        res = await _mach.sugerir_ia(content, tipo=(tipo or "").strip(),
                                     api_key=ANTHROPIC_API_KEY)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[machotes] error al sugerir: {e}")
        raise HTTPException(status_code=500, detail="No pudimos revisar tu contrato. Márcalo tú y quedará igual de bien.")

    for raw in res.get("raws") or []:
        try:
            _track_anthropic(user_id, "contratos", "/contrato/machote/sugerir", raw,
                             modelo=(raw or {}).get("model") or _mach.MODELO_DEFAULT)
        except Exception:
            pass

    return {"campos": res["campos"], "marcas": res["marcas"],
            "descartados": res["descartados"]}


@app.post("/contrato/machote/crear")
async def crear_machote(
    request: Request,
    file: UploadFile = File(...),
    titulo: str = FastAPIForm(...),
    tipo: str = FastAPIForm(default=""),
    campos: str = FastAPIForm(...),
    marcas: str = FastAPIForm(...),
):
    """Crea el machote con las marcas que hizo el usuario sobre su contrato."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión para guardar tu machote.")

    titulo = (titulo or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="Ponle un título a tu machote para poder identificarlo después.")

    content = await file.read()
    _leer_docx_subido(file, content)
    try:
        campos_in = _json.loads(campos)
        marcas_in = _json.loads(marcas)
    except Exception:
        raise HTTPException(status_code=400, detail="Los campos marcados llegaron mal. Vuelve a intentarlo.")
    if not isinstance(campos_in, list) or not isinstance(marcas_in, list):
        raise HTTPException(status_code=400, detail="Los campos marcados llegaron mal. Vuelve a intentarlo.")

    try:
        plantilla, campos_final = await asyncio.get_event_loop().run_in_executor(
            _thread_pool, _mach.crear_plantilla, content, campos_in, marcas_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[machotes] error al crear: {e}")
        raise HTTPException(status_code=500, detail="No pudimos crear tu machote. Vuelve a intentarlo.")

    machote_id = str(_uuid.uuid4())
    storage_path = f"{user_id}/{machote_id}.docx"
    storage_path_original = f"{user_id}/{machote_id}__original.docx"

    async with httpx.AsyncClient(timeout=60) as client:
        await _subir_a_storage(client, storage_path, plantilla)
        try:
            await _subir_a_storage(client, storage_path_original, content)
        except Exception:
            storage_path_original = None

        fila = {
            "id": machote_id,
            "user_id": user_id,
            "org_id": await get_org_id_for_user(user_id),
            "titulo": titulo,
            "tipo": (tipo or "").strip() or "Personalizado",
            "storage_path": storage_path,
            "storage_path_original": storage_path_original,
            "campos": campos_final,
            "motor": "manual",
            "patron_usado": "manual",
            "descartados": [],
        }
        rd = await client.post(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers({"Content-Type": "application/json",
                                 "Prefer": "return=representation"}),
            json=fila,
        )
        if rd.status_code not in (200, 201):
            for p in (storage_path, storage_path_original):
                if not p:
                    continue
                try:
                    await client.delete(
                        f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{p}",
                        headers=_sb_headers())
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"No se pudo guardar tu machote: {rd.text[:200]}")

    return {"id": machote_id, "titulo": titulo, "tipo": fila["tipo"],
            "campos": campos_final}


@app.get("/contrato/machotes")
async def listar_machotes(request: Request):
    """Machotes guardados del usuario, para el menú de selección."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    try:
        rows = await get_rows(
            "machotes_contrato",
            {"user_id": f"eq.{user_id}",
             "select": "id,titulo,tipo,campos,motor,created_at",
             "order": "created_at.desc"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")
    return {"machotes": rows}


@app.get("/contrato/machote/{machote_id}")
async def obtener_machote(machote_id: str, request: Request):
    """Campos de un machote guardado, para volver a llenarlo."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")
    return await _machote_o_404(machote_id, user_id)


@app.patch("/contrato/machote/{machote_id}")
async def actualizar_machote(machote_id: str, request: Request):
    """Guarda los ajustes del usuario a la detección: etiquetas, tipo de dato,
    grupo, orden, valores fijos. Nunca inventa campos: solo se aceptan ids que
    de verdad existen en la plantilla."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    body = await request.json()
    machote = await _machote_o_404(machote_id, user_id)

    parche: Dict[str, Any] = {}
    titulo = (body.get("titulo") or "").strip()
    if titulo:
        parche["titulo"] = titulo
    tipo = body.get("tipo")
    if tipo is not None:
        parche["tipo"] = (tipo or "").strip() or "Personalizado"

    if isinstance(body.get("campos"), list):
        actuales = {c["id"]: c for c in (machote.get("campos") or [])}
        nuevos = []
        for c in body["campos"]:
            if not isinstance(c, dict):
                continue
            base = actuales.get(c.get("id"))
            if not base:
                continue
            fusion = dict(base)
            for k in _CAMPO_EDITABLE:
                if k in c:
                    fusion[k] = c[k]
            if fusion.get("tipo_input") not in _mach.TIPOS_INPUT:
                fusion["tipo_input"] = "text"
            fusion["label"] = (str(fusion.get("label") or "").strip()
                               or _mach.humanizar(fusion["id"]))
            fusion["grupo"] = str(fusion.get("grupo") or "").strip() or "Datos del contrato"
            fusion["fijo"] = bool(fusion.get("fijo"))
            nuevos.append(fusion)
        if not nuevos:
            raise HTTPException(status_code=400, detail="Tu machote necesita al menos un campo.")
        faltantes = [c for cid, c in actuales.items()
                     if cid not in {n["id"] for n in nuevos}]
        parche["campos"] = nuevos + faltantes

    if not parche:
        raise HTTPException(status_code=400, detail="No hay nada que actualizar.")
    parche["updated_at"] = datetime.utcnow().isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers({"Content-Type": "application/json",
                                 "Prefer": "return=representation"}),
            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},
            json=parche,
        )
    if r.status_code not in (200, 204) or not r.json():
        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")
    return r.json()[0]


@app.post("/contrato/machote/{machote_id}/preview")
async def previsualizar_machote(machote_id: str, request: Request):
    """Devuelve el contrato ya sustituido, en texto, para revisarlo antes de
    descargarlo. No consume IA."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    body = await request.json()
    datos = body.get("datos") or {}
    machote = await _machote_o_404(machote_id, user_id, "id,campos,storage_path")
    contenido = await _descargar_plantilla(machote["storage_path"])
    datos = _aplicar_fijos(datos, machote.get("campos") or [])
    try:
        parrafos = await asyncio.get_event_loop().run_in_executor(
            _thread_pool, _mach.previsualizar, contenido, datos, machote.get("campos") or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo generar la vista previa: {e}")
    return {"parrafos": parrafos}


def _aplicar_fijos(datos: dict, campos: list) -> dict:
    """Los campos marcados como fijos no se preguntan: siempre usan su valor
    por defecto."""
    datos = dict(datos or {})
    for c in campos or []:
        if c.get("fijo") and c.get("default") is not None:
            datos[c["id"]] = c["default"]
        elif not str(datos.get(c["id"], "")).strip() and c.get("default"):
            datos[c["id"]] = c["default"]
    return datos


@app.post("/contrato/machote/{machote_id}/generar")
async def generar_desde_machote_guardado(machote_id: str, request: Request):
    """Rellena la plantilla y devuelve el DOCX listo."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    body = await request.json()
    datos = body.get("datos") or {}
    if not isinstance(datos, dict):
        raise HTTPException(status_code=400, detail="El campo 'datos' debe ser un objeto.")

    machote = await _machote_o_404(machote_id, user_id, "id,titulo,campos,storage_path")
    contenido = await _descargar_plantilla(machote["storage_path"])
    campos = machote.get("campos") or []
    datos = _aplicar_fijos(datos, campos)

    try:
        docx_bytes = await asyncio.get_event_loop().run_in_executor(
            _thread_pool, _mach.rellenar, contenido, datos, campos)
    except Exception as e:
        print(f"[machotes] error al rellenar: {e}")
        raise HTTPException(status_code=500, detail="No se pudo generar el contrato. Vuelve a intentarlo.")

    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        f.write(docx_bytes)
        output_path = f.name

    titulo_limpio = re.sub(r'[^A-Za-z0-9_\- ]', '', machote.get('titulo') or 'Contrato').strip() or 'Contrato'
    return FileResponse(
        output_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=f"{titulo_limpio}.docx",
    )


@app.delete("/contrato/machote/{machote_id}")
async def eliminar_machote(machote_id: str, request: Request):
    """Elimina el machote: archivos del Storage + registro."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    machote = await _machote_o_404(machote_id, user_id,
                                   "id,storage_path,storage_path_original")
    async with httpx.AsyncClient(timeout=15) as client:
        for p in (machote.get("storage_path"), machote.get("storage_path_original")):
            if not p:
                continue
            try:
                await client.delete(
                    f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{p}",
                    headers=_sb_headers())
            except Exception:
                pass
        rd = await client.delete(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers({"Prefer": "return=minimal"}),
            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},
        )
    if rd.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail="No se pudo eliminar el machote.")
    return {"ok": True}


# ── PDF GENERATION ──────────────────────────────────────────────
from playwright.async_api import async_playwright
import base64, asyncio
from pydantic import BaseModel
from typing import List, Optional

class FotoItem(BaseModel):
    url: Optional[str] = None
    original: Optional[str] = None

class PropData(BaseModel):
    id: Optional[str] = None
    public_id: Optional[str] = None
    title: Optional[str] = None
    property_type: Optional[str] = None
    description: Optional[str] = None
    operations: Optional[list] = None
    location: Optional[dict] = None
    address: Optional[str] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    half_bathrooms: Optional[float] = None
    construction_size: Optional[float] = None
    lot_size: Optional[float] = None
    parking_spaces: Optional[float] = None
    floors: Optional[float] = None
    age: Optional[float] = None
    amenities: Optional[list] = None
    property_images: Optional[list] = None
    status: Optional[str] = None


def build_ficha_html(p: dict, images_b64: dict) -> str:
    """Plantilla editorial Broquer para la ficha técnica en PDF — edición Sky.
    Portada con tarjeta flotante sobre la foto, franja de specs con
    iconografía propia, galería en cuadrícula, características agrupadas
    por categoría, y footer de marca "Powered by Broquer" en cada página.
    """
    import re as _re
    id_prop  = p.get("public_id") or p.get("id") or ""
    titulo_base = p.get("title") or p.get("property_type") or "Propiedad"
    ops      = p.get("operations") or []
    sale_op   = next((o for o in ops if o.get("type") == "sale"), None)
    rental_op = next((o for o in ops if o.get("type") == "rental"), None)
    if not sale_op and not rental_op and ops:
        sale_op = ops[0]  # fallback: operación sin type explícito

    def fmt_money(op):
        if not op or not op.get("amount"):
            return None
        monto  = op.get("amount", 0)
        moneda = op.get("currency", "MXN")
        base = "${:,.0f}".format(monto)
        return base if moneda == "MXN" else base + " " + moneda

    es_venta_renta = bool(sale_op and rental_op)
    precio_venta = fmt_money(sale_op)
    precio_renta = fmt_money(rental_op)
    precio_principal = precio_venta or precio_renta or "—"
    if es_venta_renta:
        tipo_op = "Venta y renta"
    elif rental_op:
        tipo_op = "Renta"
    else:
        tipo_op = "Venta"

    loc      = p.get("location") or {}
    colonia  = (loc.get("name") or "").strip()
    ciudad   = (loc.get("city") or "").strip()
    direccion= (p.get("address") or "").strip()
    ubicacion= ", ".join(filter(None, [colonia, ciudad])) or direccion or "—"

    rec      = p.get("bedrooms")
    ban      = p.get("bathrooms")
    mban     = p.get("half_bathrooms")
    m2c      = p.get("construction_size")
    m2t      = p.get("lot_size")
    parking  = p.get("parking_spaces")
    niveles  = p.get("floors")
    anio     = p.get("age")
    desc     = (p.get("description") or "").replace("<br>", " ").replace("<br/>", " ")
    desc     = _re.sub(r"<[^>]+>", "", desc).strip()
    fotos    = p.get("property_images") or []
    amenids  = p.get("amenities") or []
    tipo_inmueble = (p.get("property_type") or "").strip()
    titulo   = titulo_base

    def asset_data_uri(filename: str, mime: str = "image/png") -> str:
        try:
            with open(filename, "rb") as fh:
                return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
        except Exception:
            return ""

    logo_white = asset_data_uri("logotipo-white.png")

    def fmt_m2(n):
        if not n:
            return None
        s = "{:,.2f}".format(n).rstrip("0").rstrip(".")
        return s + " m²"

    # ── Iconografía propia (línea 1.5px, redondeada, grid 24×24) ──
    ICO = {
        "bed":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a3 3 0 013-3h12a3 3 0 013 3v6"/><path d="M3 18h18M3 18v2m18-2v2"/><path d="M7 12V9a1 1 0 011-1h3a1 1 0 011 1v3"/></svg>',
        "bath":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12V6.5A2.5 2.5 0 017.5 4a2.5 2.5 0 012.5 2.5"/><path d="M3 12h18v2a5 5 0 01-5 5H8a5 5 0 01-5-5v-2z"/><path d="M6 19v2m12-2v2"/></svg>',
        "toilet":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h6a1 1 0 011 1V8H6V4.5a1 1 0 011-1z"/><path d="M5.5 8h9a2 2 0 012 2c0 6-3 10.5-6.5 10.5S3.5 16 3.5 10a2 2 0 012-2z"/></svg>',
        "area":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M15 4h5v9M20 15v5h-5M9 20H4v-5"/></svg>',
        "land":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3L3 5.5v15L9 18l6 3 6-2.5v-15L15 6 9 3z"/><path d="M9 3v15M15 6v15"/></svg>',
        "parking": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 11l1.4-4.4A2 2 0 018.3 5h7.4a2 2 0 011.9 1.6L19 11"/><path d="M5 11h14a1 1 0 011 1v4a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H7v1a1 1 0 01-1 1H5a1 1 0 01-1-1v-4a1 1 0 011-1z"/><circle cx="7.5" cy="16.5" r="1.3"/><circle cx="16.5" cy="16.5" r="1.3"/></svg>',
        "levels":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5l8.5 4.5-8.5 4.5-8.5-4.5L12 2.5z"/><path d="M3.5 12l8.5 4.5 8.5-4.5"/><path d="M3.5 16.5L12 21l8.5-4.5"/></svg>',
        "calendar":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M16 3v4M8 3v4M3.5 10h17"/></svg>',
        "tag":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.7 2.6a1.8 1.8 0 00-1.3-.5H4.3A1.8 1.8 0 002.5 3.9v6.1c0 .5.2.9.5 1.3l8 8a2.2 2.2 0 003 0l6-6a2.2 2.2 0 000-3.1l-8-8z"/><circle cx="7" cy="7.2" r="1.4"/></svg>',
        "pin":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21.3S5.5 14.8 5.5 9.8a6.5 6.5 0 0113 0c0 5-6.5 11.5-6.5 11.5z"/><circle cx="12" cy="9.8" r="2.4"/></svg>',
        "route":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18h7a4 4 0 004-4V9"/></svg>',
        "home":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 11.2L12 4l8.5 7.2"/><path d="M5.5 9.8v9.7a1 1 0 001 1H9v-6h6v6h2.5a1 1 0 001-1V9.8"/></svg>',
        "swap":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13l-3.5-3.5M20 16H7l3.5 3.5"/></svg>',
        "photo":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="10" r="1.6"/><path d="M21 15.5l-5.2-5.2a1.5 1.5 0 00-2.1 0L5 19"/></svg>',
        "sparkles":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3z"/><path d="M19 15l.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3z"/></svg>',
        "list":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg>',
    }

    # ── Specs de portada (hasta 6) ──
    specs = []
    if rec:    specs.append((ICO["bed"], str(int(rec)) if float(rec).is_integer() else str(rec), "Recámaras"))
    if ban:    specs.append((ICO["bath"], str(int(ban)) if float(ban).is_integer() else str(ban), "Baños"))
    if mban:   specs.append((ICO["toilet"], str(int(mban)) if float(mban).is_integer() else str(mban), "Medios baños"))
    def fmt_num(n):
        if not n:
            return None
        s = "{:,.2f}".format(n).rstrip("0").rstrip(".")
        return s

    if m2c:    specs.append((ICO["area"], fmt_num(m2c), "m² const."))
    if m2t:    specs.append((ICO["land"], fmt_num(m2t), "m² terreno"))
    if parking and len(specs) < 6: specs.append((ICO["parking"], str(int(parking)) if float(parking).is_integer() else str(parking), "Estac."))
    if niveles and len(specs) < 6: specs.append((ICO["levels"], str(int(niveles)) if float(niveles).is_integer() else str(niveles), "Niveles"))
    specs = specs[:6]

    specs_items = "".join(
        '<div class="spec-item"><div class="spec-ico">{}</div><div class="spec-val">{}</div><div class="spec-lbl">{}</div></div>'.format(i, v, l)
        for i, v, l in specs
    )
    specs_html = '<div class="cover-specs" style="--spec-cols:{}">{}</div>'.format(len(specs), specs_items) if specs_items else ""

    foto_urls = [f.get("url") or f.get("original") or "" for f in fotos if f]
    foto_urls = [u for u in foto_urls if u]
    hero_src  = images_b64.get(foto_urls[0], foto_urls[0]) if foto_urls else ""
    hero_html = '<img class="cover-hero" src="{}" alt="portada"/>'.format(hero_src) if hero_src else '<div class="cover-hero-placeholder">{}</div>'.format(ICO["home"])
    total_fotos = len(foto_urls)
    photocount_html = ''
    if total_fotos:
        photocount_html = '<div class="cover-photocount">{}{} foto{}</div>'.format(ICO["photo"], total_fotos, "" if total_fotos == 1 else "s")
    brandmark_html = '<div class="cover-brandmark"><img src="{}" alt="Broquer"/></div>'.format(logo_white) if logo_white else '<div class="cover-brandmark"><strong style="color:#fff">Broquer</strong></div>'

    def footer(page_num, total_pages):
        logo = '<img src="{}" alt="Broquer"/>'.format(logo_white) if logo_white else '<strong>Broquer</strong>'
        id_html = '<span class="ft-id">{}</span>'.format(id_prop) if id_prop else ''
        return (
            '<div class="ficha-footer">'
            '<div class="ft-brand">{}<span>Powered by Broquer</span></div>'
            '<div class="ft-meta">{}<span>{} / {}</span></div>'
            '</div>'
        ).format(logo, id_html, page_num, total_pages)

    precio_sec_html = ""
    if es_venta_renta and precio_renta:
        precio_sec_html = '<div class="cover-precio-sec">También disponible en renta: <b>{}/mes</b></div>'.format(precio_renta)

    cover_content = (
        '<div class="cover-hero-wrap">{}{}{}</div>'
        '<div class="cover-card">'
        '<div class="cover-card-top">'
        '<div class="cover-precio-block">'
        '<div class="cover-badge">{}</div>'
        '<div class="cover-precio">{}</div>{}'
        '</div>'
        '<div class="cover-tipo-pill">{}</div>'
        '</div>'
        '<div class="cover-titulo">{}</div>'
        '<div class="cover-ubicacion">{}{}</div>'
        '{}'
        '</div>'
        '{}'
    ).format(
        hero_html, brandmark_html, photocount_html,
        tipo_op, precio_principal, precio_sec_html,
        ICO["home"],
        titulo,
        ICO["pin"], ubicacion,
        specs_html,
        '<div class="cover-desc-wrap"><div class="cover-desc-ttl">Descripción</div><div class="cover-desc">{}</div></div>'.format(desc) if desc else '<div style="flex:1"></div>'
    )

    # ── Páginas de galería (6 fotos por página, igual que en el frontend) ──
    gallery_fotos = foto_urls[1:]
    gallery_contents = []
    for i in range(0, len(gallery_fotos), 6):
        batch = gallery_fotos[i:i+6]
        batch = batch + [None] * (6 - len(batch))
        imgs = "".join(
            '<img src="{}" alt="foto"/>'.format(images_b64.get(u, u)) if u else '<div class="ph-empty"></div>'
            for u in batch
        )
        gallery_contents.append(
            '<div class="fp-kicker"><div class="fp-kicker-left"><div class="fp-kicker-ico">{}</div><h2>Galería fotográfica</h2></div>'
            '<div class="fp-kicker-id">{}</div></div>'
            '<div class="photo-grid">{}</div>'.format(ICO["photo"], ubicacion, imgs)
        )

    # ── Características agrupadas por categoría ──
    def char_item(icon, lbl, val):
        return '<div class="char-item"><div class="char-ico">{}</div><div class="char-txt"><div class="char-lbl">{}</div><div class="char-val">{}</div></div></div>'.format(icon, lbl, val)

    prec_rows = []
    prec_rows.append(char_item(ICO["swap"], "Operación", tipo_op))
    if precio_venta: prec_rows.append(char_item(ICO["tag"], "Precio de venta" if es_venta_renta else "Precio", precio_venta))
    if es_venta_renta and precio_renta: prec_rows.append(char_item(ICO["tag"], "Precio de renta", precio_renta + "/mes"))
    if not precio_venta and not es_venta_renta and precio_renta: pass  # ya cubierto como precio principal arriba

    dist_rows = []
    if tipo_inmueble: dist_rows.append(char_item(ICO["home"], "Tipo de inmueble", tipo_inmueble))
    if rec:  dist_rows.append(char_item(ICO["bed"], "Recámaras", rec))
    if ban:  dist_rows.append(char_item(ICO["bath"], "Baños completos", ban))
    if mban: dist_rows.append(char_item(ICO["toilet"], "Medios baños", mban))
    if niveles: dist_rows.append(char_item(ICO["levels"], "Niveles", niveles))
    if anio: dist_rows.append(char_item(ICO["calendar"], "Año de construcción", anio))

    sup_rows = []
    if fmt_m2(m2c): sup_rows.append(char_item(ICO["area"], "Superficie construida", fmt_m2(m2c)))
    if fmt_m2(m2t): sup_rows.append(char_item(ICO["land"], "Superficie de terreno", fmt_m2(m2t)))
    if parking: sup_rows.append(char_item(ICO["parking"], "Estacionamientos", parking))

    ub_rows = []
    if colonia: ub_rows.append(char_item(ICO["pin"], "Colonia", colonia))
    if ciudad:  ub_rows.append(char_item(ICO["pin"], "Ciudad", ciudad))
    if direccion: ub_rows.append(char_item(ICO["route"], "Dirección", direccion))
    if id_prop: ub_rows.append(char_item(ICO["tag"], "Clave", id_prop))

    def group_html(titulo_grupo, rows):
        if not rows:
            return ""
        return '<div class="chars-group"><div class="chars-group-ttl">{}</div><div class="chars-grid">{}</div></div>'.format(titulo_grupo, "".join(rows))

    amen_html = ""
    if amenids:
        items = "".join('<div class="amen-item">{}{}</div>'.format(ICO["sparkles"], a.get("name") or a) for a in amenids)
        amen_html = '<div class="chars-group amen-section"><div class="chars-group-ttl">Amenidades y extras</div><div class="amen-grid">{}</div></div>'.format(items)

    chars_content = (
        '<div class="fp-kicker"><div class="fp-kicker-left"><div class="fp-kicker-ico">{}</div><h2>Características del inmueble</h2></div>'
        '<div class="fp-kicker-id">{}</div></div>'
        '<div class="chars-body">{}{}{}{}{}</div>'
    ).format(
        ICO["list"], id_prop,
        group_html("Operación y precio", prec_rows),
        group_html("Distribución", dist_rows),
        group_html("Superficie y estacionamiento", sup_rows),
        group_html("Ubicación", ub_rows),
        amen_html,
    )

    all_contents = [cover_content] + gallery_contents + [chars_content]
    total_pages = len(all_contents)
    pages_html = "".join(
        '<div class="ficha-page">{}{}</div>'.format(content, footer(i + 1, total_pages))
        for i, content in enumerate(all_contents)
    )

    # ── Sistema de diseño ──
    # Los colores salen de brokr-theme.css vía theme_css_for_pdf(): este
    # archivo ya no los duplica. Cero JetBrains Mono, cero mayúsculas
    # decorativas.
    # Tokens desde brokr-theme.css. Radios y sombras propios del
    # documento: la ficha es un impreso, no una pantalla.
    CSS = theme_css_for_pdf(
        "--r:14px; --r-sm:8px; --r-lg:28px; --r-pill:999px;"
        "--shadow-sm:0 1px 3px rgba(0,20,59,.10),0 1px 2px rgba(0,20,59,.06);"
        "--shadow-lg:0 18px 44px rgba(0,20,59,.18),0 4px 12px rgba(0,20,59,.10);"
    ) + """
*{box-sizing:border-box;margin:0;padding:0;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;color-adjust:exact!important}
html,body{width:210mm}
body{font-family:var(--font-sans);background:var(--paper);color:var(--ink);-webkit-font-smoothing:antialiased}
.ficha-page{position:relative;width:210mm;height:297mm;background:var(--paper);display:flex;flex-direction:column;overflow:hidden;page-break-after:always}
.ficha-page:last-child{page-break-after:avoid}

.fp-kicker{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;border-bottom:1px solid var(--line)}
.fp-kicker-left{display:flex;align-items:center;gap:10px}
.fp-kicker-ico{width:20px;height:20px;color:var(--sky-blue);flex-shrink:0}.fp-kicker-ico svg{width:100%;height:100%}
.fp-kicker h2{font-family:var(--font-display);font-size:17px;font-weight:700;color:var(--ink);letter-spacing:-.02em}
.fp-kicker-id{font-size:11px;color:var(--mute-2)}

.cover-hero-wrap{width:100%;height:128mm;position:relative;flex-shrink:0;background:linear-gradient(135deg,var(--sky-navy),var(--ink-2))}
.cover-hero{width:100%;height:100%;object-fit:cover;display:block}
.cover-hero-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.cover-hero-placeholder svg{width:56px;height:56px;color:rgba(255,255,255,.35)}
.cover-brandmark{position:absolute;top:16px;left:20px;height:20px}.cover-brandmark img{height:100%;width:auto;display:block}
.cover-photocount{position:absolute;top:16px;right:20px;background:rgba(5,32,60,.55);color:#fff;font-size:11px;font-weight:500;padding:5px 11px;border-radius:var(--r-pill);display:flex;align-items:center;gap:5px}
.cover-photocount svg{width:13px;height:13px}

.cover-card{margin:-22mm 16mm 0;background:var(--bone);border-radius:var(--r-lg);box-shadow:var(--shadow-lg);border:1px solid var(--line);padding:20px 24px 4px;position:relative;z-index:2}
.cover-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}
.cover-badge{display:inline-flex;align-items:center;background:var(--sky-navy);color:#fff;font-size:12px;font-weight:600;padding:5px 12px;border-radius:var(--r-pill);margin-bottom:10px}
.cover-precio-block{display:flex;flex-direction:column}
.cover-precio{font-family:var(--font-display);font-size:34px;font-weight:700;letter-spacing:-.03em;color:var(--ink);line-height:1.05}
.cover-precio-sec{font-size:12.5px;color:var(--mute);margin-top:4px;font-weight:500}
.cover-precio-sec b{color:var(--ink-2);font-weight:600}
.cover-tipo-pill{flex-shrink:0;width:46px;height:46px;border-radius:var(--r);background:var(--paper-2);display:flex;align-items:center;justify-content:center;color:var(--sky-navy)}
.cover-tipo-pill svg{width:22px;height:22px}
.cover-titulo{font-family:var(--font-display);font-size:16px;font-weight:700;color:var(--ink);margin-bottom:5px;letter-spacing:-.015em}
.cover-ubicacion{font-size:12.5px;color:var(--mute);display:flex;align-items:center;gap:5px;padding-bottom:16px}
.cover-ubicacion svg{width:13px;height:13px;flex-shrink:0;color:var(--mute-2)}
.cover-specs{display:grid;grid-template-columns:repeat(var(--spec-cols,4),1fr);border-top:1px solid var(--line);margin:0 -24px;padding:0 24px}
.spec-item{padding:13px 6px 12px;text-align:center;border-right:1px solid var(--line)}
.spec-item:last-child{border-right:none}
.spec-ico{width:20px;height:20px;margin:0 auto 6px;color:var(--sky-blue)}.spec-ico svg{width:100%;height:100%}
.spec-val{font-family:var(--font-display);font-size:16px;font-weight:700;color:var(--ink);line-height:1.1;letter-spacing:-.02em}
.spec-lbl{font-size:10.5px;color:var(--mute);margin-top:3px;font-weight:500}
.cover-desc-wrap{padding:18px 24px 14px;flex:1}
.cover-desc-ttl{font-family:var(--font-display);font-size:13px;font-weight:700;color:var(--ink);margin-bottom:8px;letter-spacing:-.01em}
.cover-desc{font-size:11.5px;color:var(--ink-2);line-height:1.7}

.photo-grid{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:4px;padding:4px;flex:1;overflow:hidden;background:var(--paper-2)}
.photo-grid img{width:100%;height:100%;object-fit:cover;display:block}
.photo-grid .ph-empty{width:100%;height:100%;background:var(--paper-2)}

.chars-body{padding:20px 24px 8px;flex:1}
.chars-group{margin-bottom:18px}
.chars-group-ttl{font-size:11px;font-weight:700;color:var(--mute);text-transform:uppercase;letter-spacing:.06em;margin-bottom:9px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.chars-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.char-item{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--paper-2);border-radius:var(--r-sm)}
.char-ico{width:18px;height:18px;color:var(--sky-blue);flex-shrink:0}.char-ico svg{width:100%;height:100%}
.char-txt{min-width:0}
.char-lbl{font-size:10px;color:var(--mute);margin-bottom:1px}
.char-val{font-size:13px;font-weight:600;color:var(--ink);letter-spacing:-.01em;overflow-wrap:anywhere}
.amen-grid{display:flex;flex-wrap:wrap;gap:7px}
.amen-item{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;padding:6px 12px;background:var(--paper-2);border-radius:var(--r-pill);color:var(--ink-2);border:1px solid var(--line);font-weight:500}
.amen-item svg{width:12px;height:12px;color:var(--sky-blue);flex-shrink:0}

.ficha-footer{width:100%;height:42px;background:var(--sky-navy);display:flex;align-items:center;justify-content:space-between;padding:0 22px;flex-shrink:0;margin-top:auto}
.ft-brand{display:flex;align-items:center;gap:8px}
.ft-brand img{height:16px;width:auto;display:block;opacity:.95}
.ft-brand span{font-size:10px;font-weight:500;color:rgba(255,255,255,.6);letter-spacing:.01em}
.ft-meta{display:flex;align-items:center;gap:10px;font-size:10px;color:rgba(255,255,255,.5)}
.ft-id{letter-spacing:.03em}
@page{size:A4 portrait;margin:0}
"""

    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'/>"
        "<style>{}</style></head><body>{}</body></html>"
    ).format(CSS, pages_html)



# ────────────────────────────────────────────
# NOTICIAS INMOBILIARIAS — RSS REAL
# ────────────────────────────────────────────
import xml.etree.ElementTree as ET

@app.get("/noticias")
async def get_noticias():
    """Fetch real estate news from Google News RSS — parsed server-side to avoid CORS."""
    FEEDS = [
        "https://news.google.com/rss/search?q=bienes+raices+Mexico&hl=es-419&gl=MX&ceid=MX:es-419",
        "https://news.google.com/rss/search?q=mercado+inmobiliario+Mexico&hl=es-419&gl=MX&ceid=MX:es-419",
    ]

    cached = cache_get("noticias_rss")
    if cached is not None:
        return cached

    items = []
    seen = set()

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for feed_url in FEEDS:
            try:
                r = await client.get(feed_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.text)
                channel = root.find("channel")
                if channel is None:
                    continue
                for item in channel.findall("item")[:8]:
                    title_el = item.find("title")
                    link_el  = item.find("link")
                    source_el = item.find("source")
                    if title_el is None or link_el is None:
                        continue
                    title = title_el.text or ""
                    # Strip trailing source name like "- El Universal"
                    title = re.sub(r"\s*[-–]\s*[^-–]+$", "", title).strip()
                    link  = link_el.text or ""
                    source = source_el.text if source_el is not None else "Google News"
                    if title in seen or not title or not link:
                        continue
                    seen.add(title)
                    items.append({"title": title, "url": link, "source": source})
                    if len(items) >= 12:
                        break
            except Exception:
                continue
            if len(items) >= 12:
                break

    if not items:
        # Fallback vacío — el front usará sus estáticos
        return {"items": []}

    result = {"items": items}
    cache_set("noticias_rss", result, ttl=1800)  # Cache 30 minutos
    return result


@app.post("/ficha-manual/descripcion")
async def generar_descripcion_ficha_manual(data: dict, request: Request):
    """Generate AI description for ficha manual — uses same httpx pattern as rest of backend."""
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")
    user_id = await get_user_id_from_token(request)

    tipo    = data.get("tipo", "")
    colonia = data.get("colonia", "")
    ciudad  = data.get("ciudad", "Morelia")
    m2c     = data.get("m2c", "")
    m2t     = data.get("m2t", "")
    rec     = data.get("rec", "")
    ban     = data.get("ban", "")
    est     = data.get("est", "")
    niv     = data.get("niv", "")
    anio    = data.get("anio", "")
    precio  = data.get("precio", "")
    op      = data.get("op", "Venta")
    amen    = data.get("amen", "")

    partes = []
    if tipo:    partes.append(f"Tipo: {tipo}")
    if op:      partes.append(f"Operación: {op}")
    if precio:  partes.append(f"Precio: {precio}")
    if colonia: partes.append(f"Colonia: {colonia}, {ciudad}")
    if rec:     partes.append(f"Recámaras: {rec}")
    if ban:     partes.append(f"Baños: {ban}")
    if m2c:     partes.append(f"Construcción: {m2c} m²")
    if m2t:     partes.append(f"Terreno: {m2t} m²")
    if est:     partes.append(f"Estacionamientos: {est}")
    if niv:     partes.append(f"Niveles: {niv}")
    if anio:    partes.append(f"Año: {anio}")
    if amen:    partes.append(f"Amenidades: {amen}")

    ficha_info = "\n".join(partes) if partes else "Propiedad sin datos"
    prompt = (
        "Eres un redactor especialista en bienes raíces en México. "
        "Escribe una descripción comercial atractiva, profesional y fluida "
        "de máximo 120 palabras para la siguiente propiedad. "
        "Sin bullets, sin encabezados, solo prosa natural y persuasiva. "
        "No repitas datos de forma robótica; hazlo sonar humano y apetecible.\n\n"
        f"{ficha_info}"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 350,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error IA: {r.status_code}")
    resp = r.json()
    _track_anthropic(user_id, "ficha-manual", "/ficha-manual/descripcion", resp,
                     modelo=resp.get("model") or "claude-sonnet-4-6")
    descripcion = resp.get("content", [{}])[0].get("text", "").strip()
    return {"descripcion": descripcion}


@app.post("/ficha-pdf")
async def generar_ficha_pdf(p: dict, request: Request):
    """Generate PDF from property data dict using Playwright."""
    _uid = await get_user_id_from_token(request)
    exigir_cupo(request, _uid)
    exigir_sesion(request, _uid)
    import httpx
    
    # Collect all image URLs
    fotos = p.get("property_images") or []
    urls = list(set(filter(None, [f.get("url") or f.get("original") for f in fotos])))
    
    # Download all images concurrently and convert to base64
    images_b64 = {}
    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_img(url):
            try:
                r = await client.get(url, follow_redirects=True, timeout=10.0)
                if r.status_code == 200:
                    ext = url.split(".")[-1].split("?")[0].lower()
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
                    b64 = base64.b64encode(r.content).decode()
                    images_b64[url] = f"data:{mime};base64,{b64}"
            except Exception:
                pass  # skip failed images, show blank

        # Limit to 19 gallery images (1 hero + 18 gallery = 3 full pages max)
        await asyncio.gather(*[fetch_img(u) for u in urls[:19]])
    
    # Build HTML
    html = build_ficha_html(p, images_b64)
    
    # Render to PDF with Playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        # Use domcontentloaded instead of networkidle — images are already base64
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(500)  # small wait for fonts
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}
        )
        await browser.close()
    
    from fastapi.responses import JSONResponse
    import re as _re2
    id_prop   = p.get("public_id") or p.get("id") or ""
    loc       = p.get("location") or {}
    colonia   = (loc.get("name") or "").strip()
    tipo_raw  = (p.get("property_type") or "Propiedad").strip()
    # Sanitize: remove accents and special chars for filename
    def _slug(s):
        for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n'),
                     ('Á','A'),('É','E'),('Í','I'),('Ó','O'),('Ú','U'),('Ñ','N')]:
            s = s.replace(a, b)
        return _re2.sub(r'[^A-Za-z0-9_]', '_', s).strip('_')
    parts = ["Ficha"]
    if colonia:  parts.append(_slug(colonia))
    filename = "_".join(parts) + ".pdf"
    token = str(_uuid.uuid4()).replace("-","")[:16]
    _pdf_store[token] = (pdf_bytes, filename)
    # Clean old entries if too many
    if len(_pdf_store) > 50:
        oldest = list(_pdf_store.keys())[0]
        del _pdf_store[oldest]
    return JSONResponse({"token": token, "filename": filename})

@app.get("/ficha-pdf/{token}")
async def descargar_ficha_pdf(token: str):
    """Serve generated PDF by token — opens natively in Safari."""
    from fastapi.responses import Response
    if token not in _pdf_store:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="PDF no encontrado o expirado")
    pdf_bytes, filename = _pdf_store[token]
    # Use attachment for direct download on all devices including PWA
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
            "Cache-Control": "no-store",
        }
    )
# ────────────────────────────────────────────
# AVM — COMPARABLES VÍA APIFY + INMUEBLES24
# ────────────────────────────────────────────

APIFY_ACTOR   = "azzouzana~inmuebles24-scraper-pro-by-search-url"

# Mapeo de tipo de inmueble a término de búsqueda en Inmuebles24
TIPO_URL = {
    "casa":         "casas",
    "departamento": "departamentos",
    "terreno":      "terrenos",
    "local":        "locales-comerciales",
    "oficina":      "oficinas",
    "bodega":       "bodegas",
    "edificio":     "edificios",
}

class ComparablesRequest(BaseModel):
    colonia: str
    ciudad: str = "morelia"
    estado: str = "michoacan-de-ocampo"
    tipo: str = "casa"          # casa | departamento | terreno | local | oficina | bodega | edificio
    max_resultados: int = 10    # cuántos comparables traer


def construir_url_inmuebles24(tipo: str, colonia: str, ciudad: str, estado: str) -> str:
    segmento = TIPO_URL.get(tipo, "casas")
    ciudad = ciudad.lower().strip().replace(" ", "-")
    col = colonia.lower().strip().replace(" ", "-")
    return f"https://www.inmuebles24.com/{segmento}-en-{ciudad}-o-{col}.html"


def normalizar_listing(item: dict) -> dict:
    """Convierte un resultado de Apify (scraper Azzouzana) al formato que espera el AVM."""
    
    # Precio
    precio = item.get("price_amount") or 0
    moneda = item.get("price_currency", "MN")
    # Ignorar propiedades en USD (fuera de mercado local)
    if moneda == "USD":
        return None

    # m² de construcción — viene en generatedTitle: "Casa · 120m² · 3 Recámaras"
    m2c = 0
    titulo_gen = item.get("generatedTitle", "")
    match_m2 = re.search(r'(\d+)m²', titulo_gen)
    if match_m2:
        m2c = float(match_m2.group(1))

    # Recámaras
    recamaras = 0
    match_rec = re.search(r'(\d+)\s+Rec[áa]maras?', titulo_gen, re.IGNORECASE)
    if match_rec:
        recamaras = int(match_rec.group(1))

    # Estacionamientos
    estac = 0
    match_estac = re.search(r'(\d+)\s+Estacionamientos?', titulo_gen, re.IGNORECASE)
    if match_estac:
        estac = int(match_estac.group(1))

    # m² terreno — intentar extraer de descripción
    m2t = 0
    desc = item.get("descriptionNormalized", "")
    patrones_terreno = [
        r'[Tt]erreno[:\s/]+(\d+[\.,]?\d*)\s*(?:m²|m2|metros cuadrados|metros)',
        r'(\d+[\.,]?\d*)\s*(?:m²|m2)\s*de\s+terreno',
        r'[Ss]uperficie\s+de\s+terreno[:\s]+[\d,\s]*(\d+)\s*(?:m²|m2)',
        r'[Tt]erreno\s+de\s+(\d+[\.,]?\d*)\s*(?:m²|m2)',
    ]
    for patron in patrones_terreno:
        match_t = re.search(patron, desc)
        if match_t:
            val = match_t.group(1).replace(',', '').replace('.', '')
            try:
                m2t = float(val)
                if m2t < 10 or m2t > 50000:
                    m2t = 0
            except:
                m2t = 0
            if m2t > 0:
                break

    titulo = item.get("title") or ""
    url = item.get("url") or ""
    imagenes = item.get("images", [])
    imagen = imagenes[0].split("?")[0] if imagenes else ""

    return {
        "precio": int(precio),
        "m2Construccion": m2c,
        "m2Terreno": m2t,
        "recamaras": recamaras,
        "banos": 0,
        "estacionamiento": estac,
        "edad": 0,
        "conservacion": "bueno",
        "calidad": "medio",
        "mismaZona": "si",
        "titulo": titulo,
        "url": url,
        "imagen": imagen,
    }

@app.post("/api/comparables")
async def buscar_comparables(req: ComparablesRequest):
    """
    Llama a Apify (actor de Inmuebles24) y regresa comparables normalizados
    listos para el AVM.
    """
    if not APIFY_API_KEY:
        raise HTTPException(status_code=500, detail="APIFY_API_KEY no configurada en el servidor")

    url_busqueda = construir_url_inmuebles24(req.tipo, req.colonia, req.ciudad, req.estado)

    # Cache key para no re-scrapear la misma búsqueda en 2 horas
    cache_key = f"comparables_{req.tipo}_{req.colonia}_{req.ciudad}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Llamada a Apify — run-sync-get-dataset-items (espera hasta que termina)
    apify_url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
        f"/run-sync-get-dataset-items?token={APIFY_API_KEY}"
        f"&timeout=60&memory=256"
    )

    payload = {
        "startUrl": url_busqueda,
        "maxItems": req.max_resultados,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            r = await client.post(apify_url, json=payload)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Apify tardó demasiado. Intenta de nuevo.")

        if r.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Error de Apify: {r.status_code} — {r.text[:300]}"
            )

        items = r.json()

    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Respuesta inesperada de Apify")

    # Filtrar items con precio y m2 válidos, normalizar
    comparables = []
    for item in items:
        n = normalizar_listing(item)
        if n["precio"] > 0 and n["m2Construccion"] > 0:
            comparables.append(n)

    resultado = {
        "url_busqueda": url_busqueda,
        "total": len(comparables),
        "comparables": comparables,
    }

    cache_set(cache_key, resultado, ttl=7200)  # cache 2 horas
    return resultado

# ────────────────────────────────────────────
# AVM — COLONIAS (Nominatim) Y COMPARABLES CERCANOS (Supabase)
# ────────────────────────────────────────────

class ColoniasRequest(BaseModel):
    texto: str
    ciudad: str = "Morelia"

@app.get("/api/colonias")
async def buscar_colonias(texto: str, ciudad: str = "Morelia"):
    if len(texto) < 3:
        return {"colonias": []}

    cache_key = f"colonias_g3_{ciudad}_{texto}".lower()
    cached = cache_get(cache_key)
    if cached:
        return cached

    if not GOOGLE_PLACES_KEY:
        return {"colonias": [], "error": "GOOGLE_PLACES_KEY no configurada"}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params={
                    "input": texto,
                    "types": "geocode",
                    "language": "es",
                    "components": "country:mx",
                    "locationbias": "circle:50000@19.7059504,-101.1949825",
                    "key": GOOGLE_PLACES_KEY,
                }
            )
            data = r.json()
        except Exception as e:
            return {"colonias": [], "error": str(e)}

    colonias = []
    for pred in data.get("predictions", []):
        descripcion = pred.get("description", "")
        tipos = pred.get("types", [])

        if not any(t in tipos for t in ["sublocality", "sublocality_level_1", "neighborhood"]):
            continue

        nombre = pred.get("structured_formatting", {}).get("main_text", "").strip()
        place_id = pred.get("place_id", "")

        lat, lon = 0.0, 0.0
        if place_id:
            try:
                async with httpx.AsyncClient(timeout=10) as client2:
                    r2 = await client2.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place_id,
                            "fields": "geometry",
                            "key": GOOGLE_PLACES_KEY,
                        }
                    )
                    details_data = r2.json()
                    loc = details_data.get("result", {}).get("geometry", {}).get("location", {})
                    lat = loc.get("lat", 0.0)
                    lon = loc.get("lng", 0.0)
            except Exception:
                pass

        if nombre:
            colonias.append({
                "nombre":    nombre,
                "display":   descripcion,
                "latitud":   lat,
                "longitud":  lon,
                "place_id":  place_id,
            })

    resultado = {"colonias": colonias[:6]}
    cache_set(cache_key, resultado, ttl=86400)
    return resultado


# ────────────────────────────────────────────
# AVM — COMPARABLES CERCANOS (PostGIS + Supabase)
# ────────────────────────────────────────────

# CercanosRequest — única definición
class CercanosRequest(BaseModel):
    latitud: float
    longitud: float
    tipo: str = "casa"
    radio_km: float = 2.0
    max_resultados: int = 15

# TIPO_MAP_DB — mapeo hacia tipos de Supabase/PostGIS (distinto del TIPO_MAP de EasyBroker arriba)
TIPO_MAP_DB = {
    "casa":         ["Casas", "Desarrollos horizontales", "Desarrollos Horizontal/Vertical"],
    "departamento": ["Departamentos", "Desarrollos verticales"],
    "terreno":      ["Terrenos"],
    "local":        ["Locales comerciales", "Locales Comerciales"],
    "oficina":      ["Oficinas"],
    "bodega":       ["Bodegas"],
    "edificio":     ["Edificios"],
}

@app.post("/api/comparables-cercanos")
async def comparables_cercanos(req: CercanosRequest):
    """Busca propiedades cercanas en Supabase usando PostGIS."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL o SUPABASE_ANON_KEY no configuradas")

    cache_key = f"cercanos_{req.tipo}_{req.latitud:.4f}_{req.longitud:.4f}_{req.radio_km}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    tipos_db = TIPO_MAP_DB.get(req.tipo, ["Casas"])
    radio_metros = int(req.radio_km * 1000)

    # Llamar a función RPC en Supabase que ejecuta la query PostGIS
    payload = {
        "lat": req.latitud,
        "lon": req.longitud,
        "radio": radio_metros,
        "tipos": tipos_db,
        "limite": req.max_resultados,
    }

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/buscar_cercanos",
            headers=headers,
            json=payload,
        )

    if r.status_code not in (200, 201):
        # Fallback: buscar por ciudad sin PostGIS
        try:
            items = await get_public_rows(
                "propiedades_avm",
                {
                    "ciudad": "eq.Morelia",
                    "precio": "gt.0",
                    "metros_construccion": "not.is.null",
                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",
                    "limit": req.max_resultados,
                    "order": "precio.asc",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError:
            items = []
    else:
        items = r.json() or []

    comparables = []
    for item in items:
        precio = item.get("precio") or 0
        m2c    = item.get("metros_construccion") or 0
        if precio <= 0 or m2c <= 0:
            continue
        comparables.append({
            "precio":           int(precio),
            "m2Construccion":   float(m2c),
            "m2Terreno":        float(item.get("metros_terreno") or 0),
            "recamaras":        int(item.get("recamaras") or 0),
            "estacionamiento":  int(item.get("estacionamientos") or 0),
            "banos":            0,
            "edad":             0,
            "conservacion":     "bueno",
            "calidad":          "medio",
            "mismaZona":        "si",
            "titulo":           item.get("titulo") or "",
            "url":              item.get("url") or "",
            "imagen":           "",
            "colonia":          item.get("colonia") or "",
            "distancia_metros": int(item.get("distancia_metros") or 0),
        })

    resultado = {
        "total":       len(comparables),
        "comparables": comparables,
        "latitud":     req.latitud,
        "longitud":    req.longitud,
        "radio_km":    req.radio_km,
    }
    cache_set(cache_key, resultado, ttl=3600)
    return resultado


# ─── LIMPIEZA DE IMÁGENES ─────────────────────────────────────────────────────


def _process_image_sync(file_bytes: bytes, content_type: str) -> bytes:
    """Pipeline de mejora automática (sin IA generativa): denoising, CLAHE, WB, unsharp."""
    if not PIL_AVAILABLE:
        return file_bytes
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    if CV2_AVAILABLE:
        arr = np.array(img)
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        # 1. Denoising adaptativo
        gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
        noise_est = np.std(cv2.Laplacian(gray.astype(np.float64), cv2.CV_64F))
        if noise_est > 12:
            arr_bgr = cv2.fastNlMeansDenoisingColored(arr_bgr, None, 7, 7, 7, 21)

        # 2. Espacio LAB
        lab = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)

        # 3. CLAHE en L
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)

        # 4. LUT sombras/altas luces
        lut = np.arange(256, dtype=np.float32)
        lut = np.where(lut < 80,  lut * 1.12, lut)
        lut = np.where(lut > 210, 210 + (lut - 210) * 0.55, lut)
        lut = np.clip(lut, 0, 255).astype(np.uint8)
        l_ch = cv2.LUT(l_ch, lut)

        # 5. Vibrance A/B
        a_ch = np.clip((a_ch.astype(np.int16) - 128) * 1.1 + 128, 0, 255).astype(np.uint8)
        b_ch = np.clip((b_ch.astype(np.int16) - 128) * 1.1 + 128, 0, 255).astype(np.uint8)
        arr_bgr = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

        # 6. Balance de blancos parcial (70% gray-world)
        bc, gc, rc = cv2.split(arr_bgr.astype(np.float32))
        mb, mg, mr = bc.mean(), gc.mean(), rc.mean()
        mg_all = (mb + mg + mr) / 3
        s = 0.7
        bc = np.clip(bc * (1 + s * (mg_all / max(mb, 1) - 1)), 0, 255)
        gc = np.clip(gc * (1 + s * (mg_all / max(mg, 1) - 1)), 0, 255)
        rc = np.clip(rc * (1 + s * (mg_all / max(mr, 1) - 1)), 0, 255)
        arr_bgr = cv2.merge([bc.astype(np.uint8), gc.astype(np.uint8), rc.astype(np.uint8)])

        # 7. Unsharp masking
        blur = cv2.GaussianBlur(arr_bgr, (0, 0), 1.5)
        arr_bgr = np.clip(cv2.addWeighted(arr_bgr, 1.45, blur, -0.45, 0), 0, 255).astype(np.uint8)

        img = Image.fromarray(cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB))
    else:
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.6)

    out = io.BytesIO()
    fmt = "JPEG" if (content_type or "").lower() in ("image/jpeg", "image/jpg") else "PNG"
    img.save(out, format=fmt, quality=92, optimize=True)
    return out.getvalue()


async def _process_with_gemini(img_bytes: bytes, content_type: str, prompt: str) -> bytes:
    """Edita la imagen con Gemini Flash imagen-generation."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    # Resize a máx 1024px para reducir payload y tiempo de proceso
    if PIL_AVAILABLE:
        pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = pil.size
        if max(w, h) > 1024:
            scale = 1024 / max(w, h)
            pil = pil.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

    img_b64 = base64.b64encode(img_bytes).decode()
    full_prompt = (
        "You are a professional real estate photo editor. "
        "Edit this photo: " + prompt + ". "
        "Output only the edited image."
    )

    # Solo v1beta — los modelos Nano Banana no están en v1
    # Solo 2 payloads: con imagen (preferido) y solo texto (fallback)
    _payloads = [
        {"contents": [{"parts": [
            {"text": full_prompt},
            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
        ]}]},
        {"contents": [{"parts": [{"text": full_prompt}]}]},
    ]

    # Modelos en orden de preferencia — solo v1beta
    _model_names = [m for m in [
        settings.gemini_image_model,
        "gemini-3.1-flash-image-preview",   # Nano Banana 2
        "gemini-2.5-flash-image",            # Nano Banana
        "gemini-3-pro-image-preview",        # Nano Banana Pro
    ] if m]

    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    last_err = "Sin modelos disponibles"

    # Timeout 25s por petición — Railway corta a ~60s total, necesitamos margen
    async with httpx.AsyncClient(timeout=25) as client:
        for model_name in _model_names:
            url = f"{GEMINI_BASE_URL}/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            for payload in _payloads:
                try:
                    r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                except Exception as e:
                    last_err = f"Timeout ({model_name}): {e}"
                    break  # red fallida, pasar al siguiente modelo

                if r.status_code == 404:
                    last_err = f"Modelo no encontrado: {model_name}"
                    break  # este modelo no existe, probar siguiente

                if r.status_code == 429:
                    # Cuota agotada — no tiene sentido probar otros modelos
                    raise RuntimeError(
                        "Cuota de Gemini agotada. Espera a que se reinicie tu límite gratuito "
                        "(~24h) o activa billing en https://aistudio.google.com/apikey."
                    )

                if r.status_code == 200:
                    try:
                        data = r.json()
                        parts = data["candidates"][0]["content"]["parts"]
                    except Exception as e:
                        last_err = f"JSON inválido ({model_name}): {e}"
                        continue

                    for part in parts:
                        if "inlineData" in part:
                            raw = base64.b64decode(part["inlineData"]["data"])
                            if PIL_AVAILABLE:
                                pil2 = Image.open(io.BytesIO(raw)).convert("RGB")
                                out = io.BytesIO()
                                pil2.save(out, format="JPEG", quality=92)
                                return out.getvalue()
                            return raw

                    text_parts = [p.get("text", "") for p in parts if "text" in p]
                    last_err = f"Sin imagen en respuesta ({model_name}): {' '.join(text_parts)[:150]}"
                    continue

                last_err = f"Error {r.status_code} ({model_name}): {r.text[:200]}"
                continue

    raise RuntimeError(last_err)


from fastapi import Form as _Form

@app.post("/images/clean")
async def clean_images(
    request: Request,
    files: List[UploadFile] = File(...),
    prompt: str = _Form(""),
    # legacy field kept for backward compat
    remove_furniture: str = _Form("false"),
):
    user_id = await get_user_id_from_token(request)
    exigir_cupo(request, user_id)
    exigir_sesion(request, user_id)
    use_gemini = bool(prompt.strip()) and bool(GEMINI_API_KEY)

    async def process_one(uf: UploadFile):
        raw = await uf.read()
        ct = uf.content_type or "image/jpeg"
        try:
            if use_gemini:
                processed = await _process_with_gemini(raw, ct, prompt.strip())
                return {
                    "name": uf.filename,
                    "cleaned_b64": base64.b64encode(processed).decode(),
                    "content_type": "image/jpeg",
                    "used_gemini": True,
                    "error": None,
                }
            else:
                loop = asyncio.get_event_loop()
                processed = await loop.run_in_executor(
                    _thread_pool, _process_image_sync, raw, ct
                )
                return {
                    "name": uf.filename,
                    "cleaned_b64": base64.b64encode(processed).decode(),
                    "content_type": ct,
                    "used_gemini": False,
                    "error": None,
                }
        except Exception as exc:
            return {
                "name": uf.filename,
                "cleaned_b64": None,
                "content_type": ct,
                "used_gemini": False,
                "error": str(exc),
            }

    results = await asyncio.gather(*[process_one(f) for f in files])
    # Trackeo: solo imágenes procesadas exitosamente con Gemini (cobro real)
    try:
        gemini_ok = sum(1 for r in results if r.get("used_gemini") and not r.get("error"))
        if gemini_ok > 0:
            _track_gemini_image(user_id, "image-cleaner", "/images/clean",
                                unidades=gemini_ok,
                                modelo=settings.gemini_image_model)
    except Exception:
        pass
    return {"images": list(results)}


# ════════════════════════════════════════════════════════════════
# META GRAPH API — capa común
# ════════════════════════════════════════════════════════════════
# Todas las llamadas al Graph API de Meta (Facebook) pasan por aquí.
# Antes cada endpoint hacía su propio httpx.get/post: la versión de la API
# estaba escrita a mano en ~40 lugares (y una se quedó en v18.0), nadie
# reintentaba cuando Meta contestaba 429, y los errores se devolvían como
# texto crudo. Esta capa arregla las tres cosas de un solo lugar.
#
# Es el espejo de _eb_get_reintentos() (EasyBroker), pero para Meta:
# Meta además codifica el motivo real del rechazo en `error.code`, no solo
# en el status HTTP, y publica su presupuesto de llamadas en la cabecera
# X-Business-Use-Case-Usage. Ambas cosas se honran abajo.

_fb_log = logging.getLogger("broquer.facebook")


# ─── Cifrado de tokens en reposo ──────────────────────────────────────────────
# Los tokens de Meta (página y usuario) vivían en texto plano en Supabase.
# Quien leyera esa tabla —un respaldo filtrado, una service_role key expuesta,
# un empleado con acceso a la consola— podía publicar y GASTAR en nombre del
# agente. Ahora se guardan cifrados con Fernet (AES-128-CBC + HMAC).
#
# Compatibilidad: los valores viejos siguen en claro y se leen igual. Se
# vuelven a escribir cifrados en cuanto la fila se actualiza, o de un jalón con
# POST /facebook/encrypt-tokens.
#
# Sin TOKEN_ENC_KEY configurada todo sigue funcionando en claro (y se avisa una
# vez en el log). Generar una llave:
#     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

_PREFIJO_CIFRADO = "enc:v1:"
_TOKEN_ENC_KEY = legacy_main_settings.token_enc_key
_fermet_aviso_dado = False

try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET = Fernet(_TOKEN_ENC_KEY.encode()) if _TOKEN_ENC_KEY else None
except Exception as _e:
    _FERNET = None
    InvalidToken = Exception  # type: ignore
    if _TOKEN_ENC_KEY:
        logging.getLogger("broquer.facebook").error(
            "TOKEN_ENC_KEY inválida (%s). Los tokens seguirán en texto plano. "
            "Genera una con: python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"", _e)


def cifrar_secreto(valor: str) -> str:
    """Cifra un token. Si no hay llave configurada, lo devuelve tal cual."""
    global _fermet_aviso_dado
    if not valor:
        return valor
    if valor.startswith(_PREFIJO_CIFRADO):
        return valor                      # ya venía cifrado
    if not _FERNET:
        if not _fermet_aviso_dado:
            _fb_log.warning("TOKEN_ENC_KEY no configurada: los tokens de Meta se "
                            "guardan en texto plano en Supabase.")
            _fermet_aviso_dado = True
        return valor
    try:
        return _PREFIJO_CIFRADO + _FERNET.encrypt(valor.encode("utf-8")).decode("ascii")
    except Exception as e:
        _fb_log.error("No se pudo cifrar el token: %s", e)
        return valor


def descifrar_secreto(valor: str) -> str:
    """Descifra si hace falta. Los valores en claro (de antes) pasan derecho."""
    if not valor or not isinstance(valor, str):
        return valor or ""
    if not valor.startswith(_PREFIJO_CIFRADO):
        return valor
    if not _FERNET:
        # Hay datos cifrados pero se borró la llave: eso NO se puede adivinar.
        _fb_log.error("Hay tokens cifrados en la base pero TOKEN_ENC_KEY no está "
                      "configurada. Restaura la llave o el usuario tendrá que reconectar.")
        return ""
    try:
        return _FERNET.decrypt(valor[len(_PREFIJO_CIFRADO):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        _fb_log.error("Token cifrado con OTRA llave (TOKEN_ENC_KEY cambió). "
                      "El usuario tendrá que reconectar Facebook.")
        return ""
    except Exception as e:
        _fb_log.error("No se pudo descifrar el token: %s", e)
        return ""

FB_API_VERSION = legacy_main_settings.fb_api_version
FB_GRAPH       = f"https://graph.facebook.com/{FB_API_VERSION}"

_FB_REINTENTOS  = 4
_FB_ESPERA_BASE = 1.5    # segundos; se duplica en cada reintento
_FB_ESPERA_MAX  = 30.0   # techo por espera individual

# Códigos de error de Meta que significan "vuelve a intentar", NO "estás mal".
#   1     · API Unknown (error transitorio del lado de Meta)
#   2     · API Service (servicio temporalmente caído)
#   4     · Application request limit reached (límite de la app)
#   17    · User request limit reached (límite del usuario)
#   32    · Page-level throttling
#   341   · Application limit reached (límite temporal)
#   613   · Calls to this API have exceeded the rate limit
#   80000-80006 · Rate limits por caso de uso (80004 = ads_management)
_FB_CODIGOS_REINTENTABLES = {1, 2, 4, 17, 32, 341, 613,
                             80000, 80001, 80002, 80003, 80004, 80005, 80006}

# Códigos que significan "el token murió" — reintentar no sirve de nada.
_FB_CODIGOS_TOKEN = {102, 190, 463, 467}

# Interruptor de emergencia: si el appsecret_proof rompiera algo en producción
# se apaga con FB_APPSECRET_PROOF=0 en Railway sin tocar código.
_FB_USAR_PROOF = legacy_main_settings.fb_appsecret_proof


def _fb_appsecret_proof(token: str) -> str:
    """Firma HMAC del token con el secreto de la app.

    Meta recomienda mandarla en TODA llamada server-side: si alguien roba un
    token de la base de datos, sin el app secret no puede usarlo contra la API.
    """
    if not token or not FB_APP_SECRET:
        return ""
    try:
        return hmac.new(FB_APP_SECRET.encode("utf-8"),
                        token.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    except Exception:
        return ""


def _fb_parse_error(resp: "httpx.Response | None") -> dict:
    """Extrae el objeto `error` de una respuesta de Meta. Siempre devuelve dict."""
    if resp is None:
        return {"message": "Facebook no respondió.", "code": None, "error_subcode": None}
    try:
        payload = resp.json()
    except Exception:
        return {"message": (resp.text or "")[:300], "code": None, "error_subcode": None}
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return payload["error"]
    return {}


# Errores de Meta traducidos a español de negocio. La llave es el
# error_subcode (o el code si no hay subcode) que manda Meta.
_FB_ERRORES_COMUNES = {
    1487888: "Tu cuenta publicitaria requiere un Píxel de Facebook configurado para optimizar conversiones. Contacta soporte de Broquer.",
    4834011: "La cuenta tiene 'Optimización del presupuesto de campaña' activada. Desactívala en Business Manager o crea el anuncio directamente en Ads Manager.",
    2069013: "La imagen no cumple los requisitos de Facebook (mínimo 600x600, sin texto excesivo). Usa otra imagen.",
    1815245: "Para anuncios inmobiliarios en EE.UU./Canadá, Meta exige la categoría especial 'Vivienda'. En México no aplica — verifica tu ubicación de cuenta.",
    1815111: "El público objetivo es muy pequeño. Amplía la edad, la ciudad o quita filtros.",
    368:     "Facebook bloqueó la acción por seguridad. Espera unos minutos y reintenta, o reconecta tu cuenta.",
    190:     "Tu sesión de Facebook expiró o fue revocada. Reconecta tu Facebook desde tu perfil.",
    102:     "Tu sesión de Facebook expiró. Reconecta tu Facebook desde tu perfil.",
    4:       "Facebook está limitando las peticiones de Broquer en este momento. Espera unos minutos y reintenta.",
    17:      "Facebook está limitando las peticiones de tu cuenta. Espera unos minutos y reintenta.",
    613:     "Alcanzaste el límite de peticiones de Facebook. Espera unos minutos y reintenta.",
    80004:   "Alcanzaste el límite de peticiones de la API de anuncios. Espera unos minutos y reintenta.",
}


def _fb_friendly_error(resp_text: str, prefix: str) -> str:
    """Convierte el JSON de error de Meta en un mensaje que el agente entienda.

    Recibe TEXTO (no Response) para no romper a los llamadores que ya lo usaban
    así. Si no reconoce el error, degrada al mensaje crudo recortado.
    """
    try:
        payload = json.loads(resp_text or "{}")
        err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
        sub = err.get("error_subcode") or err.get("code")
        user_title = err.get("error_user_title") or ""
        user_msg = err.get("error_user_msg") or err.get("message") or ""
        if sub in _FB_ERRORES_COMUNES:
            return f"{prefix}: {_FB_ERRORES_COMUNES[sub]}"
        if user_title or user_msg:
            return f"{prefix}: {user_title}. {user_msg}".strip(". ").strip()
        return f"{prefix}: {err.get('message') or (resp_text or '')[:300]}"
    except Exception:
        return f"{prefix}: {(resp_text or '')[:300]}"


def _fb_espera_por_uso(headers) -> float:
    """Lee X-Business-Use-Case-Usage y decide cuánto esperar.

    Meta publica ahí cuánto del presupuesto llevamos gastado (0-100) y, cuando
    ya nos bloqueó, `estimated_time_to_regain_access` EN MINUTOS. Devolver ese
    número tal cual serviría de poco (puede ser 60 min), así que lo usamos solo
    como señal: si nos bloqueó, esperamos el techo; si vamos raspando el límite,
    frenamos tantito antes de seguir.
    """
    raw = ""
    try:
        raw = headers.get("X-Business-Use-Case-Usage") or headers.get("x-business-use-case-usage") or ""
    except Exception:
        return 0.0
    if not raw:
        return 0.0
    try:
        data = json.loads(raw)
    except Exception:
        return 0.0
    peor_uso = 0
    bloqueado = False
    for entradas in (data or {}).values():
        for e in (entradas or []):
            if not isinstance(e, dict):
                continue
            for k in ("call_count", "total_cputime", "total_time"):
                try:
                    peor_uso = max(peor_uso, int(e.get(k) or 0))
                except (TypeError, ValueError):
                    pass
            try:
                if float(e.get("estimated_time_to_regain_access") or 0) > 0:
                    bloqueado = True
            except (TypeError, ValueError):
                pass
    if bloqueado:
        return _FB_ESPERA_MAX
    if peor_uso >= 95:
        return 5.0
    if peor_uso >= 80:
        return 1.0
    return 0.0


def _fb_debe_reintentar(resp: "httpx.Response") -> bool:
    """True si vale la pena repetir la llamada."""
    if resp.status_code == 429 or resp.status_code >= 500:
        return True
    if resp.status_code == 400 or resp.status_code == 403:
        # Meta manda los límites de tasa como 400/403 con un code específico.
        err = _fb_parse_error(resp)
        code = err.get("code")
        if code in _FB_CODIGOS_TOKEN:
            return False
        try:
            return int(code) in _FB_CODIGOS_REINTENTABLES
        except (TypeError, ValueError):
            return False
    return False


async def _fb_request(client: httpx.AsyncClient, method: str, path: str, *,
                      token: str = "", params: dict = None, json_body: dict = None,
                      data: dict = None, files=None,
                      timeout: float = 30.0,
                      reintentos: int = _FB_REINTENTOS,
                      espera_base: float = None,
                      espera_max: float = None) -> "httpx.Response":
    """Llamada única al Graph API de Meta, con reintentos y backoff.

    - `path` puede ser una URL completa o un nodo/arista ("act_123/campaigns").
    - Inyecta access_token y appsecret_proof automáticamente.
    - Reintenta en 429, 5xx y los códigos de límite de Meta (4/17/32/613/80004…),
      respetando Retry-After y X-Business-Use-Case-Usage.
    - NUNCA lanza por status: devuelve la Response para que el llamador decida.
      Si la red falló en todos los intentos, devuelve la última Response o None.
    """
    url = path if path.startswith("http") else f"{FB_GRAPH}/{path.lstrip('/')}"
    base = _FB_ESPERA_BASE if espera_base is None else espera_base
    techo = _FB_ESPERA_MAX if espera_max is None else espera_max
    p = dict(params or {})
    if token:
        p.setdefault("access_token", token)
    proof = _fb_appsecret_proof(p.get("access_token", ""))
    if proof and _FB_USAR_PROOF:
        p.setdefault("appsecret_proof", proof)

    ultimo = None
    for intento in range(max(1, reintentos)):
        try:
            r = await client.request(method.upper(), url, params=p, json=json_body,
                                     data=data, files=files, timeout=timeout)
            ultimo = r

            # El app secret proof puede fallar si la app cambió de secreto.
            # Antes que dejar al usuario tirado, reintentamos una vez sin él.
            if (r.status_code in (400, 403) and "appsecret_proof" in p
                    and "appsecret_proof" in (r.text or "")):
                _fb_log.warning("appsecret_proof rechazado por Meta; reintento sin él")
                p.pop("appsecret_proof", None)
                continue

            if not _fb_debe_reintentar(r) or intento == reintentos - 1:
                return r

            try:
                espera = float(r.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                espera = 0.0
            espera = max(espera, _fb_espera_por_uso(r.headers))
            if espera <= 0:
                espera = base * (2 ** intento)
            espera = min(espera, techo)
            _fb_log.warning("Meta %s %s → %s; reintento %s/%s en %.1fs",
                            method.upper(), url.split("?")[0], r.status_code,
                            intento + 1, reintentos, espera)
            await asyncio.sleep(espera)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            _fb_log.warning("Fallo de red hablando con Meta (%s); intento %s/%s: %s",
                            url.split("?")[0], intento + 1, reintentos, e)
            ultimo = None
            if intento == reintentos - 1:
                break
            await asyncio.sleep(min(base * (2 ** intento), techo))
    return ultimo


def _fb_exigir_ok(resp: "httpx.Response | None", prefix: str,
                  status_code: int = 502) -> dict:
    """Devuelve el JSON de una respuesta de Meta, o lanza HTTPException legible."""
    if resp is None:
        raise HTTPException(status_code=504,
                            detail=f"{prefix}: Facebook no respondió después de varios intentos.")
    if resp.status_code not in (200, 201, 204):
        err = _fb_parse_error(resp)
        code = err.get("code")
        # Token muerto → 401 para que el frontend mande a reconectar.
        sc = 401 if code in _FB_CODIGOS_TOKEN else status_code
        raise HTTPException(status_code=sc, detail=_fb_friendly_error(resp.text, prefix))
    try:
        return resp.json() or {}
    except Exception:
        return {}


async def _fb_get_json(client: httpx.AsyncClient, path: str, *, token: str,
                       params: dict = None, prefix: str = "Error de Facebook",
                       timeout: float = 30.0) -> dict:
    """GET + validación en una línea. Lanza HTTPException si Meta falla."""
    r = await _fb_request(client, "GET", path, token=token, params=params, timeout=timeout)
    return _fb_exigir_ok(r, prefix)


async def _fb_paginate(client: httpx.AsyncClient, path: str, *, token: str,
                       params: dict = None, max_paginas: int = 10,
                       max_items: int = 500, prefix: str = "Error de Facebook",
                       timeout: float = 30.0, espera_base: float = None,
                       espera_max: float = None) -> list:
    """Recorre `paging.next` y devuelve TODOS los elementos de una arista.

    Sin esto, un `limit=20` cortaba la lista en silencio y el agente creía que
    solo tenía 20 campañas. Los topes evitan que una cuenta enorme cuelgue la
    petición: si se alcanzan, se devuelve lo que se alcanzó a leer.
    """
    items: list = []
    afinado = {"espera_base": espera_base, "espera_max": espera_max}
    r = await _fb_request(client, "GET", path, token=token, params=params,
                          timeout=timeout, **afinado)
    data = _fb_exigir_ok(r, prefix)
    items.extend(data.get("data") or [])
    paginas = 1
    while paginas < max_paginas and len(items) < max_items:
        siguiente = ((data.get("paging") or {}).get("next")) or ""
        if not siguiente:
            break
        # La URL `next` ya trae token, cursor y appsecret_proof: se usa tal cual.
        r = await _fb_request(client, "GET", siguiente, timeout=timeout, **afinado)
        if r is None or r.status_code != 200:
            break
        try:
            data = r.json() or {}
        except Exception:
            break
        nuevos = data.get("data") or []
        if not nuevos:
            break
        items.extend(nuevos)
        paginas += 1
    return items[:max_items]


# ─── Tokens: vida, permisos y avisos de expiración ────────────────────────────

# Los tokens de larga duración de Meta duran ~60 días. Cuando Meta no manda
# expires_in (tokens de página, que no expiran solos), asumimos este valor para
# poder avisar de todas formas.
_FB_TOKEN_VIDA_DEFECTO = 60 * 24 * 3600  # 60 días en segundos

# Días antes de la expiración en que empezamos a avisar en la UI.
_FB_AVISO_DIAS = 14

# Permisos sin los cuales el módulo de anuncios no puede funcionar.
_FB_SCOPES_REQUERIDOS = [
    "ads_management",        # crear/leer/pausar campañas
    "pages_show_list",       # ver las páginas del usuario
    "pages_read_engagement", # leer publicaciones para promocionarlas
    "leads_retrieval",       # bajar los leads de los Lead Ads
]


async def _fb_debug_token(client: httpx.AsyncClient, token: str) -> dict:
    """Pregunta a Meta qué es realmente este token (tipo, permisos, expiración).

    Usa el app token (`APP_ID|APP_SECRET`) como credencial, que es lo que exige
    /debug_token. Nunca lanza: si falla, devuelve {} y el llamador decide.
    """
    if not token or not FB_APP_ID or not FB_APP_SECRET:
        return {}
    try:
        r = await _fb_request(client, "GET", "debug_token",
                              params={"input_token": token,
                                      "access_token": f"{FB_APP_ID}|{FB_APP_SECRET}"},
                              reintentos=2)
        if r is None or r.status_code != 200:
            return {}
        return (r.json() or {}).get("data") or {}
    except Exception:
        return {}


def _fb_estado_token(meta: dict) -> dict:
    """Traduce token_expires_at a algo que la UI pueda enseñar.

    Devuelve dict con días restantes, si urge reconectar y un mensaje listo.
    Si no hay fecha guardada (conexiones viejas, de antes de este cambio) se
    devuelve `desconocido` en vez de inventar un estado sano.
    """
    raw = (meta or {}).get("token_expires_at") or ""
    if not raw:
        return {"conocido": False, "dias_restantes": None, "expirado": False,
                "por_expirar": False, "mensaje": ""}
    try:
        venc = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if venc.tzinfo is None:
            venc = venc.replace(tzinfo=timezone.utc)
    except Exception:
        return {"conocido": False, "dias_restantes": None, "expirado": False,
                "por_expirar": False, "mensaje": ""}

    dias = (venc - datetime.now(timezone.utc)).total_seconds() / 86400.0
    # Se redondea hacia arriba: a 4.9 días le quedan "5 días", no "4".
    # Decirle a alguien que le quedan menos días de los que tiene no ayuda.
    dias_int = int(-(-dias // 1)) if dias > 0 else int(dias // 1)
    if dias <= 0:
        msg = ("Tu conexión con Facebook expiró. Reconéctala desde tu perfil o "
               "tus anuncios dejarán de actualizarse.")
    elif dias <= _FB_AVISO_DIAS:
        msg = (f"Tu conexión con Facebook expira en {max(dias_int, 1)} día(s). "
               f"Reconéctala desde tu perfil para no perder tus campañas de vista.")
    else:
        msg = ""
    return {
        "conocido": True,
        "expira_en": venc.isoformat(),
        "dias_restantes": dias_int,
        "expirado": dias <= 0,
        "por_expirar": 0 < dias <= _FB_AVISO_DIAS,
        "mensaje": msg,
    }


async def _fb_batch(client: httpx.AsyncClient, token: str, peticiones: list,
                    timeout: float = 60.0, espera_base: float = None,
                    espera_max: float = None) -> list:
    """Ejecuta hasta 50 llamadas al Graph en UNA sola petición HTTP.

    `peticiones` = [{"method": "POST", "relative_url": "123", "body": "status=PAUSED"}, …]
    Devuelve una lista paralela de {"code": int, "body": dict|str} — un elemento
    por petición, en el mismo orden. Si el batch entero falla, devuelve
    elementos con code=0 para que el llamador reporte fallo parcial honesto.
    """
    salida: list = []
    for i in range(0, len(peticiones), 50):
        lote = peticiones[i:i + 50]
        r = await _fb_request(client, "POST", "", token=token,
                              data={"batch": json.dumps(lote),
                                    "include_headers": "false"},
                              timeout=timeout, espera_base=espera_base,
                              espera_max=espera_max)
        if r is None or r.status_code != 200:
            detalle = _fb_friendly_error(r.text if r is not None else "", "Batch")
            salida.extend([{"code": 0, "body": detalle} for _ in lote])
            continue
        try:
            resultados = r.json()
        except Exception:
            salida.extend([{"code": 0, "body": "Respuesta ilegible de Facebook"} for _ in lote])
            continue
        if not isinstance(resultados, list):
            salida.extend([{"code": 0, "body": "Respuesta inesperada de Facebook"} for _ in lote])
            continue
        for res in resultados:
            if not isinstance(res, dict):
                salida.append({"code": 0, "body": "Elemento inesperado"})
                continue
            cuerpo = res.get("body")
            try:
                cuerpo = json.loads(cuerpo) if isinstance(cuerpo, str) else cuerpo
            except Exception:
                pass
            salida.append({"code": int(res.get("code") or 0), "body": cuerpo})
    return salida


# ════════════════════════════════════════════════════════════════
# META — memoria de lo que Broquer creó (tabla fb_ad_entities)
# ════════════════════════════════════════════════════════════════
# Antes, crear un anuncio era una operación sin memoria: si el flujo se rompía
# a la mitad, los IDs se perdían y los recursos quedaban huérfanos en la cuenta
# publicitaria sin que nadie supiera que existían. Y un doble clic creaba dos
# campañas cobrando en paralelo.
#
# Todo esto degrada con elegancia: si la tabla no existe todavía (migración sin
# correr), se registra un aviso en el log y el anuncio se crea igual. Perder la
# bitácora no puede ser motivo para no poder anunciar.

_FB_TABLA_ENTIDADES = "fb_ad_entities"
_fb_aviso_tabla_dado = False


def _sb_headers(extra: dict = None) -> dict:
    h = {"apikey": SUPABASE_SERVICE_KEY,
         "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _fb_tabla_falta(resp) -> bool:
    """True si Supabase contesta 'esa tabla no existe' (migración pendiente)."""
    if resp is None:
        return False
    if resp.status_code not in (404, 400):
        return False
    texto = (resp.text or "").lower()
    return ("does not exist" in texto or "could not find the table" in texto
            or "pgrst205" in texto)


def _fb_avisa_migracion(donde: str, resp=None) -> None:
    global _fb_aviso_tabla_dado
    if not _fb_aviso_tabla_dado:
        _fb_log.warning(
            "La tabla %s no existe (en %s). Corre migracion-facebook-ads.sql en "
            "Supabase para habilitar idempotencia, reconciliación y limpieza de "
            "huérfanos. Los anuncios se siguen creando sin ella.",
            _FB_TABLA_ENTIDADES, donde)
        _fb_aviso_tabla_dado = True


async def _fb_reservar_creacion(user_id: str, org_id, datos: dict,
                                idempotency_key: str = "") -> dict:
    """Aparta el lugar ANTES de tocar Meta.

    Devuelve:
      {"modo": "nuevo",      "row_id": …}  → sigue adelante
      {"modo": "duplicado",  "row": {…}}   → ya existía: devuelve lo de antes
      {"modo": "sin_tabla"}                → migración pendiente, sigue sin memoria

    El INSERT con la llave de idempotencia es lo que hace el trabajo: si dos
    peticiones llegan a la vez, el índice único deja pasar una sola.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"modo": "sin_tabla"}

    fila = {
        "id": str(_uuid.uuid4()),
        "user_id": user_id,
        "org_id": org_id,
        "status": "CREANDO",
        **datos,
    }
    if idempotency_key:
        fila["idempotency_key"] = idempotency_key

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}",
                headers=_sb_headers({"Prefer": "return=representation"}),
                json=fila,
            )
        if r.status_code in (200, 201):
            filas = r.json() if r.text else []
            return {"modo": "nuevo", "row_id": (filas[0]["id"] if filas else fila["id"])}

        if _fb_tabla_falta(r):
            _fb_avisa_migracion("reservar creación", r)
            return {"modo": "sin_tabla"}

        # 409 = chocó con el índice único → ya hay una creación con esa llave.
        if r.status_code == 409 and idempotency_key:
            previa = await _fb_buscar_por_idempotencia(user_id, idempotency_key)
            if previa:
                return {"modo": "duplicado", "row": previa}

        _fb_log.error("No se pudo registrar la creación en %s: %s %s",
                      _FB_TABLA_ENTIDADES, r.status_code, (r.text or "")[:300])
    except Exception as e:
        _fb_log.error("Error registrando la creación en %s: %s", _FB_TABLA_ENTIDADES, e)
    return {"modo": "sin_tabla"}


async def _fb_buscar_por_idempotencia(user_id: str, idempotency_key: str) -> dict:
    """Devuelve la creación previa con esa llave, o {}."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not idempotency_key:
        return {}
    try:
        try:
            filas = await get_rows(
                _FB_TABLA_ENTIDADES,
                {"user_id": f"eq.{user_id}",
                 "idempotency_key": f"eq.{idempotency_key}",
                 "limit": "1"},
                timeout=10,
            )
        except httpx.HTTPStatusError as e:
            if _fb_tabla_falta(e.response):
                _fb_avisa_migracion("buscar idempotencia", e.response)
            return {}
        if filas:
            return filas[0]
    except Exception as e:
        _fb_log.error("Error buscando idempotencia: %s", e)
    return {}


async def _fb_actualizar_entidad(row_id: str, updates: dict) -> None:
    """Anota el resultado de la creación. Nunca lanza: es bitácora, no el trabajo."""
    if not row_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        try:
            await patch_rows(
                _FB_TABLA_ENTIDADES,
                {"id": f"eq.{row_id}"},
                {**updates, "updated_at": datetime.now(timezone.utc).isoformat()},
                timeout=10,
            )
        except httpx.HTTPStatusError as e:
            if _fb_tabla_falta(e.response):
                _fb_avisa_migracion("actualizar entidad", e.response)
            else:
                _fb_log.error("No se pudo actualizar %s: %s %s",
                              _FB_TABLA_ENTIDADES, e.response.status_code,
                              (e.response.text or "")[:300])
    except Exception as e:
        _fb_log.error("Error actualizando %s: %s", _FB_TABLA_ENTIDADES, e)


# ─── FACEBOOK OAUTH ───────────────────────────────────────────────────────────

# ────────────────────────────────────────────
# FACEBOOK — guardar / leer conexión por usuario
# ────────────────────────────────────────────
class FbSavePageRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    user_token: str = ""  # token de usuario (larga duración) — requerido para Ads API
    token_expires_at: str = ""  # ISO-8601; lo calcula /facebook/callback

@app.post("/facebook/save-page")
async def facebook_save_page(req: FbSavePageRequest, request: Request):
    """Guarda el page_token, user_token y AUTO-SELECCIONA la cuenta publicitaria
    asociada a la página (la primera cuenta activa autorizada para anunciar
    esa página). Esto elimina el riesgo de publicar en una cuenta equivocada.

    La página de Facebook es de la EMPRESA: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no configurado")

    # ── Verificar el token antes de guardarlo ──────────────────────────
    # Si el frontend no mandó la fecha de expiración (o mandó basura), se la
    # preguntamos a Meta. Guardar un token sin saber cuándo muere es lo que
    # hacía que el módulo se apagara solo sin aviso.
    token_expires_at = (req.token_expires_at or "").strip()
    scopes: list = []
    if req.user_token:
        try:
            async with httpx.AsyncClient(timeout=10) as client_t:
                info = await _fb_debug_token(client_t, req.user_token)
            scopes = info.get("scopes") or []
            expira_ts = info.get("expires_at")
            if not token_expires_at and expira_ts:
                token_expires_at = datetime.fromtimestamp(int(expira_ts), timezone.utc).isoformat()
            elif not token_expires_at and info.get("data_access_expires_at"):
                token_expires_at = datetime.fromtimestamp(
                    int(info["data_access_expires_at"]), timezone.utc).isoformat()
        except Exception:
            pass
    if not token_expires_at:
        token_expires_at = (datetime.now(timezone.utc)
                            + timedelta(seconds=_FB_TOKEN_VIDA_DEFECTO)).isoformat()

    # ── Auto-seleccionar cuenta publicitaria compatible con la página ──
    ad_account_id = ""
    ad_account_name = ""
    page_pic = ""
    try:
        async with httpx.AsyncClient(timeout=15) as client_a:
            # 1) Foto de la página (mejora UI)
            try:
                rpic = await _fb_request(client_a, "GET", req.page_id,
                                         token=req.user_token,
                                         params={"fields": "picture.type(square)"})
                if rpic is not None and rpic.status_code == 200:
                    page_pic = ((rpic.json().get("picture") or {}).get("data") or {}).get("url", "")
            except Exception:
                page_pic = ""

            # 2) Cuentas publicitarias del usuario (todas: sin paginar, una
            #    empresa con >50 cuentas perdía las de la cola)
            cuentas_raw = await _fb_paginate(
                client_a, "me/adaccounts", token=req.user_token,
                params={"fields": "id,name,account_status,currency", "limit": "50"},
                prefix="Error leyendo cuentas publicitarias",
            )
            accounts = [a for a in cuentas_raw if a.get("account_status") == 1]

            # 3) Para cada cuenta, ver si puede anunciar nuestra página
            chosen = None
            for a in accounts:
                try:
                    pids = await _fb_paginate(
                        client_a, f"{a['id']}/promote_pages", token=req.user_token,
                        params={"fields": "id", "limit": "100"},
                        prefix="Error leyendo páginas promocionables",
                    )
                    if req.page_id in [p.get("id") for p in pids if p.get("id")]:
                        chosen = a
                        break
                except Exception:
                    continue
            # Fallback: si ninguna está autorizada explícitamente, usar la primera activa
            if not chosen and accounts:
                chosen = accounts[0]
            if chosen:
                ad_account_id = chosen.get("id", "")
                ad_account_name = chosen.get("name", ad_account_id)
    except Exception:
        # No bloquear el guardado de página si hubo error obteniendo cuenta
        pass

    meta = {
        "page_id": req.page_id,
        "page_name": req.page_name,
        "page_pic": page_pic,
        "user_token": cifrar_secreto(req.user_token),
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
        "token_expires_at": token_expires_at,
        "scopes": scopes,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": cifrar_secreto(req.page_token),
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat()
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: Supabase HTTP rejections did not fail save-page.
        pass
    return {
        "ok": True,
        "page_id": req.page_id,
        "page_name": req.page_name,
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
        "token_expires_at": token_expires_at,
        "scopes_faltantes": [s for s in _FB_SCOPES_REQUERIDOS if s not in scopes] if scopes else [],
    }

@app.get("/facebook/connection")
async def facebook_get_connection(request: Request):
    """Devuelve si el usuario tiene Facebook conectado y el nombre de la página."""
    user_id = await get_user_id_from_token(request)
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"connected": False}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=8,
        )
        if rows and rows[0].get("api_key"):
            meta_str = rows[0].get("meta", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}
            estado_token = _fb_estado_token(meta)
            return {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "page_pic": meta.get("page_pic", ""),
                # Los tokens YA NO viajan al navegador. El frontend solo
                # los usaba para saber si existían; mandarlos era regalar
                # permiso de gastar a cualquier extensión o XSS que
                # leyera la respuesta. El backend los saca de Supabase
                # cuando los necesita.
                "tiene_token_ads": bool(meta.get("user_token")),
                "ad_account_id": meta.get("ad_account_id", ""),
                "ad_account_name": meta.get("ad_account_name", ""),
                # Estado del token: la UI avisa ANTES de que expire, en
                # vez de que el agente descubra el corte cuando ya no
                # puede pausar una campaña que está gastando.
                "token": estado_token,
                "scopes_faltantes": [s for s in _FB_SCOPES_REQUERIDOS
                                     if s not in (meta.get("scopes") or [])]
                                    if meta.get("scopes") else [],
            }
    except Exception:
        pass
    return {"connected": False}


async def _fb_get_meta_row(user_id: str) -> dict:
    """Devuelve la fila completa (api_key + meta dict) del usuario, o {}."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: an HTTP rejection meant "no row"; transport
        # failures still propagate to callers.
        return {}
    if not rows:
        return {}
    row = rows[0]
    meta_raw = row.get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}
    # Los tokens salen ya descifrados: quien llame a este helper no tiene por
    # qué saber si están cifrados en reposo o no.
    if meta.get("user_token"):
        meta["user_token"] = descifrar_secreto(meta["user_token"])
    return {"page_token": descifrar_secreto(row.get("api_key", "")), "meta": meta}


async def _fb_patch_meta(user_id: str, updates: dict, new_page_token: str | None = None) -> None:
    """Actualiza la fila de Facebook del usuario fusionando 'updates' en meta.

    Al reescribir, los tokens quedan cifrados aunque hubieran entrado en claro:
    así las conexiones viejas se van migrando solas con el uso normal.
    """
    cur = await _fb_get_meta_row(user_id)
    meta = cur.get("meta") or {}
    meta.update(updates)
    if meta.get("user_token"):
        meta["user_token"] = cifrar_secreto(meta["user_token"])
    page_token = new_page_token if new_page_token is not None else cur.get("page_token", "")
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": cifrar_secreto(page_token),
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: HTTP rejection was ignored; transport failures
        # still propagate.
        pass


@app.get("/facebook/pages")
async def facebook_list_pages(request: Request):
    """Lista TODAS las páginas que el usuario administra (sin reconectar FB)."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    row = await _fb_get_meta_row(user_id)
    user_token = (row.get("meta") or {}).get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook para habilitar el cambio de página.")
    async with httpx.AsyncClient(timeout=15) as client:
        data = await _fb_paginate(
            client, "me/accounts", token=user_token,
            params={"fields": "id,name,access_token,picture.type(square)", "limit": "100"},
            prefix="Error leyendo tus páginas",
        )
    pages = [{
        "id": p.get("id", ""),
        "name": p.get("name", p.get("id", "")),
        "picture": ((p.get("picture") or {}).get("data") or {}).get("url", ""),
    } for p in data if p.get("id")]
    active_id = (row.get("meta") or {}).get("page_id", "")
    return {"pages": pages, "active_page_id": active_id}


class FbSelectPageRequest(BaseModel):
    page_id: str

@app.post("/facebook/select-page")
async def facebook_select_page(req: FbSelectPageRequest, request: Request):
    """Cambia la página activa de la empresa (sin re-OAuth)."""
    user_id = await exigir_gestion_integraciones(request)
    row = await _fb_get_meta_row(user_id)
    user_token = (row.get("meta") or {}).get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    # Buscar la página en /me/accounts para obtener su page_token específico
    async with httpx.AsyncClient(timeout=10) as client:
        paginas = await _fb_paginate(
            client, "me/accounts", token=user_token,
            params={"fields": "id,name,access_token", "limit": "100"},
            prefix="Error leyendo tus páginas",
        )
    target = next((p for p in paginas if p.get("id") == req.page_id), None)
    if not target:
        raise HTTPException(status_code=400, detail="No administras esa página o ya no es accesible.")
    page_token = target.get("access_token", "")
    page_name = target.get("name", req.page_id)
    await _fb_patch_meta(user_id, {"page_id": req.page_id, "page_name": page_name},
                        new_page_token=page_token)
    return {"ok": True, "page_id": req.page_id, "page_name": page_name}


class FbSelectAdAccountRequest(BaseModel):
    account_id: str
    account_name: str = ""

@app.post("/facebook/select-ad-account")
async def facebook_select_ad_account(req: FbSelectAdAccountRequest, request: Request):
    """Recuerda la última cuenta publicitaria elegida.
    Toca dónde se cobran los anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    await _fb_patch_meta(user_id, {
        "ad_account_id": req.account_id,
        "ad_account_name": req.account_name or req.account_id,
    })
    return {"ok": True, "account_id": req.account_id}

@app.post("/facebook/encrypt-tokens")
async def facebook_encrypt_tokens(request: Request):
    """Cifra los tokens que quedaron en texto plano de antes de este cambio.

    Es idempotente: correrlo dos veces no hace daño. Cada dueño lo corre para
    su propia conexión; no toca la de nadie más.
    """
    user_id = await exigir_gestion_integraciones(request)
    if not _FERNET:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar TOKEN_ENC_KEY en el servidor. Genera una con: "
                   "python3 -c \"from cryptography.fernet import Fernet; "
                   "print(Fernet.generate_key().decode())\"")
    fila = await _fb_get_meta_row(user_id)
    if not fila:
        raise HTTPException(status_code=400, detail="No hay conexión de Facebook.")
    # _fb_patch_meta ya cifra al reescribir; basta con forzar una reescritura.
    await _fb_patch_meta(user_id, {"tokens_cifrados_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "mensaje": "Tus tokens de Facebook quedaron cifrados en reposo."}


@app.post("/facebook/refresh-token")
async def facebook_refresh_token(request: Request):
    """Renueva el token de larga duración sin volver a pasar por el OAuth.

    Meta deja re-intercambiar un token de larga duración por otro nuevo con el
    mismo `fb_exchange_token`, siempre que el actual siga vivo. La UI llama a
    esto sola cuando faltan pocos días para que expire, así el agente nunca ve
    el módulo apagado. Si el token ya murió, no hay nada que renovar y hay que
    reconectar de verdad — eso se dice claro, no se disfraza.
    """
    user_id = await exigir_gestion_integraciones(request)
    if not FB_APP_ID or not FB_APP_SECRET:
        raise HTTPException(status_code=500, detail="FB_APP_ID o FB_APP_SECRET no configurados.")
    row = await _fb_get_meta_row(user_id)
    meta = row.get("meta") or {}
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="No hay conexión de Facebook que renovar.")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await _fb_request(
            client, "GET", "oauth/access_token",
            params={"grant_type": "fb_exchange_token",
                    "client_id": FB_APP_ID,
                    "client_secret": FB_APP_SECRET,
                    "fb_exchange_token": user_token},
        )
        if r is None or r.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=_fb_friendly_error(
                    r.text if r is not None else "",
                    "No se pudo renovar la conexión con Facebook. Reconéctala desde tu perfil"),
            )
        datos = r.json() or {}
        nuevo = datos.get("access_token", "")
        if not nuevo:
            raise HTTPException(status_code=502,
                                detail="Facebook no devolvió un token nuevo. Reconecta desde tu perfil.")
        try:
            expires_in = int(datos.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        info = await _fb_debug_token(client, nuevo)

    vence = (datetime.now(timezone.utc)
             + timedelta(seconds=expires_in or _FB_TOKEN_VIDA_DEFECTO)).isoformat()
    await _fb_patch_meta(user_id, {
        "user_token": nuevo,
        "token_expires_at": vence,
        "scopes": info.get("scopes") or meta.get("scopes") or [],
        "token_refreshed_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "token_expires_at": vence,
            "dias_restantes": int((expires_in or _FB_TOKEN_VIDA_DEFECTO) / 86400)}


@app.delete("/facebook/connection")
async def facebook_disconnect(request: Request):
    """Elimina la conexión de Facebook de la EMPRESA en Supabase.
    Deja al equipo entero sin anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        await delete_rows(
            "user_integrations",
            {"user_id": f"eq.{user_id}", "provider": "eq.facebook"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: HTTP rejection was ignored; transport failures
        # still propagate.
        pass
    return {"ok": True}


@app.post("/facebook/publish-property")
async def facebook_publish_property(request: Request):
    """Publica una propiedad en Facebook usando el token guardado del usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    body = await request.json()
    titulo = body.get("titulo", "Nueva propiedad")
    precio = body.get("precio", "")
    tipo = body.get("tipo", "Inmueble")
    operacion = body.get("operacion", "venta")
    colonia = body.get("colonia", "")
    ciudad = body.get("ciudad", "")
    m2 = body.get("m2_construccion", "")
    recamaras = body.get("recamaras", "")
    fotos = body.get("fotos", [])
    descripcion = body.get("descripcion", "")

    # Obtener conexión de Facebook del usuario. El page_token se saca de la
    # fila directa (_fb_get_meta_row), no de /facebook/connection: ese endpoint
    # ya no devuelve tokens porque su respuesta viaja al navegador.
    fila = await _fb_get_meta_row(user_id)
    meta_fb = fila.get("meta") or {}
    page_id = meta_fb.get("page_id", "")
    page_token = fila.get("page_token", "")
    if not page_id or not page_token:
        raise HTTPException(status_code=400, detail="Facebook no conectado. Ve a tu perfil para conectar tu página.")
    fb = {"page_name": meta_fb.get("page_name", "")}

    # Construir mensaje
    precio_fmt = f"${int(precio):,}" if precio else ""
    ubicacion = ", ".join(filter(None, [colonia, ciudad]))
    specs = []
    if m2: specs.append(f"🏠 {m2} m²")
    if recamaras: specs.append(f"🛏️ {recamaras} rec.")
    specs_str = " · ".join(specs)

    mensaje_lines = [
        f"{'🏠' if operacion == 'venta' else '🔑'} {tipo} en {operacion.upper()} — {titulo}",
        "",
    ]
    if ubicacion: mensaje_lines.append(f"📍 {ubicacion}")
    if precio_fmt: mensaje_lines.append(f"💰 {precio_fmt} MXN")
    if specs_str: mensaje_lines.append(specs_str)
    if descripcion: mensaje_lines.extend(["", descripcion[:200]])
    mensaje_lines.extend(["", "✅ Publicado con Broquer"])
    mensaje = "\n".join(mensaje_lines)

    # Publicar en Facebook
    async with httpx.AsyncClient(timeout=30) as client:
        photo_ids = []
        for url in (fotos or [])[:5]:
            try:
                r = await _fb_request(client, "POST", f"{page_id}/photos",
                                      token=page_token,
                                      json_body={"url": url, "published": False})
                if r is not None and r.status_code in (200, 201):
                    pid = r.json().get("id")
                    if pid: photo_ids.append({"media_fbid": pid})
            except Exception:
                pass

        payload: dict = {"message": mensaje}
        if photo_ids:
            payload["attached_media"] = photo_ids

        r_post = await _fb_request(client, "POST", f"{page_id}/feed",
                                   token=page_token, json_body=payload)

    datos = _fb_exigir_ok(r_post, "Error publicando en Facebook")
    return {"ok": True, "post_id": datos.get("id"), "page_name": fb.get("page_name", "")}


@app.get("/facebook/callback")
async def facebook_callback(code: str = Query(...), state: str = Query(None), redirect_uri: str = Query(None)):
    """Intercambia el code de OAuth por un token de página de Facebook.

    Regla dura: si NO se consigue un token de larga duración, esto falla con
    error HTTP y no devuelve nada guardable. Antes, cuando fb_exchange_token
    fallaba, se caía al token corto (≈1 hora), el frontend lo guardaba tan
    contento y los anuncios dejaban de funcionar esa misma tarde sin que nadie
    entendiera por qué. Un error ruidoso hoy vale más que un módulo muerto mañana.
    """
    if not FB_APP_ID or not FB_APP_SECRET:
        raise HTTPException(status_code=500,
                            detail="FB_APP_ID o FB_APP_SECRET no configurados en el servidor.")
    redirect_uri = redirect_uri or (FRONTEND_URL + "/facebook/callback")
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Token de usuario (corta duración)
        r = await _fb_request(
            client, "GET", "oauth/access_token",
            params={
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_token = _fb_exigir_ok(r, "No se pudo completar la conexión con Facebook",
                                    status_code=400).get("access_token", "")
        if not short_token:
            raise HTTPException(status_code=502,
                                detail="Facebook no devolvió un token de acceso. Intenta conectar de nuevo.")

        # 2. Token de larga duración (≈60 días). Obligatorio.
        r2 = await _fb_request(
            client, "GET", "oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "fb_exchange_token": short_token,
            },
        )
        if r2 is None or r2.status_code != 200:
            _fb_log.error("fb_exchange_token falló: %s",
                          (r2.text if r2 is not None else "sin respuesta")[:400])
            raise HTTPException(
                status_code=502,
                detail=_fb_friendly_error(
                    r2.text if r2 is not None else "",
                    "Facebook no entregó un token de larga duración, así que no se guardó "
                    "la conexión (con el token corto los anuncios dejarían de funcionar en "
                    "una hora). Intenta conectar de nuevo"),
            )
        datos_token = r2.json() or {}
        long_token = datos_token.get("access_token", "")
        if not long_token:
            raise HTTPException(status_code=502,
                                detail="Facebook no devolvió el token de larga duración. Intenta conectar de nuevo.")

        # expires_in viene en segundos. Si Meta no lo manda, el token es de los
        # que no expiran solos — se asume el estándar de 60 días para poder
        # avisar a tiempo de todos modos.
        try:
            expires_in = int(datos_token.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        token_expires_at = (datetime.now(timezone.utc)
                            + timedelta(seconds=expires_in or _FB_TOKEN_VIDA_DEFECTO)).isoformat()

        # 3. Verificar el token contra /debug_token: es la única forma de saber
        #    de verdad si quedó de larga duración y con qué permisos.
        info_token = await _fb_debug_token(client, long_token)
        faltantes = [s for s in _FB_SCOPES_REQUERIDOS if s not in (info_token.get("scopes") or [])]

        # 4. Lista de páginas administradas
        paginas = await _fb_paginate(client, "me/accounts", token=long_token,
                                     params={"fields": "id,name,access_token", "limit": "100"},
                                     prefix="Error leyendo tus páginas")

    if not paginas:
        raise HTTPException(
            status_code=400,
            detail="No se encontraron páginas administradas en esta cuenta de Facebook. "
                   "Crea o pide acceso a una página antes de conectar.")

    # Usar la primera página
    page = paginas[0]

    # Devolver datos para que el frontend los guarde en Supabase
    # user_token (long_token) se necesita para la Ads API — distinto al page_token
    return {
        "ok": True,
        "page_id": page.get("id", ""),
        "page_name": page.get("name", ""),
        "page_token": page.get("access_token", ""),
        "user_token": long_token,
        "token_expires_at": token_expires_at,
        "token_expires_in": expires_in,
        "scopes": info_token.get("scopes") or [],
        "scopes_faltantes": faltantes,
        "pages": [{"id": p.get("id"), "name": p.get("name"), "access_token": p.get("access_token")}
                  for p in paginas],
    }


class FbPublishRequest(BaseModel):
    page_id: str
    page_token: str
    message: str
    photo_urls: list[str] = []

@app.post("/facebook/publish")
async def facebook_publish(req: FbPublishRequest):
    """Publica una propiedad en la página de Facebook."""
    photo_ids = []
    async with httpx.AsyncClient(timeout=30) as client:
        # Subir fotos como no publicadas
        for url in req.photo_urls[:10]:
            r = await _fb_request(client, "POST", f"{req.page_id}/photos",
                                  token=req.page_token,
                                  json_body={"url": url, "published": False})
            if r is not None and r.status_code in (200, 201):
                pid = r.json().get("id")
                if pid:
                    photo_ids.append({"media_fbid": pid})

        # Crear el post. (Este endpoint iba en v18.0 mientras el resto del
        # módulo ya usaba v21.0; ahora la versión sale de FB_API_VERSION.)
        payload: dict = {"message": req.message}
        if photo_ids:
            payload["attached_media"] = photo_ids

        r_post = await _fb_request(client, "POST", f"{req.page_id}/feed",
                                   token=req.page_token, json_body=payload)

    datos = _fb_exigir_ok(r_post, "Error publicando en Facebook")
    return {"ok": True, "post_id": datos.get("id")}



# ─── FACEBOOK ADS ─────────────────────────────────────────────────────────────

@app.get("/facebook/ad-accounts")
async def facebook_ad_accounts(request: Request):
    """Devuelve las cuentas publicitarias accesibles por el usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    # Recuperar user_token guardado en meta. Via _get_fb_meta() para que el
    # descifrado ocurra en un solo lugar.
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Token de usuario sin permisos de ads. Reconecta tu Facebook.")

    async with httpx.AsyncClient(timeout=15) as client:
        accounts = await _fb_paginate(
            client, "me/adaccounts", token=user_token,
            params={"fields": "id,name,account_status,currency", "limit": "50"},
            prefix="Error leyendo cuentas publicitarias",
        )
    # Solo cuentas activas (account_status == 1)
    active_raw = [a for a in accounts if a.get("account_status", 0) == 1]

    # Para cada cuenta activa, traer las páginas que puede anunciar (promote_pages).
    # Esto permite al frontend auto-seleccionar la cuenta correcta para la página
    # conectada del usuario y marcar las que no pueden anunciar esa página.
    #
    # Va en UNA sola petición (batch). Antes era un loop N+1: con 30 cuentas
    # publicitarias eran 30 viajes a Meta y la pantalla tardaba una eternidad.
    paginas_por_cuenta: dict = {}
    if active_raw:
        async with httpx.AsyncClient(timeout=30) as client:
            resultados = await _fb_batch(client, user_token, [
                {"method": "GET",
                 "relative_url": f"{a['id']}/promote_pages?fields=id&limit=100"}
                for a in active_raw
            ])
            for cuenta, res in zip(active_raw, resultados):
                ids: list[str] = []
                cuerpo = res.get("body")
                if res.get("code") == 200 and isinstance(cuerpo, dict):
                    ids = [p["id"] for p in (cuerpo.get("data") or []) if p.get("id")]
                elif res.get("code") != 200:
                    _fb_log.warning("promote_pages falló para %s: %s",
                                    cuenta.get("id"), str(cuerpo)[:200])
                paginas_por_cuenta[cuenta["id"]] = ids

    active: list[dict] = []
    for a in active_raw:
        page_ids: list[str] = paginas_por_cuenta.get(a["id"], [])
        active.append({
            "id": a["id"],
            "name": a.get("name", a["id"]),
            "currency": a.get("currency", "MXN"),
            "promote_pages": page_ids,
        })
    return {"accounts": active}


class FbCreateAdRequest(BaseModel):
    account_id: str
    campaign_name: str
    ad_text: str = ""
    headline: str = ""
    # Carrusel Click-to-Messenger: hasta 10 imagenes en base64
    images_b64: list = []       # lista de strings base64 (1-10 imagenes)
    images_mime: list = []      # lista de mime types correspondientes
    daily_budget_mxn: float = 50.0
    duration_days: int = 7
    age_min: int = 18
    age_max: int = 0
    country: str = "MX"
    city: str = ""              # key de ciudad/region para geo-targeting
    city_type: str = "city"     # "city" | "region" | "neighborhood" | "subcity"
    page_id: str = ""
    objective: str = "OUTCOME_ENGAGEMENT"
    publish_now: bool = False   # si True, crea y activa; si False, queda en PAUSED
    post_id: str = ""           # si viene, promociona una publicacion existente (formato pageid_postid)
    # Llave de idempotencia del cliente: mismo valor = misma campaña. Evita que
    # un doble clic (o un reintento por red lenta) cree DOS campañas cobrando.
    idempotency_key: str = ""
    # Públicos personalizados/similares a incluir o excluir en el targeting.
    custom_audience_ids: list = []
    excluded_audience_ids: list = []


@app.post("/facebook/create-ad")
async def facebook_create_ad(req: FbCreateAdRequest, request: Request):
    """Crea una campaña de carrusel Click-to-Messenger en Facebook Ads.

    Flujo: Campaign → AdSet → AdCreative (carrusel, CTA = MESSAGE_PAGE) → Ad.
    Objetivo fijo: OUTCOME_ENGAGEMENT / CONVERSATIONS.
    No usa destination_url: el CTA abre Messenger directamente.

    Si req.publish_now=True, queda en ACTIVE; si no, en PAUSED.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    # Recuperar user_token (descifrado por el helper)
    row = await _fb_get_meta_row(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta = row.get("meta") or {}

    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Token sin permisos de ads. Reconecta tu Facebook.")

    # SEGURIDAD: ignoramos req.page_id y req.account_id si vienen del cliente.
    # Usamos SIEMPRE los guardados en server por el flujo de conexión, así no
    # hay forma de que el cliente induzca a publicar en la página equivocada
    # (bug que pasó con la versión anterior con selector dinámico).
    page_id = meta.get("page_id", "")
    if not page_id:
        raise HTTPException(status_code=400, detail="Página de Facebook no identificada. Reconecta tu Facebook desde tu perfil.")

    server_account_id = meta.get("ad_account_id", "")
    if not server_account_id:
        raise HTTPException(status_code=400, detail="Cuenta publicitaria no seleccionada. Reconecta tu Facebook desde tu perfil.")
    # Normalizar el account_id servidor y forzarlo (ignora cualquier valor del cliente)
    req.account_id = server_account_id if server_account_id.startswith("act_") else f"act_{server_account_id}"
    # Forzar la página oficial del usuario, no la del request
    req.page_id = page_id

    # Validación cruzada: la cuenta debe poder anunciar la página. Si no,
    # rechazar ANTES de crear nada para evitar el bug "publica en otra página".
    try:
        async with httpx.AsyncClient(timeout=10) as client_v:
            promote_ids = [p.get("id") for p in await _fb_paginate(
                client_v, f"{req.account_id}/promote_pages", token=user_token,
                params={"fields": "id", "limit": "100"},
                prefix="Error validando la página",
            ) if p.get("id")]
            if promote_ids and page_id not in promote_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Tu cuenta publicitaria no está autorizada para anunciar tu página de Facebook. Asocia la página a la cuenta en business.facebook.com → Configuración del negocio → Páginas → Asignar a cuenta publicitaria, y luego reconecta Facebook."
                )
    except HTTPException:
        raise
    except Exception:
        # Si Meta no responde a la verificación, dejamos pasar pero anotamos.
        pass

    # Promocionar publicación existente: validar formato pageid_postid
    if req.post_id:
        if "_" not in req.post_id:
            # Si nos pasaron solo el post id, lo concatenamos con la page
            req.post_id = f"{page_id}_{req.post_id}"

    # Carrusel Click-to-Messenger: objetivo y optimización fijos
    # CONVERSATIONS + IMPRESSIONS es el par correcto para anuncios que abren Messenger.
    optimization_goal = "CONVERSATIONS"
    billing_event = "IMPRESSIONS"

    target_status = "ACTIVE" if req.publish_now else "PAUSED"

    # Normalizar account_id (asegurar prefijo act_)
    account_id = req.account_id if req.account_id.startswith("act_") else f"act_{req.account_id}"
    # (base_url/params_base ya no hacen falta: _fb_request arma la URL con
    #  FB_API_VERSION e inyecta access_token + appsecret_proof.)

    # Presupuesto diario en centavos
    daily_budget_cents = int(req.daily_budget_mxn * 100)

    # _fb_friendly_error() vive ahora en la capa común de Meta (arriba en este
    # archivo), para que TODOS los endpoints traduzcan igual los errores.

    # ── Idempotencia + bitácora ────────────────────────────────────────
    # Se aparta el lugar ANTES de tocar Meta. Si el agente da doble clic (o el
    # celular reintenta por red lenta), la segunda petición choca contra el
    # índice único y devuelve la campaña que ya existe en vez de crear otra
    # cobrando en paralelo.
    idem = (req.idempotency_key or "").strip()[:120]
    reserva = await _fb_reservar_creacion(
        user_id,
        await get_org_id_for_user(user_id),
        {
            "ad_account_id": account_id,
            "page_id": page_id,
            "campaign_name": (req.campaign_name or "Campaña Broquer")[:120],
            "objective": "OUTCOME_ENGAGEMENT",
            "daily_budget_mxn": req.daily_budget_mxn,
            "duration_days": req.duration_days,
            "meta": {"city": req.city, "city_type": req.city_type,
                     "imagenes": len(req.images_b64 or []),
                     "post_id": req.post_id, "publish_now": bool(req.publish_now)},
        },
        idempotency_key=idem,
    )

    if reserva.get("modo") == "duplicado":
        previa = reserva.get("row") or {}
        estado_previo = previa.get("status") or ""
        if estado_previo == "CREANDO":
            raise HTTPException(
                status_code=409,
                detail="Ese anuncio ya se está creando en este momento. Espera unos "
                       "segundos y revisa «Tus campañas» antes de volver a enviarlo.")
        if estado_previo == "FALLIDO":
            # El intento anterior no dejó nada creado: se deja pasar de nuevo.
            _fb_log.info("Reintento tras fallo previo (idempotency_key=%s)", idem)
            reserva = {"modo": "nuevo", "row_id": previa.get("id")}
        else:
            acct_prev = (previa.get("ad_account_id") or account_id).replace("act_", "")
            return {
                "ok": True,
                "duplicado": True,
                "status": estado_previo,
                "campaign_id": previa.get("campaign_id"),
                "adset_id": previa.get("adset_id"),
                "creative_id": previa.get("creative_id"),
                "ad_id": previa.get("ad_id"),
                "ads_manager_url": (
                    f"https://www.facebook.com/adsmanager/manage/campaigns"
                    f"?act={acct_prev}&selected_campaign_ids={previa.get('campaign_id')}"),
                "warning": "Este anuncio ya se había creado. No se cobró dos veces.",
            }

    row_id = reserva.get("row_id", "")

    async def _marcar_fallo(detalle: str) -> None:
        """Deja la bitácora en FALLIDO para que un reintento pueda proceder."""
        if row_id:
            await _fb_actualizar_entidad(row_id, {"status": "FALLIDO",
                                                  "error_detail": detalle[:1000]})

    # Cualquier fallo a partir de aquí deja la bitácora en FALLIDO, para que
    # un reintento con la misma llave de idempotencia pueda proceder en vez
    # de quedarse trabado creyendo que hay una creación en curso.
    try:
        async with httpx.AsyncClient(timeout=60) as client:

            # ── 0. Validar imágenes ────────────────────────────────────────
            images_b64 = [b for b in (req.images_b64 or []) if b]
            images_mime = list(req.images_mime or [])
            if not req.post_id and not images_b64:
                raise HTTPException(status_code=400, detail="Sube al menos una imagen para el anuncio.")
            if len(images_b64) > 10:
                images_b64 = images_b64[:10]
                images_mime = images_mime[:10]
            # Completar mimes si faltan
            while len(images_mime) < len(images_b64):
                images_mime.append("image/jpeg")

            # ── 0a. Validar la ciudad ANTES de tocar Meta ──────────────────
            # Esta validación vivía después de crear la campaña: si el agente
            # mandaba el formulario sin ciudad, la campaña ya existía en la cuenta
            # y se quedaba huérfana para siempre. Ahora corta antes de crear nada.
            if not req.city:
                raise HTTPException(status_code=400, detail="Debes seleccionar una ciudad para el anuncio.")

            # ── 0b. Subir todas las imágenes a Meta ANTES de crear campaña ──
            # Si cualquier imagen falla, abortamos sin dejar basura en la cuenta.
            image_hashes = []
            if not req.post_id:
                for idx, b64 in enumerate(images_b64):
                    r_img = await _fb_request(client, "POST", f"{account_id}/adimages",
                                              token=user_token, json_body={"bytes": b64})
                    if r_img is not None and r_img.status_code in (200, 201):
                        for v in (r_img.json().get("images") or {}).values():
                            h = v.get("hash")
                            if h:
                                image_hashes.append(h)
                            break
                    if len(image_hashes) < idx + 1:
                        raise HTTPException(
                            status_code=502,
                            detail=_fb_friendly_error(
                                r_img.text if r_img is not None else "",
                                f"No se pudo subir la imagen {idx + 1}"
                            )
                        )

            # ── Recortar campos a límites Meta ─────────────────────────────
            ad_text = (req.ad_text or "")[:2200]
            headline = (req.headline or "")[:40]      # recomendado <40 para carrusel
            campaign_name = (req.campaign_name or "Campaña Broquer")[:120]

            # ── 1. Crear Campaign (siempre en PAUSED; activamos al final) ──
            r_camp = await _fb_request(
                client, "POST", f"{account_id}/campaigns", token=user_token,
                json_body={
                    "name": campaign_name,
                    "objective": "OUTCOME_ENGAGEMENT",
                    "status": "PAUSED",
                    "special_ad_categories": [],
                    "buying_type": "AUCTION",
                    "is_adset_budget_sharing_enabled": False,
                }
            )
            campaign_id = _fb_exigir_ok(r_camp, "Error creando campaña").get("id")

            # Cleanup helper: borra recursos creados si algo falla a medio camino.
            # Devuelve los ids que NO se pudieron borrar, para poder avisar en vez
            # de dejar huérfanos silenciosos cobrando en la cuenta.
            async def _cleanup(*ids) -> list:
                huerfanos = []
                for rid in ids:
                    if not rid:
                        continue
                    try:
                        rr = await _fb_request(client, "DELETE", str(rid),
                                               token=user_token, reintentos=2)
                        if rr is None or rr.status_code not in (200, 204):
                            huerfanos.append(rid)
                    except Exception:
                        huerfanos.append(rid)
                if huerfanos:
                    _fb_log.error("No se pudieron borrar recursos de Meta: %s", huerfanos)
                return huerfanos

            def _detalle_con_huerfanos(base: str, huerfanos: list) -> str:
                if not huerfanos:
                    return base
                return (f"{base} · Aviso: quedaron recursos sin borrar en tu cuenta "
                        f"({', '.join(str(h) for h in huerfanos)}). Revísalos en Ads Manager.")

            # ── 2. Crear AdSet ─────────────────────────────────────────────
            # Siempre se segmenta por ciudad. No se usa countries — no tiene sentido
            # para un agente inmobiliario anunciar en todo un país.
            # Meta exige que la key vaya en el bucket correcto: una key de estado
            # dentro de "cities" hace fallar la creación del conjunto de anuncios.
            _geo_bucket = {
                "city": "cities",
                "region": "regions",
                "neighborhood": "neighborhoods",
                "subcity": "subcities",
            }.get((req.city_type or "city").lower(), "cities")
            geo: dict = {_geo_bucket: [{"key": req.city}]}
            targeting: dict = {
                "age_min": req.age_min,
                "geo_locations": geo,
                # Meta requiere desde 2024 que se declare EXPLÍCITAMENTE si se usa
                # Advantage Audience. 0 = desactivado (público controlado por el agente).
                "targeting_automation": {"advantage_audience": 0},
            }
            if req.age_max and req.age_max > 0:
                targeting["age_max"] = req.age_max

            # Públicos personalizados / similares creados desde el CRM.
            incluidos = [str(a).strip() for a in (req.custom_audience_ids or []) if str(a).strip()]
            excluidos = [str(a).strip() for a in (req.excluded_audience_ids or []) if str(a).strip()]
            if incluidos:
                targeting["custom_audiences"] = [{"id": a} for a in incluidos]
            if excluidos:
                targeting["excluded_custom_audiences"] = [{"id": a} for a in excluidos]

            adset_payload: dict = {
                "name": f"{campaign_name} — AdSet",
                "campaign_id": campaign_id,
                "daily_budget": daily_budget_cents,
                "billing_event": billing_event,
                "optimization_goal": optimization_goal,
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "targeting": targeting,
                "status": "PAUSED",
                # Click-to-Messenger: promoted_object apunta a la página.
                "promoted_object": {"page_id": page_id},
                # destination_type = MESSENGER indica a Meta que el destino es Messenger.
                # Esto es obligatorio para anuncios Click-to-Messenger.
                "destination_type": "MESSENGER",
            }

            if req.duration_days and req.duration_days > 0:
                from datetime import timedelta
                end_dt = datetime.utcnow() + timedelta(days=req.duration_days)
                adset_payload["end_time"] = end_dt.strftime("%Y-%m-%dT%H:%M:%S+0000")

            r_adset = await _fb_request(client, "POST", f"{account_id}/adsets",
                                        token=user_token, json_body=adset_payload)
            if r_adset is None or r_adset.status_code not in (200, 201):
                huerfanos = await _cleanup(campaign_id)
                raise HTTPException(status_code=502, detail=_detalle_con_huerfanos(
                    _fb_friendly_error(r_adset.text if r_adset is not None else "",
                                       "Error creando conjunto de anuncios"), huerfanos))
            adset_id = r_adset.json().get("id")

            # ── 3. Crear AdCreative (carrusel Click-to-Messenger) ──────────
            if req.post_id:
                # Modo boost de publicación existente (no carrusel)
                creative_payload: dict = {
                    "name": f"{campaign_name} — Boost",
                    "object_story_id": req.post_id,
                }
            else:
                # Construir child_attachments: una tarjeta por imagen.
                # CTA = MESSAGE_PAGE abre Messenger sin URL de destino.
                child_attachments = []
                for i, img_hash in enumerate(image_hashes):
                    attachment: dict = {
                        "name": headline,
                        "image_hash": img_hash,
                        "call_to_action": {
                            "type": "MESSAGE_PAGE",
                            "value": {"app_destination": "MESSENGER"},
                        },
                    }
                    child_attachments.append(attachment)

                # link_data del carrusel: message global + tarjetas hijas.
                # link es obligatorio en link_data pero para Click-to-Messenger
                # apuntamos a la página de Facebook (no a un sitio web).
                link_data: dict = {
                    "message": ad_text,
                    "link": f"https://www.facebook.com/{page_id}",
                    "child_attachments": child_attachments,
                    "call_to_action": {
                        "type": "MESSAGE_PAGE",
                        "value": {"app_destination": "MESSENGER"},
                    },
                }

                creative_payload = {
                    "name": f"{campaign_name} — Creative",
                    "object_story_spec": {
                        "page_id": page_id,
                        "link_data": link_data,
                    },
                }

            r_creative = await _fb_request(client, "POST", f"{account_id}/adcreatives",
                                           token=user_token, json_body=creative_payload)
            if r_creative is None or r_creative.status_code not in (200, 201):
                huerfanos = await _cleanup(adset_id, campaign_id)
                raise HTTPException(status_code=502, detail=_detalle_con_huerfanos(
                    _fb_friendly_error(r_creative.text if r_creative is not None else "",
                                       "Error creando creativo"), huerfanos))
            creative_id = r_creative.json().get("id")

            # ── 4. Crear Ad (PAUSED; activamos en cascada al final) ────────
            r_ad = await _fb_request(
                client, "POST", f"{account_id}/ads", token=user_token,
                json_body={
                    "name": f"{campaign_name} — Ad",
                    "adset_id": adset_id,
                    "creative": {"creative_id": creative_id},
                    "status": "PAUSED",
                }
            )
            if r_ad is None or r_ad.status_code not in (200, 201):
                # El creativo también se borra: sin él, quedaba colgado en la cuenta.
                huerfanos = await _cleanup(creative_id, adset_id, campaign_id)
                raise HTTPException(status_code=502, detail=_detalle_con_huerfanos(
                    _fb_friendly_error(r_ad.text if r_ad is not None else "",
                                       "Error creando anuncio"), huerfanos))
            ad_id = r_ad.json().get("id")

            # ── 5. Activar en cascada si el usuario marcó "Publicar ahora" ──
            # Orden: ad → adset → campaign (Meta exige hijos activos primero).
            # Si CUALQUIER nivel falla, revertimos los que sí se activaron: dejar
            # media cascada activa hace que el usuario vea "Activa" mientras el
            # anuncio no entrega nada, o peor, que entregue creyendo que está en
            # pausa. El estado que devolvemos tiene que ser el estado REAL.
            aviso_activacion = ""
            if target_status == "ACTIVE":
                activados: list = []
                fallo = None
                for nivel, rid in (("anuncio", ad_id), ("conjunto", adset_id), ("campaña", campaign_id)):
                    rr = await _fb_request(client, "POST", str(rid), token=user_token,
                                           json_body={"status": "ACTIVE"})
                    if rr is None or rr.status_code not in (200, 201):
                        fallo = (nivel, _fb_friendly_error(rr.text if rr is not None else "",
                                                           f"No se pudo activar el {nivel}"))
                        break
                    activados.append(rid)

                if fallo:
                    for rid in reversed(activados):
                        try:
                            await _fb_request(client, "POST", str(rid), token=user_token,
                                              json_body={"status": "PAUSED"}, reintentos=2)
                        except Exception:
                            _fb_log.error("No se pudo revertir a PAUSED: %s", rid)
                    target_status = "PAUSED"
                    aviso_activacion = (
                        f"{fallo[1]}. La campaña quedó creada y EN PAUSA: revísala y "
                        f"actívala desde «Tus campañas» cuando esté lista."
                    )
    except HTTPException as e:
        await _marcar_fallo(str(e.detail))
        raise
    except Exception as e:
        await _marcar_fallo(f"Error inesperado: {e}")
        raise

    # Bitácora: los IDs quedan guardados en Broquer. Es lo que permite después
    # reconciliar, pollear el estado de revisión y detectar huérfanos.
    await _fb_actualizar_entidad(row_id, {
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "status": target_status,
        "error_detail": aviso_activacion or None,
    })

    # account_id sin prefijo act_ para el deep-link al Ads Manager
    acct_short = account_id.replace("act_", "")
    ads_manager_url = (
        f"https://www.facebook.com/adsmanager/manage/campaigns"
        f"?act={acct_short}&selected_campaign_ids={campaign_id}"
    )

    return {
        "ok": True,
        "status": target_status,
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "ads_manager_url": ads_manager_url,
        "warning": aviso_activacion,
    }


async def _get_fb_meta(user_id: str) -> dict:
    """Helper: recupera meta de Facebook del usuario desde Supabase."""
    try:
        rows = await get_rows(
            "user_integrations",
            {"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "meta", "limit": "1"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    if not rows:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta_raw = rows[0].get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        return {}
    if meta.get("user_token"):
        meta["user_token"] = descifrar_secreto(meta["user_token"])
    return meta


@app.post("/facebook/ad-description")
async def facebook_ad_description(request: Request):
    """Genera o MEJORA texto del anuncio con Claude. Máx 150 caracteres.

    Body acepta:
      - titulo: texto base / título de referencia
      - mejorar: bool — si True, mejora el texto en lugar de generar desde cero
      - emojis: bool — si True, incluye emojis relevantes en el resultado
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")
    body = await request.json()
    titulo = (body.get("titulo") or "").strip()
    mejorar = bool(body.get("mejorar"))
    emojis = bool(body.get("emojis"))

    emoji_instr = " Incluye 2–3 emojis relevantes (🏡, 📍, ✨, 🔑, 🌳, etc.) integrados naturalmente, no al inicio/final." if emojis else ""

    if mejorar and titulo:
        prompt = (
            f"Mejora este texto para un anuncio inmobiliario en Facebook, conservando su intención original.\n"
            f"Texto del agente: \"{titulo}\"\n\n"
            f"Reglas: máximo 150 caracteres; tono profesional y convincente; "
            f"corrige ortografía/redacción; agrega 1 gancho corto si falta.{emoji_instr} "
            f"Devuelve SOLO el texto mejorado, sin comillas ni explicaciones."
        )
    else:
        prompt = (
            f"Escribe el texto principal para un anuncio de Facebook de una propiedad inmobiliaria. "
            f"{'Título/referencia: ' + titulo + '. ' if titulo else ''}"
            f"El texto debe ser directo, profesional y convincente. "
            f"Máximo 150 caracteres.{emoji_instr} "
            f"Solo el texto del anuncio, sin comillas ni explicaciones."
        )

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 120, "messages": [{"role": "user", "content": prompt}]}
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Error generando descripción")
    _resp_json = r.json()
    _track_anthropic(user_id, "facebook-ads", "/facebook/ad-description", _resp_json,
                     modelo=_resp_json.get("model") or "claude-sonnet-4-6")
    text = _resp_json.get("content", [{}])[0].get("text", "").strip()[:200]
    return {"text": text}


@app.get("/facebook/city-search")
async def facebook_city_search(request: Request, q: str = ""):
    """Busca ciudades/regiones en Meta para targeting geográfico.

    `request` va primero y sin valor por defecto: antes era `request: Request = None`
    detrás de un parámetro sin default, así que una llamada interna sin request
    reventaba con AttributeError en vez de dar un 401 honesto.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if len(q) < 2:
        return {"results": []}
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")

    # IMPORTANTE: Meta exige location_types como ARRAY JSON, no como lista
    # separada por comas. Enviar "city,region" devuelve error 100 y el
    # buscador de ciudades queda mudo.
    base_params = {
        "type": "adgeolocation",
        "q": q,
        "country_code": "MX",
        "limit": "10",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await _fb_request(
                client, "GET", "search", token=user_token,
                params={**base_params, "location_types": json.dumps(["city", "region"])}
            )
            # Fallback: si Meta rechaza el filtro, repetimos sin él para no
            # dejar al agente sin resultados.
            if r is None or r.status_code != 200:
                r = await _fb_request(client, "GET", "search",
                                      token=user_token, params=base_params)
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo conectar con Facebook. Intenta de nuevo.")

    if r is None:
        raise HTTPException(status_code=504, detail="Facebook no respondió al buscar ciudades. Intenta de nuevo.")
    if r.status_code != 200:
        try:
            _msg = r.json().get("error", {}).get("message", "")
        except Exception:
            _msg = ""
        raise HTTPException(
            status_code=502,
            detail=f"Facebook no pudo buscar ciudades: {_msg}" if _msg
                   else "Facebook no pudo buscar ciudades. Reconecta tu cuenta desde tu perfil."
        )

    allowed = {"city", "region", "neighborhood", "subcity"}
    results = []
    for d in r.json().get("data", []):
        if not d.get("key") or not d.get("name"):
            continue
        if d.get("type") and d["type"] not in allowed:
            continue
        results.append({
            "key": d["key"],
            "name": d["name"],
            "type": d.get("type", ""),
            "region": d.get("region", ""),
            "country_name": d.get("country_name", ""),
        })
    return {"results": results}


# Periodos que Meta acepta en `date_preset`. Se valida contra esta lista para
# no reenviar a Meta cualquier cosa que llegue por query string.
_FB_DATE_PRESETS = {
    "today", "yesterday", "this_week_mon_today", "last_week_mon_sun",
    "last_7d", "last_14d", "last_28d", "last_30d", "last_90d",
    "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year", "maximum",
}

# Breakdowns soportados. Meta no deja combinar cualquiera con cualquiera; esta
# lista es la que el módulo ofrece y sabe pintar.
_FB_BREAKDOWNS = {"age", "gender", "publisher_platform", "platform_position",
                  "impression_device", "region", "country"}

# Las acciones que de verdad importan para un anuncio Click-to-Messenger.
# El KPI real del agente inmobiliario NO son las impresiones: son las
# conversaciones abiertas en Messenger y lo que cuesta cada una.
_FB_ACCIONES_CLAVE = {
    "onsite_conversion.messaging_conversation_started_7d": "conversaciones",
    "onsite_conversion.total_messaging_connection": "mensajes",
    "link_click": "clics_enlace",
    "post_engagement": "engagement",
    "landing_page_view": "vistas_destino",
    "lead": "leads",
    "leadgen_grouped": "leads_formulario",
}

_FB_INSIGHTS_FIELDS = ("impressions,reach,clicks,ctr,cpc,cpm,spend,frequency,"
                       "actions,cost_per_action_type,objective,date_start,date_stop")


def _fb_normaliza_insights(ins: dict) -> dict:
    """Aplana un registro de insights de Meta a números que la UI pueda pintar.

    `actions` y `cost_per_action_type` vienen como listas de {action_type, value}
    — inservibles tal cual. Aquí se convierten en campos planos, incluyendo el
    dato que de verdad importa: conversaciones de Messenger y su costo.
    """
    ins = ins or {}
    # Meta a veces mete elementos que no son dicts en estas listas (o valores
    # que no son números). Un AttributeError aquí tumbaba toda la pantalla de
    # campañas, así que se filtra defensivamente.
    def _a_mapa(lista) -> dict:
        salida = {}
        for item in (lista or []):
            if not isinstance(item, dict):
                continue
            tipo = item.get("action_type")
            if not tipo:
                continue
            try:
                salida[tipo] = float(item.get("value") or 0)
            except (TypeError, ValueError):
                continue
        return salida

    acciones = _a_mapa(ins.get("actions"))
    costos = _a_mapa(ins.get("cost_per_action_type"))

    out = {
        "impressions": ins.get("impressions", "0"),
        "reach": ins.get("reach", "0"),
        "clicks": ins.get("clicks", "0"),
        "ctr": ins.get("ctr", "0"),
        "cpc": ins.get("cpc", "0"),
        "cpm": ins.get("cpm", "0"),
        "spend": ins.get("spend", "0"),
        "frequency": ins.get("frequency", "0"),
        "date_start": ins.get("date_start", ""),
        "date_stop": ins.get("date_stop", ""),
        # Crudos, por si la UI quiere enseñar el detalle completo.
        "actions": ins.get("actions") or [],
        "cost_per_action_type": ins.get("cost_per_action_type") or [],
    }
    for clave, nombre in _FB_ACCIONES_CLAVE.items():
        out[nombre] = acciones.get(clave, 0)
        out[f"costo_{nombre}"] = costos.get(clave, 0)
    # `engagement` se llamaba así en la respuesta vieja: se conserva el nombre
    # para no romper la UI actual.
    out["engagement"] = out.get("engagement", 0) or acciones.get("post_engagement", 0)
    return out


@app.get("/facebook/campaigns")
async def facebook_campaigns_list(request: Request):
    """Lista las campañas con sus métricas reales.

    Antes esto hacía 1 + N peticiones (una por campaña) y solo traía métricas de
    vanidad. Ahora pide TODOS los insights en UNA sola llamada a nivel cuenta
    (`level=campaign`) e incluye conversaciones de Messenger y su costo, que es
    lo que el agente realmente necesita para decidir si el anuncio sirve.

    Query params:
      account_id  (requerido)
      date_preset (opcional, default last_7d)
      status      (opcional: ACTIVE|PAUSED|ALL, default ALL)
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    account_id_raw = request.query_params.get("account_id", "")
    if not account_id_raw:
        raise HTTPException(status_code=400, detail="account_id requerido")
    account_id = account_id_raw if account_id_raw.startswith("act_") else f"act_{account_id_raw}"

    date_preset = (request.query_params.get("date_preset") or "last_7d").strip()
    if date_preset not in _FB_DATE_PRESETS:
        raise HTTPException(status_code=400,
                            detail=f"Periodo no válido. Usa uno de: {', '.join(sorted(_FB_DATE_PRESETS))}")

    async with httpx.AsyncClient(timeout=40) as client:
        # 1. Campañas (paginadas: el limit=20 escondía las demás)
        campaigns = await _fb_paginate(
            client, f"{account_id}/campaigns", token=user_token,
            params={"fields": "id,name,status,effective_status,objective,created_time,"
                              "daily_budget,lifetime_budget,stop_time",
                    "limit": "50"},
            max_items=200, prefix="Error obteniendo campañas",
        )

        # 2. TODOS los insights de un jalón, a nivel campaña.
        insights_por_campana: dict = {}
        try:
            filas = await _fb_paginate(
                client, f"{account_id}/insights", token=user_token,
                params={"level": "campaign",
                        "fields": _FB_INSIGHTS_FIELDS + ",campaign_id",
                        "date_preset": date_preset,
                        "limit": "200"},
                max_items=500, prefix="Error obteniendo métricas",
            )
            for fila in filas:
                cid = fila.get("campaign_id")
                if cid:
                    insights_por_campana[cid] = _fb_normaliza_insights(fila)
        except HTTPException as e:
            # Sin métricas la lista sigue sirviendo (se puede pausar/activar),
            # así que se degrada con aviso en vez de tumbar la pantalla.
            _fb_log.warning("Insights no disponibles para %s: %s", account_id, e.detail)

    vacio = _fb_normaliza_insights({})
    results = []
    for camp in campaigns:
        cid = camp.get("id", "")
        results.append({
            "id": cid,
            "name": camp.get("name", ""),
            "status": camp.get("status", ""),
            "effective_status": camp.get("effective_status", ""),
            "objective": camp.get("objective", ""),
            "created_time": camp.get("created_time", ""),
            "stop_time": camp.get("stop_time", ""),
            "daily_budget": camp.get("daily_budget", ""),
            **insights_por_campana.get(cid, vacio),
        })
    return {"campaigns": results, "date_preset": date_preset,
            "con_metricas": bool(insights_por_campana)}


@app.get("/facebook/insights")
async def facebook_insights(request: Request):
    """Insights a cualquier nivel, con desgloses. Es la vista de análisis.

    Query params:
      object_id   (requerido) — act_XXX, campaign_id, adset_id o ad_id
      level       account|campaign|adset|ad     (default: campaign)
      date_preset (default last_7d)
      breakdowns  lista separada por comas: age, gender, publisher_platform,
                  platform_position, impression_device, region, country
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    qp = request.query_params
    object_id = (qp.get("object_id") or "").strip()
    if not object_id:
        raise HTTPException(status_code=400, detail="object_id requerido")

    level = (qp.get("level") or "campaign").strip().lower()
    if level not in ("account", "campaign", "adset", "ad"):
        raise HTTPException(status_code=400, detail="level debe ser account, campaign, adset o ad")

    date_preset = (qp.get("date_preset") or "last_7d").strip()
    if date_preset not in _FB_DATE_PRESETS:
        raise HTTPException(status_code=400,
                            detail=f"Periodo no válido. Usa uno de: {', '.join(sorted(_FB_DATE_PRESETS))}")

    breakdowns_raw = [b.strip() for b in (qp.get("breakdowns") or "").split(",") if b.strip()]
    invalidos = [b for b in breakdowns_raw if b not in _FB_BREAKDOWNS]
    if invalidos:
        raise HTTPException(status_code=400,
                            detail=f"Desglose no soportado: {', '.join(invalidos)}. "
                                   f"Disponibles: {', '.join(sorted(_FB_BREAKDOWNS))}")

    params = {
        "level": level,
        "fields": _FB_INSIGHTS_FIELDS + ",campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name",
        "date_preset": date_preset,
        "limit": "200",
    }
    if breakdowns_raw:
        params["breakdowns"] = ",".join(breakdowns_raw)

    async with httpx.AsyncClient(timeout=60) as client:
        filas = await _fb_paginate(client, f"{object_id}/insights", token=user_token,
                                   params=params, max_items=1000,
                                   prefix="Error obteniendo métricas")

    salida = []
    for fila in filas:
        registro = _fb_normaliza_insights(fila)
        for k in ("campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name"):
            if fila.get(k):
                registro[k] = fila[k]
        # Las columnas del desglose (age, gender, region…) vienen sueltas.
        for b in breakdowns_raw:
            if b in fila:
                registro[b] = fila[b]
        salida.append(registro)

    return {"rows": salida, "level": level, "date_preset": date_preset,
            "breakdowns": breakdowns_raw, "total": len(salida)}


# Traducción de los effective_status de Meta. Un anuncio puede decir ACTIVE y
# no entregar nada porque Meta lo rechazó: sin esto el agente solo ve que "no
# llegan mensajes" y no sabe por qué.
_FB_ESTADOS_EFECTIVOS = {
    "ACTIVE":               ("ok",     "Entregando"),
    "PAUSED":               ("neutro", "Pausado por ti"),
    "DELETED":              ("neutro", "Eliminado"),
    "ARCHIVED":             ("neutro", "Archivado"),
    "PENDING_REVIEW":       ("aviso",  "En revisión por Meta (suele tardar menos de 24 h)"),
    "IN_PROCESS":           ("aviso",  "Meta lo está procesando"),
    "PREAPPROVED":          ("aviso",  "Preaprobado, aún no entrega"),
    "DISAPPROVED":          ("error",  "Rechazado por Meta"),
    "WITH_ISSUES":          ("error",  "Con observaciones de Meta"),
    "PENDING_BILLING_INFO": ("error",  "Falta método de pago en la cuenta publicitaria"),
    "CAMPAIGN_PAUSED":      ("neutro", "La campaña padre está pausada"),
    "ADSET_PAUSED":         ("neutro", "El conjunto padre está pausado"),
}


@app.get("/facebook/campaign/review")
async def facebook_campaign_review(request: Request):
    """Estado de revisión real de una campaña, anuncio por anuncio.

    Meta puede rechazar un anuncio y dejar la campaña en ACTIVE: en Broquer se
    veía "Activa" sin entregar nada y sin explicación. Aquí se lee
    effective_status + ad_review_feedback + issues_info de cada anuncio y se
    devuelve el motivo del rechazo en español.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    campaign_id = (request.query_params.get("campaign_id") or "").strip()
    if not campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id requerido")
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    async with httpx.AsyncClient(timeout=30) as client:
        campana = await _fb_get_json(client, campaign_id, token=user_token,
                                     params={"fields": "id,name,status,effective_status"},
                                     prefix="Error leyendo la campaña")
        anuncios = await _fb_paginate(
            client, f"{campaign_id}/ads", token=user_token,
            params={"fields": "id,name,status,effective_status,"
                              "ad_review_feedback,issues_info,adset_id",
                    "limit": "50"},
            prefix="Error leyendo los anuncios",
        )

    def _motivos(ad: dict) -> list:
        """Junta los motivos de rechazo en frases sueltas y legibles."""
        salida = []
        feedback = ad.get("ad_review_feedback") or {}
        # Meta anida esto como {"global": {...}} o {"placement": {...}}
        for bloque in feedback.values():
            if isinstance(bloque, dict):
                salida.extend(str(v) for v in bloque.values() if v)
            elif bloque:
                salida.append(str(bloque))
        for issue in (ad.get("issues_info") or []):
            if not isinstance(issue, dict):
                continue
            texto = issue.get("error_summary") or issue.get("error_message") or ""
            if texto:
                salida.append(str(texto))
        # Sin duplicar, conservando el orden.
        return list(dict.fromkeys([s for s in salida if s.strip()]))

    detalle = []
    for ad in anuncios:
        eff = ad.get("effective_status", "")
        severidad, etiqueta = _FB_ESTADOS_EFECTIVOS.get(eff, ("neutro", eff or "Desconocido"))
        detalle.append({
            "ad_id": ad.get("id", ""),
            "adset_id": ad.get("adset_id", ""),
            "name": ad.get("name", ""),
            "status": ad.get("status", ""),
            "effective_status": eff,
            "severidad": severidad,
            "etiqueta": etiqueta,
            "motivos": _motivos(ad),
            "apelable": eff in ("DISAPPROVED", "WITH_ISSUES"),
        })

    eff_camp = campana.get("effective_status", "")
    sev_camp, etq_camp = _FB_ESTADOS_EFECTIVOS.get(eff_camp, ("neutro", eff_camp or "Desconocido"))
    rechazados = [d for d in detalle if d["severidad"] == "error"]

    return {
        "campaign_id": campaign_id,
        "name": campana.get("name", ""),
        "status": campana.get("status", ""),
        "effective_status": eff_camp,
        "severidad": "error" if rechazados else sev_camp,
        "etiqueta": etq_camp,
        "ads": detalle,
        "con_problemas": len(rechazados),
        # Meta no expone la apelación por API: el agente tiene que entrar.
        "url_revision": f"https://www.facebook.com/adsmanager/manage/ads?selected_campaign_ids={campaign_id}",
    }


# ════════════════════════════════════════════════════════════════
# META — Lead Ads: webhook y captura automática de prospectos
# ════════════════════════════════════════════════════════════════
# Un "Lead Ad" es el anuncio con formulario dentro de Facebook: la persona
# llena sus datos sin salir de la app. Meta avisa por webhook y hay que ir a
# recoger el lead con el token de la página.
#
# Sin esto, los leads se quedaban en Meta hasta que alguien se acordaba de
# bajarlos a mano — y un prospecto inmobiliario que espera dos días ya le
# compró a alguien más.

# Token que Meta usa para verificar la suscripción. Si no está configurado, el
# webhook queda cerrado (no se acepta ninguna suscripción a ciegas).
FB_VERIFY_TOKEN = legacy_main_settings.fb_verify_token
# Secreto para validar la firma. Se cae a FB_APP_SECRET porque los Lead Ads
# viven en la misma app de Meta que los anuncios.
_FB_WEBHOOK_SECRET = legacy_main_settings.fb_webhook_secret or FB_APP_SECRET


@app.get("/facebook/leadgen/webhook")
async def facebook_leadgen_verify(request: Request):
    """Handshake de verificación de Meta (hub.challenge)."""
    p = request.query_params
    if not FB_VERIFY_TOKEN:
        _fb_log.error("FB_VERIFY_TOKEN no configurado: el webhook de Lead Ads está cerrado.")
        return Response(content="not configured", status_code=503)
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == FB_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@app.post("/facebook/leadgen/webhook")
async def facebook_leadgen_webhook(request: Request, background: BackgroundTasks):
    """Recibe el aviso de Meta y encola la captura del lead.

    Se contesta 200 rápido (Meta reintenta y deja de mandar si tardamos) y el
    trabajo pesado —ir por los datos del lead y crear el contacto— se hace en
    segundo plano.

    Sin secreto configurado NO se procesa nada: si no, cualquiera en internet
    podría inyectar prospectos falsos en el CRM del agente.
    """
    raw = await request.body()

    if not _FB_WEBHOOK_SECRET:
        _fb_log.error("FB_APP_SECRET/FB_WEBHOOK_SECRET vacíos: el webhook de Lead Ads "
                      "queda CERRADO hasta que se configure uno en Railway.")
        return Response(status_code=503)

    firma = request.headers.get("X-Hub-Signature-256", "")
    esperada = "sha256=" + hmac.new(_FB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma, esperada):
        _fb_log.warning("Firma inválida en el webhook de Lead Ads")
        return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)   # basura: no pedir reintento

    pendientes = []
    for entrada in (payload.get("entry") or []):
        for cambio in (entrada.get("changes") or []):
            if cambio.get("field") != "leadgen":
                continue
            valor = cambio.get("value") or {}
            if valor.get("leadgen_id"):
                pendientes.append(valor)

    for valor in pendientes:
        background.add_task(_fb_procesar_lead, valor)

    return Response(status_code=200)


async def _fb_buscar_dueno_de_pagina(page_id: str) -> dict:
    """Encuentra a qué usuario de Broquer pertenece una página de Facebook.

    meta se guarda como JSON serializado en una columna de texto, así que no se
    puede filtrar con el operador -> de PostgREST. Se prefiltra con LIKE y se
    confirma en Python; el universo son las filas de Facebook, que son pocas.
    """
    if not page_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    try:
        try:
            filas = await get_rows(
                "user_integrations",
                {"provider": "eq.facebook",
                 "select": "user_id,org_id,api_key,meta",
                 "meta": f"like.*{page_id}*",
                 "limit": "20"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            filas = []
        if not filas:
            # Respaldo: si el LIKE no aplica (columna jsonb), se revisa todo.
            try:
                filas = await get_rows(
                    "user_integrations",
                    {"provider": "eq.facebook",
                     "select": "user_id,org_id,api_key,meta", "limit": "500"},
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                filas = []
    except Exception as e:
        _fb_log.error("Error buscando al dueño de la página %s: %s", page_id, e)
        return {}

    for fila in filas:
        meta_raw = fila.get("meta") or "{}"
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
        except Exception:
            continue
        if meta.get("page_id") == page_id:
            return {"user_id": fila.get("user_id"), "org_id": fila.get("org_id"),
                    "page_token": descifrar_secreto(fila.get("api_key", "")), "meta": meta}
    return {}


# Cómo se llaman los campos estándar de Meta y a qué columna del CRM van.
_FB_CAMPOS_LEAD = {
    "full_name": "nombre", "first_name": "_nombre_pila", "last_name": "_apellido",
    "email": "email", "phone_number": "telefono", "company_name": "empresa",
    "city": "mpio", "street_address": "calle", "post_code": "cp",
}


async def _fb_procesar_lead(valor: dict) -> None:
    """Baja un lead de Meta y lo guarda como contacto potencial en el CRM.

    Corre en segundo plano. Nunca lanza: un error aquí no puede tumbar el
    webhook (Meta desuscribe apps que fallan seguido). Todo queda anotado en
    fb_leads_recibidos, incluso los que fallan, para poder reintentar a mano.
    """
    leadgen_id = str(valor.get("leadgen_id") or "")
    page_id = str(valor.get("page_id") or "")
    if not leadgen_id:
        return

    bitacora = {
        "leadgen_id": leadgen_id, "page_id": page_id,
        "form_id": str(valor.get("form_id") or ""),
        "ad_id": str(valor.get("ad_id") or ""),
        "adset_id": str(valor.get("adgroup_id") or valor.get("adset_id") or ""),
        "campaign_id": str(valor.get("campaign_id") or ""),
        "payload": valor,
        "procesado": False,
    }

    async def _anota(extra: dict) -> None:
        """Escribe la bitácora. El unique en leadgen_id es el anti-duplicado:
        si Meta reenvía el mismo aviso, el INSERT choca y no se crea otro
        contacto."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{SUPABASE_URL}/rest/v1/fb_leads_recibidos",
                    headers=_sb_headers({"Prefer": "return=minimal"}),
                    json={**bitacora, **extra})
            if r.status_code not in (200, 201, 204) and not _fb_tabla_falta(r):
                if r.status_code != 409:
                    _fb_log.error("No se pudo anotar el lead %s: %s %s",
                                  leadgen_id, r.status_code, (r.text or "")[:200])
        except Exception as e:
            _fb_log.error("Error anotando el lead %s: %s", leadgen_id, e)

    # ── 0. ¿Ya lo procesamos? Meta reintenta y no queremos duplicados ──
    try:
        try:
            filas_previas = await get_rows(
                "fb_leads_recibidos",
                {"leadgen_id": f"eq.{leadgen_id}", "select": "id,procesado", "limit": "1"},
                timeout=10,
            )
        except httpx.HTTPStatusError as e:
            if _fb_tabla_falta(e.response):
                _fb_avisa_migracion("procesar lead", e.response)
            filas_previas = []
        if filas_previas and (filas_previas[0] or {}).get("procesado"):
            _fb_log.info("Lead %s ya procesado; se ignora el reenvío.", leadgen_id)
            return
    except Exception:
        pass

    # ── 1. ¿De quién es esta página? ───────────────────────────────────
    dueno = await _fb_buscar_dueno_de_pagina(page_id)
    if not dueno.get("user_id"):
        _fb_log.warning("Llegó un lead de la página %s pero ningún usuario de "
                        "Broquer la tiene conectada.", page_id)
        await _anota({"error_detail": "Página no conectada a ningún usuario de Broquer."})
        return

    user_id = dueno["user_id"]
    org_id = dueno.get("org_id")
    page_token = dueno.get("page_token", "")
    bitacora["user_id"] = user_id
    bitacora["org_id"] = org_id

    if not page_token:
        await _anota({"error_detail": "No hay token de página para leer el lead."})
        return

    # ── 2. Bajar los datos del lead ────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await _fb_request(client, "GET", leadgen_id, token=page_token,
                                  params={"fields": "id,created_time,field_data,"
                                                    "ad_id,adset_id,campaign_id,form_id"})
        if r is None or r.status_code != 200:
            detalle = _fb_friendly_error(r.text if r is not None else "", "No se pudo leer el lead")
            _fb_log.error("Lead %s: %s", leadgen_id, detalle)
            await _anota({"error_detail": detalle})
            return
        lead = r.json() or {}
    except Exception as e:
        await _anota({"error_detail": f"Error leyendo el lead: {e}"})
        return

    # ── 3. Mapear los campos del formulario al CRM ─────────────────────
    campos: dict = {}
    extras: list = []
    for campo in (lead.get("field_data") or []):
        nombre_campo = (campo.get("name") or "").lower()
        valores = campo.get("values") or []
        valor_txt = str(valores[0]).strip() if valores else ""
        if not valor_txt:
            continue
        destino = _FB_CAMPOS_LEAD.get(nombre_campo)
        if destino:
            campos[destino] = valor_txt
        else:
            # Preguntas personalizadas del formulario: se guardan como nota.
            etiqueta = (campo.get("name") or "").replace("_", " ").capitalize()
            extras.append(f"{etiqueta}: {valor_txt}")

    # Nombre: se arma con lo que haya.
    nombre = campos.pop("nombre", "") or " ".join(
        x for x in (campos.pop("_nombre_pila", ""), campos.pop("_apellido", "")) if x).strip()
    campos.pop("_nombre_pila", None)
    campos.pop("_apellido", None)

    telefono = campos.get("telefono", "")
    email = campos.get("email", "")
    if not nombre and not telefono and not email:
        await _anota({"error_detail": "El formulario no traía nombre, teléfono ni correo."})
        return

    notas = ["Llegó por un anuncio de Facebook (Lead Ad)."]
    if lead.get("created_time"):
        notas.append(f"Fecha del formulario: {lead['created_time']}")
    if lead.get("campaign_id"):
        notas.append(f"Campaña: {lead['campaign_id']}")
    notas.extend(extras)

    ahora = datetime.now(timezone.utc).isoformat()
    contacto = {
        "id": str(_uuid.uuid4()),
        "user_id": user_id,
        "org_id": org_id,
        "nombre": nombre or "Prospecto de Facebook",
        "tipo": "otro",
        "es_potencial": True,
        "fuente": "Facebook Lead Ads",
        "etiquetas": ["Facebook", "Lead Ad"],
        "notas": "\n".join(notas),
        "created_at": ahora,
        "updated_at": ahora,
        **{k: v for k, v in campos.items() if v},
    }
    if telefono and not contacto.get("wa"):
        contacto["wa"] = telefono

    # ── 4. Deduplicar contra los contactos que ya tiene el agente ──────
    try:
        filtro = {"select": "id,nombre,email,telefono", "limit": "1"}
        if org_id:
            filtro["org_id"] = f"eq.{org_id}"
        else:
            filtro["user_id"] = f"eq.{user_id}"
        if telefono:
            filtro["telefono"] = f"eq.{telefono}"
        elif email:
            filtro["email"] = f"eq.{email}"

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                filas_existentes = await get_rows(
                    "contactos",
                    filtro,
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                filas_existentes = []
            existente = filas_existentes[0] if filas_existentes else None

            if existente:
                # No se pisa lo que el agente ya escribió: solo se marca como
                # potencial y se agrega la nota del anuncio.
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/contactos",
                    headers=_sb_headers({"Prefer": "return=minimal"}),
                    params={"id": f"eq.{existente['id']}"},
                    json={"es_potencial": True, "updated_at": ahora})
                await _anota({"procesado": True, "contacto_id": existente["id"],
                              "error_detail": "Contacto ya existía; se marcó como potencial."})
                _fb_log.info("Lead %s emparejado con el contacto %s", leadgen_id, existente["id"])
                return

            rc = await client.post(
                f"{SUPABASE_URL}/rest/v1/contactos",
                headers=_sb_headers({"Prefer": "return=minimal"}),
                json={k: v for k, v in contacto.items() if v not in ("", None, [])})
        if rc.status_code not in (200, 201, 204):
            await _anota({"error_detail": f"No se pudo crear el contacto: {(rc.text or '')[:200]}"})
            return
    except Exception as e:
        await _anota({"error_detail": f"Error guardando el contacto: {e}"})
        return

    await _anota({"procesado": True, "contacto_id": contacto["id"]})
    _fb_log.info("Lead %s guardado como contacto %s del usuario %s",
                 leadgen_id, contacto["id"], user_id)


@app.post("/facebook/leadgen/subscribe")
async def facebook_leadgen_subscribe(request: Request):
    """Suscribe la página del agente a los avisos de Lead Ads."""
    user_id = await exigir_gestion_integraciones(request)
    if not FB_VERIFY_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar FB_VERIFY_TOKEN en el servidor. Sin él, Meta no "
                   "puede verificar el webhook y los leads no llegarían.")
    fila = await _fb_get_meta_row(user_id)
    meta = fila.get("meta") or {}
    page_id = meta.get("page_id", "")
    page_token = fila.get("page_token", "")
    if not page_id or not page_token:
        raise HTTPException(status_code=400, detail="Conecta tu página de Facebook primero.")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await _fb_request(client, "POST", f"{page_id}/subscribed_apps",
                              token=page_token,
                              json_body={"subscribed_fields": ["leadgen"]})
        _fb_exigir_ok(r, "No se pudo activar la captura de prospectos")

        # Confirmar contra Meta: que conteste 200 no siempre significa que quedó.
        confirmacion = await _fb_paginate(client, f"{page_id}/subscribed_apps",
                                          token=page_token,
                                          params={"fields": "id,name,subscribed_fields"},
                                          max_paginas=1,
                                          prefix="No se pudo verificar la suscripción")

    suscrito = any("leadgen" in (a.get("subscribed_fields") or []) for a in confirmacion)
    if not suscrito:
        raise HTTPException(
            status_code=502,
            detail="Meta aceptó la petición pero la página no quedó suscrita a 'leadgen'. "
                   "Revisa que tu app tenga el permiso leads_retrieval aprobado.")

    await _fb_patch_meta(user_id, {"leadgen_suscrito": True,
                                   "leadgen_suscrito_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "page_id": page_id, "suscrito": True,
            "nota": "A partir de ahora, los prospectos de tus anuncios con formulario "
                    "entran solos a tu lista de prospectos."}


@app.get("/facebook/leadgen/status")
async def facebook_leadgen_status(request: Request):
    """Dice si la página está capturando prospectos automáticamente."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    fila = await _fb_get_meta_row(user_id)
    meta = fila.get("meta") or {}
    page_id = meta.get("page_id", "")
    page_token = fila.get("page_token", "")
    if not page_id or not page_token:
        return {"configurado": False, "suscrito": False,
                "motivo": "No hay página de Facebook conectada."}
    if not FB_VERIFY_TOKEN or not _FB_WEBHOOK_SECRET:
        return {"configurado": False, "suscrito": False,
                "motivo": "El servidor no tiene FB_VERIFY_TOKEN o FB_APP_SECRET configurados."}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            apps = await _fb_paginate(client, f"{page_id}/subscribed_apps", token=page_token,
                                      params={"fields": "id,name,subscribed_fields"},
                                      max_paginas=1, prefix="Error consultando la suscripción")
    except HTTPException as e:
        return {"configurado": True, "suscrito": False, "motivo": str(e.detail)}

    suscrito = any("leadgen" in (a.get("subscribed_fields") or []) for a in apps)
    return {"configurado": True, "suscrito": suscrito, "page_id": page_id,
            "motivo": "" if suscrito else "La página no está suscrita a los avisos de prospectos.",
            "webhook_url": f"{FRONTEND_URL.rstrip('/')}/facebook/leadgen/webhook"}


# ════════════════════════════════════════════════════════════════
# META — públicos personalizados y similares (desde el CRM)
# ════════════════════════════════════════════════════════════════
# Sube los contactos del agente a Meta HASHEADOS (SHA-256) para poder
# anunciarle a su propia cartera, y para generar "públicos similares"
# (lookalikes): gente parecida a quienes ya le compraron.
#
# Meta NUNCA recibe datos en claro: el hash se hace aquí y es irreversible.
# Aun así, subir datos de clientes exige que el dueño de la cuenta haya
# aceptado las Condiciones de Públicos Personalizados en Business Manager;
# si no lo hizo, Meta rechaza con el código 2654 y aquí se traduce a
# instrucciones concretas en vez de un error críptico.

def _hash_meta(valor: str) -> str:
    """SHA-256 en minúsculas, como exige Meta para el matching."""
    if not valor:
        return ""
    return hashlib.sha256(valor.strip().lower().encode("utf-8")).hexdigest()


def _normaliza_email(email: str) -> str:
    """Valida y hashea. Un correo mal formado ensucia el público sin aportar."""
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return ""
    local, _, dominio = email.partition("@")
    # Hace falta parte local, dominio con punto y algo después del punto.
    if not local or "." not in dominio:
        return ""
    if not dominio.split(".")[0] or len(dominio.rsplit(".", 1)[-1]) < 2:
        return ""
    return _hash_meta(email)


def _normaliza_telefono(tel: str, lada_pais: str = "52") -> str:
    """Deja el teléfono en E.164 sin '+' y lo hashea.

    México: 10 dígitos → se antepone 52. Si ya trae 52 delante (12 dígitos) se
    respeta. También se limpia el viejo '1' de celular (521…) que Meta no espera.
    """
    digitos = re.sub(r"\D", "", tel or "")
    if not digitos:
        return ""
    if len(digitos) == 10:
        digitos = lada_pais + digitos
    elif len(digitos) == 13 and digitos.startswith(lada_pais + "1"):
        digitos = lada_pais + digitos[3:]
    if len(digitos) < 11 or len(digitos) > 15:
        return ""
    return _hash_meta(digitos)


class FbAudienceRequest(BaseModel):
    nombre: str = ""
    solo_potenciales: bool = False   # True = solo contactos marcados como potenciales
    etiquetas: list = []             # filtrar por etiquetas del CRM
    descripcion: str = ""


@app.post("/facebook/audiences/from-contacts")
async def facebook_audience_from_contacts(req: FbAudienceRequest, request: Request):
    """Crea un público personalizado con los contactos del CRM (hasheados).

    Meta necesita ~100 coincidencias para que un público sea utilizable; abajo
    se avisa cuando no se llega, en vez de dejar al agente esperando resultados
    de un público que nunca va a servir.
    """
    user_id = await exigir_gestion_integraciones(request)
    meta_fb = await _get_fb_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    # ── 1. Traer los contactos del agente (o de su empresa) ────────────
    org_id = await get_org_id_for_user(user_id)
    filtros = {"select": "id,nombre,email,telefono,wa,etiquetas,es_potencial", "limit": "5000"}
    if org_id:
        filtros["org_id"] = f"eq.{org_id}"
    else:
        filtros["user_id"] = f"eq.{user_id}"
    if req.solo_potenciales:
        filtros["es_potencial"] = "eq.true"

    try:
        contactos = await get_rows(
            "contactos",
            filtros,
            timeout=30,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")

    etiquetas_filtro = {str(e).strip().lower() for e in (req.etiquetas or []) if str(e).strip()}
    if etiquetas_filtro:
        contactos = [c for c in contactos
                     if etiquetas_filtro & {str(e).lower() for e in (c.get("etiquetas") or [])}]

    # ── 2. Hashear. Cada fila es [email, teléfono]; "" si no hay dato. ──
    datos: list = []
    for c in contactos:
        h_mail = _normaliza_email(c.get("email") or "")
        h_tel = _normaliza_telefono(c.get("telefono") or c.get("wa") or "")
        if h_mail or h_tel:
            datos.append([h_mail, h_tel])

    if not datos:
        raise HTTPException(
            status_code=400,
            detail="Ninguno de tus contactos tiene correo o teléfono utilizable. "
                   "Completa esos datos en el CRM antes de crear el público.")

    nombre = (req.nombre or f"Broquer · Contactos {datetime.now(timezone.utc):%Y-%m-%d}")[:100]

    async with httpx.AsyncClient(timeout=60) as client:
        # ── 3. Crear el público vacío ──────────────────────────────────
        r_aud = await _fb_request(
            client, "POST", f"{account_id}/customaudiences", token=user_token,
            json_body={
                "name": nombre,
                "subtype": "CUSTOM",
                "description": (req.descripcion or "Contactos del CRM de Broquer")[:200],
                "customer_file_source": "USER_PROVIDED_ONLY",
            })
        if r_aud is None or r_aud.status_code not in (200, 201):
            texto = r_aud.text if r_aud is not None else ""
            if "2654" in texto or "terms of service" in texto.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Falta aceptar las Condiciones de Públicos Personalizados de Meta. "
                           "Entra a business.facebook.com → Configuración del negocio → "
                           "Cuentas publicitarias → tu cuenta → Condiciones de públicos "
                           "personalizados, acéptalas y vuelve a intentar.")
            raise HTTPException(status_code=502,
                                detail=_fb_friendly_error(texto, "Error creando el público"))
        audience_id = r_aud.json().get("id", "")

        # ── 4. Subir los hashes en lotes de 5,000 (tope de Meta) ───────
        subidos = 0
        fallos = []
        for i in range(0, len(datos), 5000):
            lote = datos[i:i + 5000]
            r_up = await _fb_request(
                client, "POST", f"{audience_id}/users", token=user_token,
                json_body={"payload": {"schema": ["EMAIL", "PHONE"], "data": lote}},
                timeout=90)
            if r_up is not None and r_up.status_code in (200, 201):
                subidos += len(lote)
            else:
                fallos.append(_fb_friendly_error(r_up.text if r_up is not None else "",
                                                 f"Lote {i // 5000 + 1}"))

        if not subidos:
            # Público vacío = basura en la cuenta. Se limpia.
            await _fb_request(client, "DELETE", audience_id, token=user_token, reintentos=2)
            raise HTTPException(
                status_code=502,
                detail="No se pudo subir ningún contacto a Meta: " + ("; ".join(fallos) or "error desconocido"))

    await _fb_guardar_audiencia(user_id, org_id, {
        "ad_account_id": account_id, "audience_id": audience_id,
        "nombre": nombre, "tipo": "CUSTOM", "contactos_enviados": subidos,
    })

    aviso = ""
    if subidos < 100:
        aviso = (f"Solo se subieron {subidos} contactos. Meta necesita alrededor de 100 "
                 f"coincidencias para que un público se pueda usar en un anuncio; "
                 f"este puede quedar inutilizable hasta que crezca tu cartera.")
    elif fallos:
        aviso = "Algunos lotes fallaron: " + "; ".join(fallos)

    return {"ok": True, "audience_id": audience_id, "nombre": nombre,
            "contactos_enviados": subidos, "contactos_totales": len(datos),
            "warning": aviso,
            "nota": "Meta tarda entre 30 minutos y varias horas en procesar el público."}


class FbLookalikeRequest(BaseModel):
    origin_audience_id: str
    nombre: str = ""
    ratio: float = 0.01   # 1% = el más parecido; hasta 0.20
    pais: str = "MX"


@app.post("/facebook/audiences/lookalike")
async def facebook_audience_lookalike(req: FbLookalikeRequest, request: Request):
    """Crea un público similar (lookalike) a partir de uno existente."""
    user_id = await exigir_gestion_integraciones(request)
    meta_fb = await _get_fb_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    if not req.origin_audience_id:
        raise HTTPException(status_code=400, detail="Falta el público de origen.")
    ratio = req.ratio if 0.01 <= req.ratio <= 0.20 else 0.01
    pais = (req.pais or "MX").upper()[:2]
    nombre = (req.nombre or f"Broquer · Similar {int(ratio * 100)}% {pais}")[:100]

    async with httpx.AsyncClient(timeout=60) as client:
        r = await _fb_request(
            client, "POST", f"{account_id}/customaudiences", token=user_token,
            json_body={
                "name": nombre,
                "subtype": "LOOKALIKE",
                "origin_audience_id": req.origin_audience_id,
                "lookalike_spec": {"ratio": ratio, "country": pais, "type": "similarity"},
            })
    datos = _fb_exigir_ok(r, "Error creando el público similar")
    audience_id = datos.get("id", "")

    await _fb_guardar_audiencia(user_id, await get_org_id_for_user(user_id), {
        "ad_account_id": account_id, "audience_id": audience_id, "nombre": nombre,
        "tipo": "LOOKALIKE", "origen_id": req.origin_audience_id,
        "pais": pais, "ratio": ratio,
    })

    return {"ok": True, "audience_id": audience_id, "nombre": nombre,
            "ratio": ratio, "pais": pais,
            "nota": "Meta tarda entre 6 y 24 horas en construir un público similar. "
                    "Hasta entonces no lo podrás usar en un anuncio."}


@app.get("/facebook/audiences")
async def facebook_audiences_list(request: Request):
    """Lista los públicos de la cuenta, con su estado real en Meta."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta_fb = await _get_fb_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        filas = await _fb_paginate(
            client, f"{account_id}/customaudiences", token=user_token,
            params={"fields": "id,name,subtype,approximate_count_lower_bound,"
                              "approximate_count_upper_bound,operation_status,"
                              "delivery_status,time_created",
                    "limit": "100"},
            prefix="Error leyendo tus públicos")

    salida = []
    for a in filas:
        entrega = (a.get("delivery_status") or {})
        operacion = (a.get("operation_status") or {})
        listo = entrega.get("code") == 200
        salida.append({
            "id": a.get("id", ""),
            "nombre": a.get("name", ""),
            "tipo": a.get("subtype", ""),
            "tamano_min": a.get("approximate_count_lower_bound"),
            "tamano_max": a.get("approximate_count_upper_bound"),
            "listo": listo,
            "estado": entrega.get("description") or operacion.get("description") or "",
            "creado": a.get("time_created", ""),
        })
    return {"audiences": salida}


async def _fb_guardar_audiencia(user_id: str, org_id, datos: dict) -> None:
    """Bitácora del público creado. Nunca lanza: no es el trabajo principal."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{SUPABASE_URL}/rest/v1/fb_audiences",
                headers=_sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json={"user_id": user_id, "org_id": org_id, **datos})
        if r.status_code not in (200, 201, 204):
            if _fb_tabla_falta(r):
                _fb_avisa_migracion("guardar público", r)
            else:
                _fb_log.error("No se pudo guardar el público: %s %s",
                              r.status_code, (r.text or "")[:200])
    except Exception as e:
        _fb_log.error("Error guardando el público: %s", e)


@app.post("/facebook/reconcile")
async def facebook_reconcile(request: Request):
    """Cuadra lo que Broquer cree que creó contra lo que Meta realmente tiene.

    Para qué sirve, en corto: si una creación se rompió a medias (se cayó la red
    justo después de crear la campaña), quedó una campaña en la cuenta que nadie
    ve en Broquer. Esto la encuentra y la borra, o la marca como buena si sí
    llegó a existir completa. También refresca effective_status para saber si
    Meta rechazó algo.

    Por seguridad NO borra nada que Meta reporte como entregando: si una
    campaña está ACTIVE se marca para revisión manual y se deja en paz.

    Body opcional: {"limpiar": true} para borrar los huérfanos encontrados.
    """
    user_id = await exigir_gestion_integraciones(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    limpiar = bool(body.get("limpiar"))

    meta_fb = await _get_fb_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no configurado")

    try:
        filas = await get_rows(
            _FB_TABLA_ENTIDADES,
            {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"},
            timeout=15,
        )
    except httpx.HTTPStatusError as e:
        if _fb_tabla_falta(e.response):
            _fb_avisa_migracion("reconciliar", e.response)
            raise HTTPException(
                status_code=503,
                detail="Falta correr migracion-facebook-ads.sql en Supabase. Sin esa tabla "
                       "Broquer no lleva registro de lo que creó y no puede reconciliar.")
        raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")
    sanas, huerfanas, revisar, corregidas = [], [], [], []

    async with httpx.AsyncClient(timeout=40) as client:
        for fila in filas:
            cid = fila.get("campaign_id")
            row_id = fila.get("id")

            # Caso 1: quedó en CREANDO sin campaign_id → nunca llegó a crear nada.
            if not cid:
                if fila.get("status") == "CREANDO":
                    await _fb_actualizar_entidad(row_id, {
                        "status": "FALLIDO",
                        "error_detail": "Creación interrumpida antes de crear la campaña."})
                    corregidas.append({"row_id": row_id, "accion": "marcada como fallida"})
                continue

            # Caso 2: hay campaign_id → preguntarle a Meta si sigue existiendo.
            rc = await _fb_request(client, "GET", str(cid), token=user_token,
                                   params={"fields": "id,name,status,effective_status"},
                                   reintentos=2)
            existe = rc is not None and rc.status_code == 200
            datos = rc.json() if existe else {}

            if not existe:
                await _fb_actualizar_entidad(row_id, {
                    "status": "ELIMINADO",
                    "last_checked_at": datetime.now(timezone.utc).isoformat()})
                corregidas.append({"row_id": row_id, "campaign_id": cid,
                                   "accion": "ya no existe en Meta"})
                continue

            eff = datos.get("effective_status", "")
            estado_meta = datos.get("status", "")
            await _fb_actualizar_entidad(row_id, {
                "status": estado_meta or fila.get("status"),
                "effective_status": eff,
                "last_checked_at": datetime.now(timezone.utc).isoformat()})

            # Caso 3: la creación se rompió a medias (no hay ad_id) pero la
            # campaña sí existe en Meta → es huérfana: cobra estructura sin
            # anuncio y nadie la ve en Broquer.
            incompleta = not fila.get("ad_id")
            if incompleta:
                entrega = eff in ("ACTIVE", "PENDING_REVIEW", "IN_PROCESS")
                if entrega:
                    # Jamás borramos algo que Meta reporta entregando.
                    revisar.append({"campaign_id": cid, "name": datos.get("name", ""),
                                    "effective_status": eff,
                                    "motivo": "Incompleta en Broquer pero activa en Meta. "
                                              "Revísala a mano antes de borrar."})
                elif limpiar:
                    rd = await _fb_request(client, "DELETE", str(cid),
                                           token=user_token, reintentos=2)
                    if rd is not None and rd.status_code in (200, 204):
                        await _fb_actualizar_entidad(row_id, {"status": "ELIMINADO"})
                        huerfanas.append({"campaign_id": cid, "name": datos.get("name", ""),
                                          "borrada": True})
                    else:
                        huerfanas.append({"campaign_id": cid, "name": datos.get("name", ""),
                                          "borrada": False,
                                          "detalle": _fb_friendly_error(
                                              rd.text if rd is not None else "", "No se pudo borrar")})
                else:
                    huerfanas.append({"campaign_id": cid, "name": datos.get("name", ""),
                                      "borrada": False,
                                      "detalle": "Manda {\"limpiar\": true} para borrarla."})
            else:
                sanas.append(cid)

    return {
        "ok": True,
        "revisadas": len(filas),
        "sanas": len(sanas),
        "huerfanas": huerfanas,
        "requieren_revision_manual": revisar,
        "corregidas": corregidas,
        "limpieza_aplicada": limpiar,
    }


@app.get("/facebook/page-posts")
async def facebook_page_posts(request: Request, page_id: str = ""):
    """Lista las últimas publicaciones de la página para promocionarlas.

    Si se pasa page_id por query, se usa esa página (resolviendo su page_token
    desde /me/accounts con el user_token). Si no, usa la página activa guardada.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    row = await _fb_get_meta_row(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta = row.get("meta") or {}
    user_token = meta.get("user_token", "")

    target_page_id = (page_id or meta.get("page_id", "")).strip()
    if not target_page_id:
        raise HTTPException(status_code=400, detail="No hay página seleccionada.")

    # Resolver el page_token correcto: si nos piden la página guardada usamos
    # api_key directo; si nos piden otra, resolvemos con user_token.
    if target_page_id == meta.get("page_id", ""):
        page_token = row.get("page_token", "")
    else:
        if not user_token:
            raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
        async with httpx.AsyncClient(timeout=10) as client:
            paginas = await _fb_paginate(
                client, "me/accounts", token=user_token,
                params={"fields": "id,access_token", "limit": "100"},
                prefix="No se pudieron resolver las páginas",
            )
        match = next((p for p in paginas if p.get("id") == target_page_id), None)
        if not match:
            raise HTTPException(status_code=400, detail="No administras esa página.")
        page_token = match.get("access_token", "")

    if not page_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    page_id = target_page_id

    # Traer las últimas 25 publicaciones de la página con campos útiles para la galería
    async with httpx.AsyncClient(timeout=15) as client:
        posts = await _fb_paginate(
            client, f"{page_id}/posts", token=page_token,
            params={
                "fields": "id,message,created_time,full_picture,permalink_url,"
                          "reactions.summary(true),comments.summary(true),shares,is_published",
                "limit": "25",
            },
            max_paginas=1, max_items=25,
            prefix="Error obteniendo publicaciones",
        )

    items = []
    for p in posts:
        if p.get("is_published") is False:
            continue
        msg = (p.get("message") or "").strip()
        items.append({
            "id": p["id"],                              # formato pageid_postid
            "message": msg[:280],
            "created_time": p.get("created_time", ""),
            "image": p.get("full_picture", ""),
            "permalink": p.get("permalink_url", ""),
            "reactions": ((p.get("reactions") or {}).get("summary") or {}).get("total_count", 0),
            "comments":  ((p.get("comments")  or {}).get("summary") or {}).get("total_count", 0),
            "shares":    (p.get("shares") or {}).get("count", 0),
            "has_image": bool(p.get("full_picture")),
        })

    return {"posts": items, "page_id": page_id}


@app.post("/facebook/campaign/toggle")
async def facebook_campaign_toggle(request: Request):
    """Activa o pausa una campaña y todos sus adsets y ads hijos.

    Este endpoint mueve DINERO: si dice "pausada" y no pausó, el agente sigue
    pagando sin saberlo. Por eso:
      1. Se revisa el resultado de CADA POST (antes se ignoraban todos y se
         devolvía {"ok": True} pasara lo que pasara).
      2. Los hijos se actualizan en batch (una petición HTTP en vez de N).
      3. Al final se RELEE effective_status desde Meta y se devuelve el estado
         verificado, no el que pedimos.
      4. Si algo quedó fuera, se devuelve 207 con el detalle de qué falló.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    body = await request.json()
    campaign_id = str(body.get("campaign_id", "") or "").strip()
    new_status = body.get("status", "PAUSED")
    if not campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id requerido")
    if new_status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail="status debe ser ACTIVE o PAUSED")
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    fallos: list[dict] = []

    def _anota_fallo(nivel: str, rid: str, resp) -> None:
        fallos.append({
            "nivel": nivel,
            "id": rid,
            "detalle": _fb_friendly_error(resp.text if resp is not None else "",
                                          f"No se pudo cambiar el {nivel}"),
        })

    async with httpx.AsyncClient(timeout=30) as client:
        # ── 1. Inventario de hijos (paginado: un limit=50 dejaba adsets fuera)
        adsets = await _fb_paginate(client, f"{campaign_id}/adsets", token=user_token,
                                    params={"fields": "id", "limit": "50"},
                                    prefix="Error leyendo los conjuntos de anuncios")
        adset_ids = [a["id"] for a in adsets if a.get("id")]

        ad_ids: list[str] = []
        for adset_id in adset_ids:
            try:
                ads = await _fb_paginate(client, f"{adset_id}/ads", token=user_token,
                                         params={"fields": "id", "limit": "50"},
                                         prefix="Error leyendo los anuncios")
                ad_ids.extend([a["id"] for a in ads if a.get("id")])
            except HTTPException as e:
                fallos.append({"nivel": "anuncios", "id": adset_id, "detalle": str(e.detail)})

        # ── 2. Aplicar el cambio ───────────────────────────────────────
        # Al ACTIVAR se va de abajo hacia arriba (Meta exige hijos activos
        # antes que el padre); al PAUSAR, de arriba hacia abajo, para cortar el
        # gasto en la campaña lo antes posible aunque falle algún hijo.
        if new_status == "ACTIVE":
            orden = [("anuncio", ad_ids), ("conjunto", adset_ids), ("campaña", [campaign_id])]
        else:
            orden = [("campaña", [campaign_id]), ("conjunto", adset_ids), ("anuncio", ad_ids)]

        for nivel, ids in orden:
            if not ids:
                continue
            if len(ids) == 1:
                rr = await _fb_request(client, "POST", str(ids[0]), token=user_token,
                                       json_body={"status": new_status})
                if rr is None or rr.status_code not in (200, 201):
                    _anota_fallo(nivel, ids[0], rr)
                continue
            # En el batch de Meta, los parámetros de un POST van en `body`
            # (form-encoded), no en el query string del relative_url.
            resultados = await _fb_batch(client, user_token, [
                {"method": "POST", "relative_url": str(rid),
                 "body": f"status={new_status}"} for rid in ids
            ])
            for rid, res in zip(ids, resultados):
                if res.get("code") not in (200, 201):
                    cuerpo = res.get("body")
                    fallos.append({
                        "nivel": nivel, "id": rid,
                        "detalle": _fb_friendly_error(
                            json.dumps(cuerpo) if isinstance(cuerpo, dict) else str(cuerpo),
                            f"No se pudo cambiar el {nivel}"),
                    })

        # ── 3. Verificar contra Meta lo que realmente quedó ────────────
        verificado = {}
        try:
            rv = await _fb_request(client, "GET", campaign_id, token=user_token,
                                   params={"fields": "status,effective_status"})
            if rv is not None and rv.status_code == 200:
                verificado = rv.json() or {}
        except Exception:
            pass

    estado_real = verificado.get("status") or ""
    ok = not fallos and (estado_real == new_status if estado_real else False)

    respuesta = {
        "ok": ok,
        "campaign_id": campaign_id,
        "status": estado_real or new_status,
        "status_solicitado": new_status,
        "effective_status": verificado.get("effective_status", ""),
        "adsets": len(adset_ids),
        "ads": len(ad_ids),
        "fallos": fallos,
    }
    if not ok:
        from fastapi.responses import JSONResponse
        # 207 Multi-Status: parte se aplicó y parte no. El frontend DEBE
        # enseñar esto — antes decía "listo" con la campaña todavía activa.
        resumen = "; ".join(f["detalle"] for f in fallos[:3]) or (
            f"Facebook reporta la campaña en {estado_real or 'estado desconocido'}, "
            f"no en {new_status}.")
        respuesta["detail"] = (
            f"El cambio quedó incompleto: {resumen}. "
            f"Revisa la campaña en Ads Manager antes de confiar en el estado."
        )
        return JSONResponse(status_code=207, content=respuesta)
    return respuesta


# ════════════════════════════════════════════════════════════════
# META — AUTODIAGNÓSTICO (solo contra cuenta de PRUEBAS)
# ════════════════════════════════════════════════════════════════
# Ejercita la integración de punta a punta contra una TEST AD ACCOUNT de Meta:
# crea campaña, conjunto, creativo y anuncio de verdad, los lee, los prende y
# apaga, y al final los borra. Las cuentas de prueba de Meta NO cobran.
#
# Tres candados para que esto no pueda correr contra producción:
#   1. FB_QA_ENABLED=1 en el entorno.
#   2. FB_QA_AD_ACCOUNT_ID apuntando explícitamente a la cuenta de pruebas.
#   3. Verificación CONTRA META de que esa cuenta aparece en la lista de
#      cuentas de prueba de la app (/{app_id}/adaccounts). Si no aparece, se
#      aborta. No hay bandera para saltarse este candado.

FB_QA_ENABLED = legacy_main_settings.fb_qa_enabled
FB_QA_AD_ACCOUNT_ID = legacy_main_settings.fb_qa_ad_account_id
FB_QA_PAGE_ID = legacy_main_settings.fb_qa_page_id


def _qa_imagen_jpeg(color=(120, 150, 200), tam=(600, 600)) -> str:
    """JPEG mínimo válido en base64. 600x600 es el mínimo que acepta Meta."""
    if not PIL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Pillow no disponible para generar imágenes de prueba.")
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


async def _qa_es_cuenta_de_pruebas(client: httpx.AsyncClient, token: str,
                                   account_id: str) -> tuple:
    """(es_de_pruebas, explicación). Le pregunta a Meta, no confía en el entorno."""
    if not FB_APP_ID or not FB_APP_SECRET:
        return False, "FB_APP_ID/FB_APP_SECRET no configurados: no se puede verificar."
    try:
        cuentas = await _fb_paginate(
            client, f"{FB_APP_ID}/adaccounts",
            token=f"{FB_APP_ID}|{FB_APP_SECRET}",
            params={"limit": "200"}, prefix="Error listando cuentas de prueba")
    except HTTPException as e:
        return False, f"No se pudo consultar la lista de cuentas de prueba: {e.detail}"

    ids = set()
    for c in cuentas:
        cid = str(c.get("id") or c.get("account_id") or "")
        if cid:
            ids.add(cid if cid.startswith("act_") else f"act_{cid}")
    if account_id in ids:
        return True, "Confirmada como cuenta de prueba de la app."
    return False, (
        f"{account_id} NO aparece en las cuentas de prueba de la app "
        f"({len(ids)} encontradas). El autodiagnóstico se niega a correr contra "
        f"una cuenta que podría ser de producción.")


@app.post("/facebook/qa-selfcheck")
async def facebook_qa_selfcheck(request: Request):
    """Ejercita la integración de Meta de punta a punta. Solo cuenta de pruebas.

    Devuelve un reporte paso por paso. Cada paso trae ok/detalle, así que si algo
    se rompe se ve exactamente dónde. No lanza en el primer fallo: sigue para
    dar el cuadro completo, salvo que falte una precondición.

    Body opcional:
      {"pasos": ["tokens","crear","insights","toggle","negativos","throttle","limpieza"]}
    """
    user_id = await exigir_gestion_integraciones(request)

    if not FB_QA_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="El autodiagnóstico está apagado. Enciéndelo con FB_QA_ENABLED=1 "
                   "y FB_QA_AD_ACCOUNT_ID apuntando a tu cuenta publicitaria de PRUEBAS.")
    if not FB_QA_AD_ACCOUNT_ID:
        raise HTTPException(status_code=400,
                            detail="Falta FB_QA_AD_ACCOUNT_ID (la cuenta de pruebas de Meta).")

    try:
        body = await request.json()
    except Exception:
        body = {}
    pedidos = set(body.get("pasos") or
                  ["tokens", "crear", "insights", "toggle", "negativos", "throttle", "limpieza"])

    meta_fb = await _get_fb_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook antes de correr el autodiagnóstico.")

    account_id = (FB_QA_AD_ACCOUNT_ID if FB_QA_AD_ACCOUNT_ID.startswith("act_")
                  else f"act_{FB_QA_AD_ACCOUNT_ID}")
    page_id = FB_QA_PAGE_ID or meta_fb.get("page_id", "")

    reporte: list = []
    creados: dict = {}

    def paso(nombre: str, ok: bool, detalle="", datos=None) -> None:
        reporte.append({"paso": nombre, "ok": bool(ok), "detalle": detalle,
                        "datos": datos if datos is not None else {}})

    async with httpx.AsyncClient(timeout=90) as client:

        # ── CANDADO: ¿es de verdad una cuenta de pruebas? ──────────────
        es_prueba, motivo = await _qa_es_cuenta_de_pruebas(client, user_token, account_id)
        paso("candado_cuenta_de_pruebas", es_prueba, motivo, {"account_id": account_id})
        if not es_prueba:
            return {"ok": False, "abortado": True, "account_id": account_id,
                    "motivo": motivo, "reporte": reporte}

        # ── 1. Tokens y permisos ───────────────────────────────────────
        if "tokens" in pedidos:
            info = await _fb_debug_token(client, user_token)
            if not info:
                paso("token_debug", False, "Meta no devolvió información del token.")
            else:
                scopes = info.get("scopes") or []
                faltantes = [s for s in _FB_SCOPES_REQUERIDOS if s not in scopes]
                expira = info.get("expires_at") or 0
                # 0 = no expira; si expira, debe faltar bastante más que una hora.
                segundos_restantes = (int(expira) - int(time.time())) if expira else -1
                larga_duracion = (expira == 0) or segundos_restantes > 7 * 24 * 3600
                paso("token_es_larga_duracion", larga_duracion,
                     "El token no expira (page token) o le quedan semanas." if larga_duracion
                     else f"El token expira en {max(segundos_restantes, 0) // 3600} h: "
                          f"NO es de larga duración.",
                     {"expires_at": expira, "segundos_restantes": segundos_restantes})
                paso("token_scopes", not faltantes,
                     "Todos los permisos requeridos están concedidos." if not faltantes
                     else f"Faltan permisos: {', '.join(faltantes)}",
                     {"scopes": scopes, "faltantes": faltantes})
                paso("token_es_valido", bool(info.get("is_valid")),
                     "Meta reporta el token como válido." if info.get("is_valid")
                     else "Meta reporta el token como INVÁLIDO.")

        # ── 2. Crear el anuncio completo ───────────────────────────────
        if "crear" in pedidos:
            if not page_id:
                paso("crear_anuncio", False,
                     "No hay page_id: define FB_QA_PAGE_ID o conecta una página.")
            else:
                nombre = f"[QA Broquer] {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}"
                try:
                    # 2a. Subir 3 imágenes
                    hashes = []
                    for i, color in enumerate([(200, 80, 80), (80, 200, 120), (80, 120, 200)]):
                        r = await _fb_request(client, "POST", f"{account_id}/adimages",
                                              token=user_token,
                                              json_body={"bytes": _qa_imagen_jpeg(color)})
                        if r is not None and r.status_code in (200, 201):
                            for v in (r.json().get("images") or {}).values():
                                if v.get("hash"):
                                    hashes.append(v["hash"])
                                break
                    paso("subir_3_imagenes", len(hashes) == 3,
                         f"{len(hashes)} de 3 imágenes subidas.", {"hashes": hashes})

                    # 2b. Campaña
                    r = await _fb_request(client, "POST", f"{account_id}/campaigns",
                                          token=user_token,
                                          json_body={"name": nombre,
                                                     "objective": "OUTCOME_ENGAGEMENT",
                                                     "status": "PAUSED",
                                                     "special_ad_categories": [],
                                                     "buying_type": "AUCTION"})
                    cid = (r.json().get("id") if r is not None and r.status_code in (200, 201) else "")
                    if cid:
                        creados["campaign_id"] = cid
                    paso("crear_campana", bool(cid),
                         "Campaña creada." if cid else
                         _fb_friendly_error(r.text if r is not None else "", "Falló"),
                         {"campaign_id": cid})

                    # 2c. Conjunto de anuncios
                    aid = ""
                    if cid:
                        fin = datetime.utcnow() + timedelta(days=7)
                        r = await _fb_request(
                            client, "POST", f"{account_id}/adsets", token=user_token,
                            json_body={
                                "name": f"{nombre} — AdSet", "campaign_id": cid,
                                "daily_budget": 5000, "billing_event": "IMPRESSIONS",
                                "optimization_goal": "CONVERSATIONS",
                                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                                "status": "PAUSED",
                                "promoted_object": {"page_id": page_id},
                                "destination_type": "MESSENGER",
                                "end_time": fin.strftime("%Y-%m-%dT%H:%M:%S+0000"),
                                "targeting": {
                                    "age_min": 25,
                                    "geo_locations": {"countries": ["MX"]},
                                    "targeting_automation": {"advantage_audience": 0},
                                },
                            })
                        aid = (r.json().get("id") if r is not None and r.status_code in (200, 201) else "")
                        if aid:
                            creados["adset_id"] = aid
                        paso("crear_conjunto", bool(aid),
                             "Conjunto creado." if aid else
                             _fb_friendly_error(r.text if r is not None else "", "Falló"),
                             {"adset_id": aid})

                    # 2d. Creativo carrusel
                    crid = ""
                    if aid and hashes:
                        hijos = [{"name": "QA", "image_hash": h,
                                  "call_to_action": {"type": "MESSAGE_PAGE",
                                                     "value": {"app_destination": "MESSENGER"}}}
                                 for h in hashes]
                        r = await _fb_request(
                            client, "POST", f"{account_id}/adcreatives", token=user_token,
                            json_body={"name": f"{nombre} — Creative",
                                       "object_story_spec": {
                                           "page_id": page_id,
                                           "link_data": {
                                               "message": "Prueba automática de Broquer.",
                                               "link": f"https://www.facebook.com/{page_id}",
                                               "child_attachments": hijos,
                                               "call_to_action": {
                                                   "type": "MESSAGE_PAGE",
                                                   "value": {"app_destination": "MESSENGER"}},
                                           }}})
                        crid = (r.json().get("id") if r is not None and r.status_code in (200, 201) else "")
                        if crid:
                            creados["creative_id"] = crid
                        paso("crear_creativo", bool(crid),
                             "Creativo carrusel creado." if crid else
                             _fb_friendly_error(r.text if r is not None else "", "Falló"),
                             {"creative_id": crid})

                    # 2e. Anuncio
                    adid = ""
                    if aid and crid:
                        r = await _fb_request(client, "POST", f"{account_id}/ads",
                                              token=user_token,
                                              json_body={"name": f"{nombre} — Ad",
                                                         "adset_id": aid,
                                                         "creative": {"creative_id": crid},
                                                         "status": "PAUSED"})
                        adid = (r.json().get("id") if r is not None and r.status_code in (200, 201) else "")
                        if adid:
                            creados["ad_id"] = adid
                        paso("crear_anuncio", bool(adid),
                             "Anuncio creado." if adid else
                             _fb_friendly_error(r.text if r is not None else "", "Falló"),
                             {"ad_id": adid})

                    # 2f. Todo debe nacer en PAUSED
                    if adid:
                        d = await _fb_get_json(client, adid, token=user_token,
                                               params={"fields": "status,effective_status"},
                                               prefix="Error releyendo el anuncio")
                        paso("nace_en_pausa", d.get("status") == "PAUSED",
                             f"status={d.get('status')} effective_status={d.get('effective_status')}",
                             d)
                except HTTPException as e:
                    paso("crear_anuncio", False, f"Excepción: {e.detail}")

        # ── 3. Insights ────────────────────────────────────────────────
        if "insights" in pedidos:
            try:
                filas = await _fb_paginate(
                    client, f"{account_id}/insights", token=user_token,
                    params={"level": "campaign",
                            "fields": _FB_INSIGHTS_FIELDS + ",campaign_id",
                            "date_preset": "last_30d", "limit": "50"},
                    prefix="Error leyendo métricas")
                # Una cuenta de pruebas casi nunca tiene datos: lo que se
                # verifica es que la LLAMADA funcione y que el normalizador
                # entregue las llaves esperadas, no que haya gasto.
                muestra = _fb_normaliza_insights(filas[0] if filas else {})
                esperadas = {"impressions", "reach", "spend", "conversaciones",
                             "costo_conversaciones", "actions"}
                paso("insights_llamada", True,
                     f"{len(filas)} fila(s) devueltas por Meta.", {"filas": len(filas)})
                paso("insights_normalizados", esperadas <= set(muestra.keys()),
                     "El normalizador entrega spend/reach/actions/conversaciones.",
                     {"llaves_faltantes": sorted(esperadas - set(muestra.keys()))})
            except HTTPException as e:
                paso("insights_llamada", False, str(e.detail))

        # ── 4. Prender y apagar, verificando en cada nivel ─────────────
        if "toggle" in pedidos and creados.get("campaign_id"):
            cid = creados["campaign_id"]
            for objetivo in ("ACTIVE", "PAUSED"):
                errores = []
                for nivel, rid in (("anuncio", creados.get("ad_id")),
                                   ("conjunto", creados.get("adset_id")),
                                   ("campaña", cid)):
                    if not rid:
                        continue
                    r = await _fb_request(client, "POST", str(rid), token=user_token,
                                          json_body={"status": objetivo})
                    if r is None or r.status_code not in (200, 201):
                        errores.append(f"{nivel}: " + _fb_friendly_error(
                            r.text if r is not None else "", "falló"))

                # Releer de Meta lo que REALMENTE quedó, nivel por nivel.
                estados = {}
                for nivel, rid in (("ad", creados.get("ad_id")),
                                   ("adset", creados.get("adset_id")),
                                   ("campaign", cid)):
                    if not rid:
                        continue
                    try:
                        estados[nivel] = await _fb_get_json(
                            client, str(rid), token=user_token,
                            params={"fields": "status,effective_status"},
                            prefix="Error releyendo")
                    except HTTPException as e:
                        estados[nivel] = {"error": str(e.detail)}

                coinciden = all(v.get("status") == objetivo for v in estados.values() if "error" not in v)
                paso(f"toggle_{objetivo.lower()}", coinciden and not errores,
                     "Los tres niveles quedaron en el estado pedido."
                     if coinciden and not errores
                     else "; ".join(errores) or "Algún nivel no quedó en el estado pedido.",
                     estados)

        # ── 5. Casos negativos ─────────────────────────────────────────
        if "negativos" in pedidos:
            # 5a. Imagen inválida → debe fallar con mensaje traducido
            r = await _fb_request(client, "POST", f"{account_id}/adimages",
                                  token=user_token,
                                  json_body={"bytes": base64.b64encode(b"esto no es una imagen").decode()},
                                  reintentos=1)
            rechazada = r is None or r.status_code not in (200, 201)
            mensaje = _fb_friendly_error(r.text if r is not None else "", "Imagen inválida")
            paso("negativo_imagen_invalida", rechazada,
                 mensaje if rechazada else "Meta ACEPTÓ una imagen inválida (inesperado).")
            paso("negativo_imagen_mensaje_legible", rechazada and "Imagen inválida" in mensaje,
                 "El error se traduce a un mensaje entendible.", {"mensaje": mensaje})

            # 5b. Presupuesto absurdo → debe fallar SIN dejar campaña huérfana
            nombre_h = f"[QA huérfana] {datetime.now(timezone.utc):%H:%M:%S}"
            r = await _fb_request(client, "POST", f"{account_id}/campaigns",
                                  token=user_token,
                                  json_body={"name": nombre_h, "objective": "OUTCOME_ENGAGEMENT",
                                             "status": "PAUSED", "special_ad_categories": [],
                                             "buying_type": "AUCTION"})
            cid_h = (r.json().get("id") if r is not None and r.status_code in (200, 201) else "")
            if cid_h:
                r2 = await _fb_request(
                    client, "POST", f"{account_id}/adsets", token=user_token,
                    json_body={"name": f"{nombre_h} — AdSet", "campaign_id": cid_h,
                               "daily_budget": 99999999999,   # absurdo a propósito
                               "billing_event": "IMPRESSIONS",
                               "optimization_goal": "CONVERSATIONS",
                               "status": "PAUSED",
                               "targeting": {"geo_locations": {"countries": ["MX"]},
                                             "targeting_automation": {"advantage_audience": 0}}},
                    reintentos=1)
                fallo_esperado = r2 is None or r2.status_code not in (200, 201)
                # Limpieza igual que hace create-ad: la campaña NO debe quedarse.
                rd = await _fb_request(client, "DELETE", cid_h, token=user_token, reintentos=2)
                borrada = rd is not None and rd.status_code in (200, 204)
                rv = await _fb_request(client, "GET", cid_h, token=user_token,
                                       params={"fields": "id"}, reintentos=1)
                desaparecio = rv is None or rv.status_code != 200
                paso("negativo_presupuesto_excesivo", fallo_esperado,
                     _fb_friendly_error(r2.text if r2 is not None else "", "Presupuesto excesivo")
                     if fallo_esperado else "Meta aceptó un presupuesto absurdo (inesperado).")
                paso("negativo_sin_huerfanos", borrada and desaparecio,
                     "La campaña del intento fallido se borró y ya no existe."
                     if borrada and desaparecio
                     else f"QUEDÓ HUÉRFANA: {cid_h}. Bórrala a mano en Ads Manager.",
                     {"campaign_id": cid_h, "borrada": borrada, "desaparecio": desaparecio})
            else:
                paso("negativo_presupuesto_excesivo", False,
                     "No se pudo crear la campaña de prueba para el caso negativo.")

            # 5c. Página que la cuenta no puede anunciar
            try:
                promocionables = [p.get("id") for p in await _fb_paginate(
                    client, f"{account_id}/promote_pages", token=user_token,
                    params={"fields": "id", "limit": "100"}, prefix="promote_pages")]
                detecta = bool(promocionables) and page_id in promocionables
                paso("negativo_pagina_cuenta_correcta", True,
                     f"La cuenta puede anunciar {len(promocionables)} página(s); "
                     f"la configurada {'SÍ' if detecta else 'NO'} está entre ellas.",
                     {"promote_pages": promocionables, "page_id": page_id})
            except HTTPException as e:
                paso("negativo_pagina_cuenta_correcta", False, str(e.detail))

        # ── 6. Limpieza ────────────────────────────────────────────────
        if "limpieza" in pedidos and creados.get("campaign_id"):
            cid = creados["campaign_id"]
            rd = await _fb_request(client, "DELETE", cid, token=user_token, reintentos=3)
            borrada = rd is not None and rd.status_code in (200, 204)
            rv = await _fb_request(client, "GET", cid, token=user_token,
                                   params={"fields": "id"}, reintentos=1)
            desaparecio = rv is None or rv.status_code != 200
            paso("limpieza_campana_borrada", borrada and desaparecio,
                 "La campaña de prueba se borró y ya no existe en Meta."
                 if borrada and desaparecio
                 else f"NO se pudo borrar {cid}. Bórrala a mano en Ads Manager.",
                 {"campaign_id": cid, "borrada": borrada, "ya_no_existe": desaparecio})

    # ── 7. Backoff ante 429 (en proceso, sin tocar Meta) ───────────────
    if "throttle" in pedidos:
        resultado = await _qa_probar_backoff()
        paso("throttle_backoff_429", resultado["ok"], resultado["detalle"], resultado)

    fallidos = [p for p in reporte if not p["ok"]]
    return {
        "ok": not fallidos,
        "account_id": account_id,
        "page_id": page_id,
        "total": len(reporte),
        "fallidos": len(fallidos),
        "resumen": ("Todo en orden." if not fallidos
                    else "Fallaron: " + ", ".join(p["paso"] for p in fallidos)),
        "recursos_creados": creados,
        "reporte": reporte,
    }


async def _qa_probar_backoff() -> dict:
    """Comprueba que _fb_request se recupera de un 429 sin salir a internet.

    Se le pone un transporte falso que contesta 429 con Retry-After las
    primeras veces y luego 200. Si el wrapper reintenta y respeta la espera,
    la llamada termina en 200.
    """
    intentos = {"n": 0}

    def responder(req: httpx.Request) -> httpx.Response:
        intentos["n"] += 1
        if intentos["n"] <= 2:
            return httpx.Response(
                429,
                headers={"Retry-After": "0",
                         "X-Business-Use-Case-Usage": json.dumps(
                             {"1": [{"type": "ads_management", "call_count": 100,
                                     "total_cputime": 100, "total_time": 100,
                                     "estimated_time_to_regain_access": 0}]})},
                json={"error": {"message": "User request limit reached",
                                "code": 17, "type": "OAuthException"}})
        return httpx.Response(200, json={"data": [], "ok": True})

    inicio = time.monotonic()
    try:
        transporte = httpx.MockTransport(responder)
        async with httpx.AsyncClient(transport=transporte) as client:
            # espera_base corta para que el diagnóstico no tarde. Va como
            # parámetro, no tocando el global: si dos diagnósticos corren a la
            # vez no se pisan la configuración de reintentos del resto de la app.
            r = await _fb_request(client, "GET", "me/adaccounts", token="fake",
                                  espera_base=0.05, espera_max=0.2)
    except Exception as e:
        return {"ok": False, "detalle": f"El wrapper lanzó excepción: {e}", "intentos": intentos["n"]}

    duracion = time.monotonic() - inicio
    ok = r is not None and r.status_code == 200 and intentos["n"] == 3
    return {
        "ok": ok,
        "detalle": (f"Se recuperó del 429 tras {intentos['n']} intentos "
                    f"({duracion:.2f}s) y terminó en 200."
                    if ok else
                    f"No se recuperó: {intentos['n']} intentos, "
                    f"status final {getattr(r, 'status_code', 'ninguno')}."),
        "intentos": intentos["n"],
        "status_final": getattr(r, "status_code", None),
        "segundos": round(duracion, 3),
    }


# ════════════════════════════════════════════════════════════════
# STRIPE — SUSCRIPCIONES
# ════════════════════════════════════════════════════════════════

STRIPE_SECRET_KEY      = settings.stripe_secret_key
STRIPE_WEBHOOK_SECRET  = legacy_main_settings.stripe_webhook_secret

# IDs de Precios en Stripe (crear en dashboard.stripe.com → Productos → Precios)
STRIPE_PRICE_PRO       = legacy_main_settings.stripe_price_pro       # Plan Broquer Pro
STRIPE_PRICE_AMPI      = legacy_main_settings.stripe_price_ampi      # Plan AMPI (precio especial)

# ── Broquer para Empresas ────────────────────────────────────────
# Se cobra en DOS líneas dentro de la misma suscripción de Stripe:
#   · base  → paquete de 5 usuarios, cantidad siempre 1
#   · extra → usuario adicional, cantidad = asientos - 5
# Así el dueño puede subir o bajar lugares sin cambiar de suscripción.
STRIPE_PRICE_EMPRESA_MENSUAL       = legacy_main_settings.stripe_price_empresa_mensual
STRIPE_PRICE_EMPRESA_ANUAL         = legacy_main_settings.stripe_price_empresa_anual
STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL = legacy_main_settings.stripe_price_empresa_extra_mensual
STRIPE_PRICE_EMPRESA_EXTRA_ANUAL   = legacy_main_settings.stripe_price_empresa_extra_anual

EMPRESA_ASIENTOS_BASE = 5      # lugares incluidos en el precio base
EMPRESA_ASIENTOS_MAX  = 500    # tope duro para no crear cargos absurdos por error

# Solo para pintar la pantalla. El cobro real siempre lo manda Stripe.
EMPRESA_TARIFAS = {
    "mensual": {"base": 3499, "extra": 599, "etiqueta": "al mes"},
    "anual":   {"base": 38489, "extra": 6589, "etiqueta": "al año"},   # 11 meses
}


def _precio_empresa(periodo: str, extra: bool = False) -> str:
    """Devuelve el price_id de Stripe para el periodo pedido."""
    if periodo == "anual":
        return STRIPE_PRICE_EMPRESA_EXTRA_ANUAL if extra else STRIPE_PRICE_EMPRESA_ANUAL
    return STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL if extra else STRIPE_PRICE_EMPRESA_MENSUAL


async def _sb_service_get(tabla: str, params: dict) -> list:
    """GET a Supabase con service key. Devuelve [] si algo falla."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{tabla}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params=params,
        )
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except Exception:
        return []


async def _sb_service_patch(tabla: str, params: dict, payload: dict) -> None:
    """PATCH a Supabase con service key."""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/{tabla}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "return=minimal"},
            params=params, json=payload,
        )


async def _exigir_admin_de_org(request: Request) -> dict:
    """Quien contrata o modifica el plan de la empresa tiene que ser el dueño
    (o un administrador) de su propia cuenta. Un agente invitado no puede."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")
    if ctx.get("rol_org") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Solo el dueño de la cuenta puede contratar o cambiar el plan de la empresa.")
    ctx["user_id"] = user_id
    return ctx

# Código promocional para el plan AMPI (válido en Supabase tabla promo_codes)
PROMO_CODE_AMPI = "ampi2026"

def _stripe_headers() -> dict:
    return {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

TRIAL_MAX_DIAS = 7

async def _trial_max_disponible(user_id: str) -> bool:
    """El regalo de 7 días de Broquer Max es UNA sola vez por cuenta.
    No aplica si el usuario ya tuvo cualquier suscripción (activa, cancelada
    o en prueba) ni si ya quemó su trial aunque la fila se haya borrado."""
    try:
        u = await _sb_service_get("usuarios", {
            "id": f"eq.{user_id}", "select": "trial_max_usado", "limit": "1"})
        if u and u[0].get("trial_max_usado"):
            return False
        subs = await _sb_service_get("suscripciones", {
            "user_id": f"eq.{user_id}", "select": "id", "limit": "1"})
        return not subs
    except Exception:
        # Ante la duda NO se regala el trial: es dinero.
        return False


class CheckoutRequest(BaseModel):
    plan_id: str         # "max" o "ampi"
    promo_code: str = "" # código promocional para plan AMPI
    success_url: str = ""
    cancel_url: str  = ""

async def _get_or_create_stripe_customer(user_id: str, email: str, nombre: str) -> str:
    """
    Busca el stripe_customer_id del usuario en Supabase.
    Si no existe, crea un nuevo Customer en Stripe y lo guarda.
    Devuelve el stripe_customer_id (string).
    """
    # 1. Buscar en Supabase
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "stripe_customer_id,nombre"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        rows = []
    row = rows[0] if rows else {}

    if row.get("stripe_customer_id"):
        return row["stripe_customer_id"]

    # 2. Crear Customer en Stripe
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.stripe.com/v1/customers",
            headers=_stripe_headers(),
            data={"name": nombre or email, "email": email, "metadata[user_id]": user_id},
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe crear customer: {r.text}")
    customer_id = r.json().get("id")

    # 3. Guardar en Supabase
    async with httpx.AsyncClient(timeout=10) as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"stripe_customer_id": customer_id}
        )

    return customer_id


@app.post("/subscription/checkout")
async def subscription_checkout(req: CheckoutRequest, request: Request):
    """
    Crea una Stripe Checkout Session y devuelve la URL de pago.
    El frontend redirige al usuario a esa URL; Stripe maneja todo el pago.
    Flujo:
      1. Validar JWT → obtener user_id + email
      2. Validar plan_id
      3. Si plan AMPI: verificar código promo
      4. Obtener o crear Customer en Stripe
      5. Crear Checkout Session (modo suscripción)
      6. Devolver {checkout_url}
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    # Validar plan
    plan_map = {"max": STRIPE_PRICE_PRO, "ampi": STRIPE_PRICE_AMPI}
    if req.plan_id not in plan_map:
        raise HTTPException(status_code=400, detail="Plan inválido.")
    price_id = plan_map[req.plan_id]
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Precio Stripe no configurado para el plan '{req.plan_id}'.")

    # Validar código promo si es plan AMPI
    if req.plan_id == "ampi":
        if req.promo_code.strip().lower() != PROMO_CODE_AMPI.lower():
            raise HTTPException(status_code=400, detail="Código promocional inválido para el plan AMPI.")

    # Obtener datos del usuario
    auth_tok = request.headers.get("Authorization", "")[7:]
    async with httpx.AsyncClient(timeout=10) as client:
        r_user = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth_tok}"}
        )
    if r_user.status_code != 200:
        raise HTTPException(status_code=401, detail="No se pudo verificar el usuario.")
    email = r_user.json().get("email", "")

    try:
        filas_nombre = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "nombre"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        filas_nombre = []
    nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)

    # Obtener o crear Customer en Stripe
    customer_id = await _get_or_create_stripe_customer(user_id, email, nombre)

    # URLs de retorno (el frontend puede enviarlas o usamos defaults)
    origin = request.headers.get("origin", "https://navarroai.github.io/Brokr")
    success_url = req.success_url or f"{origin}/index.html?suscripcion=ok"
    cancel_url  = req.cancel_url  or f"{origin}/index.html?suscripcion=cancelada"

    # ¿Le toca el regalo de bienvenida? 7 días de Broquer Max sin costo,
    # solo para quien nunca ha tenido suscripción. Stripe pide la tarjeta
    # pero no cobra nada hasta que termina la prueba.
    con_trial = await _trial_max_disponible(user_id)

    # Crear Checkout Session
    data = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[user_id]": user_id,
        "metadata[plan_id]": req.plan_id,
        "allow_promotion_codes": "true",
        "locale": "es",
    }
    if con_trial:
        data["subscription_data[trial_period_days]"] = str(TRIAL_MAX_DIAS)
        data["metadata[trial]"] = "1"
    async with httpx.AsyncClient(timeout=15) as client:
        r_cs = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            headers=_stripe_headers(),
            data=data,
        )
    if r_cs.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe checkout session: {r_cs.text}")

    session = r_cs.json()
    return {"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id")}


# ════════════════════════════════════════════════════════════════
# BROQUER PARA EMPRESAS — contratación y lugares
# ════════════════════════════════════════════════════════════════

class EmpresaCheckoutRequest(BaseModel):
    asientos: int = EMPRESA_ASIENTOS_BASE
    periodo: str = "mensual"        # mensual | anual
    nombre_empresa: str = ""
    success_url: str = ""
    cancel_url: str = ""


class EmpresaAsientosRequest(BaseModel):
    asientos: int


def _valida_asientos(n: int) -> int:
    try:
        n = int(n)
    except Exception:
        raise HTTPException(status_code=400, detail="Número de lugares inválido.")
    if n < EMPRESA_ASIENTOS_BASE:
        raise HTTPException(
            status_code=400,
            detail=f"El plan de empresas empieza en {EMPRESA_ASIENTOS_BASE} lugares.")
    if n > EMPRESA_ASIENTOS_MAX:
        raise HTTPException(status_code=400, detail="Para más lugares escríbenos a soporte.")
    return n


async def _ocupacion_org(org_id: str) -> dict:
    """Cuántos lugares están usados: miembros activos + invitaciones pendientes."""
    miembros = await _sb_service_get("organizacion_miembros",
                                     {"org_id": f"eq.{org_id}", "activo": "eq.true", "select": "id"})
    invitaciones = await _sb_service_get("organizacion_invitaciones",
                                         {"org_id": f"eq.{org_id}", "aceptada_el": "is.null", "select": "id"})
    return {"miembros": len(miembros), "invitaciones": len(invitaciones),
            "usados": len(miembros) + len(invitaciones)}


@app.get("/subscription/empresa/plan")
async def empresa_plan(request: Request):
    """Estado del plan de empresa del usuario. Alimenta la pantalla de compra:
    tarifas, lugares contratados y cuántos ya están ocupados."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        return {"tiene_org": False, "tarifas": EMPRESA_TARIFAS,
                "asientos_base": EMPRESA_ASIENTOS_BASE, "asientos_max": EMPRESA_ASIENTOS_MAX}

    ocup = await _ocupacion_org(ctx["org_id"])
    sub = await _sb_service_get("suscripciones", {
        "org_id": f"eq.{ctx['org_id']}", "select": "plan_id,plan_nombre,status,periodo,updated_at",
        "order": "updated_at.desc", "limit": "1",
    })
    sub = sub[0] if sub else {}

    return {
        "tiene_org": True,
        "org_id": ctx["org_id"],
        "nombre": ctx.get("org_nombre"),
        "es_empresa": ctx.get("org_tipo") == "empresa",
        "es_admin": ctx.get("rol_org") in ("owner", "admin"),
        "activa": bool(ctx.get("org_activo", True)) and sub.get("status") in ("active", "trialing"),
        "status": sub.get("status"),
        "periodo": sub.get("periodo"),
        "plan_id": sub.get("plan_id"),
        "asientos_contratados": ctx.get("asientos_max"),
        "asientos_base": EMPRESA_ASIENTOS_BASE,
        "asientos_max": EMPRESA_ASIENTOS_MAX,
        "ocupacion": ocup,
        "tarifas": EMPRESA_TARIFAS,
    }


@app.post("/subscription/empresa/checkout")
async def empresa_checkout(req: EmpresaCheckoutRequest, request: Request):
    """Crea la Checkout Session de Broquer para Empresas.
    Cobro web únicamente: la app de iOS nunca abre este flujo (regla 3.1.3(c))."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    ctx = await _exigir_admin_de_org(request)
    user_id = ctx["user_id"]

    periodo = (req.periodo or "mensual").strip().lower()
    if periodo not in ("mensual", "anual"):
        raise HTTPException(status_code=400, detail="El periodo debe ser mensual o anual.")

    asientos = _valida_asientos(req.asientos)
    price_base  = _precio_empresa(periodo, extra=False)
    price_extra = _precio_empresa(periodo, extra=True)
    if not price_base:
        raise HTTPException(status_code=500,
                            detail=f"Falta configurar el precio de empresas ({periodo}) en Stripe.")
    extras = asientos - EMPRESA_ASIENTOS_BASE
    if extras > 0 and not price_extra:
        raise HTTPException(status_code=500,
                            detail=f"Falta configurar el precio de usuario adicional ({periodo}) en Stripe.")

    # Nunca dejar la empresa con menos lugares de los que ya usa.
    ocup = await _ocupacion_org(ctx["org_id"])
    if asientos < ocup["usados"]:
        raise HTTPException(
            status_code=400,
            detail=f"Ya tienes {ocup['usados']} lugares ocupados. Contrata al menos esa cantidad.")

    auth_tok = request.headers.get("Authorization", "")[7:]
    async with httpx.AsyncClient(timeout=10) as client:
        r_user = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth_tok}"})
    if r_user.status_code != 200:
        raise HTTPException(status_code=401, detail="No se pudo verificar el usuario.")
    email = r_user.json().get("email", "")

    filas = await _sb_service_get("usuarios", {"id": f"eq.{user_id}", "select": "nombre"})
    nombre = (filas[0] if filas else {}).get("nombre") or email

    customer_id = await _get_or_create_stripe_customer(user_id, email, nombre)

    origin = request.headers.get("origin", "https://broquer.app")
    success_url = req.success_url or f"{origin}/equipo.html?empresa=ok"
    cancel_url  = req.cancel_url  or f"{origin}/empresas.html?empresa=cancelada"

    nombre_empresa = (req.nombre_empresa or "").strip()[:120] or (ctx.get("org_nombre") or nombre)

    data = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items[0][price]": price_base,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[user_id]": user_id,
        "metadata[plan_id]": "empresas",
        "metadata[org_id]": ctx["org_id"],
        "metadata[asientos]": str(asientos),
        "metadata[periodo]": periodo,
        "metadata[nombre_empresa]": nombre_empresa,
        "subscription_data[metadata][user_id]": user_id,
        "subscription_data[metadata][plan_id]": "empresas",
        "subscription_data[metadata][org_id]": ctx["org_id"],
        "allow_promotion_codes": "true",
        "locale": "es",
    }
    if extras > 0:
        data["line_items[1][price]"] = price_extra
        data["line_items[1][quantity]"] = str(extras)

    async with httpx.AsyncClient(timeout=15) as client:
        r_cs = await client.post("https://api.stripe.com/v1/checkout/sessions",
                                 headers=_stripe_headers(), data=data)
    if r_cs.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe checkout session: {r_cs.text}")

    session = r_cs.json()
    return {"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id"),
            "asientos": asientos, "periodo": periodo}


async def _activar_empresa(org_id: str, user_id: str, asientos: int,
                           nombre_empresa: str = "") -> None:
    """Deja la organización lista para operar como empresa tras el pago."""
    payload = {
        "tipo": "empresa",
        "plan": "Broquer para Empresas",
        "asientos_max": int(asientos),
        "activo": True,
        "vence_el": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if nombre_empresa:
        payload["nombre"] = nombre_empresa[:120]
    await _sb_service_patch("organizaciones", {"id": f"eq.{org_id}"}, payload)
    # El titular tiene que ser owner para poder invitar a su equipo.
    await _sb_service_patch("organizacion_miembros",
                            {"user_id": f"eq.{user_id}", "org_id": f"eq.{org_id}"},
                            {"rol_org": "owner"})


@app.post("/subscription/empresa/asientos")
async def empresa_asientos(req: EmpresaAsientosRequest, request: Request):
    """Sube o baja los lugares contratados sin cambiar de suscripción.
    Stripe prorratea la diferencia en la siguiente factura."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    ctx = await _exigir_admin_de_org(request)
    asientos = _valida_asientos(req.asientos)

    ocup = await _ocupacion_org(ctx["org_id"])
    if asientos < ocup["usados"]:
        raise HTTPException(
            status_code=400,
            detail=f"Tienes {ocup['usados']} lugares ocupados. Da de baja a alguien antes de reducir.")

    filas = await _sb_service_get("suscripciones", {
        "org_id": f"eq.{ctx['org_id']}", "plan_id": "eq.empresas",
        "select": "stripe_subscription_id,periodo,status",
        "order": "updated_at.desc", "limit": "1"})
    row = filas[0] if filas else {}
    sub_id = row.get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=404, detail="No encontré una suscripción de empresa activa.")

    async with httpx.AsyncClient(timeout=15) as client:
        r_sub = await client.get(f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                                 headers=_stripe_headers())
    if r_sub.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Stripe suscripción: {r_sub.text}")
    items = r_sub.json().get("items", {}).get("data", [])

    periodo = row.get("periodo") or "mensual"
    price_base  = _precio_empresa(periodo, extra=False)
    price_extra = _precio_empresa(periodo, extra=True)
    # Si el periodo guardado no cuadra con lo que hay en Stripe, se deduce.
    if not any((it.get("price") or {}).get("id") == price_base for it in items):
        for alt in ("mensual", "anual"):
            if any((it.get("price") or {}).get("id") == _precio_empresa(alt) for it in items):
                periodo = alt
                price_base  = _precio_empresa(alt, extra=False)
                price_extra = _precio_empresa(alt, extra=True)
                break

    item_extra = next((it for it in items if (it.get("price") or {}).get("id") == price_extra), None)
    extras = asientos - EMPRESA_ASIENTOS_BASE

    async with httpx.AsyncClient(timeout=15) as client:
        if item_extra and extras > 0:
            r = await client.post(
                f"https://api.stripe.com/v1/subscription_items/{item_extra['id']}",
                headers=_stripe_headers(),
                data={"quantity": str(extras), "proration_behavior": "create_prorations"})
        elif item_extra and extras == 0:
            r = await client.delete(
                f"https://api.stripe.com/v1/subscription_items/{item_extra['id']}",
                headers=_stripe_headers(),
                params={"proration_behavior": "create_prorations"})
        elif extras > 0:
            if not price_extra:
                raise HTTPException(status_code=500,
                                    detail="Falta configurar el precio de usuario adicional en Stripe.")
            r = await client.post(
                "https://api.stripe.com/v1/subscription_items",
                headers=_stripe_headers(),
                data={"subscription": sub_id, "price": price_extra, "quantity": str(extras),
                      "proration_behavior": "create_prorations"})
        else:
            r = None

    if r is not None and r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe lugares: {r.text}")

    await _sb_service_patch("organizaciones", {"id": f"eq.{ctx['org_id']}"},
                            {"asientos_max": asientos,
                             "updated_at": datetime.utcnow().isoformat()})

    return {"ok": True, "asientos": asientos, "periodo": periodo, "ocupacion": ocup}


@app.post("/subscription/webhook")
async def stripe_webhook(request: Request):
    """
    Recibe eventos de Stripe (stripe listen → o endpoint configurado en dashboard).
    Actualiza el estado de suscripción en Supabase de forma automática.
    Configura en Stripe Dashboard: checkout.session.completed,
    customer.subscription.updated, customer.subscription.deleted,
    invoice.payment_failed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Verificar firma del webhook. Sin secreto NO se procesa: antes, si la
    # variable faltaba en Railway, cualquiera podía mandar un evento inventado
    # de "pago exitoso" y activarse el plan.
    if not STRIPE_WEBHOOK_SECRET:
        print("[stripe] STRIPE_WEBHOOK_SECRET no configurado: webhook cerrado.")
        raise HTTPException(status_code=503, detail="Webhook no disponible.")
    if STRIPE_WEBHOOK_SECRET:
        try:
            import hmac as _hmac, hashlib as _hashlib, time as _time
            parts = {p.split("=")[0]: p.split("=")[1] for p in sig_header.split(",") if "=" in p}
            ts = parts.get("t", "")
            v1 = parts.get("v1", "")
            signed_payload = f"{ts}.{payload.decode()}"
            expected = _hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed_payload.encode(), _hashlib.sha256).hexdigest()
            if not _hmac.compare_digest(expected, v1):
                raise HTTPException(status_code=400, detail="Firma de webhook inválida.")
        except Exception:
            raise HTTPException(status_code=400, detail="Error verificando webhook.")

    event = await request.json()
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        meta = obj.get("metadata", {}) or {}
        user_id = meta.get("user_id")
        plan_id = meta.get("plan_id", "max")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if user_id and subscription_id:
            plan_nombre = {"ampi": "AMPI", "empresas": "Broquer para Empresas"}.get(plan_id, "Broquer Max")
            _org_id = meta.get("org_id") or await get_org_id_for_user(user_id)
            _es_trial = meta.get("trial") == "1"
            sb = {
                "user_id": user_id,
                "org_id": _org_id,
                "plan_id": plan_id,
                "plan_nombre": plan_nombre,
                "stripe_subscription_id": subscription_id,
                "stripe_customer_id": customer_id,
                "status": "trialing" if _es_trial else "active",
                "updated_at": datetime.utcnow().isoformat(),
            }
            if _es_trial:
                # Se quema el trial de por vida, aunque después cancele o
                # se borre la fila de suscripciones.
                await _sb_service_patch("usuarios", {"id": f"eq.{user_id}"},
                                        {"trial_max_usado": True})
            if plan_id == "empresas":
                # El plan de empresas guarda periodo y lugares: se necesitan
                # después para prorratear altas y bajas de usuarios.
                try:
                    _asientos = int(meta.get("asientos") or EMPRESA_ASIENTOS_BASE)
                except Exception:
                    _asientos = EMPRESA_ASIENTOS_BASE
                sb["periodo"] = meta.get("periodo") or "mensual"
                sb["asientos"] = _asientos
                if _org_id:
                    await _activar_empresa(_org_id, user_id, _asientos,
                                           meta.get("nombre_empresa") or "")
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/suscripciones",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    json=sb,
                )

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription_id = obj.get("id")
        new_status = obj.get("status", "canceled")
        if event_type == "customer.subscription.deleted":
            new_status = "canceled"
        if subscription_id:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/suscripciones?stripe_subscription_id=eq.{subscription_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    json={"status": new_status, "updated_at": datetime.utcnow().isoformat()}
                )
            # En empresas el acceso de TODO el equipo cuelga de organizaciones.activo.
            _filas = await _sb_service_get("suscripciones", {
                "stripe_subscription_id": f"eq.{subscription_id}",
                "select": "org_id,plan_id", "limit": "1"})
            _fila = _filas[0] if _filas else {}
            if _fila.get("plan_id") == "empresas" and _fila.get("org_id"):
                await _sb_service_patch(
                    "organizaciones", {"id": f"eq.{_fila['org_id']}"},
                    {"activo": new_status in ("active", "trialing"),
                     "updated_at": datetime.utcnow().isoformat()})

    elif event_type == "invoice.payment_failed":
        subscription_id = obj.get("subscription")
        if subscription_id:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/suscripciones?stripe_subscription_id=eq.{subscription_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    json={"status": "past_due", "updated_at": datetime.utcnow().isoformat()}
                )

    return {"ok": True}


@app.post("/subscription/activate")
async def subscription_activate(request: Request):
    """
    Endpoint simple para Zapier.
    Recibe { customer_id, plan_id? } y activa la suscripción en Supabase.
    No requiere JWT — usa una clave secreta interna.
    """
    ACTIVATE_SECRET = legacy_main_settings.activate_secret
    body = await request.json()

    # Sin clave configurada NO se activa nada. Antes, si la variable faltaba en
    # Railway, este endpoint regalaba suscripciones a cualquiera que lo llamara.
    if not ACTIVATE_SECRET:
        print("[subscription] ACTIVATE_SECRET no configurado: endpoint cerrado.")
        raise HTTPException(status_code=503, detail="Activación no disponible.")
    if not hmac_compare(body.get("secret", ""), ACTIVATE_SECRET):
        raise HTTPException(status_code=403, detail="No autorizado.")

    customer_id = body.get("customer_id", "").strip()
    plan_id = body.get("plan_id", "max").strip() or "max"

    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id requerido.")

    # Buscar user_id por stripe_customer_id en tabla usuarios
    try:
        usuarios = await get_rows(
            "usuarios",
            {"stripe_customer_id": f"eq.{customer_id}", "select": "id,nombre,email"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        usuarios = []

    if not usuarios:
        raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")

    usuario = usuarios[0]
    user_id = usuario["id"]
    plan_nombre = "AMPI" if plan_id == "ampi" else "Broquer Max"

    sb = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": plan_id,
        "plan_nombre": plan_nombre,
        "stripe_customer_id": customer_id,
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
    }

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=sb,
        )

    return {"ok": True, "user_id": user_id, "plan": plan_nombre}


@app.get("/subscription/status")
async def subscription_status(request: Request):
    """Devuelve el estado actual de la suscripción del usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    # Verificar rol y estado activo en una sola llamada
    access = await get_user_access_state(user_id)
    rol = access["rol"]
    activo = access["activo"]

    # Cuenta desactivada: bloquear acceso sin importar rol o suscripción
    if not activo:
        return {"active": False, "plan": None, "plan_id": None, "status": "desactivada"}

    # Equipo interno y admin siempre tienen acceso activo sin necesidad de suscripción
    if rol in ("equipo", "admin"):
        return {"active": True, "plan": "Equipo Interno" if rol == "equipo" else "Admin", "plan_id": rol, "status": "active"}

    # Empresas: el acceso de todo el equipo cuelga de la organización
    # (activo + vence_el). Lo enciende y apaga el webhook de Stripe cuando el
    # dueño contrata, cambia lugares o deja de pagar; y admin.html puede
    # activarlo a mano para casos negociados.
    _ctx = await get_org_context(user_id)
    if _ctx and _ctx.get("org_tipo") == "empresa":
        _vigente = _ctx.get("org_activo", True)
        _vence = _ctx.get("vence_el")
        if _vigente and _vence:
            try:
                from datetime import timezone as _tz
                _vigente = datetime.fromisoformat(str(_vence).replace("Z", "+00:00")) > datetime.now(_tz.utc)
            except Exception:
                pass
        return {
            "active": bool(_vigente),
            "plan": _ctx.get("org_plan") or "Empresas",
            "plan_id": "empresas",
            "status": "active" if _vigente else "vencida",
        }

    _oid = await get_org_id_for_user(user_id)
    try:
        subscription_rows = await get_rows(
            "suscripciones",
            {"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        subscription_rows = []
    if not subscription_rows:
        return {"active": False, "plan": None, "status": "sin_suscripcion",
                "trial_disponible": await _trial_max_disponible(user_id)}

    row = subscription_rows[0]
    estado = row.get("status")
    activo_sub = estado in ("active", "trialing")
    # Trial sin tarjeta: al vencer trial_hasta el candado se cierra solo.
    # Las suscripciones de Stripe/RevenueCat no traen trial_hasta y no se tocan.
    if estado == "trialing" and row.get("trial_hasta") and _trial_ya_vencio(row.get("trial_hasta")):
        activo_sub = False
        estado = "trial_vencido"
        asyncio.create_task(_expirar_trial_suscripcion(row.get("id")))
    return {
        "active": activo_sub,
        "plan": row.get("plan_nombre"),
        "plan_id": row.get("plan_id"),
        "status": estado,
        "trial_hasta": row.get("trial_hasta"),
        "updated_at": row.get("updated_at"),
        "trial_disponible": (await _trial_max_disponible(user_id)) if not activo_sub else False,
    }


# ════════════════════════════════════════════════════════════════
# Trial de Broquer Max SIN tarjeta (7 días, una sola vez por cuenta)
# ════════════════════════════════════════════════════════════════

def _trial_ya_vencio(trial_hasta) -> bool:
    """True si la fecha de vencimiento del trial ya pasó."""
    try:
        return datetime.fromisoformat(str(trial_hasta).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except Exception:
        return False


async def _expirar_trial_suscripcion(sub_id) -> None:
    """Marca la fila del trial como expirada. Fallar aquí no es grave:
    el status endpoint la seguirá reportando inactiva de todos modos."""
    if not sub_id:
        return
    try:
        await patch_rows(
            "suscripciones",
            {"id": f"eq.{sub_id}"},
            {"status": "expired", "updated_at": datetime.utcnow().isoformat()},
            timeout=8,
        )
    except Exception:
        pass


@app.post("/subscription/trial-max")
async def subscription_trial_max(request: Request):
    """Activa 7 días de Broquer Max sin pedir tarjeta.
    Una sola vez por cuenta (mismo regalo que el trial de Stripe: si ya se
    usó cualquiera de los dos, no hay otro). Al vencer trial_hasta el acceso
    se corta solo en /subscription/status y /profile/status."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    exigir_cupo(request, user_id)

    if not await _trial_max_disponible(user_id):
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta ya usó su periodo de prueba de Broquer Max.")

    hasta = datetime.now(timezone.utc) + timedelta(days=TRIAL_MAX_DIAS)
    fila = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": "max",
        "plan_nombre": "Broquer Max",
        "status": "trialing",
        "trial_hasta": hasta.isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=fila,
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")
        # Quemar el regalo: aunque la fila se borre después, no se repite.
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"trial_max_usado": True},
        )
    return {"ok": True, "plan": "Broquer Max", "trial_hasta": hasta.isoformat(), "dias": TRIAL_MAX_DIAS}


# ════════════════════════════════════════════════════════════════
# Agendar demo (público: landing e index) — guarda y avisa por correo
# ════════════════════════════════════════════════════════════════

DEMO_NOTIF_EMAIL = legacy_main_settings.demo_notif_email
_RESEND_KEY_DEMO = settings.resend_api_key
_RESEND_FROM_DEMO = settings.resend_from


class DemoRequest(BaseModel):
    nombre: str
    contacto: str        # teléfono o correo
    fecha: str           # YYYY-MM-DD
    hora: str            # HH:MM
    mensaje: str = ""
    origen: str = ""     # landing | index


@app.post("/demo/agendar")
async def demo_agendar(req: DemoRequest, request: Request):
    """Recibe la solicitud de demo, la guarda en Supabase y avisa por correo.
    Es público (la landing no tiene sesión); el tope por IP de limites.py
    corta cualquier abuso."""
    user_id = await get_user_id_from_token(request)
    exigir_cupo(request, user_id)

    nombre = (req.nombre or "").strip()[:120]
    contacto = (req.contacto or "").strip()[:160]
    fecha = (req.fecha or "").strip()[:10]
    hora = (req.hora or "").strip()[:5]
    mensaje = (req.mensaje or "").strip()[:800]
    origen = (req.origen or "").strip()[:20]

    if not nombre or not contacto:
        raise HTTPException(status_code=400, detail="Escribe tu nombre y un teléfono o correo.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise HTTPException(status_code=400, detail="Elige una fecha válida.")
    if not re.fullmatch(r"\d{2}:\d{2}", hora):
        raise HTTPException(status_code=400, detail="Elige una hora válida.")
    try:
        if date.fromisoformat(fecha) < date.today():
            raise HTTPException(status_code=400, detail="La fecha ya pasó. Elige otra.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Elige una fecha válida.")

    fila = {"nombre": nombre, "contacto": contacto, "fecha": fecha, "hora": hora,
            "mensaje": mensaje, "origen": origen, "user_id": user_id}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/demos_agendadas",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=fila,
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="No se pudo agendar. Intenta de nuevo en un momento.")

    # Aviso por correo. Si Resend falla, la demo ya quedó guardada: no se rompe.
    if _RESEND_KEY_DEMO:
        cuerpo = (
            f"<h2>Nueva demo agendada</h2>"
            f"<p><strong>Nombre:</strong> {nombre}</p>"
            f"<p><strong>Contacto:</strong> {contacto}</p>"
            f"<p><strong>Fecha:</strong> {fecha} a las {hora}</p>"
            f"<p><strong>Mensaje:</strong> {mensaje or '—'}</p>"
            f"<p><strong>Origen:</strong> {origen or 'web'}</p>")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {_RESEND_KEY_DEMO}",
                             "Content-Type": "application/json"},
                    json={"from": _RESEND_FROM_DEMO, "to": [DEMO_NOTIF_EMAIL],
                          "subject": f"Demo agendada: {nombre} — {fecha} {hora}",
                          "html": cuerpo},
                )
        except Exception:
            pass

    return {"ok": True}


@app.post("/subscription/cancel")
async def subscription_cancel(request: Request):
    """Cancela la suscripción activa del usuario al final del período actual (at_period_end)."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado.")

    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    # Obtener stripe_subscription_id de Supabase
    try:
        subscription_rows = await get_rows(
            "suscripciones",
            {"user_id": f"eq.{user_id}", "select": "stripe_subscription_id,status", "order": "updated_at.desc", "limit": "1"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        subscription_rows = []
    row = subscription_rows[0] if subscription_rows else {}
    subscription_id = row.get("stripe_subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=404, detail="No se encontró suscripción activa.")

    # Cancelar en Stripe al final del período
    async with httpx.AsyncClient(timeout=10) as client:
        r_cancel = await client.post(
            f"https://api.stripe.com/v1/subscriptions/{subscription_id}",
            headers=_stripe_headers(),
            data={"cancel_at_period_end": "true"},
        )
    if r_cancel.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Error al cancelar: {r_cancel.text}")

    # Marcar en Supabase
    async with httpx.AsyncClient(timeout=8) as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/suscripciones?user_id=eq.{user_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"status": "canceled", "updated_at": datetime.utcnow().isoformat()}
        )

    return {"ok": True, "message": "Suscripción cancelada correctamente."}


@app.post("/subscription/revenuecat-webhook")
async def revenuecat_webhook(request: Request):
    """
    Recibe los eventos de RevenueCat (compras IAP de iOS vía App Store).
    RevenueCat valida el recibo con Apple y nos avisa de cada cambio de estado.
    Escribe en la MISMA tabla `suscripciones` que Stripe, por lo que
    /subscription/status NO necesita cambios: un usuario con IAP activo se
    marca status="active" igual que uno de Stripe.

    Configurar en RevenueCat → Project settings → Integrations → Webhooks:
      URL:  https://api.broquer.app/subscription/revenuecat-webhook
      Authorization header value: el mismo string que pongas en la env var
      REVENUECAT_WEBHOOK_AUTH (Railway). Si la env var está vacía, no se valida.

    IMPORTANTE: la app de iOS debe identificar al usuario en RevenueCat con su
    user_id de Supabase (Purchases.logIn(user_id)). Así el `app_user_id` que
    llega aquí ES el user_id de Supabase y no hay que mapear nada.
    """
    # 1. Validar el header de autorización compartido (anti-spoofing)
    expected_auth = legacy_main_settings.revenuecat_webhook_auth
    # Sin secreto NO se procesa. Antes, con la variable vacía, cualquiera podía
    # mandar un "INITIAL_PURCHASE" falso con el user_id que quisiera.
    if not expected_auth:
        print("[revenuecat] REVENUECAT_WEBHOOK_AUTH no configurado: webhook cerrado.")
        raise HTTPException(status_code=503, detail="Webhook no disponible.")
    if not hmac_compare(request.headers.get("Authorization", ""), expected_auth):
        raise HTTPException(status_code=403, detail="No autorizado.")

    body = await request.json()
    event = body.get("event", {}) or {}
    event_type = event.get("type", "")
    user_id = event.get("app_user_id") or event.get("original_app_user_id")
    if not user_id:
        return {"ok": True, "skipped": "sin app_user_id"}

    # 2. Traducir el evento de RevenueCat a un status de nuestra tabla
    ACTIVA = {
        "INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION",
        "NON_RENEWING_PURCHASE", "SUBSCRIPTION_EXTENDED",
    }
    if event_type in ACTIVA:
        nuevo_status = "active"
    elif event_type == "EXPIRATION":
        nuevo_status = "expired"          # el acceso terminó de verdad → cortar
    elif event_type == "BILLING_ISSUE":
        nuevo_status = "past_due"         # problema de cobro; sigue en gracia
    elif event_type == "CANCELLATION":
        # Canceló la renovación, pero conserva acceso hasta que expire.
        # No tocamos el status todavía; ya llegará EXPIRATION cuando termine.
        return {"ok": True, "noted": "cancelacion_programada", "user_id": user_id}
    else:
        # PRODUCT_CHANGE, TRANSFER, TEST, etc. — no cambian el acceso.
        return {"ok": True, "ignored": event_type}

    # 3. Upsert en la misma tabla que usa Stripe (merge por user_id)
    sb = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": "max",
        "plan_nombre": "Broquer Max",
        "status": nuevo_status,
        "updated_at": datetime.utcnow().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=sb,
        )

    return {"ok": True, "user_id": user_id, "status": nuevo_status, "event": event_type}


# ════════════════════════════════════════════════════════════════
# Contactos / Importar desde EasyBroker
# ════════════════════════════════════════════════════════════════

async def _mapa_agentes_org(org_id: str, user_id: str) -> dict:
    """
    Miembros de la empresa en Broquer, para asignar cada contacto importado
    al agente que le corresponde. Regresa dos índices:
      por_email:  correo (minúsculas) → user_id
      por_nombre: nombre normalizado (sin acentos, minúsculas) → user_id
    Si no hay empresa, regresa índices vacíos (todo cae al importador).
    """
    import unicodedata as _ud

    def _nrm(t):
        t = _ud.normalize("NFD", str(t or ""))
        t = "".join(c for c in t if _ud.category(c) != "Mn")
        return " ".join(t.lower().split())

    por_email, por_nombre = {}, {}
    if not org_id:
        return {"por_email": por_email, "por_nombre": por_nombre, "_nrm": _nrm}
    try:
        try:
            miembros = await get_rows(
                "organizacion_miembros",
                {"org_id": f"eq.{org_id}", "select": "user_id", "limit": "200"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            miembros = []
        ids = [m["user_id"] for m in miembros if m.get("user_id")]
        if ids:
            try:
                perfiles = await get_rows(
                    "usuarios",
                    {"id": f"in.({','.join(ids)})", "select": "id,nombre,email", "limit": "200"},
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                perfiles = []
            for u in perfiles:
                uid = u.get("id")
                if not uid:
                    continue
                em = (u.get("email") or "").strip().lower()
                if em:
                    por_email[em] = uid
                nm = _nrm(u.get("nombre"))
                if nm:
                    por_nombre[nm] = uid
    except Exception as e:
        print(f"[importar] No se pudo leer el mapa de agentes: {e}")
    return {"por_email": por_email, "por_nombre": por_nombre, "_nrm": _nrm}



@app.post("/contactos/importar-eb")
async def importar_contactos_eb(request: Request):
    """
    Jala los contactos (leads) de EasyBroker del usuario y los guarda
    en la tabla `contactos` de Supabase.
    Deduplication: si ya existe un contacto con el mismo teléfono o email del mismo user_id, lo actualiza en lugar de duplicar.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    # Obtener EB key del usuario
    eb_key = await get_eb_key_for_user(user_id)
    if not eb_key:
        raise HTTPException(status_code=400, detail="No tienes una API Key de EasyBroker configurada. Ve a Configuración → Integraciones.")

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # La empresa comparte UNA cuenta de EasyBroker. Si deduplicamos por agente,
    # cada agente que importe crea su propia copia del mismo directorio. Por eso
    # el universo de comparación es la empresa completa.
    org_id_import = await get_org_id_for_user(user_id)

    # Obtener contactos existentes (de la empresa si la hay, si no del agente)
    filtro_existentes = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                         else {"user_id": f"eq.{user_id}"})
    try:
        existing = await get_rows(
            "contactos",
            {**filtro_existentes,
             "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        existing = []
    existing_by_tel = {c["telefono"]: c for c in existing if c.get("telefono")}
    existing_by_email = {c["email"]: c for c in existing if c.get("email")}

    # Paginar EasyBroker /contacts (leads)
    importados = 0
    actualizados = 0
    omitidos = 0
    errores = 0
    total_eb = 0
    page = 1

    # ── Mapeo EasyBroker → Broquer ──
    _PROB = {"low": "baja", "medium": "media", "high": "alta"}

    def _tel_wa(c):
        """Del array phones de EB saca (teléfono principal, whatsapp)."""
        tel, wa = "", ""
        for p in (c.get("phones") or []):
            num = re.sub(r"[^+\d]", "", p.get("phone") or "")
            if not num:
                continue
            t = (p.get("type") or "").lower()
            if t == "whatsapp" and not wa:
                wa = num
            if not tel or t in ("mobile", "whatsapp"):
                tel = num  # preferir móvil / whatsapp como principal
        return tel[:20], wa[:20]

    def _first_email(c):
        for e in (c.get("emails") or []):
            if e.get("email"):
                return e["email"].strip().lower()[:120]
        return ""

    mapa_ag = await _mapa_agentes_org(org_id_import, user_id)

    def _user_de_agente_eb(c):
        """user_id de Broquer para el agente asignado en EasyBroker."""
        ag = c.get("agent") or {}
        em = (ag.get("email") or "").strip().lower()
        if em and em in mapa_ag["por_email"]:
            return mapa_ag["por_email"][em]
        for llave in ("full_name", "name"):
            nm = mapa_ag["_nrm"](ag.get(llave))
            if nm and nm in mapa_ag["por_nombre"]:
                return mapa_ag["por_nombre"][nm]
        return None

    def _mapear(c):
        nombre = (c.get("full_name")
                  or " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x)
                  or "").strip()[:120]
        tel, wa = _tel_wa(c)
        dirs = c.get("addresses") or []
        dom = dirs[0] if dirs else {}
        return {
            "nombre":       nombre,
            "telefono":     tel,
            "wa":           wa,
            "email":        _first_email(c),
            "empresa":      (c.get("company") or "")[:120],
            "notas":        (c.get("private_description") or "")[:2000],
            "etiquetas":    [t for t in (c.get("tags") or []) if t][:40],
            "fuente":       (c.get("source") or None),
            "probabilidad": _PROB.get((c.get("probability") or "").lower()),
            "calle":        (dom.get("street") or "")[:160],
            "mpio":         (dom.get("city") or "")[:80],
            "cp":           (dom.get("postal_code") or "")[:12],
        }

    # ── Fase 1: paginar la lista de contactos de EasyBroker (solo IDs) ──
    eb_ids = []
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            r = await _eb_get_reintentos(
                client,
                f"{EB_BASE}/contacts",
                eb_headers(eb_key),
                {"page": page, "limit": 50},
            )
            if r is None:
                raise HTTPException(status_code=502, detail="EasyBroker no respondió tras varios intentos. Espera un minuto y vuelve a intentar.")
            if r.status_code == 404:
                raise HTTPException(status_code=400, detail="Tu plan de EasyBroker no tiene acceso a contactos vía API, o el endpoint no está disponible.")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"EasyBroker respondió {r.status_code}: {r.text[:300]}")
            data = r.json()
            items = data.get("content", data.get("data", [])) or []
            if not items:
                break
            for it in items:
                cid = it.get("id")
                if cid is not None:
                    eb_ids.append(cid)
            pagination = data.get("pagination", {})
            if len(items) < 50 or not pagination.get("next_page"):
                break
            page += 1

    total_eb = len(eb_ids)

    # ── Fase 2: traer el detalle de cada contacto en lotes paralelos ──
    # El detalle trae emails, phones, tags, source, probability, company, etc.
    async def _detalle(client, cid):
        try:
            rd = await _eb_get_reintentos(
                client, f"{EB_BASE}/contacts/{cid}", eb_headers(eb_key))
            if rd is not None and rd.status_code == 200:
                return rd.json()
        except Exception:
            pass
        return None

    # Mismo ritmo controlado que el import de propiedades: lotes de _EB_LOTE
    # con pausa mínima entre lotes para no rebasar el límite de EasyBroker
    # (20 req/s). Sin esto, EB regresa 429 y castiga los pasos siguientes.
    detalles = []
    lotes_fallidos_seguidos = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for i in range(0, len(eb_ids), _EB_LOTE):
            lote = eb_ids[i:i + _EB_LOTE]
            _prog(user_id, f"contactos {min(i + _EB_LOTE, len(eb_ids))} de {len(eb_ids)}")
            inicio_lote = time.monotonic()
            res = await asyncio.gather(*[_detalle(client, cid) for cid in lote])
            buenos = [d for d in res if d]
            detalles.extend(buenos)
            resto = _EB_PAUSA_LOTE - (time.monotonic() - inicio_lote)
            if resto > 0 and i + _EB_LOTE < len(eb_ids):
                await asyncio.sleep(resto)
            # Cortacircuito ante 429 sostenido: abortar claro, no moler.
            lotes_fallidos_seguidos = (lotes_fallidos_seguidos + 1
                                       if not buenos else 0)
            if lotes_fallidos_seguidos >= 4:
                raise HTTPException(status_code=429, detail="EasyBroker está limitando las peticiones de tu cuenta (429 sostenido). Espera 10-15 minutos y vuelve a correr la migración: lo ya importado no se pierde ni se duplica.")

    # ── Fase 3: mapear, deduplicar y guardar ──
    async with httpx.AsyncClient(timeout=20) as client:
        for _idx_c, c in enumerate(detalles):
            if _idx_c % 25 == 0:
                _prog(user_id, f"guardando contactos {_idx_c} de {len(detalles)}")
            m = _mapear(c)
            if not m["nombre"] and not m["telefono"] and not m["email"]:
                omitidos += 1
                continue

            now_iso = datetime.utcnow().isoformat()
            existente = existing_by_tel.get(m["telefono"]) or existing_by_email.get(m["email"])

            if existente:
                # Rellenar solo lo que Broquer tenga vacío; nunca pisar lo del usuario
                patch = {}
                for campo in ("nombre", "telefono", "email", "wa", "empresa",
                              "notas", "fuente", "probabilidad", "calle", "mpio", "cp"):
                    if not existente.get(campo) and m.get(campo):
                        patch[campo] = m[campo]
                # Etiquetas: unir sin duplicar
                if m["etiquetas"]:
                    prev = existente.get("etiquetas") or []
                    union = list(dict.fromkeys([*prev, *m["etiquetas"]]))
                    if union != prev:
                        patch["etiquetas"] = union
                if patch:
                    patch["updated_at"] = now_iso
                    filtro_patch = (f"org_id=eq.{org_id_import}" if org_id_import
                                    else f"user_id=eq.{user_id}")
                    rb = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/contactos?id=eq.{existente['id']}&{filtro_patch}",
                        headers=sb_headers,
                        json=patch
                    )
                    if rb.status_code in (200, 204):
                        actualizados += 1
                    else:
                        errores += 1
                else:
                    omitidos += 1
            else:
                nuevo = {
                    "id":         str(_uuid.uuid4()),
                    "user_id":    _user_de_agente_eb(c) or user_id,
                    "org_id":     org_id_import,
                    "tipo":       "otro",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    **m,
                }
                nuevo["nombre"] = m["nombre"] or "Sin nombre"
                # No mandar vacíos que ensucien la fila
                nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
                ri = await client.post(
                    f"{SUPABASE_URL}/rest/v1/contactos",
                    headers={**sb_headers, "Prefer": "return=minimal"},
                    json=nuevo
                )
                if ri.status_code in (200, 201):
                    importados += 1
                    if m["telefono"]:
                        existing_by_tel[m["telefono"]] = nuevo
                    if m["email"]:
                        existing_by_email[m["email"]] = nuevo
                else:
                    errores += 1

    return {
        "ok": True,
        "total": total_eb,
        "importados": importados,
        "actualizados": actualizados,
        "omitidos": omitidos,
        "errores": errores,
    }


@app.post("/contactos/importar-archivo")
async def importar_contactos_archivo(request: Request, file: UploadFile = File(...)):
    """
    Importa contactos desde un archivo exportado de EasyBroker (o cualquier
    CSV / Excel con encabezados). Pensado para la migracion completa: la API
    de EasyBroker no expone toda la bitacora del CRM, pero el export de
    Contactos si trae notas, estatus, fechas reales y codigos de propiedad.

    Como funciona:
    - Acepta .csv (coma o punto y coma, UTF-8 o Latin-1) y .xlsx.
    - Detecta las columnas por nombre, sin importar el orden ni el idioma
      (Nombre, Telefono, Correo, Etiquetas, Fuente, Probabilidad, Notas,
      Estatus, Fecha de creacion, Agente, Propiedades, etc.).
    - Deduplica contra los contactos de la empresa por telefono y correo.
      En existentes solo rellena campos vacios; nunca pisa lo del usuario.
    - Conserva la fecha de creacion REAL del archivo para que Estadisticas
      muestre el historial en su mes correcto.
    - Detecta codigos EB-XXXX en cualquier columna o en las notas y liga el
      contacto con la propiedad ya importada via contactos_propiedades.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    nombre_archivo = (file.filename or "").lower()
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo llegó vacío.")
    if len(contenido) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo pesa más de 15 MB. Divide el export en partes más chicas.")

    # ─── Paso 1: leer filas del archivo como lista de dicts ───
    filas: list = []
    if nombre_archivo.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(contenido), read_only=True, data_only=True)
            hoja = wb.worksheets[0]
            iterador = hoja.iter_rows(values_only=True)
            encabezados = None
            for row in iterador:
                celdas = ["" if v is None else str(v).strip() for v in row]
                if encabezados is None:
                    if not any(celdas):
                        continue
                    encabezados = celdas
                    continue
                if any(celdas):
                    filas.append(dict(zip(encabezados, celdas)))
            wb.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el Excel: {str(e)[:150]}")
    else:
        import csv as _csv
        from io import StringIO
        texto = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                texto = contenido.decode(enc)
                break
            except Exception:
                continue
        if texto is None:
            raise HTTPException(status_code=400, detail="No se pudo leer el archivo. Guárdalo como CSV UTF-8 o Excel.")
        primera = texto.splitlines()[0] if texto.splitlines() else ""
        delim = ";" if primera.count(";") > primera.count(",") else ","
        lector = _csv.DictReader(StringIO(texto), delimiter=delim)
        for row in lector:
            fila = {(k or "").strip(): ("" if v is None else str(v).strip()) for k, v in row.items()}
            if any(fila.values()):
                filas.append(fila)

    if not filas:
        raise HTTPException(status_code=400, detail="No se encontraron filas con datos. Revisa que la primera fila tenga los encabezados.")

    # ─── Paso 2: mapear encabezados por nombre, sin importar orden ni acentos ───
    import unicodedata

    def _norm(t: str) -> str:
        t = unicodedata.normalize("NFD", str(t or ""))
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()

    ALIAS = {
        "nombre":       ("nombre completo", "nombre", "name", "full name", "contacto", "cliente"),
        "apellido":     ("apellidos", "apellido", "last name"),
        "telefono":     ("telefono movil", "telefono celular", "telefonos", "telefono", "celular", "movil", "phone", "tel"),
        "wa":           ("whatsapp",),
        "email":        ("correo electronico", "correos", "correo", "email", "e mail", "mail"),
        "empresa":      ("empresa", "compania", "company"),
        "notas":        ("descripcion privada", "descripcion", "notas", "comentarios", "notes", "observaciones"),
        "etiquetas":    ("etiquetas", "tags"),
        "fuente":       ("fuente", "origen", "source"),
        "probabilidad": ("probabilidad", "probability"),
        "estatus":      ("estatus", "estado", "etapa", "status"),
        "calle":        ("direccion", "calle", "domicilio", "street"),
        "mpio":         ("municipio", "ciudad", "city"),
        "cp":           ("codigo postal", "cp", "postal code"),
        "fecha":        ("fecha de creacion", "fecha de registro", "fecha de alta", "creado", "created at", "fecha"),
        "agente":       ("agente asignado", "agente", "asesor", "responsable", "agent"),
        "props":        ("codigos de propiedad", "codigo de propiedad", "propiedades", "propiedades de interes", "propiedad", "inmuebles", "properties"),
        "tipo":         ("tipo de contacto", "tipo", "rol", "perfil"),
    }
    columnas_archivo = list(filas[0].keys())
    col_de = {}
    usadas = set()
    for campo, alias in ALIAS.items():
        for a in alias:
            for col in columnas_archivo:
                if col in usadas:
                    continue
                if a == _norm(col) or (len(a) > 3 and a in _norm(col)):
                    col_de[campo] = col
                    usadas.add(col)
                    break
            if campo in col_de:
                break

    if "nombre" not in col_de and "telefono" not in col_de and "email" not in col_de:
        raise HTTPException(status_code=400, detail=("No reconocí las columnas del archivo. Necesita al menos una de: "
                    "Nombre, Teléfono o Correo. Columnas recibidas: "
                    + ", ".join(columnas_archivo[:12])))

    _PROB = {"low": "baja", "baja": "baja", "medium": "media", "media": "media",
             "high": "alta", "alta": "alta"}
    _TIPO = {"comprador": "comprador", "buyer": "comprador",
             "vendedor": "vendedor", "seller": "vendedor",
             "propietario": "vendedor", "owner": "vendedor",
             "arrendador": "arrendador", "arrendatario": "arrendatario",
             "inquilino": "arrendatario"}
    _RE_EB = re.compile(r"EB-[A-Za-z0-9]{4,10}")

    def _tel_limpio_csv(x):
        t = re.sub(r"[^+\d]", "", str(x or ""))
        return t[:20] if len(t) >= 7 else ""

    def _fecha_iso(x):
        x = str(x or "").strip()
        if not x:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                    "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(x[:19], fmt).isoformat()
            except Exception:
                continue
        return None

    def _valor(fila, campo):
        col = col_de.get(campo)
        return (fila.get(col) or "").strip() if col else ""

    # ─── Paso 3: universo existente de la empresa (dedupe org-wide) ───
    org_id_import = await get_org_id_for_user(user_id)
    filtro_org = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                  else {"user_id": f"eq.{user_id}"})
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    prop_por_eb_id = {}
    pares_existentes = set()
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            existentes = await get_rows(
                "contactos",
                {**filtro_org, "limit": "10000",
                 "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"},
                timeout=20,
            )
        except httpx.HTTPStatusError:
            existentes = []
        try:
            propiedades_existentes = await get_rows(
                "propiedades",
                {**filtro_org, "eb_public_id": "not.is.null",
                 "select": "id,eb_public_id", "limit": "5000"},
                timeout=20,
            )
        except httpx.HTTPStatusError:
            propiedades_existentes = []
        for row in propiedades_existentes:
            if row.get("eb_public_id"):
                prop_por_eb_id[row["eb_public_id"]] = row["id"]
        try:
            vinculos_existentes = await get_rows(
                "contactos_propiedades",
                {"select": "contacto_id,propiedad_id", "limit": "20000"},
                timeout=20,
            )
        except httpx.HTTPStatusError:
            vinculos_existentes = []
        for v in vinculos_existentes:
            pares_existentes.add((v.get("contacto_id"), v.get("propiedad_id")))

    por_tel   = {_tel_limpio_csv(c.get("telefono")): c for c in existentes if _tel_limpio_csv(c.get("telefono"))}
    por_email = {(c.get("email") or "").strip().lower(): c for c in existentes if c.get("email")}

    mapa_ag = await _mapa_agentes_org(org_id_import, user_id)

    def _user_de_agente_txt(texto):
        """user_id de Broquer para el agente del archivo (correo o nombre)."""
        t = (texto or "").strip()
        if not t:
            return None
        if "@" in t:
            return mapa_ag["por_email"].get(t.lower())
        return mapa_ag["por_nombre"].get(mapa_ag["_nrm"](t))

    # ─── Paso 4: mapear, deduplicar y guardar ───
    importados = actualizados = omitidos = errores = 0
    vinculos_nuevos = 0
    sin_propiedad = 0

    async with httpx.AsyncClient(timeout=20) as client:
        for fila in filas:
            nombre = _valor(fila, "nombre")
            apellido = _valor(fila, "apellido")
            if apellido and apellido.lower() not in nombre.lower():
                nombre = f"{nombre} {apellido}".strip()
            nombre = nombre[:120]
            tel   = _tel_limpio_csv(_valor(fila, "telefono"))
            wa    = _tel_limpio_csv(_valor(fila, "wa"))
            email = _valor(fila, "email").lower()
            if email and ("@" not in email or " " in email):
                email = ""
            email = email[:120]
            if not nombre and not tel and not email:
                omitidos += 1
                continue

            notas = _valor(fila, "notas")[:2000]
            agente = _valor(fila, "agente")
            agente_uid = _user_de_agente_txt(agente)
            if agente and not agente_uid:
                # Sin match con un usuario de Broquer: al menos queda constancia
                linea = f"Asesor en EasyBroker: {agente}"
                notas = (notas + "\n" + linea).strip() if notas else linea
                notas = notas[:2000]
            etiquetas = [t.strip() for t in re.split(r"[,;|]", _valor(fila, "etiquetas")) if t.strip()][:40]
            fecha_real = _fecha_iso(_valor(fila, "fecha"))
            now_iso = datetime.utcnow().isoformat()

            m = {
                "nombre":       nombre,
                "telefono":     tel,
                "wa":           wa,
                "email":        email,
                "empresa":      _valor(fila, "empresa")[:120],
                "notas":        notas,
                "etiquetas":    etiquetas,
                "fuente":       (_valor(fila, "fuente") or "EasyBroker (archivo)")[:80],
                "probabilidad": _PROB.get(_valor(fila, "probabilidad").lower()),
                "estatus":      _valor(fila, "estatus").lower()[:40] or None,
                "calle":        _valor(fila, "calle")[:160],
                "mpio":         _valor(fila, "mpio")[:80],
                "cp":           _valor(fila, "cp")[:12],
            }

            # Codigos EB-XXXX: en la columna de propiedades y en las notas
            codigos = set(_RE_EB.findall(_valor(fila, "props")))
            codigos.update(_RE_EB.findall(notas))

            existente = (por_tel.get(tel) if tel else None) or (por_email.get(email) if email else None)

            if existente:
                contacto_id = existente["id"]
                patch = {}
                for campo in ("nombre", "telefono", "email", "wa", "empresa", "notas",
                              "fuente", "probabilidad", "estatus", "calle", "mpio", "cp"):
                    if not existente.get(campo) and m.get(campo):
                        patch[campo] = m[campo]
                if etiquetas:
                    prev = existente.get("etiquetas") or []
                    union = list(dict.fromkeys([*prev, *etiquetas]))
                    if union != prev:
                        patch["etiquetas"] = union
                if patch:
                    patch["updated_at"] = now_iso
                    rb = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/contactos",
                        headers={**sb_headers, "Prefer": "return=minimal"},
                        params={"id": f"eq.{contacto_id}"},
                        json=patch
                    )
                    if rb.status_code in (200, 204):
                        actualizados += 1
                        existente.update(patch)
                    else:
                        errores += 1
                else:
                    omitidos += 1
            else:
                nuevo = {
                    "id":         str(_uuid.uuid4()),
                    "user_id":    agente_uid or user_id,
                    "org_id":     org_id_import,
                    "tipo":       _TIPO.get(_valor(fila, "tipo").lower(), "otro"),
                    "created_at": fecha_real or now_iso,
                    "updated_at": now_iso,
                    **m,
                }
                nuevo["nombre"] = nombre or "Sin nombre"
                nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
                ri = await client.post(
                    f"{SUPABASE_URL}/rest/v1/contactos",
                    headers={**sb_headers, "Prefer": "return=minimal"},
                    json=nuevo
                )
                if ri.status_code in (200, 201, 204):
                    importados += 1
                    contacto_id = nuevo["id"]
                    if tel:
                        por_tel[tel] = {"id": contacto_id, **m}
                    if email:
                        por_email[email] = {"id": contacto_id, **m}
                else:
                    errores += 1
                    continue

            # Ligar propiedades por codigo EB (solo las ya importadas en Broquer)
            for cod in codigos:
                propiedad_id = prop_por_eb_id.get(cod)
                if not propiedad_id:
                    sin_propiedad += 1
                    continue
                if (contacto_id, propiedad_id) in pares_existentes:
                    continue
                rv = await client.post(
                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades",
                    headers={**sb_headers, "Prefer": "return=minimal"},
                    json={"user_id": user_id, "contacto_id": contacto_id,
                          "propiedad_id": propiedad_id, "relacion": "interes"}
                )
                if rv.status_code in (200, 201, 204):
                    vinculos_nuevos += 1
                    pares_existentes.add((contacto_id, propiedad_id))

    return {
        "ok": True,
        "filas":         len(filas),
        "importados":    importados,
        "actualizados":  actualizados,
        "omitidos":      omitidos,
        "vinculos":      vinculos_nuevos,
        "sin_propiedad": sin_propiedad,
        "errores":       errores,
        "columnas":      {k: v for k, v in col_de.items()},
    }


# ════════════════════════════════════════════════════════════════
# Migración completa EasyBroker como TRABAJO EN SEGUNDO PLANO
# El navegador ya no sostiene peticiones largas (se caían con cualquier
# corte o reinicio): inicia el trabajo y consulta el avance cada pocos
# segundos. El trabajo corre en el servidor y sobrevive a recargas de
# página. Los tres pasos se llaman internamente (localhost) reusando la
# lógica existente sin duplicarla.
# ════════════════════════════════════════════════════════════════

_MIGRACIONES: dict = {}   # org o user -> estado del trabajo
_PROGRESO_IMPORT: dict = {}   # user_id -> texto de avance granular


def _prog(user_id: str, texto: str):
    """Avance granular del import en curso, visible en migracion/estado."""
    try:
        _PROGRESO_IMPORT[user_id] = texto
    except Exception:
        pass


def _mig_llave(org_id, user_id):
    return f"org:{org_id}" if org_id else f"user:{user_id}"


async def _job_migracion_eb(llave: str, auth_header: str):
    est = _MIGRACIONES[llave]
    base = f"http://127.0.0.1:{legacy_main_settings.port}"
    pasos = [
        ("propiedades", "/easybroker/import-all",   {"fotos_diferidas": True}),
        ("contactos",   "/contactos/importar-eb",   None),
        ("historial",   "/easybroker/import-stats", None),
    ]
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            for idx, (nombre, ruta, body) in enumerate(pasos, start=1):
                est["paso"] = idx
                r = await client.post(
                    base + ruta,
                    headers={"Authorization": auth_header,
                             "Content-Type": "application/json"},
                    json=body if body is not None else {}
                )
                try:
                    d = r.json()
                except Exception:
                    d = {}
                if r.status_code != 200:
                    est["error"] = (d.get("detail")
                                    or f"Error {r.status_code} al importar {nombre}")
                    est["terminado"] = True
                    return
                est[nombre] = d
        est["terminado"] = True
    except Exception as e:
        est["error"] = f"El trabajo se interrumpió: {str(e)[:150]}"
        est["terminado"] = True


@app.post("/easybroker/migracion/iniciar")
async def migracion_eb_iniciar(request: Request):
    """
    Arranca la migración completa (propiedades → contactos → historial) en
    segundo plano. Si ya hay una corriendo para la misma empresa, no lanza
    otra: regresa en_curso para que el frontend solo consulte el avance.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    llave = _mig_llave(org_id, user_id)

    previa = _MIGRACIONES.get(llave)
    if previa and not previa.get("terminado") \
       and time.time() - previa.get("inicio", 0) < 1800:
        return {"ok": True, "en_curso": True}

    auth_header = request.headers.get("Authorization") or ""
    _MIGRACIONES[llave] = {
        "paso": 1, "terminado": False, "error": None,
        "propiedades": None, "contactos": None, "historial": None,
        "inicio": time.time(),
    }
    asyncio.create_task(_job_migracion_eb(llave, auth_header))
    return {"ok": True, "en_curso": False}


@app.get("/easybroker/migracion/estado")
async def migracion_eb_estado(request: Request):
    """Avance de la migración en curso (o de la última terminada)."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    est = _MIGRACIONES.get(_mig_llave(org_id, user_id))
    if not est:
        return {"ok": True, "existe": False}
    return {
        "ok": True, "existe": True,
        "detalle":     _PROGRESO_IMPORT.get(user_id),
        "paso":        est["paso"],
        "terminado":   est["terminado"],
        "error":       est["error"],
        "propiedades": est["propiedades"],
        "contactos":   est["contactos"],
        "historial":   est["historial"],
    }


@app.post("/easybroker/import-stats")
async def easybroker_import_stats(request: Request):
    """
    Importa el HISTORIAL DE LEADS de EasyBroker (contact_requests) para que
    el agente no pierda sus estadísticas al migrar a Broquer.

    Qué hace:
    - Pagina GET /v1/contact_requests de la cuenta EB del usuario.
    - Agrupa las solicitudes por persona (teléfono → email → nombre).
    - Crea el contacto como lead (es_potencial=true) con created_at = fecha
      REAL de la primera solicitud en EB, para que las gráficas de
      Estadísticas muestren el historial en su mes correcto, no todo hoy.
    - Liga cada lead con la propiedad que preguntó vía contactos_propiedades
      (relacion='interes'), emparejando por eb_public_id de las propiedades
      ya importadas con /easybroker/import-all.
    - Si la persona ya existe como contacto, NO pisa nada: solo la marca
      como lead y le liga las propiedades que le faltaban.

    Nota: EasyBroker no expone vistas ni métricas calculadas por API; los
    contact_requests son la materia prima real de sus estadísticas de leads.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    eb_key = await get_eb_key_for_user(user_id)
    if not eb_key:
        raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker antes de importar.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    org_id_import = await get_org_id_for_user(user_id)

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    # El universo de comparación es la empresa completa (una cuenta EB por
    # empresa); si no hay empresa, el agente solo.
    filtro_org = ({"org_id": f"eq.{org_id_import}"} if org_id_import
                  else {"user_id": f"eq.{user_id}"})

    # ─── Paso 1: propiedades ya importadas (eb_public_id → id interno) ───
    prop_por_eb_id = {}
    try:
        propiedades_importadas = await get_rows(
            "propiedades",
            {**filtro_org, "eb_public_id": "not.is.null",
             "select": "id,eb_public_id", "limit": "5000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        propiedades_importadas = []
    for row in propiedades_importadas:
        if row.get("eb_public_id"):
            prop_por_eb_id[row["eb_public_id"]] = row["id"]

    # ─── Paso 2: contactos existentes (dedupe por teléfono/email) ───
    try:
        existentes = await get_rows(
            "contactos",
            {**filtro_org, "select": "id,telefono,email,es_potencial",
             "limit": "10000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        existentes = []

    # ─── Paso 3: vínculos existentes (para no duplicar 'interes') ───
    try:
        vinculos_existentes = await get_rows(
            "contactos_propiedades",
            {"select": "contacto_id,propiedad_id",
             "relacion": "eq.interes", "limit": "20000"},
            timeout=20,
        )
    except httpx.HTTPStatusError:
        vinculos_existentes = []
    pares_existentes = {
        (v.get("contacto_id"), v.get("propiedad_id")) for v in vinculos_existentes
    }

    def _tel_limpio(x):
        return re.sub(r"[^+\d]", "", x or "")[:20]

    por_tel   = {_tel_limpio(c.get("telefono")): c for c in existentes if _tel_limpio(c.get("telefono"))}
    por_email = {(c.get("email") or "").strip().lower(): c for c in existentes if c.get("email")}

    # ─── Paso 4: paginar contact_requests de EasyBroker ───
    solicitudes = []
    pagina = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while pagina <= 400:
            r = await _eb_get_reintentos(
                client,
                f"{EB_BASE}/contact_requests",
                eb_headers(eb_key),
                [("limit", 50), ("page", pagina)],
                timeout=30.0,
            )
            if r is None:
                break
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil.")
            if r.status_code == 404:
                raise HTTPException(status_code=400, detail="Tu plan de EasyBroker no tiene acceso a solicitudes de contacto vía API.")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"EasyBroker respondió {r.status_code}: {r.text[:200]}")
            data = r.json()
            items = data.get("content", []) or []
            if not items:
                break
            solicitudes.extend(items)
            if not data.get("pagination", {}).get("next_page"):
                break
            pagina += 1

    total_eb = len(solicitudes)

    # ─── Paso 5: agrupar por persona ───
    def _pid_de(cr):
        # EB ha variado el nombre del campo; se cubren las tres formas vistas.
        return (cr.get("property_public_id")
                or cr.get("property_id")
                or (cr.get("property") or {}).get("public_id")
                or "")

    grupos = {}  # llave persona → {nombre, tel, email, fuentes, fechas, props, mensajes}
    sin_datos = 0
    for cr in solicitudes:
        tel    = _tel_limpio(cr.get("phone"))
        email  = (cr.get("email") or "").strip().lower()[:120]
        nombre = (cr.get("name") or "").strip()[:120]
        if not tel and not email and not nombre:
            sin_datos += 1
            continue
        llave = tel or email or f"nombre:{nombre.lower()}"
        g = grupos.setdefault(llave, {
            "nombre": nombre, "tel": tel, "email": email,
            "fuentes": [], "fechas": [], "props": [], "mensajes": [],
        })
        if nombre and not g["nombre"]:
            g["nombre"] = nombre
        if tel and not g["tel"]:
            g["tel"] = tel
        if email and not g["email"]:
            g["email"] = email
        fuente = (cr.get("source") or "").strip()
        if fuente and fuente not in g["fuentes"]:
            g["fuentes"].append(fuente)
        fecha = cr.get("created_at")
        if fecha:
            g["fechas"].append(fecha)
        pid = _pid_de(cr)
        if pid and pid not in g["props"]:
            g["props"].append(pid)
        msg = (cr.get("message") or "").strip()
        if msg and msg not in g["mensajes"]:
            g["mensajes"].append(msg[:500])

    # ─── Paso 6: crear / marcar contactos y ligar propiedades — EN LOTES ───
    # Antes se hacia un POST por persona y otro por vinculo: con cientos de
    # leads eran cientos de escrituras secuenciales y el paso tardaba minutos.
    # Ahora: 1 POST por cada 100 contactos nuevos, 1 PATCH por cada 200 a
    # marcar y 1 POST por cada 200 vinculos.
    creados = 0
    marcados = 0
    ya_estaban = 0
    vinculos_nuevos = 0
    sin_propiedad = 0
    errores = 0

    nuevos_lote: list = []      # filas de contactos a crear
    ids_marcar: list = []       # ids existentes a marcar es_potencial
    vinculos_lote: list = []    # filas de contactos_propiedades a crear
    ahora = datetime.utcnow().isoformat()

    for g in grupos.values():
        existente = (por_tel.get(g["tel"]) if g["tel"] else None) \
                    or (por_email.get(g["email"]) if g["email"] else None)

        if existente:
            contacto_id = existente["id"]
            if not existente.get("es_potencial"):
                ids_marcar.append(str(contacto_id))
                existente["es_potencial"] = True
            else:
                ya_estaban += 1
        else:
            fecha_real = min(g["fechas"]) if g["fechas"] else ahora
            notas = ""
            if g["mensajes"]:
                notas = ("Mensajes del historial de EasyBroker:\n— "
                         + "\n— ".join(g["mensajes"]))[:2000]
            nuevo = {
                "id":           str(_uuid.uuid4()),
                "user_id":      user_id,
                "org_id":       org_id_import,
                "nombre":       (g["nombre"] or "Sin nombre").upper()[:120],
                "telefono":     g["tel"],
                "email":        g["email"],
                "tipo":         "comprador",
                "es_potencial": True,
                "estatus":      "nuevo",
                "fuente":       (g["fuentes"][0] if g["fuentes"] else "EasyBroker")[:80],
                "notas":        notas,
                "created_at":   fecha_real,
                "updated_at":   ahora,
            }
            nuevo = {k: v for k, v in nuevo.items() if v not in ("", None, [])}
            nuevos_lote.append(nuevo)
            contacto_id = nuevo["id"]
            if g["tel"]:
                por_tel[g["tel"]] = {"id": contacto_id, "es_potencial": True}
            if g["email"]:
                por_email[g["email"]] = {"id": contacto_id, "es_potencial": True}

        for pid in g["props"]:
            propiedad_id = prop_por_eb_id.get(pid)
            if not propiedad_id:
                sin_propiedad += 1
                continue
            if (contacto_id, propiedad_id) in pares_existentes:
                continue
            vinculos_lote.append({"user_id": user_id, "contacto_id": contacto_id,
                                  "propiedad_id": propiedad_id, "relacion": "interes"})
            pares_existentes.add((contacto_id, propiedad_id))

    ids_creados_ok = set()
    async with httpx.AsyncClient(timeout=60) as client:
        # a) Crear contactos nuevos, 100 por POST
        for i in range(0, len(nuevos_lote), 100):
            chunk = nuevos_lote[i:i+100]
            ri = await client.post(
                f"{SUPABASE_URL}/rest/v1/contactos",
                headers={**sb_headers, "Prefer": "return=minimal"},
                json=chunk
            )
            if ri.status_code in (200, 201, 204):
                creados += len(chunk)
                ids_creados_ok.update(c["id"] for c in chunk)
            else:
                errores += len(chunk)

        # b) Marcar existentes como lead, 200 por PATCH
        for i in range(0, len(ids_marcar), 200):
            lote = ids_marcar[i:i+200]
            lista = ",".join(f'"{x}"' for x in lote)
            rp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contactos",
                headers={**sb_headers, "Prefer": "return=minimal"},
                params={"id": f"in.({lista})"},
                json={"es_potencial": True, "updated_at": ahora}
            )
            if rp.status_code in (200, 204):
                marcados += len(lote)
            else:
                errores += len(lote)

        # c) Vinculos contacto-propiedad, 200 por POST. Se descartan los que
        # apuntan a un contacto nuevo cuyo lote fallo.
        ids_nuevos_todos = {n["id"] for n in nuevos_lote}
        vinculos_validos = [v for v in vinculos_lote
                            if v["contacto_id"] in ids_creados_ok
                            or v["contacto_id"] not in ids_nuevos_todos]
        for i in range(0, len(vinculos_validos), 200):
            chunk = vinculos_validos[i:i+200]
            rv = await client.post(
                f"{SUPABASE_URL}/rest/v1/contactos_propiedades",
                headers={**sb_headers, "Prefer": "return=minimal"},
                json=chunk
            )
            if rv.status_code in (200, 201, 204):
                vinculos_nuevos += len(chunk)

    return {
        "ok": True,
        "solicitudes_eb":   total_eb,
        "personas":         len(grupos),
        "creados":          creados,
        "marcados":         marcados,       # ya existían; se marcaron como lead
        "ya_estaban":       ya_estaban,     # ya eran leads
        "vinculos":         vinculos_nuevos,
        "sin_propiedad":    sin_propiedad,  # la propiedad no está importada en Broquer
        "sin_datos":        sin_datos,
        "errores":          errores,
    }


# ─────────────────────────────────────────────
# ADMIN
# Endpoints basados en rol (admin/equipo/agente) + activo (bool).
# El rol gobierna el acceso; las suscripciones de Stripe son solo para agentes.
# Solo accesibles si el caller tiene rol=admin (verificado vía service key).
# ─────────────────────────────────────────────

async def require_admin(request: Request) -> str:
    """Verifica que el caller esté autenticado y tenga rol=admin. Devuelve su user_id."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    rol = await get_user_rol(user_id)
    if rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    return user_id


@app.get("/admin/me")
async def admin_me(request: Request):
    """Verifica que el usuario autenticado tiene rol=admin."""
    await require_admin(request)
    return {"ok": True, "rol": "admin"}


@app.get("/admin/users")
async def admin_list_users(request: Request):
    """
    Lista todos los usuarios con su rol, estado activo y datos de suscripción.
    Hace merge de tabla `usuarios` con tabla `suscripciones` (última por user_id).
    """
    await require_admin(request)

    # 1) Traer todos los usuarios
    try:
        users = await get_rows(
            "usuarios",
            {
                "select": "id,email,nombre,telefono,rol,activo,created_at",
                "order": "created_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")

    # 2) Traer todas las suscripciones (más reciente primero)
    try:
        subs = await get_rows(
            "suscripciones",
            {
                "select": "user_id,plan_id,plan_nombre,status,updated_at",
                "order": "updated_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError:
        subs = []
    subs_by_user = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in subs_by_user:  # primera = más reciente
            subs_by_user[uid] = s

    # 3) Merge
    result = []
    for u in users:
        uid = u.get("id")
        sub = subs_by_user.get(uid)
        result.append({
            "id": uid,
            "email": u.get("email"),
            "nombre": u.get("nombre"),
            "telefono": u.get("telefono"),
            "rol": u.get("rol") or "agente",
            "activo": u.get("activo") if u.get("activo") is not None else True,
            "created_at": u.get("created_at"),
            "sub_status": sub.get("status") if sub else None,
            "sub_plan": sub.get("plan_nombre") if sub else None,
            "sub_plan_id": sub.get("plan_id") if sub else None,
            "sub_updated_at": sub.get("updated_at") if sub else None,
            "sub_active": (sub.get("status") in ("active", "trialing")) if sub else False,
        })

    return {"ok": True, "users": result, "count": len(result)}


class AdminRolReq(BaseModel):
    user_id: str
    rol: str


@app.post("/admin/user/rol")
async def admin_set_rol(req: AdminRolReq, request: Request):
    """Cambia el rol de un usuario. Roles válidos: admin, equipo, agente."""
    caller_id = await require_admin(request)

    ROLES_VALIDOS = {"admin", "equipo", "agente"}
    if req.rol not in ROLES_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Válidos: {', '.join(sorted(ROLES_VALIDOS))}")

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")

    # Protección: el admin no puede degradarse a sí mismo (evita quedarse sin admins)
    if target_id == caller_id and req.rol != "admin":
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol de admin. Pide a otro admin que lo haga.")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{target_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"rol": req.rol},
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Error actualizando rol: {r.text}")

    return {"ok": True, "user_id": target_id, "rol": req.rol}


class AdminActivoReq(BaseModel):
    user_id: str
    activo: bool


@app.post("/admin/user/activo")
async def admin_set_activo(req: AdminActivoReq, request: Request):
    """Activa o desactiva una cuenta. Cuenta desactivada = sin acceso, sin importar rol o suscripción."""
    caller_id = await require_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")

    # Protección: el admin no puede desactivarse a sí mismo
    if target_id == caller_id and not req.activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta de admin.")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{target_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"activo": bool(req.activo)},
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Error actualizando activo: {r.text}")

    return {"ok": True, "user_id": target_id, "activo": bool(req.activo)}


class AdminEliminarReq(BaseModel):
    user_id: str
    email_confirmacion: str


@app.post("/admin/user/eliminar")
async def admin_eliminar_usuario(req: AdminEliminarReq, request: Request):
    """
    Elimina POR COMPLETO a un usuario: sus filas en todas las tablas
    (propiedades, contactos, tareas, WhatsApp, firmas, etc.), sus archivos
    en Storage, las organizaciones que posee, su perfil y su cuenta de
    autenticación. Tras esto, el correo puede volver a registrarse desde cero.

    Toda la lógica de borrado vive en la función SQL
    admin_eliminar_usuario_total (migracion-eliminar-usuario.sql), que escanea
    dinámicamente las tablas — módulos nuevos quedan cubiertos sin tocar esto.

    Protecciones:
      - Solo rol=admin puede llamar.
      - El frontend confirma dos veces (el usuario escribe el correo) antes de llamar.
      - No puedes eliminarte a ti mismo.
      - No puedes eliminar a otro admin (primero bájalo a agente).
      - email_confirmacion debe coincidir con el correo real de la cuenta.
    """
    caller_id = await require_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")
    if target_id == caller_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta de admin.")

    # Verificar que el objetivo existe y validar correo + rol
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"id": f"eq.{target_id}", "select": "id,email,rol", "limit": "1"},
        )
    filas = r.json() if r.status_code == 200 else []
    if not filas:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    objetivo = filas[0]
    if (objetivo.get("rol") or "agente") == "admin":
        raise HTTPException(status_code=400,
                            detail="No se puede eliminar a un admin. Primero cámbiale el rol a agente.")
    email_real = (objetivo.get("email") or "").strip().lower()
    if (req.email_confirmacion or "").strip().lower() != email_real:
        raise HTTPException(status_code=400,
                            detail="El correo de confirmación no coincide con el de la cuenta.")

    # Las fotos de propiedades viven en la RAÍZ del bucket con nombres uuid
    # (no bajo carpeta del usuario), así que sus rutas hay que recolectarlas
    # ANTES de que el RPC borre las filas de `propiedades`.
    rutas_fotos = await _storage_rutas_fotos_de_usuario(target_id)

    # Ejecutar la eliminación total vía RPC (service key)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/admin_eliminar_usuario_total",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
            },
            json={"p_user_id": target_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {r.text}")
    resultado = r.json()
    if not (isinstance(resultado, dict) and resultado.get("ok")):
        detalle = resultado.get("error") if isinstance(resultado, dict) else str(resultado)
        raise HTTPException(status_code=500, detail=f"La eliminación no se completó: {detalle}")

    borrado = dict(resultado.get("borrado", {}))

    # Archivos en Storage: Supabase prohíbe borrarlos con SQL directo
    # ("Use the Storage API instead"), así que se hace aquí vía Storage API.
    # Se recorren TODOS los buckets dinámicamente (buckets futuros quedan
    # cubiertos) y se borra todo lo que viva bajo la carpeta {user_id}/.
    # Si Storage falla, la cuenta ya quedó eliminada — se reporta pero no truena.
    archivos_borrados = await _storage_borrar_carpeta_usuario(target_id, rutas_fotos)
    if archivos_borrados > 0:
        borrado["storage (archivos)"] = archivos_borrados
    elif archivos_borrados < 0:
        borrado["storage (archivos)"] = "revisar logs — no se pudieron borrar todos"

    return {"ok": True, "user_id": target_id, "email": email_real,
            "borrado": borrado}


async def _storage_rutas_fotos_de_usuario(user_id: str) -> dict:
    """Extrae, por bucket, las rutas de archivos referenciados en columnas de
    URLs del usuario (propiedades.fotos). Se llama ANTES de borrar las filas."""
    rutas: dict = {}
    prefijo_pub = f"{SUPABASE_URL}/storage/v1/object/public/"
    try:
        try:
            filas = await get_rows(
                "propiedades",
                {"user_id": f"eq.{user_id}", "select": "fotos", "limit": "10000"},
                timeout=30,
            )
        except httpx.HTTPStatusError:
            filas = []
        for fila in filas:
            for url in (fila.get("fotos") or []):
                if not isinstance(url, str) or not url.startswith(prefijo_pub):
                    continue
                resto = url[len(prefijo_pub):]
                if "/" not in resto:
                    continue
                bucket, ruta = resto.split("/", 1)
                rutas.setdefault(bucket, set()).add(ruta)
    except Exception as e:
        print(f"[eliminar-usuario] No se pudieron recolectar fotos de {user_id}: {e}")
    return {b: sorted(v) for b, v in rutas.items()}


async def _storage_borrar_carpeta_usuario(user_id: str, rutas_extra: dict | None = None) -> int:
    """Borra vía Storage API:
      1. Todo lo que viva bajo {user_id}/ en todos los buckets, recorriendo
         subcarpetas recursivamente (firmas, expedientes PLD, machotes, videos…).
      2. Las rutas sueltas recolectadas antes del borrado de filas (fotos de
         propiedades, que viven en la raíz del bucket con nombre uuid).
    Devuelve el total borrado, o -1 si algo falló (borrado parcial)."""
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    total = 0
    hubo_error = False

    async def _borrar_lote(client, bucket: str, rutas: list) -> bool:
        nonlocal total
        for i in range(0, len(rutas), 100):
            rd = await client.request(
                "DELETE",
                f"{SUPABASE_URL}/storage/v1/object/{bucket}",
                headers={**sb_headers, "Content-Type": "application/json"},
                json={"prefixes": rutas[i:i + 100]},
            )
            if rd.status_code != 200:
                return False
            total += len(rutas[i:i + 100])
        return True

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(f"{SUPABASE_URL}/storage/v1/bucket", headers=sb_headers)
            buckets = [b.get("name") for b in (r.json() if r.status_code == 200 else [])
                       if isinstance(b, dict) and b.get("name")]

            for bucket in buckets:
                # Recorrido recursivo de la carpeta del usuario
                pendientes = [f"{user_id}/"]
                archivos: list = []
                pasos = 0
                while pendientes and pasos < 500:  # tope de seguridad
                    pasos += 1
                    prefijo = pendientes.pop()
                    offset = 0
                    while pasos < 500:
                        rl = await client.post(
                            f"{SUPABASE_URL}/storage/v1/object/list/{bucket}",
                            headers={**sb_headers, "Content-Type": "application/json"},
                            json={"prefix": prefijo, "limit": 100, "offset": offset},
                        )
                        if rl.status_code != 200:
                            hubo_error = True
                            break
                        items = rl.json() or []
                        for it in items:
                            if not isinstance(it, dict) or not it.get("name"):
                                continue
                            if it.get("id"):
                                archivos.append(f"{prefijo}{it['name']}")
                            else:
                                pendientes.append(f"{prefijo}{it['name']}/")
                        if len(items) < 100:
                            break
                        offset += 100
                        pasos += 1
                if archivos and not await _borrar_lote(client, bucket, archivos):
                    hubo_error = True

            # Rutas sueltas (fotos de propiedades en la raíz del bucket)
            for bucket, rutas in (rutas_extra or {}).items():
                if rutas and not await _borrar_lote(client, bucket, list(rutas)):
                    hubo_error = True
    except Exception as e:
        print(f"[eliminar-usuario] Error limpiando Storage de {user_id}: {e}")
        hubo_error = True

    return -1 if hubo_error else total


@app.get("/admin/user/{user_id}/uso")
async def admin_user_uso(user_id: str, request: Request, dias: int = 30):
    """Agregaciones de uso y costo IA de un usuario, junto con tiempo por módulo.
    Devuelve totales, desglose por módulo y desglose por herramienta para el rango
    indicado (default 30 días). Solo accesible para rol=admin.
    """
    await require_admin(request)
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")

    try:
        dias_int = max(1, min(int(dias), 365))
    except Exception:
        dias_int = 30
    desde_iso = (datetime.utcnow() - timedelta(days=dias_int)).isoformat() + "Z"

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    # 1) usage_logs en el rango
    usage_rows: List[Dict[str, Any]] = []
    try:
        usage_rows = await get_rows(
            "usage_logs",
            {
                "user_id": f"eq.{user_id}",
                "ts": f"gte.{desde_iso}",
                "select": "modulo,herramienta,proveedor,modelo,tokens_in,tokens_out,unidades,costo_usd,ts",
                "order": "ts.desc",
                "limit": "20000",
            },
            timeout=15,
        )
    except Exception:
        usage_rows = []

    # 2) module_sessions en el rango
    session_rows: List[Dict[str, Any]] = []
    try:
        session_rows = await get_rows(
            "module_sessions",
            {
                "user_id": f"eq.{user_id}",
                "ts": f"gte.{desde_iso}",
                "select": "modulo,segundos,ts",
                "limit": "50000",
            },
            timeout=15,
        )
    except Exception:
        session_rows = []

    # 3) Agregar — por módulo (combinando tiempo + costo de IA)
    por_modulo: Dict[str, Dict[str, Any]] = {}
    for row in session_rows:
        m = (row.get("modulo") or "desconocido")
        slot = por_modulo.setdefault(m, {"modulo": m, "segundos": 0, "costo_usd": 0.0, "llamadas": 0})
        slot["segundos"] += int(row.get("segundos") or 0)
    for row in usage_rows:
        m = (row.get("modulo") or "desconocido")
        slot = por_modulo.setdefault(m, {"modulo": m, "segundos": 0, "costo_usd": 0.0, "llamadas": 0})
        slot["costo_usd"] += float(row.get("costo_usd") or 0)
        slot["llamadas"] += 1

    # 4) Por herramienta
    por_herramienta: Dict[str, Dict[str, Any]] = {}
    for row in usage_rows:
        key = f"{row.get('herramienta','')}|{row.get('proveedor','')}|{row.get('modelo','')}"
        slot = por_herramienta.setdefault(key, {
            "herramienta": row.get("herramienta") or "",
            "proveedor":   row.get("proveedor") or "",
            "modelo":      row.get("modelo") or "",
            "llamadas":    0,
            "tokens_in":   0,
            "tokens_out":  0,
            "unidades":    0,
            "costo_usd":   0.0,
        })
        slot["llamadas"]   += 1
        slot["tokens_in"]  += int(row.get("tokens_in") or 0)
        slot["tokens_out"] += int(row.get("tokens_out") or 0)
        slot["unidades"]   += int(row.get("unidades") or 0)
        slot["costo_usd"]  += float(row.get("costo_usd") or 0)

    # 5) Totales y ordenamientos
    costo_total = round(sum(float(r.get("costo_usd") or 0) for r in usage_rows), 4)
    tiempo_total = sum(int(r.get("segundos") or 0) for r in session_rows)
    llamadas_total = len(usage_rows)

    # Round per-module
    modulos_arr = []
    for slot in por_modulo.values():
        modulos_arr.append({
            "modulo":    slot["modulo"],
            "segundos":  int(slot["segundos"]),
            "costo_usd": round(float(slot["costo_usd"]), 4),
            "llamadas":  int(slot["llamadas"]),
        })
    modulos_arr.sort(key=lambda x: (x["segundos"], x["costo_usd"]), reverse=True)

    herr_arr = []
    for slot in por_herramienta.values():
        slot["costo_usd"] = round(float(slot["costo_usd"]), 4)
        herr_arr.append(slot)
    herr_arr.sort(key=lambda x: x["costo_usd"], reverse=True)

    # Última actividad observada
    ultima = None
    if usage_rows:
        ultima = usage_rows[0].get("ts")

    return {
        "ok": True,
        "user_id": user_id,
        "rango_dias": dias_int,
        "costo_total_usd": costo_total,
        "llamadas_total": llamadas_total,
        "tiempo_total_seg": int(tiempo_total),
        "ultima_actividad": ultima,
        "por_modulo":      modulos_arr,
        "por_herramienta": herr_arr,
    }


# ════════════════════════════════════════════════════════════════
# Eliminar cuenta y datos del usuario (acción irreversible)
# ════════════════════════════════════════════════════════════════
@app.delete("/usuario/eliminar-cuenta")
async def eliminar_cuenta_y_datos(request: Request):
    """Borra TODA la información del usuario autenticado, de forma permanente.

    Pasos (irreversibles, en este orden):
      1. Cancela de inmediato la suscripción de Stripe (si tiene una activa).
      2. Borra las fotos del usuario del bucket de Storage (fotos-propiedades).
      3. Borra sus filas: propiedades, contactos, contratos, user_integrations,
         suscripciones, usage_logs, module_sessions.
      4. Borra su fila en `usuarios`.
      5. Borra al usuario de Supabase Auth (auth.users).

    El frontend confirma dos veces (el usuario escribe su correo) antes de llamar.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    sb_read_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    tablas = ["propiedades", "contactos", "contratos", "user_integrations",
              "suscripciones", "usage_logs", "module_sessions"]
    borrados = {}
    errores = []
    async with httpx.AsyncClient(timeout=30) as client:
        # ── 1. Cancelar la suscripción de Stripe de inmediato ──────────
        # Al borrar la cuenta, Stripe NO debe seguir cobrando. Cancelación
        # inmediata (no al final del período). Si algo falla, se registra en
        # `errores` pero no detiene el resto del borrado.
        if STRIPE_SECRET_KEY:
            try:
                rs = await client.get(
                    f"{SUPABASE_URL}/rest/v1/suscripciones",
                    headers=sb_read_headers,
                    params={
                        "user_id": f"eq.{user_id}",
                        "select": "stripe_subscription_id",
                        "order": "updated_at.desc",
                        "limit": "1",
                    },
                )
                sub_rows = rs.json() if rs.status_code == 200 else []
                sub_id = sub_rows[0].get("stripe_subscription_id") if sub_rows else None
                if sub_id:
                    rc = await client.delete(
                        f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                        headers=_stripe_headers(),
                    )
                    borrados["stripe"] = (rc.status_code in (200, 201))
                    if rc.status_code not in (200, 201):
                        errores.append(f"stripe: {rc.status_code} {rc.text[:120]}")
                else:
                    borrados["stripe"] = "sin_suscripcion"
            except Exception as e:
                errores.append(f"stripe: {e}")
                borrados["stripe"] = False

        # ── 2. Borrar las fotos del usuario del bucket de Storage ──────
        # Las fotos se guardan con nombre aleatorio (sin prefijo de usuario),
        # así que se obtienen las URLs de sus propiedades ANTES de borrar las filas.
        try:
            rp = await client.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=sb_read_headers,
                params={"user_id": f"eq.{user_id}", "select": "fotos"},
            )
            objetos = []
            if rp.status_code == 200:
                for fila in (rp.json() or []):
                    for url in (fila.get("fotos") or []):
                        if not isinstance(url, str):
                            continue
                        marcador = "/fotos-propiedades/"
                        if marcador in url:
                            nombre = url.split(marcador, 1)[1].split("?", 1)[0]
                            if nombre:
                                objetos.append(nombre)
            objetos = list(dict.fromkeys(objetos))  # quitar duplicados
            fotos_borradas = 0
            for nombre in objetos:
                try:
                    rf = await client.delete(
                        f"{SUPABASE_URL}/storage/v1/object/fotos-propiedades/{nombre}",
                        headers=sb_read_headers,
                    )
                    if rf.status_code in (200, 204):
                        fotos_borradas += 1
                except Exception:
                    pass
            borrados["fotos_storage"] = f"{fotos_borradas}/{len(objetos)}"
        except Exception as e:
            errores.append(f"fotos_storage: {e}")
            borrados["fotos_storage"] = False

        # ── 3. Borrar las filas de datos del usuario ───────────────────
        for tabla in tablas:
            try:
                r = await client.delete(
                    f"{SUPABASE_URL}/rest/v1/{tabla}?user_id=eq.{user_id}",
                    headers=sb_headers,
                )
                borrados[tabla] = (r.status_code in (200, 204))
                if r.status_code not in (200, 204):
                    errores.append(f"{tabla}: {r.status_code} {r.text[:120]}")
            except Exception as e:
                errores.append(f"{tabla}: {e}")
                borrados[tabla] = False

        # Borrar fila en `usuarios` (el id es el mismo de auth.users)
        try:
            r = await client.delete(
                f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",
                headers=sb_headers,
            )
            borrados["usuarios"] = (r.status_code in (200, 204))
        except Exception as e:
            errores.append(f"usuarios: {e}")
            borrados["usuarios"] = False

        # Borrar el usuario de auth.users (admin API)
        try:
            r = await client.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                },
            )
            borrados["auth"] = (r.status_code in (200, 204))
            if r.status_code not in (200, 204):
                errores.append(f"auth: {r.status_code} {r.text[:120]}")
        except Exception as e:
            errores.append(f"auth: {e}")
            borrados["auth"] = False

    return {"ok": True, "user_id": user_id, "borrados": borrados, "errores": errores}


# ════════════════════════════════════════════════════════════════
# Instagram — cuadrícula pública del landing
# Jala los últimos posts de la cuenta de Broquer vía Graph API y los
# cachea 6 horas en memoria. Público (el landing no tiene sesión);
# el caché protege el límite de la API. Requiere INSTAGRAM_TOKEN
# (long-lived) en las variables de Railway.
# ════════════════════════════════════════════════════════════════
_IG_CACHE = {"t": 0.0, "data": None}

@app.get("/instagram/feed")
async def instagram_feed():
    ahora = time.time()
    if _IG_CACHE["data"] is not None and (ahora - _IG_CACHE["t"]) < 21600:
        return _IG_CACHE["data"]
    tok = legacy_main_settings.instagram_token
    ig_id = legacy_main_settings.ig_user_id
    if not tok or not ig_id:
        raise HTTPException(status_code=503, detail="Instagram no configurado")
    # Ruta vía app de Facebook (Tech Provider): la cuenta de IG se consulta
    # por su id de negocio, no por /me.
    url = ("https://graph.facebook.com/v25.0/" + ig_id + "/media"
           "?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
           "&limit=12&access_token=" + tok)
    try:
        async with httpx.AsyncClient(timeout=12) as cli:
            r = await cli.get(url)
        if r.status_code != 200:
            # Si hay caché viejo, mejor servirlo que fallar.
            if _IG_CACHE["data"] is not None:
                return _IG_CACHE["data"]
            raise HTTPException(status_code=502, detail="Instagram no respondió")
        crudo = r.json().get("data", [])
    except HTTPException:
        raise
    except Exception:
        if _IG_CACHE["data"] is not None:
            return _IG_CACHE["data"]
        raise HTTPException(status_code=502, detail="Sin conexión con Instagram")

    posts = []
    for p in crudo:
        posts.append({
            "id": p.get("id"),
            "tipo": p.get("media_type"),
            "portada": p.get("thumbnail_url") or p.get("media_url"),
            "liga": p.get("permalink"),
            "texto": (p.get("caption") or "")[:120],
        })
    data = {"ok": True, "posts": posts}
    _IG_CACHE["data"] = data
    _IG_CACHE["t"] = ahora
    return data


# ═══════════════════════════════════════════════════════════════════════════
# LEADS DEL SITIO PÚBLICO DE AGENTES
# Endpoint público (sin sesión): el formulario de contacto de sitio.html
# registra al visitante como lead en el CRM del agente dueño del slug,
# ANTES de abrirle WhatsApp. Así el lead queda en Broquer aunque el
# visitante nunca llegue a enviar el mensaje.
# Anti-spam: rate limit en memoria por IP y por slug + honeypot.
# ═══════════════════════════════════════════════════════════════════════════

_SITIO_LEAD_RL = {}  # {clave: [timestamps]}

def _sitio_lead_permitido(clave: str, limite: int, ventana_seg: int) -> bool:
    import time as _t
    ahora = _t.time()
    lst = [t for t in _SITIO_LEAD_RL.get(clave, []) if ahora - t < ventana_seg]
    if len(lst) >= limite:
        _SITIO_LEAD_RL[clave] = lst
        return False
    lst.append(ahora)
    _SITIO_LEAD_RL[clave] = lst
    # Poda ocasional para que el dict no crezca sin límite
    if len(_SITIO_LEAD_RL) > 5000:
        viejas = [k for k, v in _SITIO_LEAD_RL.items() if not v or ahora - v[-1] > ventana_seg]
        for k in viejas:
            _SITIO_LEAD_RL.pop(k, None)
    return True


class SitioLeadIn(BaseModel):
    nombre: str
    telefono: str = ""
    mensaje: str = ""
    sitio_web: str = ""  # honeypot: los humanos nunca llenan este campo


@app.post("/sitio/{slug}/lead")
async def sitio_registrar_lead(slug: str, payload: SitioLeadIn, request: Request):
    """Registra un lead proveniente del sitio público del agente."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Servicio no disponible")

    # Honeypot: si viene lleno, es un bot. Respondemos ok sin guardar nada.
    if (payload.sitio_web or "").strip():
        return {"ok": True}

    nombre = (payload.nombre or "").strip()[:120]
    telefono = "".join(ch for ch in (payload.telefono or "") if ch.isdigit() or ch == "+")[:20]
    mensaje = (payload.mensaje or "").strip()[:1000]
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")

    # Rate limit: 5 leads/hora por IP y 30/hora por sitio
    ip = (request.headers.get("cf-connecting-ip")
          or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    if not _sitio_lead_permitido(f"ip:{ip}", 5, 3600) or \
       not _sitio_lead_permitido(f"slug:{slug}", 30, 3600):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes, intenta más tarde")

    async with httpx.AsyncClient(timeout=10) as client:
        hdr = {"apikey": SUPABASE_SERVICE_KEY,
               "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
               "Content-Type": "application/json"}

        # 1) Resolver el slug → agente dueño del sitio (solo sitios activos)
        try:
            rows = await get_rows(
                "usuarios",
                {"slug": f"eq.{slug}", "sitio_activo": "eq.true",
                 "select": "id", "limit": "1"},
                timeout=10,
            )
        except httpx.HTTPStatusError:
            rows = []
        if not rows:
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
        user_id = rows[0]["id"]

        ahora = datetime.now(timezone.utc).isoformat()
        nota = f"Lead del sitio web ({ahora[:10]}): {mensaje}" if mensaje else f"Lead del sitio web ({ahora[:10]})."

        # 2) Dedup: si ya existe un contacto de este agente con el mismo
        #    teléfono, solo lo marcamos como lead y le agregamos la nota.
        existente = None
        if telefono:
            try:
                filas = await get_rows(
                    "contactos",
                    {"user_id": f"eq.{user_id}", "telefono": f"eq.{telefono}",
                     "select": "id,notas,es_potencial", "limit": "1"},
                    timeout=10,
                )
            except httpx.HTTPStatusError:
                filas = []
            existente = filas[0] if filas else None

        if existente:
            notas_prev = (existente.get("notas") or "").strip()
            nuevas_notas = (notas_prev + "\n\n" + nota).strip() if notas_prev else nota
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/contactos", headers=hdr,
                params={"id": f"eq.{existente['id']}"},
                json={"es_potencial": True, "notas": nuevas_notas[:5000],
                      "updated_at": ahora})
            return {"ok": True, "duplicado": True}

        # 3) Crear el lead nuevo (mismo esquema que usa leads.html)
        import random as _rnd
        nuevo = {
            "id": f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}{_rnd.randint(100, 999)}",
            "user_id": user_id,
            "nombre": nombre.upper(),
            "telefono": telefono or None,
            "notas": nota,
            "es_potencial": True,
            "estatus": "nuevo",
            "fuente": "Sitio web",
            "etiquetas": [],
            "operaciones": [],
            "created_at": ahora,
            "updated_at": ahora,
        }
        r = await client.post(f"{SUPABASE_URL}/rest/v1/contactos", headers=hdr, json=nuevo)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="No se pudo registrar el lead")

    return {"ok": True}
