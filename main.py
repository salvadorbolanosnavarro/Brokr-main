from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import time
import re
import asyncio
import base64
import uuid as _uuid
import io
import json
import concurrent.futures
from typing import Optional, List
from datetime import datetime
from pathlib import Path

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

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers.campanas import router as campanas_router
app.include_router(campanas_router)

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
    return {"status": "Brokr API activa", "version": "4.0"}

# ────────────────────────────────────────────
# CONFIG — EB API KEY PERSISTENCE
# ────────────────────────────────────────────
class EbKeyRequest(BaseModel):
    key: str

@app.post("/config/eb-key")
async def set_eb_key(req: EbKeyRequest):
    global EB_API_KEY, _config
    EB_API_KEY = req.key.strip()
    _config["eb_api_key"] = EB_API_KEY
    save_config(_config)
    return {"ok": True, "saved": True}

@app.get("/config/eb-key")
async def get_eb_key():
    if EB_API_KEY and len(EB_API_KEY) > 4:
        masked = "*" * (len(EB_API_KEY) - 4) + EB_API_KEY[-4:]
    else:
        masked = ""
    return {"configured": bool(EB_API_KEY), "masked": masked}

# ────────────────────────────────────────────
# GROQ CHAT PROXY
# ────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list
    model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1024
    temperature: float = 0.7

@app.post("/chat")
async def chat_proxy(req: ChatRequest):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY no configurada en el servidor")
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
        return r.json()


