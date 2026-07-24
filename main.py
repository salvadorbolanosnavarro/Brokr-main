from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import time
import re
import asyncio
import logging
import base64
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
# Espejo del :root de la edición "Navarro".
_THEME_TOKENS_FALLBACK = """
  --paper:#F4F7FD; --paper-2:#EDF2FB; --bone:#FFFFFF; --shell:#F4F7FE;
  --ink:#00143B; --ink-2:#1B2C4F; --ink-3:#4A5875;
  --mute:#4A5875; --mute-2:#8592AB; --mute-3:#BFCADD;
  --line:#E6ECF6; --line-2:#D8E1EF; --line-3:#BFCADD;
  --forest:#1240A0; --forest-2:#0B2E78; --forest-soft:rgba(18,64,160,0.10);
  --sky-navy:#00143B; --sky-navy-mid:#032873; --sky-navy-deep:#000D28;
  --sky-blue:#1240A0; --sky-blue-press:#0B2E78; --sky-blue-lift:#3A6FD8;
  --sky-canvas:#E8F0FE; --sky-blue-on-dark:#7FA8F0;
  --warn:#B45309; --warn-soft:rgba(180,83,9,0.10);
  --danger:#C62839; --danger-soft:rgba(198,40,57,0.10);
  --success:#0C7A5E; --success-soft:rgba(12,122,94,0.10);
  --info:#0B2E78; --info-soft:rgba(11,46,120,0.10);
  --r-xs:6px; --r-sm:8px; --r:10px; --r-lg:16px; --r-xl:22px; --r-pill:999px;
  --font-sans:'Manrope',-apple-system,BlinkMacSystemFont,system-ui,Roboto,'Helvetica Neue',sans-serif;
  --font-display:'Manrope',-apple-system,BlinkMacSystemFont,system-ui,Roboto,sans-serif;
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
        "family=Manrope:wght@400;500;600;700;800&display=swap');\n"
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

EB_API_KEY       = os.environ.get("EB_API_KEY", "") or _config.get("eb_api_key", "")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
EB_BASE          = "https://api.easybroker.com/v1"
GROQ_BASE        = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE   = "https://api.anthropic.com/v1"
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta"
APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "")
GOOGLE_PLACES_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY      = os.environ.get("SUPABASE_ANON_KEY", "")
FB_APP_ID     = os.environ.get("FB_APP_ID", "")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET", "")
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "https://app.navarroai.com.mx")
# Banxico SIE — INPC + UDIS para calculadora ISR
BANXICO_TOKEN     = os.environ.get("BANXICO_TOKEN", "").strip().strip('"').strip("'")
BANXICO_BASE      = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = os.environ.get("BANXICO_SERIE_UDIS", "SP68257")  # Valor de UDIS (diaria)
BANXICO_SERIE_INPC = os.environ.get("BANXICO_SERIE_INPC", "SP74625")  # INPC mensual base 2Q-jul-2018=100
# service_role key — bypasea RLS. Solo para operaciones del backend en nombre
# del usuario, DESPUÉS de validar su JWT con get_user_id_from_token().
# NUNCA expongas esta variable al frontend.
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
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
    return {"status": "Brokr API activa", "version": "4.4"}

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
    if not datos:
        raise HTTPException(status_code=404, detail=f"INPC no publicado para {anio}-{mes:02d}")
    valor = float(str(datos[-1]["dato"]).replace(",", ""))
    fecha_pub = datos[-1]["fecha"]
    result = {"anio": anio, "mes": mes, "valor": valor,
              "fecha_publicacion": fecha_pub, "fuente": "banxico_sie"}
    now = datetime.now()
    is_past = (anio < now.year) or (anio == now.year and mes < now.month)
    cache_set(key, result, ttl=30 * 86400 if is_past else 6 * 3600)
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

# Helper: extrae el user_id del token de Supabase
async def get_user_id_from_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("id")
    except Exception:
        pass
    return None

# ════════════════════════════════════════════════════════════════
# CONTEXTO DE ORGANIZACIÓN (Broquer para empresas)
# Tras la migración, la RLS filtra por org_id — NO por user_id. Todo registro
# que cree el backend debe llevar org_id o queda huérfano e invisible para
# todos. El backend usa service key y se brinca la RLS, así que un olvido aquí
# no truena: silenciosamente crea basura. Por eso va explícito en cada INSERT.
# ════════════════════════════════════════════════════════════════
try:
    from routers.organizaciones import (
        get_org_id_for_user, get_org_context, permiso_efectivo,
        exigir_gestion_integraciones,
    )
except Exception as _e:
    print(f"[org] No se pudo importar el contexto de organización: {_e}")
    async def get_org_id_for_user(user_id: str):
        return None
    async def get_org_context(user_id: str):
        return None
    def permiso_efectivo(ctx, clave):
        return False
    async def exigir_gestion_integraciones(request):
        return await get_user_id_from_token(request)


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
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_integrations",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                         "Content-Type": "application/json"},
                params={"org_id": f"eq.{org_id}", "provider": "eq.easybroker",
                        "select": "api_key", "limit": "1"}
            )
            if r.status_code == 200:
                rows = r.json()
                if rows and rows[0].get("api_key"):
                    return rows[0]["api_key"]
    except Exception:
        pass
    return None

# Helper: obtiene el rol del usuario desde la tabla usuarios
async def get_user_rol(user_id: str) -> str:
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return "agente"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/usuarios",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"id": f"eq.{user_id}", "select": "rol", "limit": "1"}
            )
            if r.status_code == 200:
                rows = r.json()
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
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/usuarios",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"id": f"eq.{user_id}", "select": "rol,activo", "limit": "1"}
            )
            if r.status_code == 200:
                rows = r.json()
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
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/usage_logs",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=payload,
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
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/module_sessions",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"user_id": user_id, "modulo": modulo, "segundos": segs},
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
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload
        )
        # No fallar en silencio: si Supabase rechaza, devolvemos error real al frontend
        if r.status_code not in (200, 201, 204):
            err_body = r.text or ""
            print(f"[set_eb_key] Supabase respondió {r.status_code}: {err_body}")
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo guardar la API key (Supabase {r.status_code}). Reintenta o avisa a soporte si persiste."
            )
    return {"ok": True, "saved": True, "scope": "user"}

# Endpoint para desconectar EasyBroker (borrar la API key del usuario)
@app.delete("/config/eb-key")
async def delete_eb_key(request: Request):
    # Desconectar deja SIN INVENTARIO a todo el equipo. Solo el dueño o designado.
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")
    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json"},
            params={"org_id": f"eq.{await get_org_id_for_user(user_id)}",
                    "provider": "eq.easybroker"}
        )
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

    # Una sola query trae AMBAS integraciones (EB + FB) del usuario
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_integrations",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"user_id": f"eq.{user_id}",
                        "provider": "in.(easybroker,facebook)",
                        "select": "provider,api_key,meta"}
            )
            if r.status_code != 200:
                return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
            rows = r.json()
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
            fb_state = {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "user_token": meta.get("user_token", ""),
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
            async with httpx.AsyncClient(timeout=6) as client:
                # La suscripción cuelga de la ORG: en una empresa la paga el
                # titular y la heredan todos sus agentes.
                _oid = await get_org_id_for_user(user_id)
                rs = await client.get(
                    f"{SUPABASE_URL}/rest/v1/suscripciones",
                    headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                    params={"org_id": f"eq.{_oid}", "select": "status,plan_nombre", "order": "updated_at.desc", "limit": "1"}
                )
                if rs.status_code == 200 and rs.json():
                    row = rs.json()[0]
                    sub_state = {
                        "active": row.get("status") in ("active", "trialing"),
                        "plan": row.get("plan_nombre"),
                        "status": row.get("status"),
                    }
    except Exception:
        pass

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
async def generar_isr_pdf(p: dict):
    """Recibe HTML del cálculo ISR y lo convierte a PDF con Playwright."""
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
_EB_REINTENTOS    = 4
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

    out = {"version_api": "4.4"}

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
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=sb_headers,
                params={"user_id": f"eq.{user_id}",
                        "eb_public_id": "not.is.null",
                        "select": "eb_public_id,notas,estatus"}
            )
            if r.status_code == 200:
                for row in r.json():
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
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(ids_published), BATCH):
            chunk = ids_published[i:i+BATCH]
            inicio_lote = time.monotonic()
            results = await asyncio.gather(*[fetch_one(client, pid) for pid in chunk])
            # Mantener el ritmo por debajo del límite de EasyBroker: si el lote
            # tardó menos que la pausa mínima, esperamos la diferencia.
            resto = _EB_PAUSA_LOTE - (time.monotonic() - inicio_lote)
            if resto > 0 and i + BATCH < len(ids_published):
                await asyncio.sleep(resto)
            for status, payload in results:
                if status == "ok":
                    inmuebles_listos.append(payload)
                else:
                    errores.append(payload)

    # ─── Paso 4: UPSERT en lotes a Supabase (50 por POST) ───
    # Necesita el índice único (user_id, eb_public_id) en Supabase para que
    # on_conflict funcione.
    upserted = 0
    UPSERT_BATCH = 50
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(inmuebles_listos), UPSERT_BATCH):
            chunk = inmuebles_listos[i:i+UPSERT_BATCH]
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
                else:
                    # Si el lote falla, registrar como error global del lote
                    errores.append({
                        "id": f"lote_{i // UPSERT_BATCH}",
                        "error": f"Supabase {ri.status_code}: {ri.text[:200]}"
                    })
            except Exception as e:
                errores.append({"id": f"lote_{i // UPSERT_BATCH}", "error": str(e)[:200]})

    nuevas      = sum(1 for inm in inmuebles_listos if inm["eb_public_id"] not in existentes_por_eb_id)
    actualizadas = upserted - nuevas if upserted >= nuevas else 0

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
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",
                                 headers=sb_headers, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")
        filas = r.json() or []
    except HTTPException:
        raise
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

SEARCH_TIMEOUT = float(os.environ.get("AVM_SEARCH_TIMEOUT", "18"))
FETCH_TIMEOUT = float(os.environ.get("AVM_FETCH_TIMEOUT", "10"))
MAX_SEARCH_RESULTS = int(os.environ.get("AVM_MAX_SEARCH_RESULTS", "16"))
MAX_URLS_TO_FETCH = int(os.environ.get("AVM_MAX_URLS_TO_FETCH", "8"))
MAX_TEXT_CHARS_PER_URL = int(os.environ.get("AVM_MAX_TEXT_CHARS_PER_URL", "6500"))

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
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_CONCURRENCY = int(os.environ.get("FIRECRAWL_CONCURRENCY", "5"))
FIRECRAWL_TIMEOUT = float(os.environ.get("FIRECRAWL_TIMEOUT", "45"))

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
    key = os.environ.get("GOOGLE_CSE_API_KEY", "") or os.environ.get("GOOGLE_SEARCH_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_ID", "") or os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "")
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
    key = os.environ.get("SERPAPI_API_KEY", "")
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
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
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
    key = os.environ.get("TAVILY_API_KEY", "")
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
        "google_cse": bool((os.environ.get("GOOGLE_CSE_API_KEY") or os.environ.get("GOOGLE_SEARCH_API_KEY")) and (os.environ.get("GOOGLE_CSE_ID") or os.environ.get("GOOGLE_SEARCH_ENGINE_ID"))),
        "serpapi": bool(os.environ.get("SERPAPI_API_KEY")),
        "brave": bool(os.environ.get("BRAVE_SEARCH_API_KEY")),
        "tavily": bool(os.environ.get("TAVILY_API_KEY")),
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
                "model": os.environ.get("ANTHROPIC_AVM_MODEL", "claude-sonnet-4-6"),
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
                     modelo=_resp_json.get("model") or os.environ.get("ANTHROPIC_AVM_MODEL", "claude-sonnet-4-6"))
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


@app.get("/img")
async def proxy_image(url: str):
    """Proxy image from EasyBroker to avoid CORS issues in PDF printing."""
    import base64
    from fastapi.responses import Response
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.easybroker.com/",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                content_type = r.headers.get("content-type", "image/jpeg")
                return Response(content=r.content, media_type=content_type,
                    headers={"Access-Control-Allow-Origin": "*",
                             "Cache-Control": "public, max-age=3600"})
    except Exception as e:
        pass
    raise HTTPException(status_code=404, detail="Image not available")

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
                "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY','')}",
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
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{SUPABASE_URL}/rest/v1/tareas", headers=_sb_headers(), params={
                "select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes",
                "completada": "eq.false", "recordatorio_enviado": "eq.false",
                "fecha_entrega": "not.is.null", "limit": "200",
            })
        if r.status_code >= 300:
            _recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", r.text[:200])
            return
        tareas = r.json()
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
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers(),
            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}",
                    "select": select, "limit": "1"},
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    return r.json()[0]


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

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}",
                    "select": "id,titulo,tipo,campos,motor,created_at",
                    "order": "created_at.desc"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")
    return {"machotes": r.json() or []}


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
async def generar_ficha_pdf(p: dict):
    """Generate PDF from property data dict using Playwright."""
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
        async with httpx.AsyncClient(timeout=15) as client:
            r2 = await client.get(
                f"{SUPABASE_URL}/rest/v1/propiedades_avm",
                headers=headers,
                params={
                    "ciudad": "eq.Morelia",
                    "precio": "gt.0",
                    "metros_construccion": "not.is.null",
                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",
                    "limit": req.max_resultados,
                    "order": "precio.asc",
                }
            )
        items = r2.json() if r2.status_code == 200 else []
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
        os.environ.get("GEMINI_IMAGE_MODEL", ""),
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
                                modelo=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"))
    except Exception:
        pass
    return {"images": list(results)}


# ─── FACEBOOK OAUTH ───────────────────────────────────────────────────────────

# ────────────────────────────────────────────
# FACEBOOK — guardar / leer conexión por usuario
# ────────────────────────────────────────────
class FbSavePageRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    user_token: str = ""  # token de usuario (larga duración) — requerido para Ads API

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

    # ── Auto-seleccionar cuenta publicitaria compatible con la página ──
    ad_account_id = ""
    ad_account_name = ""
    page_pic = ""
    try:
        async with httpx.AsyncClient(timeout=15) as client_a:
            # 1) Foto de la página (mejora UI)
            try:
                rpic = await client_a.get(
                    f"https://graph.facebook.com/v21.0/{req.page_id}",
                    params={"access_token": req.user_token, "fields": "picture.type(square)"}
                )
                if rpic.status_code == 200:
                    page_pic = ((rpic.json().get("picture") or {}).get("data") or {}).get("url", "")
            except Exception:
                page_pic = ""

            # 2) Cuentas publicitarias del usuario
            ra = await client_a.get(
                "https://graph.facebook.com/v21.0/me/adaccounts",
                params={"access_token": req.user_token, "fields": "id,name,account_status,currency", "limit": "50"}
            )
            accounts = []
            if ra.status_code == 200:
                accounts = [a for a in ra.json().get("data", []) if a.get("account_status") == 1]

            # 3) Para cada cuenta, ver si puede anunciar nuestra página
            chosen = None
            for a in accounts:
                try:
                    rp = await client_a.get(
                        f"https://graph.facebook.com/v21.0/{a['id']}/promote_pages",
                        params={"access_token": req.user_token, "fields": "id", "limit": "100"}
                    )
                    if rp.status_code == 200:
                        pids = [p.get("id") for p in rp.json().get("data", []) if p.get("id")]
                        if req.page_id in pids:
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
        "user_token": req.user_token,
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
    }
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": req.page_token,
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat()
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload
        )
    return {
        "ok": True,
        "page_id": req.page_id,
        "page_name": req.page_name,
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
    }

@app.get("/facebook/connection")
async def facebook_get_connection(request: Request):
    """Devuelve si el usuario tiene Facebook conectado y el nombre de la página."""
    user_id = await get_user_id_from_token(request)
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"connected": False}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_integrations",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"user_id": f"eq.{user_id}", "provider": "eq.facebook",
                        "select": "api_key,meta", "limit": "1"}
            )
            if r.status_code == 200:
                rows = r.json()
                if rows and rows[0].get("api_key"):
                    meta_str = rows[0].get("meta", "{}")
                    try:
                        meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except Exception:
                        meta = {}
                    return {
                        "connected": True,
                        "page_id": meta.get("page_id", ""),
                        "page_name": meta.get("page_name", "Página conectada"),
                        "page_pic": meta.get("page_pic", ""),
                        "page_token": rows[0]["api_key"],
                        "user_token": meta.get("user_token", ""),
                        "ad_account_id": meta.get("ad_account_id", ""),
                        "ad_account_name": meta.get("ad_account_name", ""),
                    }
    except Exception:
        pass
    return {"connected": False}


async def _fb_get_meta_row(user_id: str) -> dict:
    """Devuelve la fila completa (api_key + meta dict) del usuario, o {}."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook",
                    "select": "api_key,meta", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        return {}
    row = r.json()[0]
    meta_raw = row.get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}
    return {"page_token": row.get("api_key", ""), "meta": meta}


async def _fb_patch_meta(user_id: str, updates: dict, new_page_token: str | None = None) -> None:
    """Actualiza la fila de Facebook del usuario fusionando 'updates' en meta."""
    cur = await _fb_get_meta_row(user_id)
    meta = cur.get("meta") or {}
    meta.update(updates)
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": new_page_token if new_page_token is not None else cur.get("page_token", ""),
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=payload,
        )


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
        r = await client.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={"access_token": user_token,
                    "fields": "id,name,access_token,picture.type(square)",
                    "limit": "200"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Facebook: {r.text}")
    data = r.json().get("data", []) or []
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
        r = await client.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={"access_token": user_token, "fields": "id,name,access_token", "limit": "200"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Facebook: {r.text}")
    target = next((p for p in r.json().get("data", []) if p.get("id") == req.page_id), None)
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

@app.delete("/facebook/connection")
async def facebook_disconnect(request: Request):
    """Elimina la conexión de Facebook de la EMPRESA en Supabase.
    Deja al equipo entero sin anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook"}
        )
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

    # Obtener conexión de Facebook del usuario
    fb = await facebook_get_connection(request)
    if not fb.get("connected"):
        raise HTTPException(status_code=400, detail="Facebook no conectado. Ve a tu perfil para conectar tu página.")

    page_id = fb["page_id"]
    page_token = fb["page_token"]

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
                r = await client.post(
                    f"https://graph.facebook.com/v21.0/{page_id}/photos",
                    params={"access_token": page_token},
                    json={"url": url, "published": False},
                )
                if r.status_code == 200:
                    pid = r.json().get("id")
                    if pid: photo_ids.append({"media_fbid": pid})
            except Exception:
                pass

        payload: dict = {"message": mensaje, "access_token": page_token}
        if photo_ids:
            payload["attached_media"] = photo_ids

        r_post = await client.post(
            f"https://graph.facebook.com/v21.0/{page_id}/feed",
            params={"access_token": page_token},
            json=payload,
        )

    if r_post.status_code not in (200, 201):
        err = r_post.text
        raise HTTPException(status_code=502, detail=f"Error de Facebook: {err}")

    return {"ok": True, "post_id": r_post.json().get("id"), "page_name": fb.get("page_name", "")}


@app.get("/facebook/callback")
async def facebook_callback(code: str = Query(...), state: str = Query(None), redirect_uri: str = Query(None)):
    """Intercambia el code de OAuth por un token de página de Facebook."""
    redirect_uri = redirect_uri or (FRONTEND_URL + "/facebook/callback")
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Token de usuario (corta duración)
        r = await client.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        if r.status_code != 200:
            return {"error": r.text}
        short_token = r.json().get("access_token", "")

        # 2. Token de larga duración
        r2 = await client.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "fb_exchange_token": short_token,
            },
        )
        long_token = r2.json().get("access_token", short_token)

        # 3. Lista de páginas administradas
        r3 = await client.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={"access_token": long_token},
        )
        pages = r3.json().get("data", [])

    if not pages:
        return {"error": "No se encontraron páginas administradas en esta cuenta de Facebook."}

    # Usar la primera página
    page = pages[0]
    page_token = page.get("access_token", "")
    page_id    = page.get("id", "")
    page_name  = page.get("name", "")

    # Devolver datos para que el frontend los guarde en Supabase
    # user_token (long_token) se necesita para la Ads API — distinto al page_token
    return {
        "ok": True,
        "page_id": page_id,
        "page_name": page_name,
        "page_token": page_token,
        "user_token": long_token,
        "pages": [{"id": p.get("id"), "name": p.get("name"), "access_token": p.get("access_token")} for p in pages],
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
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{req.page_id}/photos",
                params={"access_token": req.page_token},
                json={"url": url, "published": False},
            )
            if r.status_code == 200:
                pid = r.json().get("id")
                if pid:
                    photo_ids.append({"media_fbid": pid})

        # Crear el post
        payload: dict = {
            "message": req.message,
            "access_token": req.page_token,
        }
        if photo_ids:
            payload["attached_media"] = photo_ids

        r_post = await client.post(
            f"https://graph.facebook.com/v18.0/{req.page_id}/feed",
            params={"access_token": req.page_token},
            json=payload,
        )

    if r_post.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=r_post.text)

    return {"ok": True, "post_id": r_post.json().get("id")}



# ─── FACEBOOK ADS ─────────────────────────────────────────────────────────────

@app.get("/facebook/ad-accounts")
async def facebook_ad_accounts(request: Request):
    """Devuelve las cuentas publicitarias accesibles por el usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    # Recuperar user_token guardado en meta
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "meta", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=400, detail="Facebook no conectado")

    meta_raw = r.json()[0].get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}

    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Token de usuario sin permisos de ads. Reconecta tu Facebook.")

    async with httpx.AsyncClient(timeout=15) as client:
        r2 = await client.get(
            "https://graph.facebook.com/v21.0/me/adaccounts",
            params={"access_token": user_token, "fields": "id,name,account_status,currency", "limit": "50"}
        )

    if r2.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Facebook: {r2.text}")

    accounts = r2.json().get("data", [])
    # Solo cuentas activas (account_status == 1)
    active_raw = [a for a in accounts if a.get("account_status", 0) == 1]

    # Para cada cuenta activa, traer las páginas que puede anunciar (promote_pages).
    # Esto permite al frontend auto-seleccionar la cuenta correcta para la página
    # conectada del usuario y marcar las que no pueden anunciar esa página.
    active: list[dict] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for a in active_raw:
            page_ids: list[str] = []
            try:
                rp = await client.get(
                    f"https://graph.facebook.com/v21.0/{a['id']}/promote_pages",
                    params={"access_token": user_token, "fields": "id", "limit": "100"}
                )
                if rp.status_code == 200:
                    page_ids = [p["id"] for p in rp.json().get("data", []) if "id" in p]
            except Exception:
                page_ids = []
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
    page_id: str = ""
    objective: str = "OUTCOME_ENGAGEMENT"
    publish_now: bool = False   # si True, crea y activa; si False, queda en PAUSED
    post_id: str = ""           # si viene, promociona una publicacion existente (formato pageid_postid)


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

    # Recuperar user_token
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "api_key,meta", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=400, detail="Facebook no conectado")

    row = r.json()[0]
    meta_raw = row.get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}

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
            rp = await client_v.get(
                f"https://graph.facebook.com/v21.0/{req.account_id}/promote_pages",
                params={"access_token": user_token, "fields": "id", "limit": "100"}
            )
        if rp.status_code == 200:
            promote_ids = [p.get("id") for p in rp.json().get("data", []) if p.get("id")]
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
    base_url = f"https://graph.facebook.com/v21.0/{account_id}"
    params_base = {"access_token": user_token}

    # Presupuesto diario en centavos
    daily_budget_cents = int(req.daily_budget_mxn * 100)

    # ── Helper: extrae mensaje legible de un error JSON de Meta ──────
    def _fb_friendly_error(resp_text: str, prefix: str) -> str:
        try:
            payload = json.loads(resp_text or "{}")
            err = (payload.get("error") or {})
            sub = err.get("error_subcode") or err.get("code")
            user_title = err.get("error_user_title") or ""
            user_msg = err.get("error_user_msg") or err.get("message") or ""
            # Errores comunes traducidos
            COMMON = {
                1487888: "Tu cuenta publicitaria requiere un Píxel de Facebook configurado para optimizar conversiones. Contacta soporte de Broquer.",
                4834011: "La cuenta tiene 'Optimización del presupuesto de campaña' activada. Desactívala en Business Manager o crea el anuncio directamente en Ads Manager.",
                2069013: "La imagen no cumple los requisitos de Facebook (mínimo 600x600, sin texto excesivo). Usa otra imagen.",
                1815245: "Para anuncios inmobiliarios en EE.UU./Canadá, Meta exige la categoría especial 'Vivienda'. En México no aplica — verifica tu ubicación de cuenta.",
                1815111: "El público objetivo es muy pequeño. Amplía la edad, la ciudad o quita filtros.",
                368:    "Facebook bloqueó la acción por seguridad. Espera unos minutos y reintenta, o reconecta tu cuenta.",
            }
            if sub in COMMON:
                return f"{prefix}: {COMMON[sub]}"
            if user_title or user_msg:
                return f"{prefix}: {user_title}. {user_msg}".strip(". ").strip()
            return f"{prefix}: {err.get('message') or resp_text[:300]}"
        except Exception:
            return f"{prefix}: {resp_text[:300]}"

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

        # ── 0b. Subir todas las imágenes a Meta ANTES de crear campaña ──
        # Si cualquier imagen falla, abortamos sin dejar basura en la cuenta.
        image_hashes = []
        if not req.post_id:
            for idx, b64 in enumerate(images_b64):
                r_img = await client.post(
                    f"{base_url}/adimages",
                    params=params_base,
                    json={"bytes": b64}
                )
                if r_img.status_code in (200, 201):
                    for v in r_img.json().get("images", {}).values():
                        h = v.get("hash")
                        if h:
                            image_hashes.append(h)
                        break
                if not image_hashes or len(image_hashes) < idx + 1:
                    raise HTTPException(
                        status_code=502,
                        detail=_fb_friendly_error(
                            r_img.text,
                            f"No se pudo subir la imagen {idx + 1}"
                        )
                    )

        # ── Recortar campos a límites Meta ─────────────────────────────
        ad_text = (req.ad_text or "")[:2200]
        headline = (req.headline or "")[:40]      # recomendado <40 para carrusel
        campaign_name = (req.campaign_name or "Campaña Broquer")[:120]

        # ── 1. Crear Campaign (siempre en PAUSED; activamos al final) ──
        r_camp = await client.post(
            f"{base_url}/campaigns",
            params=params_base,
            json={
                "name": campaign_name,
                "objective": "OUTCOME_ENGAGEMENT",
                "status": "PAUSED",
                "special_ad_categories": [],
                "buying_type": "AUCTION",
                "is_adset_budget_sharing_enabled": False,
            }
        )
        if r_camp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=_fb_friendly_error(r_camp.text, "Error creando campaña"))
        campaign_id = r_camp.json().get("id")

        # Cleanup helper: borra recursos creados si algo falla a medio camino
        async def _cleanup(*ids):
            for rid in ids:
                if not rid: continue
                try: await client.delete(f"https://graph.facebook.com/v21.0/{rid}", params=params_base)
                except Exception: pass

        # ── 2. Crear AdSet ─────────────────────────────────────────────
        # Siempre se segmenta por ciudad. No se usa countries — no tiene sentido
        # para un agente inmobiliario anunciar en todo un país.
        if not req.city:
            raise HTTPException(status_code=400, detail="Debes seleccionar una ciudad para el anuncio.")
        geo: dict = {"cities": [{"key": req.city}]}
        targeting: dict = {
            "age_min": req.age_min,
            "geo_locations": geo,
            # Meta requiere desde 2024 que se declare EXPLÍCITAMENTE si se usa
            # Advantage Audience. 0 = desactivado (público controlado por el agente).
            "targeting_automation": {"advantage_audience": 0},
        }
        if req.age_max and req.age_max > 0:
            targeting["age_max"] = req.age_max

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

        r_adset = await client.post(
            f"{base_url}/adsets",
            params=params_base,
            json=adset_payload
        )
        if r_adset.status_code not in (200, 201):
            await _cleanup(campaign_id)
            raise HTTPException(status_code=502, detail=_fb_friendly_error(r_adset.text, "Error creando conjunto de anuncios"))
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

        r_creative = await client.post(
            f"{base_url}/adcreatives",
            params=params_base,
            json=creative_payload
        )
        if r_creative.status_code not in (200, 201):
            await _cleanup(adset_id, campaign_id)
            raise HTTPException(status_code=502, detail=_fb_friendly_error(r_creative.text, "Error creando creativo"))
        creative_id = r_creative.json().get("id")

        # ── 4. Crear Ad (PAUSED; activamos en cascada al final) ────────
        r_ad = await client.post(
            f"{base_url}/ads",
            params=params_base,
            json={
                "name": f"{campaign_name} — Ad",
                "adset_id": adset_id,
                "creative": {"creative_id": creative_id},
                "status": "PAUSED",
            }
        )
        if r_ad.status_code not in (200, 201):
            await _cleanup(adset_id, campaign_id)
            raise HTTPException(status_code=502, detail=_fb_friendly_error(r_ad.text, "Error creando anuncio"))
        ad_id = r_ad.json().get("id")

        # ── 5. Activar en cascada si el usuario marcó "Publicar ahora" ──
        if target_status == "ACTIVE":
            # Orden: ad → adset → campaign (Meta exige hijos activos primero)
            r_a1 = await client.post(f"https://graph.facebook.com/v21.0/{ad_id}",       params=params_base, json={"status": "ACTIVE"})
            r_a2 = await client.post(f"https://graph.facebook.com/v21.0/{adset_id}",    params=params_base, json={"status": "ACTIVE"})
            r_a3 = await client.post(f"https://graph.facebook.com/v21.0/{campaign_id}", params=params_base, json={"status": "ACTIVE"})
            # Si la activación falla, no eliminamos lo creado — solo cambiamos el
            # estado a "PAUSED" y devolvemos un aviso para que el usuario lo
            # active manualmente desde "Tus campañas" después de revisar.
            if any(rr.status_code not in (200, 201) for rr in (r_a1, r_a2, r_a3)):
                # Detectar primer error para reportarlo
                fail = next((rr for rr in (r_a1, r_a2, r_a3) if rr.status_code not in (200, 201)), None)
                if fail is not None:
                    target_status = "PAUSED"
                    # No raise: la campaña existe en pausa, el usuario puede activarla.

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
    }