# ────────────────────────────────────────────
# CLAUDE CHAT PROXY — SHAARK IA SUPERINTELIGENTE
# ────────────────────────────────────────────
SHAARK_SYSTEM_PROMPT = """Eres Shaark, el asistente de inteligencia artificial de BROKR®, la plataforma inmobiliaria más avanzada de México, especializada en Morelia y Michoacán.

Eres un experto inmobiliario que conoce a fondo:
- LISR (Ley del Impuesto Sobre la Renta) — artículos de enajenación de inmuebles
- ISR por enajenación: exención de 700,000 UDIS, deducciones permitidas, INPC
- Código Civil Federal y de Michoacán — contratos de compraventa y arrendamiento
- SAT: obligaciones fiscales del vendedor y comprador
- Mercado inmobiliario de Morelia: colonias, plusvalía, precios por zona
- Avalúos y valuación de inmuebles (método de mercado, hedónico, físico)

PERSONALIDAD:
- Hablas en español mexicano, natural y cercano
- Eres directo, preciso y profesional — nunca redundante
- Cuando el usuario habla por voz, respondes con oraciones cortas y claras
- Nunca inventes cifras ni datos legales

REGLA DE ORO:
Cuando el usuario pide realizar una tarea, recopila los datos OBLIGATORIOS de UNO EN UNO, de forma conversacional. NUNCA ejecutes la acción con datos incompletos. Cuando tengas todo, di un resumen breve y ejecuta la acción. Los datos opcionales que el usuario no conozca se omiten (usa 0 o "").

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
Cuando el usuario pide valuar, tasar, dar un precio o dar opinión de valor de un inmueble.

Datos OBLIGATORIOS (pregunta uno por uno si faltan):
1. Colonia o fraccionamiento
2. Tipo de inmueble: casa, departamento, terreno, local, oficina, bodega
3. Operación: venta o renta
4. Superficie: m² de construcción (casas/deptos/locales) o m² de terreno (terrenos)

Datos OPCIONALES que si el usuario menciona debes capturar: recámaras, baños, estacionamientos, condición del terreno (plano/pendiente), ciudad (default Morelia).

Cuando tengas los datos OBLIGATORIOS, emite la acción opinion_valor_web:
[ACCION]{"tipo":"opinion_valor_web","colonia":"Vistas Altozano","tipo_inmueble":"terreno","operacion":"venta","m2_terreno":183,"m2_construccion":0,"recamaras":0,"banos":0,"ciudad":"Morelia","condicion_terreno":"plano"}[/ACCION]

Valores "tipo_inmueble": "casa" | "departamento" | "terreno" | "local" | "oficina" | "bodega"
Valores "operacion": "venta" | "renta"
Valores "condicion_terreno": "plano" | "pendiente" | "irregular" | "" (solo para terrenos)
Para casas/deptos: usa m2_construccion. Para terrenos: usa m2_terreno. Ciudad default "Morelia".
Omite campos opcionales que no tengas (usa 0 o "").

══════════════════════════════════════════════════
ACCIÓN 3: GENERAR CONTRATO DE ARRENDAMIENTO
══════════════════════════════════════════════════
Cuando el usuario pide contrato de renta/arrendamiento.
Datos OBLIGATORIOS:
1. Calle del inmueble arrendado
2. Número exterior
3. Colonia del inmueble
4. C.P. (código postal)
5. Municipio y estado (ej: "Morelia, Michoacán")
6. Nombre completo del arrendador (dueño) — EN MAYÚSCULAS
7. Nombre completo del arrendatario (inquilino) — EN MAYÚSCULAS
8. Renta mensual (MXN)
9. Depósito en garantía (si no sabe, usa el mismo valor que la renta)
10. Fecha de inicio (día/mes/año)

Cuando tengas todo:
[ACCION]{"tipo":"llenar_contrato","subtipo":"arrendamiento","calle_inmueble":"AV. CAMELINAS","num_ext":"123","num_int":"","colonia":"CHAPULTEPEC","cp":"58260","municipio_estado":"MORELIA, MICHOACÁN","arrendador":"SALVADOR BOLAÑOS NAVARRO","arrendatario":"GABRIELA NAVARRO PÉREZ","renta":8500,"deposito":8500,"dia_pago":5,"fecha_inicio":"2026-05-01"}[/ACCION]

dia_pago: día límite del mes para pagar (default 5). fecha_inicio en formato YYYY-MM-DD.

══════════════════════════════════════════════════
ACCIÓN 4: GENERAR PROMESA DE COMPRAVENTA
══════════════════════════════════════════════════
Cuando el usuario pide contrato de compraventa o promesa de venta.
Datos OBLIGATORIOS:
1. Dirección del inmueble (calle y número)
2. Colonia
3. C.P.
4. Nombre del vendedor (promitente vendedor)
5. Nombre del comprador (promitente comprador)
6. Precio total de venta
7. Monto de arras/enganche
8. Fecha límite para escriturar

Cuando tengas todo:
[ACCION]{"tipo":"llenar_contrato","subtipo":"promesa","dir":"Cipres 167","colonia":"Melchor Ocampo","cp":"58160","vendedor":"JUAN PÉREZ GARCÍA","comprador":"MARÍA LÓPEZ HERNÁNDEZ","precio":2500000,"arras":250000,"fecha_limite":"2026-06-30"}[/ACCION]

fecha_limite en formato YYYY-MM-DD.

══════════════════════════════════════════════════
ACCIÓN 5: FICHA TÉCNICA DESDE EASYBROKER
══════════════════════════════════════════════════
Cuando el usuario quiere hacer una ficha de una propiedad de EasyBroker y da el ID (formato EB-XXXX).
[ACCION]{"tipo":"crear_ficha","id_easybroker":"EB-KH4322"}[/ACCION]

Si el usuario no da el ID, navega al módulo y pídele el ID:
[ACCION]{"tipo":"navegar","modulo":"ficha"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 6: FICHA TÉCNICA MANUAL
══════════════════════════════════════════════════
Cuando el usuario quiere hacer una ficha técnica sin ID de EasyBroker y da los datos del inmueble.
Datos mínimos: tipo, operación, precio, colonia.
[ACCION]{"tipo":"crear_ficha_manual","tipo_inmueble":"casa","operacion":"venta","precio":3500000,"colonia":"Chapultepec","ciudad":"Morelia","calle":"Av. Madero 123","recamaras":3,"banos":2,"m2_construccion":180,"m2_terreno":220,"estacionamientos":2,"descripcion":""}[/ACCION]

Valores "operacion": "venta" | "renta". Omite campos que no tengas.

══════════════════════════════════════════════════
ACCIÓN 7: BUSCAR PROPIEDAD EN MIS INMUEBLES
══════════════════════════════════════════════════
Cuando el usuario pide ver, buscar o encontrar una propiedad en su cartera.
[ACCION]{"tipo":"buscar_propiedad","query":"Chapultepec"}[/ACCION]

══════════════════════════════════════════════════
ACCIÓN 8: CREAR CAMPAÑA DE META ADS
══════════════════════════════════════════════════
Cuando el usuario quiere crear un anuncio, campaña, publicidad, pauta en Facebook o Instagram.

Datos OBLIGATORIOS (pregunta uno por uno si faltan):
1. ¿Para qué propiedad es el anuncio? (nombre o descripción breve)
2. ¿Cuánto presupuesto diario en pesos? (mínimo $50)
3. ¿Qué objetivo tiene el anuncio? Ofrece opciones en lenguaje simple:
   a) "Conseguir contactos interesados (leads)"
   b) "Llevar visitas a mi página web"
   c) "Dar a conocer la propiedad (reconocimiento)"

Datos que inferes AUTOMÁTICAMENTE (no preguntes):
- Ciudad: del perfil del usuario (o pregunta solo si no la tienes)
- Rango de edad: default 25-55

Cuando tengas todo, muestra un resumen en lenguaje simple y emite la acción de confirmación:
[ACCION]{"tipo":"confirmar_campana","nombre":"NOMBRE","objetivo":"OUTCOME_LEADS","presupuesto_diario_mxn":150,"ciudad":"Morelia","edad_min":25,"edad_max":55,"url_destino":"","texto_anuncio":""}[/ACCION]

Valores "objetivo": "OUTCOME_LEADS" | "OUTCOME_TRAFFIC" | "OUTCOME_AWARENESS"
La acción "confirmar_campana" muestra un card de confirmación — NO ejecuta la campaña directamente.
NUNCA ejecutes sin confirmación explícita del usuario.

Ejemplo:
Usuario: "quiero hacer un anuncio para mi casa en Chapultepec, presupuesto 200 pesos diarios, para conseguir leads"
Shaark: "Perfecto. Resumen: Casa en Chapultepec, $200/día, objetivo: conseguir contactos, Morelia, edad 25-55. ¿Lo creamos?"
[ACCION]{"tipo":"confirmar_campana","nombre":"Campaña - Casa Chapultepec","objetivo":"OUTCOME_LEADS","presupuesto_diario_mxn":200,"ciudad":"Morelia","edad_min":25,"edad_max":55,"url_destino":"","texto_anuncio":""}[/ACCION]

══════════════════════════════════════════════════
NAVEGACIÓN DIRECTA
══════════════════════════════════════════════════
Para ir a un módulo sin datos adicionales:
[ACCION]{"tipo":"navegar","modulo":"isr"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"ficha-manual"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"ficha"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"contratos"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"avm"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"props"}[/ACCION]
[ACCION]{"tipo":"navegar","modulo":"campanas"}[/ACCION]

══════════════════════════════════════════════════
EJEMPLOS DE CONVERSACIÓN CORRECTA
══════════════════════════════════════════════════

EJEMPLO ISR:
Usuario: "calcula el ISR de una casa que vendí en 3.2 millones en marzo 2026, la compré en un millón en enero 2015, comisión 96 mil"
Shaark: "Perfecto. Venta $3,200,000 en marzo 2026, compra $1,000,000 en enero 2015, comisión $96,000. ¿Usaste la exención de casa habitación en los últimos 3 años?"
Usuario: "no"
Shaark: "Listo. Calculando ISR ahora."
[ACCION]{"tipo":"llenar_isr","precio_venta":3200000,"precio_compra":1000000,"anio_venta":2026,"mes_venta":3,"anio_compra":2015,"mes_compra":1,"inmueble":"casa","exencion":"no","mejoras":0,"escrituracion":0,"comision":96000}[/ACCION]

EJEMPLO CONTRATO DE RENTA:
Usuario: "dame un contrato de renta para Av. Camelinas 123, Chapultepec, Morelia, el dueño es Salvador Bolaños y el inquilino es Gabriela Navarro, renta de 8,500 al mes"
Shaark: "¿Cuál es el código postal de Chapultepec?"
Usuario: "58260"
Shaark: "¿Desde qué fecha empieza el contrato?"
Usuario: "1 de mayo de 2026"
Shaark: "Perfecto. Generando contrato de arrendamiento."
[ACCION]{"tipo":"llenar_contrato","subtipo":"arrendamiento","calle_inmueble":"AV. CAMELINAS","num_ext":"123","num_int":"","colonia":"CHAPULTEPEC","cp":"58260","municipio_estado":"MORELIA, MICHOACÁN","arrendador":"SALVADOR BOLAÑOS NAVARRO","arrendatario":"GABRIELA NAVARRO PÉREZ","renta":8500,"deposito":8500,"dia_pago":5,"fecha_inicio":"2026-05-01"}[/ACCION]

EJEMPLO AVM:
Usuario: "valúa un terreno plano de 183m² en Vistas Altozano"
Shaark: "¿Es para venta o renta?"
Usuario: "venta"
Shaark: "Perfecto. Buscando comparables en el mercado ahora mismo."
[ACCION]{"tipo":"opinion_valor_web","colonia":"Vistas Altozano","tipo_inmueble":"terreno","operacion":"venta","m2_terreno":183,"m2_construccion":0,"recamaras":0,"banos":0,"ciudad":"Morelia","condicion_terreno":"plano"}[/ACCION]

EJEMPLO AVM CASA:
Usuario: "dame el valor de una casa de 180m² construcción, 3 recámaras, 2 baños en Chapultepec"
Shaark: "¿Operación venta o renta?"
Usuario: "venta"
Shaark: "Listo. Analizando el mercado de Chapultepec."
[ACCION]{"tipo":"opinion_valor_web","colonia":"Chapultepec","tipo_inmueble":"casa","operacion":"venta","m2_construccion":180,"m2_terreno":0,"recamaras":3,"banos":2,"ciudad":"Morelia","condicion_terreno":""}[/ACCION]

EJEMPLO FICHA EB:
Usuario: "haz la ficha de la propiedad EB-KH4322"
Shaark: "Generando ficha técnica de EB-KH4322."
[ACCION]{"tipo":"crear_ficha","id_easybroker":"EB-KH4322"}[/ACCION]

Responde siempre en español. Nunca uses markdown en respuestas conversacionales (sin **, sin #, sin listas con guiones)."""