async def _get_fb_meta(user_id: str) -> dict:
    """Helper: recupera meta de Facebook del usuario desde Supabase."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "meta", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta_raw = r.json()[0].get("meta", "{}")
    try:
        return json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        return {}


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
async def facebook_city_search(q: str = "", request: Request = None):
    """Busca ciudades/regiones en Meta para targeting geográfico."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if len(q) < 2:
        return {"results": []}
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://graph.facebook.com/v21.0/search",
            params={
                "access_token": user_token,
                "type": "adgeolocation",
                "location_types": "city,region",
                "q": q,
                "country_code": "MX",
                "limit": "8",
            }
        )
    if r.status_code != 200:
        return {"results": []}
    data = r.json().get("data", [])
    results = [{"key": d["key"], "name": d["name"], "type": d.get("type",""), "region": d.get("region","")} for d in data]
    return {"results": results}


@app.get("/facebook/campaigns")
async def facebook_campaigns_list(request: Request):
    """Lista las campañas con estadísticas básicas de los últimos 7 días."""
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
    async with httpx.AsyncClient(timeout=20) as client:
        r_camps = await client.get(
            f"https://graph.facebook.com/v21.0/{account_id}/campaigns",
            params={"access_token": user_token, "fields": "id,name,status,objective,created_time", "limit": "20"}
        )
        if r_camps.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Error obteniendo campañas: {r_camps.text}")
        campaigns = r_camps.json().get("data", [])
        results = []
        for camp in campaigns:
            cid = camp["id"]
            r_ins = await client.get(
                f"https://graph.facebook.com/v21.0/{cid}/insights",
                params={"access_token": user_token,
                        "fields": "impressions,reach,clicks,ctr,post_engagement,spend",
                        "date_preset": "last_7d"}
            )
            ins_data = r_ins.json().get("data", []) if r_ins.status_code == 200 else []
            ins = ins_data[0] if ins_data else {}
            results.append({
                "id": cid, "name": camp["name"], "status": camp["status"],
                "created_time": camp.get("created_time", ""),
                "impressions": ins.get("impressions", "0"),
                "reach": ins.get("reach", "0"),
                "clicks": ins.get("clicks", "0"),
                "ctr": ins.get("ctr", "0"),
                "engagement": ins.get("post_engagement", "0"),
                "spend": ins.get("spend", "0"),
            })
    return {"campaigns": results}


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
            rp = await client.get(
                "https://graph.facebook.com/v21.0/me/accounts",
                params={"access_token": user_token, "fields": "id,access_token", "limit": "200"},
            )
        if rp.status_code != 200:
            raise HTTPException(status_code=502, detail="No se pudieron resolver las páginas.")
        match = next((p for p in rp.json().get("data", []) if p.get("id") == target_page_id), None)
        if not match:
            raise HTTPException(status_code=400, detail="No administras esa página.")
        page_token = match.get("access_token", "")

    if not page_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    page_id = target_page_id

    # Traer las últimas 25 publicaciones de la página con campos útiles para la galería
    async with httpx.AsyncClient(timeout=15) as client:
        rp = await client.get(
            f"https://graph.facebook.com/v21.0/{page_id}/posts",
            params={
                "access_token": page_token,
                "fields": "id,message,created_time,full_picture,permalink_url,"
                          "reactions.summary(true),comments.summary(true),shares,is_published",
                "limit": "25",
            }
        )
    if rp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error obteniendo publicaciones: {rp.text}")

    items = []
    for p in rp.json().get("data", []):
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
    """Activa o pausa una campaña y todos sus adsets y ads hijos."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    body = await request.json()
    campaign_id = body.get("campaign_id", "")
    new_status = body.get("status", "PAUSED")
    if new_status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail="status debe ser ACTIVE o PAUSED")
    meta = await _get_fb_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    tok = {"access_token": user_token}
    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Actualizar campaña
        await client.post(f"https://graph.facebook.com/v21.0/{campaign_id}", params=tok, json={"status": new_status})
        # 2. Obtener adsets
        r_adsets = await client.get(
            f"https://graph.facebook.com/v21.0/{campaign_id}/adsets",
            params={**tok, "fields": "id", "limit": "50"}
        )
        adset_ids = [a["id"] for a in r_adsets.json().get("data", [])] if r_adsets.status_code == 200 else []
        # 3. Actualizar cada adset y sus ads
        for adset_id in adset_ids:
            await client.post(f"https://graph.facebook.com/v21.0/{adset_id}", params=tok, json={"status": new_status})
            r_ads = await client.get(
                f"https://graph.facebook.com/v21.0/{adset_id}/ads",
                params={**tok, "fields": "id", "limit": "50"}
            )
            for ad in r_ads.json().get("data", []) if r_ads.status_code == 200 else []:
                await client.post(f"https://graph.facebook.com/v21.0/{ad['id']}", params=tok, json={"status": new_status})
    return {"ok": True, "campaign_id": campaign_id, "status": new_status}


# ════════════════════════════════════════════════════════════════
# STRIPE — SUSCRIPCIONES
# ════════════════════════════════════════════════════════════════

STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# IDs de Precios en Stripe (crear en dashboard.stripe.com → Productos → Precios)
STRIPE_PRICE_PRO       = os.environ.get("STRIPE_PRICE_PRO", "")       # Plan Broquer Pro
STRIPE_PRICE_AMPI      = os.environ.get("STRIPE_PRICE_AMPI", "")      # Plan AMPI (precio especial)

# Código promocional para el plan AMPI (válido en Supabase tabla promo_codes)
PROMO_CODE_AMPI = "ampi2026"

def _stripe_headers() -> dict:
    return {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

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
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"id": f"eq.{user_id}", "select": "stripe_customer_id,nombre"}
        )
        row = r.json()[0] if r.status_code == 200 and r.json() else {}

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

    async with httpx.AsyncClient(timeout=8) as client:
        r_nombre = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"id": f"eq.{user_id}", "select": "nombre"}
        )
    nombre = (r_nombre.json()[0] if r_nombre.status_code == 200 and r_nombre.json() else {}).get("nombre", email)

    # Obtener o crear Customer en Stripe
    customer_id = await _get_or_create_stripe_customer(user_id, email, nombre)

    # URLs de retorno (el frontend puede enviarlas o usamos defaults)
    origin = request.headers.get("origin", "https://navarroai.github.io/Brokr")
    success_url = req.success_url or f"{origin}/index.html?suscripcion=ok"
    cancel_url  = req.cancel_url  or f"{origin}/index.html?suscripcion=cancelada"

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

    # Verificar firma del webhook
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
        user_id = obj.get("metadata", {}).get("user_id")
        plan_id = obj.get("metadata", {}).get("plan_id", "max")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if user_id and subscription_id:
            plan_nombre = "AMPI" if plan_id == "ampi" else "Broquer Max"
            sb = {
                "user_id": user_id,
                "org_id": await get_org_id_for_user(user_id),
                "plan_id": plan_id,
                "plan_nombre": plan_nombre,
                "stripe_subscription_id": subscription_id,
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

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription_id = obj.get("id")
        new_status = obj.get("status", "canceled")
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
    ACTIVATE_SECRET = os.environ.get("ACTIVATE_SECRET", "")
    body = await request.json()

    # Verificar clave secreta
    if ACTIVATE_SECRET and body.get("secret") != ACTIVATE_SECRET:
        raise HTTPException(status_code=403, detail="No autorizado.")

    customer_id = body.get("customer_id", "").strip()
    plan_id = body.get("plan_id", "max").strip() or "max"

    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id requerido.")

    # Buscar user_id por stripe_customer_id en tabla usuarios
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"stripe_customer_id": f"eq.{customer_id}", "select": "id,nombre,email"}
        )

    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")

    usuario = r.json()[0]
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

    # Empresas: el precio se negocia caso por caso, así que no pasan por Stripe.
    # Su acceso lo gobierna la propia organización (activo + vence_el), que tú
    # activas a mano desde admin.html.
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
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        return {"active": False, "plan": None, "status": "sin_suscripcion"}

    row = r.json()[0]
    return {
        "active": row.get("status") in ("active", "trialing"),
        "plan": row.get("plan_nombre"),
        "plan_id": row.get("plan_id"),
        "status": row.get("status"),
        "updated_at": row.get("updated_at"),
    }


@app.post("/subscription/cancel")
async def subscription_cancel(request: Request):
    """Cancela la suscripción activa del usuario al final del período actual (at_period_end)."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado.")

    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    # Obtener stripe_subscription_id de Supabase
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "select": "stripe_subscription_id,status", "order": "updated_at.desc", "limit": "1"}
        )
    row = r.json()[0] if r.status_code == 200 and r.json() else {}
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
    expected_auth = os.environ.get("REVENUECAT_WEBHOOK_AUTH", "")
    if expected_auth and request.headers.get("Authorization", "") != expected_auth:
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

    # Obtener contactos existentes del usuario para deduplicar
    async with httpx.AsyncClient(timeout=15) as client:
        r_existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/contactos",
            headers=sb_headers,
            params={"user_id": f"eq.{user_id}", "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"}
        )
    existing = r_existing.json() if r_existing.status_code == 200 else []
    existing_by_tel = {c["telefono"]: c for c in existing if c.get("telefono")}
    existing_by_email = {c["email"]: c for c in existing if c.get("email")}

    # Paginar EasyBroker /contacts (leads)
    importados = 0
    actualizados = 0
    omitidos = 0
    errores = 0
    total_eb = 0
    page = 1

    org_id_import = await get_org_id_for_user(user_id)

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
            r = await client.get(
                f"{EB_BASE}/contacts",
                headers=eb_headers(eb_key),
                params={"page": page, "limit": 50}
            )
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
            rd = await client.get(f"{EB_BASE}/contacts/{cid}", headers=eb_headers(eb_key))
            if rd.status_code == 200:
                return rd.json()
        except Exception:
            pass
        return None

    detalles = []
    async with httpx.AsyncClient(timeout=20) as client:
        for i in range(0, len(eb_ids), 10):
            lote = eb_ids[i:i + 10]
            res = await asyncio.gather(*[_detalle(client, cid) for cid in lote])
            detalles.extend([d for d in res if d])

    # ── Fase 3: mapear, deduplicar y guardar ──
    async with httpx.AsyncClient(timeout=20) as client:
        for c in detalles:
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
                    rb = await client.patch(
                        f"{SUPABASE_URL}/rest/v1/contactos?id=eq.{existente['id']}&user_id=eq.{user_id}",
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
                    "user_id":    user_id,
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
    async with httpx.AsyncClient(timeout=15) as client:
        r_users = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={
                "select": "id,email,nombre,telefono,rol,activo,created_at",
                "order": "created_at.desc",
                "limit": "10000",
            },
        )
    if r_users.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error listando usuarios: {r_users.text}")
    users = r_users.json()

    # 2) Traer todas las suscripciones (más reciente primero)
    async with httpx.AsyncClient(timeout=15) as client:
        r_subs = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={
                "select": "user_id,plan_id,plan_nombre,status,updated_at",
                "order": "updated_at.desc",
                "limit": "10000",
            },
        )
    subs_by_user = {}
    if r_subs.status_code == 200:
        for s in r_subs.json():
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
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/usage_logs",
                headers=sb_headers,
                params={
                    "user_id": f"eq.{user_id}",
                    "ts": f"gte.{desde_iso}",
                    "select": "modulo,herramienta,proveedor,modelo,tokens_in,tokens_out,unidades,costo_usd,ts",
                    "order": "ts.desc",
                    "limit": "20000",
                },
            )
            if r.status_code == 200:
                usage_rows = r.json() or []
    except Exception:
        usage_rows = []

    # 2) module_sessions en el rango
    session_rows: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/module_sessions",
                headers=sb_headers,
                params={
                    "user_id": f"eq.{user_id}",
                    "ts": f"gte.{desde_iso}",
                    "select": "modulo,segundos,ts",
                    "limit": "50000",
                },
            )
            if r.status_code == 200:
                session_rows = r.json() or []
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