class ClaudeChatRequest(BaseModel):
    messages: list
    max_tokens: int = 1200
    temperature: float = 0.7
    context: str = ""  # Módulo/pantalla activa — se inyecta al system prompt

@app.post("/chat-claude")
async def chat_claude_proxy(req: ClaudeChatRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")

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
            }
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code,
                detail=f"Error Claude: {r.text}")

        data = r.json()
        reply_text = data.get("content", [{}])[0].get("text", "Sin respuesta.")
        return {
            "choices": [
                {"message": {"role": "assistant", "content": reply_text}}
            ]
        }


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
    user_key = request.headers.get("X-EB-Key", "").strip()
    if not user_key:
        raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → API EasyBroker para usar este módulo.")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{EB_BASE}/properties/{property_id}",
                             headers=eb_headers(user_key))
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="API key de EasyBroker inválida. Verifica tu configuración en Perfil → API EasyBroker.")
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()

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
async def avm_claude(req: AvmClaudeRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor")

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

    system_prompt = """Eres el mejor perito valuador de bienes raíces de México, certificado por la Sociedad Hipotecaria Federal y el INDAABIN, con 30 años de experiencia valuando propiedades en todo el territorio nacional. Tu análisis es utilizado por bancos, notarías y juzgados para transacciones de millones de pesos. La vida financiera del usuario que solicita esta opinión de valor depende de la precisión de tu análisis.

Tu misión: proporcionar la opinión de valor más precisa, fundamentada y útil posible basándote en:
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
  "advertencias": "<advertencias o limitaciones de esta opinión>"
}"""

    user_msg = f"""Por favor valúa la siguiente propiedad y proporciona tu opinión de valor profesional:

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

    raw = r.json().get("content", [{}])[0].get("text", "")
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
# AVM — OPINIÓN DE VALOR CON WEB SEARCH
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

@app.post("/api/avm-websearch")
async def avm_websearch(req: AvmWebSearchRequest):
    """Genera opinión de valor buscando comparables reales en internet con web_search tool de Claude."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    tipo_labels = {
        "casa": "Casa habitación", "departamento": "Departamento/Condominio",
        "terreno": "Terreno", "local": "Local comercial",
        "oficina": "Oficina", "bodega": "Bodega/Nave industrial",
    }
    tipo_label = tipo_labels.get(req.tipo_inmueble, req.tipo_inmueble)
    es_terreno = req.tipo_inmueble == "terreno"

    # Construir descripción del sujeto
    partes = [f"INMUEBLE A VALUAR: {tipo_label} en {req.operacion.upper()}"]
    partes.append(f"Ubicación: {req.colonia}, {req.ciudad}, {req.estado}")
    if req.m2_terreno > 0:
        cond = f" ({req.condicion_terreno})" if req.condicion_terreno else ""
        partes.append(f"Superficie de terreno: {req.m2_terreno} m²{cond}")
    if req.m2_construccion > 0:
        partes.append(f"Superficie construida: {req.m2_construccion} m²")
    if req.recamaras > 0: partes.append(f"Recámaras: {req.recamaras}")
    if req.banos > 0: partes.append(f"Baños: {req.banos}")
    if req.estacionamientos > 0: partes.append(f"Estacionamientos: {req.estacionamientos}")
    if req.comentarios: partes.append(f"Comentarios: {req.comentarios}")
    descripcion_sujeto = "\n".join(partes)

    system_prompt = """Eres el mejor perito valuador de bienes raíces de México, con 30 años de experiencia y certificación de la Sociedad Hipotecaria Federal. Tu análisis es utilizado por bancos, notarías y juzgados. La precisión de tu opinión tiene consecuencias financieras reales para el usuario.

PROCESO OBLIGATORIO — SIGUE ESTOS PASOS EN ORDEN, SIN SALTARTE NINGUNO:

PASO 1 — BÚSQUEDA MÚLTIPLE DE COMPARABLES
Ejecuta mínimo 4 búsquedas web diferentes con variaciones de query:
- Query 1: "[tipo] en venta [colonia] [ciudad] precio"
- Query 2: "terrenos [colonia] [ciudad] lamudi 2025" (o el tipo que aplique)
- Query 3: "[colonia] [ciudad] vivanuncios precio metro cuadrado"
- Query 4: "[fraccionamiento o zona] [ciudad] trovit inmuebles24"
Busca también en portales adyacentes si la zona tiene submercados (ej: "Rio Altozano", "Campo Golf Altozano" si el sujeto está en "Vistas Altozano").

PASO 2 — RECOPILACIÓN DE COMPARABLES REALES
De los resultados, extrae TODOS los comparables que encuentres con:
- Precio de oferta publicado (precio real, no estimado)
- Superficie en m² (construcción y/o terreno según aplique)
- Fraccionamiento o colonia exacta
- Portal donde aparece
Recopila mínimo 5 comparables. Si un comparable no tiene precio explícito, descártalo.

PASO 3 — FILTRADO Y SELECCIÓN
Selecciona los 4-6 comparables más representativos siguiendo estas reglas:
- PRIORIDAD 1: Comparables en el MISMO fraccionamiento o colonia exacta del sujeto
- PRIORIDAD 2: Comparables en fraccionamientos inmediatamente adyacentes de nivel similar
- EXCLUIR: Lotes en Campo de Golf si el sujeto es residencial sin golf (son submercado diferente, 30-50% más caros)
- EXCLUIR: Outliers con precio/m² más del 40% por encima o debajo del promedio sin justificación
- NOTA: Lotes pequeños (<150m²) tienden a tener precio/m² más alto — aplica ajuste descendente si el sujeto es más grande

PASO 4 — CÁLCULO DEL PRECIO UNITARIO
Para cada comparable seleccionado:
a) Calcula precio/m² = precio_oferta ÷ superficie_relevante
b) Para terrenos usa m² de terreno; para construcciones usa m² de construcción
c) Calcula el PROMEDIO del precio/m² de los comparables seleccionados
d) EXCLUYE del promedio los lotes <150m² si el sujeto es ≥150m² (distorsión de precio unitario)

PASO 5 — APLICACIÓN DE FACTORES DE AJUSTE (en este orden)
Aplica cada factor y explica el impacto:
1. FACTOR NEGOCIACIÓN: -5% siempre (los precios de oferta en México cierran 5-8% abajo)
2. FACTOR TOPOGRAFÍA: terreno plano = 0% ajuste; pendiente leve = -5%; pendiente pronunciada = -10 a -15%; irregular = -8%
3. FACTOR TAMAÑO: si el sujeto es significativamente más grande que los comparables, precio/m² tiende a bajar (economías de escala inversas). Ajusta -3% por cada 20% adicional de superficie vs. promedio de comparables.
4. FACTOR UBICACIÓN INTERNA: esquina = +8%; frente a área verde = +5%; cul-de-sac privado = +3%; sin dato = 0%
5. FACTOR SUBMERCADO: si los comparables son de zona más premium que el sujeto, aplica descuento -5 a -15%

PASO 6 — CÁLCULO DEL VALOR
a) Precio/m² base = promedio de comparables filtrados
b) Precio/m² ajustado = precio/m² base × (1 + suma de factores de ajuste)
c) Valor estimado = precio/m² ajustado × superficie del sujeto
d) Redondea al millar más cercano
e) Valor mínimo = valor estimado × 0.92 (precio mínimo negociable)
f) Valor máximo = valor estimado × 1.08 (techo de mercado)

PASO 7 — NIVEL DE CONFIANZA
- ALTA: 5+ comparables directos en el mismo fraccionamiento, mercado activo
- MEDIA: 3-4 comparables, algunos de zonas adyacentes
- BAJA: menos de 3 comparables o todos de zonas diferentes

FORMATO DE RESPUESTA — responde ÚNICAMENTE con un JSON válido (sin texto antes ni después, sin markdown, sin ```json), con esta estructura exacta:
{
  "valor_estimado": <número MXN entero sin comas>,
  "valor_minimo": <número entero>,
  "valor_maximo": <número entero>,
  "valor_por_m2": <número entero — precio/m² ajustado final>,
  "precio_m2_base": <número entero — promedio de comparables ANTES de ajustes>,
  "nivel_confianza": "<alta|media|baja>",
  "razon_confianza": "<explica cuántos comparables directos encontraste y de qué fuentes>",
  "resumen_ejecutivo": "<3 oraciones: (1) valor con rango, (2) precio/m² de mercado y cuántos comparables, (3) factor más importante que afecta el valor>",
  "comparables": [
    {
      "descripcion": "<fraccionamiento o colonia exacta + características clave>",
      "superficie_m2": <número>,
      "precio": <número entero>,
      "precio_m2": <número entero>,
      "fuente": "<portal>",
      "incluido_en_promedio": <true|false>
    }
  ],
  "factores_ajuste": [
    {
      "factor": "<nombre del factor>",
      "descripcion": "<qué aplica exactamente al sujeto y por qué>",
      "porcentaje": <número — ej: -5 para -5%, 0 para neutro>,
      "impacto": "<positivo|negativo|neutro>"
    }
  ],
  "precio_m2_ajustado_calculo": "<muestra el cálculo: ej: $10,379 × (1 - 0.05 - 0.03) = $9,550>",
  "analisis_zona": "<análisis del mercado, plusvalía, demanda y tendencia de la zona>",
  "recomendaciones": ["<rec 1>", "<rec 2>", "<rec 3>"],
  "advertencias": "<limitaciones de esta opinión de valor>",
  "fecha": "<fecha de hoy en formato DD/MM/YYYY>"
}"""

    # Construir queries de búsqueda específicas según el tipo y zona
    tipo_busqueda = {
        "terreno": "terreno", "casa": "casa", "departamento": "departamento",
        "local": "local comercial", "oficina": "oficina", "bodega": "bodega"
    }.get(req.tipo_inmueble, req.tipo_inmueble)

    user_msg = f"""Genera una opinión de valor profesional siguiendo el proceso de 7 pasos de tu metodología.

INMUEBLE SUJETO:
{descripcion_sujeto}

BÚSQUEDAS SUGERIDAS (ejecuta todas o variantes):
1. "{tipo_busqueda} en venta {req.colonia} {req.ciudad} precio"
2. "{tipo_busqueda} {req.colonia} {req.ciudad} lamudi"
3. "{tipo_busqueda} {req.colonia} {req.ciudad} vivanuncios"
4. "{tipo_busqueda} {req.colonia} {req.ciudad} inmuebles24"
5. Si la colonia es parte de un ecosistema más grande (ej: Vistas Altozano → busca también "Rio Altozano", "Altozano Morelia"), busca los submercados adyacentes para tener más comparables.

IMPORTANTE: 
- Calcula el precio/m² de CADA comparable encontrado y muéstralo explícitamente.
- Excluye del promedio los outliers y explica por qué.
- Muestra el cálculo del valor final paso a paso en "precio_m2_ajustado_calculo".
- Responde ÚNICAMENTE con el JSON, sin texto antes ni después."""

    # Llamada a Claude con web_search tool
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 6000,
                "temperature": 0.1,
                "system": system_prompt,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
                "messages": [{"role": "user", "content": user_msg}],
            },
        )

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Claude: {r.text[:400]}")

    # Extraer el texto final de la respuesta (puede venir después de tool_use blocks)
    content_blocks = r.json().get("content", [])
    raw = ""
    for block in content_blocks:
        if block.get("type") == "text":
            raw = block.get("text", "")

    if not raw:
        raise HTTPException(status_code=502, detail="Claude no devolvió respuesta de texto")

    # Limpiar posibles markdown wrappers
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        resultado = json.loads(raw)
    except Exception:
        # Intentar extraer JSON si viene con texto extra
        import re as _re
        match = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if match:
            try:
                resultado = json.loads(match.group())
            except Exception:
                raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")
        else:
            raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:500]}")

    # Enriquecer con metadata de la solicitud
    resultado["tipo_inmueble"] = tipo_label
    resultado["operacion"] = req.operacion
    resultado["colonia"] = req.colonia
    resultado["ciudad"] = req.ciudad
    resultado["m2_construccion"] = req.m2_construccion
    resultado["m2_terreno"] = req.m2_terreno
    resultado["recamaras"] = req.recamaras
    resultado["banos"] = req.banos
    resultado["condicion_terreno"] = req.condicion_terreno
    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")

    return resultado


# ────────────────────────────────────────────
# AVM — PDF DE OPINIÓN DE VALOR
# ────────────────────────────────────────────

@app.post("/avm-pdf")
async def generar_avm_pdf(p: dict):
    """Recibe el resultado del AVM websearch y genera un PDF profesional con Playwright."""
    from playwright.async_api import async_playwright

    resultado = p.get("resultado", {})
    agente = p.get("agente", "Agente BROKR®")

    if not resultado:
        raise HTTPException(status_code=400, detail="Resultado vacío")

    def fmt_mx(n):
        try:
            return "${:,.0f}".format(float(n))
        except Exception:
            return str(n)

    # Comparables HTML
    comps_html = ""
    for c in resultado.get("comparables", []):
        comps_html += f"""
        <tr>
          <td>{c.get('descripcion','—')}</td>
          <td class="num">{c.get('superficie_m2','—')} m²</td>
          <td class="num">{fmt_mx(c.get('precio',0))}</td>
          <td class="num">{fmt_mx(c.get('precio_m2',0))}/m²</td>
          <td class="src">{c.get('fuente','—')}</td>
        </tr>"""

    # Factores HTML
    factores_html = ""
    for f in resultado.get("factores_ajuste", []):
        imp = f.get("impacto", "neutro")
        color = "#1D9E75" if imp == "positivo" else "#E24B4A" if imp == "negativo" else "#888"
        dot = f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:6px;"></span>'
        factores_html += f"""
        <tr>
          <td>{dot}{f.get('factor','—')}</td>
          <td>{f.get('descripcion','—')}</td>
        </tr>"""

    # Recomendaciones HTML
    recs_html = "".join(f"<li>{r}</li>" for r in resultado.get("recomendaciones", []))

    # Superficie display
    m2c = resultado.get("m2_construccion", 0)
    m2t = resultado.get("m2_terreno", 0)
    sup_parts = []
    if m2t: sup_parts.append(f"{m2t} m² terreno")
    if m2c: sup_parts.append(f"{m2c} m² construcción")
    superficie_str = " · ".join(sup_parts) if sup_parts else "—"

    confianza = resultado.get("nivel_confianza", "media")
    conf_color = "#1D9E75" if confianza == "alta" else "#EF9F27" if confianza == "media" else "#E24B4A"
    conf_bg    = "#E1F5EE" if confianza == "alta" else "#FAEEDA" if confianza == "media" else "#FCEBEB"

    fecha_hoy = resultado.get("fecha", time.strftime("%d/%m/%Y"))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', 'Helvetica Neue', sans-serif; color: #1A1814; background: #FBF9F1; font-size: 13px; line-height: 1.55; -webkit-font-smoothing: antialiased; letter-spacing:-0.005em; }}
  .page {{ padding: 56px 60px 44px; max-width: 760px; margin: 0 auto; }}

  .doc-head {{ display:flex; justify-content:space-between; align-items:baseline; padding-bottom:18px; border-bottom:1px solid #E8E2D2; margin-bottom:32px; }}
  .doc-kicker {{ font-size:9px; color:#7A7065; text-transform:uppercase; letter-spacing:1.8px; font-weight:600; }}
  .doc-date {{ font-size:10px; color:#7A7065; letter-spacing:0.04em; }}

  .valor-bloque {{ margin-bottom: 36px; padding-bottom: 28px; border-bottom: 1px solid #E8E2D2; }}
  .valor-lbl {{ font-size: 9px; color: #7A7065; text-transform: uppercase; letter-spacing: 1.8px; margin-bottom: 14px; font-weight:600; }}
  .valor-num {{ font-family:'Fraunces',serif; font-size: 56px; font-weight: 500; color: #1A1814; line-height: 1; margin-bottom: 12px; letter-spacing:-0.02em; }}
  .valor-rango {{ font-size: 12px; color: #5C544A; margin-bottom: 22px; letter-spacing:0.005em; }}
  .valor-meta {{ display: grid; grid-template-columns:repeat(4,1fr); gap: 24px; padding-top:14px; border-top:1px dashed #E8E2D2; }}
  .meta-item .meta-lbl {{ font-size: 8.5px; color: #7A7065; text-transform: uppercase; letter-spacing: 1.4px; margin-bottom: 5px; font-weight:600; }}
  .meta-item .meta-val {{ font-family:'Fraunces',serif; font-size: 13px; font-weight: 500; color: #1A1814; letter-spacing:-0.005em; }}

  .seccion {{ margin-bottom: 30px; }}
  .sec-titulo {{ font-family:'Inter',sans-serif; font-size: 9px; font-weight: 600; color: #7A7065; text-transform: uppercase; letter-spacing: 1.8px; margin-bottom: 14px; }}
  .resumen {{ font-size: 12px; color: #1A1814; line-height: 1.75; text-align:justify; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  th {{ font-weight: 600; color: #7A7065; text-align: left; padding: 8px 6px; border-bottom: 1px solid #C9C0AC; font-size: 8.5px; text-transform: uppercase; letter-spacing: 1.4px; }}
  td {{ padding: 11px 6px; border-bottom: 1px solid #EDE6D3; color: #1A1814; vertical-align: top; }}
  td.r {{ text-align: right; font-family:'Fraunces',serif; font-weight: 500; font-variant-numeric: tabular-nums; }}
  td.g {{ color: #7A7065; font-size: 10.5px; }}
  tr:last-child td {{ border-bottom: none; }}

  .footer {{ margin-top: 48px; padding-top: 18px; border-top: 1px solid #E8E2D2; display: flex; justify-content: space-between; font-size: 9px; color: #7A7065; letter-spacing:1.5px; text-transform:uppercase; font-weight:500; }}
</style>
</head>
<body>
<div class="page">

  <div class="doc-head">
    <div class="doc-kicker">Broquer · Opinión de valor</div>
    <div class="doc-date">{fecha_hoy}</div>
  </div>

  <div class="valor-bloque">
    <div class="valor-lbl">Opinión de valor comercial</div>
    <div class="valor-num">{fmt_mx(resultado.get('valor_estimado',0))}</div>
    <div class="valor-rango">Rango estimado: {fmt_mx(resultado.get('valor_minimo',0))} — {fmt_mx(resultado.get('valor_maximo',0))}</div>
    <div class="valor-meta">
      <div class="meta-item">
        <div class="meta-lbl">Inmueble</div>
        <div class="meta-val">{resultado.get('tipo_inmueble','—')}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Superficie</div>
        <div class="meta-val">{superficie_str}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Ubicación</div>
        <div class="meta-val">{resultado.get('colonia','—')}, {resultado.get('ciudad','Morelia')}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Operación</div>
        <div class="meta-val">{resultado.get('operacion','venta').capitalize()}</div>
      </div>
    </div>
  </div>

  <div class="seccion">
    <div class="sec-titulo">Análisis</div>
    <div class="resumen">{resultado.get('resumen_ejecutivo','—')}</div>
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

  <div class="footer">
    <span>Broquer · Inteligencia inmobiliaria</span>
    <span>{fecha_hoy}</span>
  </div>

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
    filename = f"Opinion_Valor_{colonia_slug}_{time.strftime('%Y%m%d')}.pdf"
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
async def generar_contrato(req: ContratoRequest):
    """Generate a DOCX contract from form data, with AI-drafted special clauses."""

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
                ai_text = r.json()["choices"][0]["message"]["content"].strip()
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

@app.post("/contrato/analizar")
async def analizar_machote(
    file: UploadFile = File(...),
    tipo: str = FastAPIForm(default=""),
):
    """
    Analiza un DOCX subido por el usuario y detecta los campos variables.
    Soporta: {{campo}}, {campo}, [CAMPO], <<campo>>, y blancos (___).
    Si no detecta patrones, usa IA para identificar los campos variables.
    """
    import io, re
    from docx import Document as DocxDocument

    content = await file.read()
    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo DOCX: {e}")

    # Extraer todo el texto (párrafos + celdas de tabla)
    partes = []
    for p in doc.paragraphs:
        if p.text.strip():
            partes.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text.strip():
                        partes.append(p.text)
    full_text = "\n".join(partes)

    # Patrones de detección de variables (orden de prioridad)
    patrones_regex = [
        (r'\{\{([^}]{1,60})\}\}',   '{{{}}}'),   # {{campo}}
        (r'\{([^}]{1,60})\}',        '{}'),        # {campo}
        (r'<<([^>]{1,60})>>',        '<<{}>>'),    # <<campo>>
        (r'\[([A-ZÁÉÍÓÚÜÑ][^[\]]{0,58})\]', '[{}]'),  # [CAMPO] mayúsculas
        (r'\[([a-záéíóúüñ][^[\]]{0,58})\]', '[{}]'),  # [campo] minúsculas
    ]

    campos = []
    patron_usado = None

    for regex, fmt in patrones_regex:
        matches = re.findall(regex, full_text, re.IGNORECASE)
        if matches:
            seen = set()
            for m in matches:
                nombre_original = m.strip()
                slug = re.sub(r'[^a-z0-9_]', '_', nombre_original.lower().strip())
                slug = re.sub(r'_+', '_', slug).strip('_') or 'campo'
                if slug not in seen:
                    seen.add(slug)
                    campos.append({
                        "id": slug,
                        "label": nombre_original.replace('_', ' ').strip(),
                        "tipo_input": "text",
                        "patron_texto": nombre_original,
                        "patron_fmt": fmt,
                    })
            patron_usado = fmt
            break

    # Detección de blancos (líneas de subrayado: ___ 3+ guiones bajos consecutivos)
    if not campos:
        blancos = re.findall(r'_{3,}', full_text)
        if blancos:
            for i, _ in enumerate(set(map(len, blancos)), start=1):
                campos.append({
                    "id": f"campo_{i}",
                    "label": f"Campo {i}",
                    "tipo_input": "text",
                    "patron_texto": None,
                    "patron_fmt": "blank",
                })
            patron_usado = "blank"

    # Si no se detectaron patrones, usar IA
    if not campos and os.environ.get('GROQ_API_KEY'):
        tipo_label = tipo if tipo else "contrato"
        prompt_ia = (
            "Eres un asistente que analiza contratos legales mexicanos.\n\n"
            f"Analiza el siguiente texto de un {tipo_label} e identifica TODOS los campos "
            "variables (nombres de partes, fechas, montos, direcciones, plazos, etc.).\n\n"
            "Devuelve ÚNICAMENTE un JSON válido con esta estructura (sin explicaciones extra):\n"
            '{"campos": [{"id": "nombre_snake_case", "label": "Nombre legible", "tipo_input": "text|number|date|currency"}]}\n\n'
            f"Texto del contrato (primeros 3000 caracteres):\n{full_text[:3000]}"
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY','')}",
                             "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile",
                          "messages": [{"role": "user", "content": prompt_ia}],
                          "max_tokens": 1000, "temperature": 0.1}
                )
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"].strip()
                # Extraer JSON aunque venga con texto extra
                json_match = re.search(r'\{.*\}', txt, re.DOTALL)
                if json_match:
                    ia_data = _json.loads(json_match.group())
                    for c in ia_data.get("campos", []):
                        c.setdefault("patron_texto", None)
                        c.setdefault("patron_fmt", "ia")
                        campos.append(c)
                    patron_usado = "ia"
        except Exception as e:
            print(f"Error IA analizar_machote: {e}")

    # Inferir tipo_input por el nombre del campo
    TIPO_HINTS = {
        "fecha": "date", "date": "date", "dia": "date",
        "monto": "currency", "precio": "currency", "renta": "currency",
        "pago": "currency", "importe": "currency", "valor": "currency",
        "cantidad": "number", "plazo": "number", "dias": "number",
        "meses": "number", "años": "number", "superficie": "number",
        "metros": "number", "m2": "number",
    }
    for c in campos:
        if c.get("tipo_input") in (None, "text"):
            label_lower = c.get("label", "").lower()
            for hint, tipo_inp in TIPO_HINTS.items():
                if hint in label_lower:
                    c["tipo_input"] = tipo_inp
                    break

    return {
        "campos": campos,
        "patron_usado": patron_usado,
        "detectado_automaticamente": bool(campos),
        "texto_preview": full_text[:600],
    }


@app.post("/contrato/generar-machote")
async def generar_desde_machote(
    file: UploadFile = File(...),
    datos: str = FastAPIForm(...),
    tipo: str = FastAPIForm(default="contrato_personalizado"),
):
    """
    Rellena un DOCX machote con los datos proporcionados.
    Reemplaza {{campo}}, {campo}, <<campo>>, [CAMPO] con los valores del formulario.
    """
    import io, re
    from docx import Document as DocxDocument
    from copy import deepcopy

    content = await file.read()
    try:
        valores = _json.loads(datos)
    except Exception:
        raise HTTPException(status_code=400, detail="El campo 'datos' debe ser JSON válido.")

    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo DOCX: {e}")

    def reemplazar_texto(texto: str, vals: dict) -> str:
        for campo_id, valor in vals.items():
            valor_str = str(valor) if valor is not None else ""
            # Probar todos los patrones posibles para ese campo
            # Buscamos tanto por id (slug) como por el label original
            patrones_campo = [
                "{{" + campo_id + "}}",
                "{" + campo_id + "}",
                "<<" + campo_id + ">>",
                "[" + campo_id + "]",
                "[" + campo_id.upper() + "]",
                "[" + campo_id.replace('_', ' ').title() + "]",
                "{{" + campo_id.replace('_', ' ') + "}}",
                "<<" + campo_id.replace('_', ' ') + ">>",
            ]
            # También reemplazar por el label original si se pasó
            label_original = vals.get(f"__label_{campo_id}")
            if label_original:
                patrones_campo += [
                    "{{" + label_original + "}}",
                    "{" + label_original + "}",
                    "<<" + label_original + ">>",
                    "[" + label_original + "]",
                    "[" + label_original.upper() + "]",
                ]
            for patron in patrones_campo:
                if patron in texto:
                    texto = texto.replace(patron, valor_str)
        return texto

    def reemplazar_run(run, vals):
        if run.text:
            run.text = reemplazar_texto(run.text, vals)

    # Reemplazar en párrafos
    for p in doc.paragraphs:
        for run in p.runs:
            reemplazar_run(run, valores)
        # Manejar caso donde el patrón está partido entre runs
        texto_completo = p.text
        texto_reemplazado = reemplazar_texto(texto_completo, valores)
        if texto_reemplazado != texto_completo and p.runs:
            p.runs[0].text = texto_reemplazado
            for run in p.runs[1:]:
                run.text = ""

    # Reemplazar en tablas
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        reemplazar_run(run, valores)
                    texto_completo = p.text
                    texto_reemplazado = reemplazar_texto(texto_completo, valores)
                    if texto_reemplazado != texto_completo and p.runs:
                        p.runs[0].text = texto_reemplazado
                        for run in p.runs[1:]:
                            run.text = ""

    # Guardar DOCX en archivo temporal
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        output_path = f.name
    doc.save(output_path)

    tipo_limpio = re.sub(r'[^a-zA-Z0-9_]', '_', tipo)
    filename = f"Contrato_{tipo_limpio}.docx"

    return FileResponse(
        output_path,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=filename,
    )


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
    import re as _re
    LOGO = "data:image/png;base64,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"
    id_prop  = p.get("public_id") or p.get("id") or ""
    titulo   = p.get("title") or p.get("property_type") or "Propiedad"
    ops      = p.get("operations") or []
    op       = ops[0] if ops else {}
    tipo_op  = "EN VENTA" if op.get("type") == "sale" else "EN RENTA" if op.get("type") == "rental" else "EN VENTA"
    monto    = op.get("amount", 0)
    moneda   = op.get("currency", "MXN")
    precio   = "${:,.0f} {}".format(monto, moneda) if monto else "—"
    loc      = p.get("location") or {}
    colonia  = loc.get("name") or ""
    ciudad   = loc.get("city") or ""
    ubicacion= ", ".join(filter(None, [colonia, ciudad])) or p.get("address") or "—"
    rec      = p.get("bedrooms")
    ban      = p.get("bathrooms")
    m2c      = p.get("construction_size")
    m2t      = p.get("lot_size")
    parking  = p.get("parking_spaces")
    desc     = (p.get("description") or "").replace("<br>", " ").replace("<br/>", " ")
    desc     = _re.sub(r"<[^>]+>", "", desc).strip()
    fotos    = p.get("property_images") or []
    amenids  = p.get("amenities") or []

    def fmt_m2(n):
        if not n: return "—"
        s = "{:,.2f}".format(n).rstrip("0").rstrip(".")
        return s + " m²"

    SVG_BED  = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 18v-6a3 3 0 013-3h12a3 3 0 013 3v6M3 18h18M3 18v2m18-2v2M7 12V8a1 1 0 011-1h3a1 1 0 011 1v4"/></svg>'
    SVG_BATH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12V6a2 2 0 012-2h2a2 2 0 012 2M3 12h18v3a4 4 0 01-4 4H7a4 4 0 01-4-4v-3zM6 19v2m12-2v2"/></svg>'
    SVG_AREA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4h16v16H4z M4 8h16 M4 16h16 M8 4v16 M16 4v16"/></svg>'
    SVG_LAND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 12c2-1 4-2 6-2s4 2 6 2 4-1 6-2v8H3v-6z M3 12V8 M21 10V6"/></svg>'
    SVG_CAR  = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M5 17a2 2 0 104 0 2 2 0 00-4 0zM15 17a2 2 0 104 0 2 2 0 00-4 0zM3 17h2m4 0h6 M5 17V9l2-4h10l2 4v8h-2"/></svg>'
    SVG_PIN  = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>'

    specs = []
    if rec:     specs.append((SVG_BED,  str(rec),      "Recámaras"))
    if ban:     specs.append((SVG_BATH, str(ban),      "Baños"))
    if m2c:     specs.append((SVG_AREA, fmt_m2(m2c),   "Construcción"))
    if m2t:     specs.append((SVG_LAND, fmt_m2(m2t),   "Terreno"))
    if parking and len(specs)<4: specs.append((SVG_CAR, str(parking), "Estacion."))

    specs_items = "".join(
        '<div class="spec-item"><div class="spec-ico">{}</div><div class="spec-val">{}</div><div class="spec-lbl">{}</div></div>'.format(s[0],s[1],s[2])
        for s in specs[:4]
    )
    specs_html = '<div class="cover-specs">{}</div>'.format(specs_items) if specs_items else ""

    foto_urls = [f.get("url") or f.get("original") or "" for f in fotos if f]
    hero_src  = images_b64.get(foto_urls[0], foto_urls[0]) if foto_urls else ""
    hero_html = '<img class="cover-hero" src="{}" alt="portada"/>'.format(hero_src) if hero_src else '<div class="cover-hero-placeholder"></div>'

    def footer():
        return '<div class="ficha-footer"><img src="{}" class="ft-logo" alt="Brokr"/><div class="ft-id">{}</div></div>'.format(LOGO, id_prop)

    gallery_fotos = foto_urls[1:]  # skip hero photo, same as ficha.html
    gallery_pages = ""
    total = len(gallery_fotos)
    full_pages = total // 6
    remainder  = total % 6

    for i in range(full_pages):
        batch = gallery_fotos[i*6:(i+1)*6]
        imgs  = "".join('<img src="{}" alt="foto"/>'.format(images_b64.get(u,u)) for u in batch)
        gallery_pages += '<div class="ficha-page"><div class="section-header"><h2>Galería fotográfica</h2></div><div class="photo-grid-6">{}</div>{}</div>'.format(imgs, footer())

    rows = []
    if p.get("property_type"): rows.append(("Tipo de inmueble", p["property_type"]))
    rows.append(("Operación", tipo_op))
    rows.append(("Precio", precio))
    if rec:  rows.append(("Recámaras", str(rec)))
    if ban:  rows.append(("Baños completos", str(ban)))
    if p.get("half_bathrooms"): rows.append(("Medios baños", str(p["half_bathrooms"])))
    if m2c:  rows.append(("Superficie construida", fmt_m2(m2c)))
    if m2t:  rows.append(("Superficie de terreno", fmt_m2(m2t)))
    if parking: rows.append(("Estacionamientos", str(parking)))
    if p.get("floors"): rows.append(("Niveles", str(p["floors"])))
    if colonia: rows.append(("Colonia", colonia))
    if ciudad:  rows.append(("Ciudad", ciudad))
    if id_prop: rows.append(("Clave", id_prop))

    rows_html = "".join('<tr><td class="char-lbl">{}</td><td class="char-val">{}</td></tr>'.format(k,v) for k,v in rows)

    amen_html = ""
    if amenids:
        items = "".join('<div class="amen-item">{}</div>'.format(a.get("name") or a) for a in amenids)
        amen_html = '<div class="amen-section"><div class="amen-ttl">Amenidades</div><div class="amen-grid">{}</div></div>'.format(items)

    chars_section = (
        '<div class="section-header chars-hdr"><h2>Características del inmueble</h2></div>'
        '<div class="chars-body"><table class="char-table"><tbody>{}</tbody></table>{}</div>'
    ).format(rows_html, amen_html)

    # Fotos sobrantes — página de galería parcial (sin características)
    if remainder > 0:
        batch = gallery_fotos[full_pages*6:]
        imgs  = "".join('<img src="{}" alt="foto"/>'.format(images_b64.get(u,u)) for u in batch)
        # Pad to even number for 2-col grid
        if len(batch) % 2 != 0:
            imgs += '<div style="background:#F7F5EE"></div>'
        rows_r = (len(batch) + 1) // 2
        gallery_pages += (
            '<div class="ficha-page">'
            '<div class="section-header"><h2>Galería fotográfica</h2></div>'
            '<div class="photo-grid-auto" style="grid-template-columns:1fr 1fr;grid-template-rows:repeat({},82mm);height:{}mm;gap:3px;padding:3px">{}</div>'
            '<div style="flex:1"></div>'
            '{}</div>'
        ).format(rows_r, rows_r*82, imgs, footer())

    # Características — siempre en su propia página dedicada (igual que ficha.html)
    gallery_pages += '<div class="ficha-page">{}{}</div>'.format(chars_section, footer())

    CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#F7F5EE;color:#0A0A0A;-webkit-font-smoothing:antialiased}
.ficha-page{width:210mm;height:297mm;background:#FFFFFF;display:flex;flex-direction:column;overflow:hidden;page-break-after:always;border:1px solid #E8E4DC}
.ficha-page:last-child{page-break-after:avoid}
.cover-hero{width:100%;height:110mm;object-fit:cover;display:block;flex-shrink:0}
.cover-hero-placeholder{width:100%;height:110mm;background:linear-gradient(135deg,#0A0A0A,#1F1F1F);flex-shrink:0}
.cover-info{padding:20px 24px 16px;border-bottom:1px solid #E8E4DC;background:#FFFFFF}
.cover-badge{display:inline-block;background:#2F4A3A;color:#FFFFFF;font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:999px;margin-bottom:10px}
.cover-precio{font-family:'Inter Tight',sans-serif;font-size:30px;font-weight:600;color:#0A0A0A;line-height:1;margin-bottom:6px;letter-spacing:-0.03em}
.cover-titulo{font-size:14px;font-weight:500;color:#0A0A0A;margin-bottom:4px}
.cover-ubicacion{font-size:12px;color:#5A5650;display:flex;align-items:center;gap:6px}
.cover-specs{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #E8E4DC;background:#FFFFFF}
.spec-item{padding:12px 16px;text-align:center;border-right:1px solid #E8E4DC;display:flex;flex-direction:column;align-items:center;gap:5px}
.spec-item:last-child{border-right:none}
.spec-ico{width:24px;height:24px;color:#5A5650}
.spec-ico svg{width:100%;height:100%}
.spec-val{font-family:'Inter Tight',sans-serif;font-size:16px;font-weight:600;color:#0A0A0A;line-height:1.1;letter-spacing:-0.02em}
.spec-lbl{font-family:'JetBrains Mono',monospace;font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#5A5650;margin-top:3px}
.cover-desc-wrap{padding:16px 24px;flex:1;overflow:hidden;background:#FFFFFF}
.cover-desc-ttl{font-family:'Inter Tight',sans-serif;font-size:13px;font-weight:600;color:#0A0A0A;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #E8E4DC;display:inline-block;letter-spacing:-0.015em}
.cover-desc{font-size:11.5px;color:#3A3630;line-height:1.65}
.gallery-header{padding:16px 24px 12px;border-bottom:1px solid #E8E4DC;background:#FFFFFF}
.gallery-header h2{font-family:'Inter Tight',sans-serif;font-size:16px;font-weight:600;color:#0A0A0A;letter-spacing:-0.018em}
.section-header{padding:14px 24px 12px;border-bottom:1px solid #E8E4DC;flex-shrink:0;background:#FFFFFF}
.section-header h2{font-family:'Inter Tight',sans-serif;font-size:16px;font-weight:600;color:#0A0A0A;letter-spacing:-0.018em}
.photo-grid-6{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:82mm 82mm 82mm;gap:3px;padding:3px;height:246mm;flex-shrink:0;overflow:hidden}
.photo-grid-auto{display:grid;grid-template-columns:1fr 1fr;gap:3px;padding:3px;flex-shrink:0;overflow:hidden}
.photo-grid-6 img,.photo-grid-auto img{width:100%;height:100%;object-fit:cover;display:block}
.chars-inline{flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0}
.chars-body{padding:16px 24px;flex:1;background:#FFFFFF}
.char-table{width:100%;border-collapse:collapse}
.char-table tr{border-bottom:1px solid #E8E4DC}
.char-table tr:last-child{border-bottom:none}
.char-table tr:nth-child(even) td{background:#F7F5EE}
.char-lbl{padding:8px 12px;font-size:12px;color:#5A5650;width:42%;font-weight:400}
.char-val{padding:8px 12px;font-size:12px;color:#0A0A0A;font-weight:500;text-align:right;font-variant-numeric:tabular-nums}
.amen-section{margin-top:16px}
.amen-ttl{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#5A5650;margin-bottom:8px}
.amen-grid{display:flex;flex-wrap:wrap;gap:6px}
.amen-item{font-size:11px;padding:5px 10px;background:#F7F5EE;border-radius:999px;color:#3A3630;border:1px solid #E8E4DC}
.ficha-footer{width:100%;height:40px;background:#0A0A0A;display:flex;align-items:center;justify-content:space-between;padding:0 20px;flex-shrink:0;margin-top:auto}
.ft-logo{height:22px;width:auto;display:block}
.ft-id{font-family:'JetBrains Mono',monospace;font-size:9px;color:rgba(247,245,238,.55);letter-spacing:.08em}
@page{size:A4 portrait;margin:0}
"""
    cover_desc_html = (
        '<div class="cover-desc-wrap"><div class="cover-desc-ttl">Descripción</div>'
        '<div class="cover-desc">{}</div></div>'.format(desc)
    ) if desc else '<div style="flex:1"></div>'

    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'/>"
        "<style>{}</style></head><body>"
        "<div class='ficha-page'>"
        "{}"
        "<div class='cover-info'>"
        "<div class='cover-badge'>{}</div>"
        "<div class='cover-precio'>{}</div>"
        "<div class='cover-titulo'>{}</div>"
        "<div class='cover-ubicacion'>{} {}</div>"
        "</div>"
        "{}"
        "{}"
        "{}"
        "</div>"
        "{}"
        "</body></html>"
    ).format(CSS, hero_html, tipo_op, precio, titulo, SVG_PIN, ubicacion,
             specs_html, cover_desc_html, footer(), gallery_pages)


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
async def generar_descripcion_ficha_manual(data: dict):
    """Generate AI description for ficha manual — uses same httpx pattern as rest of backend."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

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
    parts = ["Ficha_Brokr"]
    if colonia:  parts.append(_slug(colonia))
    if tipo_raw: parts.append(_slug(tipo_raw))
    if id_prop:  parts.append(_slug(id_prop))
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

FB_APP_ID     = os.environ.get("FB_APP_ID", "")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET", "")
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "https://brokr.app")

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
    files: List[UploadFile] = File(...),
    prompt: str = _Form(""),
    # legacy field kept for backward compat
    remove_furniture: str = _Form("false"),
):
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
    return {"images": list(results)}


# ─── FACEBOOK OAUTH ───────────────────────────────────────────────────────────

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
    return {
        "ok": True,
        "page_id": page_id,
        "page_name": page_name,
        "page_token": page_token,
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
