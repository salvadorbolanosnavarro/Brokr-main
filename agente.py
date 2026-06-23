# ──────────────────────────────────────────────────────────────────────────
# routers/agente.py · Broquer — Motor Agéntico de Shaark
# ──────────────────────────────────────────────────────────────────────────
# El cerebro nuevo del asistente. A diferencia del viejo /chat-claude (un solo
# turno + parseo de [ACCION] por regex), este endpoint usa TOOL-USE NATIVO de
# Claude dentro de un LOOP AGÉNTICO de varios pasos:
#
#   1. El agente puede BUSCAR datos reales del usuario (propiedades, contactos,
#      cartera) ejecutándose en el backend y razonar sobre los resultados.
#   2. Puede ENCADENAR acciones: buscar una propiedad → leer sus datos →
#      generar su ficha/contrato/estimación, viendo el resultado de cada paso.
#   3. Las acciones que ocurren en el navegador (descargar PDF, navegar,
#      pre-llenar formularios) se devuelven como `client_actions` con el MISMO
#      formato que el front ya sabe ejecutar (handleAccion), así reutilizamos
#      el 100% de la maquinaria probada del frontend.
#
# Además expone /transcribir: voz de nivel profesional con Whisper (Groq).
#
# Es autónomo: lee sus propias variables de entorno. Para activarlo basta con
# incluir su router en main.py (2 líneas). No toca nada del código existente.
# ──────────────────────────────────────────────────────────────────────────

import os
import json
import re
import time
import asyncio
import httpx
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter()

# ── Config (mismas env vars que main.py) ──────────────────────────────────
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE       = "https://api.anthropic.com/v1"
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE            = "https://api.groq.com/openai/v1"
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY         = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY

AGENT_MODEL    = "claude-sonnet-4-6"   # Sonnet 4.6 por default (preferencia del usuario)
MAX_TURNS      = 6                     # tope de iteraciones del loop agéntico
MAX_TOKENS     = 1500


# ── Auth: valida el JWT de Supabase y devuelve el user_id ─────────────────
async def _get_user_id(request: Request) -> Optional[str]:
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
                return r.json().get("id")
    except Exception:
        pass
    return None


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _money(n) -> str:
    try:
        return "$" + f"{int(round(float(n))):,}".replace(",", ",")
    except Exception:
        return str(n)


# ══════════════════════════════════════════════════════════════════════════
#  HERRAMIENTAS SERVER-SIDE — se ejecutan en el backend y devuelven datos
#  reales para que el agente razone sobre ellos.
# ══════════════════════════════════════════════════════════════════════════

async def _tool_buscar_propiedades(user_id: str, args: dict) -> str:
    """Busca en la tabla `propiedades` del usuario por texto/operación/tipo."""
    if not user_id:
        return "No pude confirmar la sesión del usuario, así que no logro leer su cartera. Pídele que cierre sesión y vuelva a entrar; no asumas que no tiene propiedades."
    query     = (args.get("query") or "").strip()
    operacion = (args.get("operacion") or "").strip().lower()
    tipo      = (args.get("tipo") or "").strip().lower()
    limit     = min(int(args.get("limit") or 8), 20)

    sel = ("id,titulo,tipo,operacion,precio,moneda,colonia,ciudad,calle,"
           "num_exterior,recamaras,banos,m2_construccion,m2_terreno,estacionamientos,estatus")

    async def _consulta(extra: dict) -> list:
        params = {"user_id": f"eq.{user_id}", "select": sel,
                  "order": "updated_at.desc", "limit": str(limit)}
        params.update(extra)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",
                                 headers=_sb_headers(), params=params)
        return r.json() if r.status_code == 200 else None

    extra = {}
    if operacion in ("venta", "renta"):
        extra["operacion"] = f"eq.{operacion}"
    if tipo:
        extra["tipo"] = f"ilike.*{tipo}*"
    if query:
        safe = query.replace(",", " ").replace("(", " ").replace(")", " ")
        extra["or"] = (f"(titulo.ilike.*{safe}*,colonia.ilike.*{safe}*,"
                       f"calle.ilike.*{safe}*,ciudad.ilike.*{safe}*,descripcion.ilike.*{safe}*)")

    try:
        rows = await _consulta(extra)
    except Exception as e:
        return f"No pude consultar las propiedades ahora mismo: {str(e)[:120]}"
    if rows is None:
        return "Hubo un error al leer la cartera. No asumas que el usuario no tiene propiedades; pídele reintentar."

    # Sin coincidencias con los filtros: revisa si SÍ tiene inventario (sin filtros)
    # para no decirle por error que no tiene nada.
    if not rows and extra:
        try:
            todas = await _consulta({})
        except Exception:
            todas = None
        if todas:
            muestras = ", ".join(filter(None, [t.get("titulo") or t.get("colonia") for t in todas[:6]]))
            return (f"No hay coincidencias con ese criterio exacto, pero el usuario SÍ tiene "
                    f"{len(todas)} propiedad(es) en su cartera (p. ej.: {muestras}). "
                    "Pídele que precise cuál, o muéstrale la lista. NUNCA le digas que no tiene inmuebles.")
        return ("El usuario aún no tiene propiedades cargadas en Mis Inmuebles. "
                "Ofrécele crearlas en ese módulo o pídele los datos para generar la ficha manual. "
                "No menciones integraciones externas.")

    if not rows:
        return ("El usuario aún no tiene propiedades cargadas en Mis Inmuebles. "
                "Ofrécele crearlas en ese módulo o pídele los datos para generar la ficha manual. "
                "No menciones integraciones externas.")

    out = []
    for p in rows:
        partes = []
        partes.append(p.get("titulo") or "Propiedad sin título")
        if p.get("operacion"): partes.append(f"({p['operacion']})")
        ubic = " · ".join(filter(None, [p.get("colonia"), p.get("ciudad")]))
        if ubic: partes.append(ubic)
        if p.get("precio"): partes.append(_money(p["precio"]) + " " + (p.get("moneda") or "MXN"))
        det = []
        if p.get("recamaras"): det.append(f"{p['recamaras']} rec")
        if p.get("banos"): det.append(f"{p['banos']} baños")
        if p.get("m2_construccion"): det.append(f"{p['m2_construccion']} m² const")
        if p.get("m2_terreno"): det.append(f"{p['m2_terreno']} m² terreno")
        linea = " — ".join(partes)
        if det: linea += " · " + ", ".join(det)
        linea += f" · id:{p.get('id')}"
        out.append("• " + linea)
    return f"Encontré {len(rows)} propiedad(es) en la cartera del usuario:\n" + "\n".join(out)


async def _tool_detalle_propiedad(user_id: str, args: dict) -> str:
    """Devuelve TODOS los datos de una propiedad concreta (por id o búsqueda)."""
    if not user_id:
        return "No hay sesión activa."
    pid   = (args.get("id") or "").strip()
    query = (args.get("query") or "").strip()
    params = {
        "user_id": f"eq.{user_id}",
        "select": "*",
        "limit": "1",
    }
    if pid:
        params["id"] = f"eq.{pid}"
    elif query:
        safe = query.replace(",", " ")
        params["or"] = f"(titulo.ilike.*{safe}*,colonia.ilike.*{safe}*,calle.ilike.*{safe}*)"
        params["order"] = "updated_at.desc"
    else:
        return "Necesito un id de propiedad o un texto de búsqueda para dar el detalle."
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",
                                 headers=_sb_headers(), params=params)
        rows = r.json() if r.status_code == 200 else []
    except Exception as e:
        return f"No pude obtener el detalle: {str(e)[:120]}"
    if not rows:
        return "No encontré esa propiedad en la cartera del usuario."
    p = rows[0]
    campos = {
        "Título": p.get("titulo"), "Tipo": p.get("tipo"), "Operación": p.get("operacion"),
        "Precio": _money(p["precio"]) + " " + (p.get("moneda") or "MXN") if p.get("precio") else None,
        "Calle": p.get("calle"), "Núm.": p.get("num_exterior"), "Colonia": p.get("colonia"),
        "Ciudad": p.get("ciudad"), "Estado": p.get("estado"), "CP": p.get("cp"),
        "Recámaras": p.get("recamaras"), "Baños": p.get("banos"),
        "Estacionamientos": p.get("estacionamientos"),
        "m² construcción": p.get("m2_construccion"), "m² terreno": p.get("m2_terreno"),
        "Estatus": p.get("estatus"),
        "id": p.get("id"),
    }
    lineas = [f"{k}: {v}" for k, v in campos.items() if v not in (None, "", 0)]
    desc = (p.get("descripcion") or "").strip()
    if desc:
        lineas.append("Descripción: " + desc[:600])
    return "Detalle de la propiedad:\n" + "\n".join(lineas)


async def _tool_buscar_contactos(user_id: str, args: dict) -> str:
    """Busca en la agenda/CRM del usuario (tabla `contactos`)."""
    if not user_id:
        return "No hay sesión activa."
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 8), 20)
    params = {
        "user_id": f"eq.{user_id}",
        "select": "id,nombre,telefono,email,empresa,tipo,notas",
        "order": "updated_at.desc",
        "limit": str(limit),
    }
    if query:
        safe = query.replace(",", " ")
        params["or"] = f"(nombre.ilike.*{safe}*,telefono.ilike.*{safe}*,email.ilike.*{safe}*,empresa.ilike.*{safe}*,notas.ilike.*{safe}*)"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{SUPABASE_URL}/rest/v1/contactos",
                                 headers=_sb_headers(), params=params)
        rows = r.json() if r.status_code == 200 else []
    except Exception as e:
        return f"No pude consultar los contactos: {str(e)[:120]}"
    if not rows:
        return "No encontré contactos que coincidan en el CRM del usuario."
    out = []
    for c in rows:
        partes = [c.get("nombre") or "Sin nombre"]
        if c.get("tipo"): partes.append(f"[{c['tipo']}]")
        if c.get("telefono"): partes.append(c["telefono"])
        if c.get("email"): partes.append(c["email"])
        linea = " · ".join(partes)
        if c.get("notas"): linea += " — " + (c["notas"] or "")[:120]
        out.append("• " + linea)
    return f"Encontré {len(rows)} contacto(s):\n" + "\n".join(out)


async def _tool_resumen_cartera(user_id: str, args: dict) -> str:
    """Resumen del inventario del usuario: totales por operación/tipo y valor."""
    if not user_id:
        return "No hay sesión activa."
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=_sb_headers(),
                params={"user_id": f"eq.{user_id}",
                        "select": "operacion,tipo,precio,moneda",
                        "limit": "5000"}
            )
        rows = r.json() if r.status_code == 200 else []
    except Exception as e:
        return f"No pude generar el resumen: {str(e)[:120]}"
    if not rows:
        return "El usuario aún no tiene propiedades en su cartera de Broquer."
    total = len(rows)
    por_op = {}
    por_tipo = {}
    valor_venta = 0.0
    n_venta = 0
    for p in rows:
        op = (p.get("operacion") or "sin operación").lower()
        tp = (p.get("tipo") or "sin tipo").lower()
        por_op[op] = por_op.get(op, 0) + 1
        por_tipo[tp] = por_tipo.get(tp, 0) + 1
        if op == "venta" and p.get("precio"):
            try:
                valor_venta += float(p["precio"]); n_venta += 1
            except Exception:
                pass
    lineas = [f"Total de propiedades: {total}"]
    lineas.append("Por operación: " + ", ".join(f"{k} {v}" for k, v in por_op.items()))
    lineas.append("Por tipo: " + ", ".join(f"{k} {v}" for k, v in por_tipo.items()))
    if n_venta:
        lineas.append(f"Valor total de inventario en venta: {_money(valor_venta)} MXN ({n_venta} props)")
    return "Resumen de la cartera:\n" + "\n".join(lineas)


# ══════════════════════════════════════════════════════════════════════════
#  FICHA TÉCNICA — GENERACIÓN AUTÓNOMA (PDF real, sin pasar por el módulo)
#  El agente lee la propiedad, arma el formato que entiende el renderizador y
#  llama al mismo motor que el módulo (/ficha-pdf, Playwright). Devuelve el PDF
#  listo: el navegador solo lo abre/descarga. NO navega al módulo.
# ══════════════════════════════════════════════════════════════════════════

def _fotos_to_images(fotos) -> list:
    """La columna `fotos` es una lista de URLs (str). El renderizador espera
    [{url}]. Soporta también que ya vengan como objetos."""
    out = []
    for f in (fotos or []):
        if isinstance(f, str) and f.strip():
            out.append({"url": f.strip()})
        elif isinstance(f, dict):
            u = f.get("url") or f.get("original")
            if u:
                out.append({"url": u})
    return out


def _propiedad_to_eb(p: dict) -> dict:
    """Mapea una fila de la tabla `propiedades` al formato que consume
    build_ficha_html / /ficha-pdf (el renderizador del PDF)."""
    op_raw = (p.get("operacion") or "").strip().lower()
    op_type = "sale" if op_raw == "venta" else "rental" if op_raw == "renta" else "sale"
    operations = []
    if p.get("precio"):
        operations.append({
            "type": op_type,
            "amount": p.get("precio"),
            "currency": p.get("moneda") or "MXN",
        })
    calle = " ".join(filter(None, [str(p.get("calle") or "").strip(),
                                   str(p.get("num_exterior") or "").strip()])).strip()
    return {
        "public_id": p.get("id") or "",
        "id": p.get("id") or "",
        "title": p.get("titulo") or p.get("tipo") or "Propiedad",
        "property_type": p.get("tipo") or "Propiedad",
        "operations": operations,
        "location": {"name": p.get("colonia") or "", "city": p.get("ciudad") or ""},
        "address": calle,
        "bedrooms": p.get("recamaras"),
        "bathrooms": p.get("banos"),
        "parking_spaces": p.get("estacionamientos"),
        "construction_size": p.get("m2_construccion"),
        "lot_size": p.get("m2_terreno"),
        "description": p.get("descripcion") or "",
        "property_images": _fotos_to_images(p.get("fotos")),
    }


def _datos_manual_to_eb(a: dict) -> dict:
    """Mapea datos sueltos (que arma el modelo) al formato del renderizador."""
    op_raw = (a.get("operacion") or "").strip().lower()
    op_type = "sale" if op_raw in ("venta", "sale") else "rental" if op_raw in ("renta", "rental") else "sale"
    operations = []
    if a.get("precio"):
        operations.append({"type": op_type, "amount": a.get("precio"),
                           "currency": a.get("moneda") or "MXN"})
    return {
        "public_id": "", "id": "",
        "title": a.get("titulo") or a.get("tipo_inmueble") or "Propiedad",
        "property_type": a.get("tipo_inmueble") or "Propiedad",
        "operations": operations,
        "location": {"name": a.get("colonia") or "", "city": a.get("ciudad") or "Morelia"},
        "address": a.get("calle") or "",
        "bedrooms": a.get("recamaras"),
        "bathrooms": a.get("banos"),
        "parking_spaces": a.get("estacionamientos"),
        "construction_size": a.get("m2_construccion"),
        "lot_size": a.get("m2_terreno"),
        "description": a.get("descripcion") or "",
        "property_images": _fotos_to_images(a.get("fotos")),
    }


async def _render_ficha_pdf(eb: dict):
    """Llama al MISMO motor de PDF que usa el módulo (Playwright vía main).
    Devuelve (token, filename) o (None, None) si no se pudo generar."""
    try:
        import json as _json
        from main import generar_ficha_pdf  # lazy: evita import circular
        resp = await generar_ficha_pdf(eb)
        body = getattr(resp, "body", None)
        if body is None:
            return None, None
        data = _json.loads(body.decode() if isinstance(body, (bytes, bytearray)) else body)
        return data.get("token"), data.get("filename")
    except Exception:
        return None, None


async def _leer_propiedad(user_id: str, args: dict) -> Optional[dict]:
    """Trae la fila completa de una propiedad por id o texto."""
    pid    = (args.get("id") or "").strip()
    query  = (args.get("query") or "").strip()
    params = {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"}
    if pid:
        params["id"] = f"eq.{pid}"
    elif query:
        safe = query.replace(",", " ")
        params["or"] = (f"(titulo.ilike.*{safe}*,colonia.ilike.*{safe}*,"
                        f"calle.ilike.*{safe}*)")
        params["order"] = "updated_at.desc"
    else:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",
                                 headers=_sb_headers(), params=params)
        rows = r.json() if r.status_code == 200 else []
    except Exception:
        return None
    return rows[0] if rows else None


async def _tool_generar_ficha(user_id: str, args: dict) -> dict:
    """Genera la ficha técnica (PDF) de una propiedad de la cartera y la entrega
    lista para abrir. Acepta id o query."""
    if not user_id:
        return {"text": "No pude confirmar la sesión; pídele al usuario reingresar. No asumas que no tiene propiedades."}
    p = await _leer_propiedad(user_id, args)
    if not p:
        return {"text": ("No ubiqué esa propiedad por ese dato. Usa buscar_propiedades para "
                         "listar la cartera del usuario y confirma con él CUÁL quiere antes de "
                         "generar la ficha. Nunca le digas que no tiene inmuebles ni menciones "
                         "integraciones externas.")}

    eb = _propiedad_to_eb(p)
    nombre = eb.get("title") or "la propiedad"
    token, filename = await _render_ficha_pdf(eb)
    if not token:
        # Fallback honesto: no pudimos renderizar; abre el módulo con los datos.
        return {
            "text": (f"Tengo los datos de «{nombre}» pero no pude terminar el PDF aquí mismo; "
                     "abrí el módulo de ficha con todo precargado para generarla. "
                     "Dile al usuario que la ficha se está preparando."),
            "client_action": {"tipo": "crear_ficha_manual", **_eb_to_prefill(eb)},
        }
    return {
        "text": (f"Ficha técnica de «{nombre}» generada con los datos reales de la cartera. "
                 "El PDF se está abriendo en el dispositivo del usuario. "
                 "Da un cierre breve confirmándolo."),
        "client_action": {"tipo": "abrir_pdf", "url": f"/ficha-pdf/{token}",
                          "filename": filename or "ficha.pdf"},
    }


async def _tool_crear_ficha_manual(user_id: str, args: dict) -> dict:
    """Genera la ficha (PDF) a partir de datos sueltos que arma el agente."""
    eb = _datos_manual_to_eb(args)
    nombre = eb.get("title") or "la propiedad"
    token, filename = await _render_ficha_pdf(eb)
    if not token:
        return {
            "text": (f"No pude terminar el PDF de «{nombre}» aquí; abrí el módulo de ficha "
                     "con los datos precargados. Dile al usuario que se está preparando."),
            "client_action": {"tipo": "crear_ficha_manual", **_eb_to_prefill(eb)},
        }
    return {
        "text": (f"Ficha técnica de «{nombre}» generada. El PDF se está abriendo en el "
                 "dispositivo del usuario. Da un cierre breve confirmándolo."),
        "client_action": {"tipo": "abrir_pdf", "url": f"/ficha-pdf/{token}",
                          "filename": filename or "ficha.pdf"},
    }


def _eb_to_prefill(eb: dict) -> dict:
    """Aplana el formato EB a los campos que el módulo de ficha manual entiende
    para precargar el formulario (fallback cuando no se pudo renderizar)."""
    op = (eb.get("operations") or [{}])[0]
    loc = eb.get("location") or {}
    return {
        "tipo_inmueble": eb.get("property_type") or "",
        "operacion": "venta" if op.get("type") == "sale" else "renta" if op.get("type") == "rental" else "",
        "precio": op.get("amount") or 0,
        "colonia": loc.get("name") or "",
        "ciudad": loc.get("city") or "",
        "calle": eb.get("address") or "",
        "recamaras": eb.get("bedrooms") or 0,
        "banos": eb.get("bathrooms") or 0,
        "m2_construccion": eb.get("construction_size") or 0,
        "m2_terreno": eb.get("lot_size") or 0,
        "estacionamientos": eb.get("parking_spaces") or 0,
        "descripcion": eb.get("description") or "",
    }


# ══════════════════════════════════════════════════════════════════════════
#  DEFINICIÓN DE HERRAMIENTAS (esquema para Claude)
# ══════════════════════════════════════════════════════════════════════════
# Server-side: el backend las ejecuta y devuelve datos reales.
# Client-side: el backend NO las ejecuta; las encola en `client_actions` con el
#   formato {tipo, ...} que el frontend (handleAccion) ya sabe procesar. Se
#   confirma al agente que la acción quedó enviada al dispositivo del usuario.

SERVER_TOOLS = {
    "buscar_propiedades":     _tool_buscar_propiedades,
    "detalle_propiedad":      _tool_detalle_propiedad,
    "buscar_contactos":       _tool_buscar_contactos,
    "resumen_cartera":        _tool_resumen_cartera,
    # Fichas técnicas: se generan de verdad en el servidor (PDF listo).
    "generar_ficha_tecnica":  _tool_generar_ficha,
    "crear_ficha_manual":     _tool_crear_ficha_manual,
}

TOOLS_SCHEMA = [
    # ── Anthropic web search nativo (Claude lo ejecuta solo) ──
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 4},

    # ── SERVER-SIDE ──
    {
        "name": "buscar_propiedades",
        "description": "Busca en la cartera REAL de propiedades del usuario en Broquer. Úsala cuando el usuario mencione 'mi propiedad', 'la casa de…', 'mis inmuebles en…', o cuando necesites datos de una propiedad para otra acción. Devuelve una lista con datos clave e ids.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto a buscar: colonia, calle, título o referencia. Ej: 'Chapultepec', 'Camelinas 123'."},
                "operacion": {"type": "string", "enum": ["venta", "renta"], "description": "Filtra por venta o renta (opcional)."},
                "tipo": {"type": "string", "description": "Filtra por tipo: casa, departamento, terreno, local, oficina, bodega (opcional)."},
                "limit": {"type": "integer", "description": "Máximo de resultados (default 8)."}
            }
        }
    },
    {
        "name": "detalle_propiedad",
        "description": "Devuelve TODOS los datos de una propiedad específica del usuario (por id devuelto por buscar_propiedades, o por texto). Úsala antes de generar una ficha o un contrato cuando necesites los datos completos del inmueble.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "id exacto de la propiedad (preferido si lo tienes)."},
                "query": {"type": "string", "description": "Texto de búsqueda si no tienes el id."}
            }
        }
    },
    {
        "name": "buscar_contactos",
        "description": "Busca en el CRM/agenda del usuario por nombre, teléfono, email o notas. Úsala para 'busca el contacto de…', 'el teléfono de…', 'qué prospectos tengo en…'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre, teléfono, email o palabra clave."},
                "limit": {"type": "integer"}
            }
        }
    },
    {
        "name": "resumen_cartera",
        "description": "Resumen del inventario del usuario: cuántas propiedades tiene, desglose por operación y tipo, y valor total en venta. Úsala para '¿cómo va mi inventario?', '¿cuántas propiedades tengo?'.",
        "input_schema": {"type": "object", "properties": {}}
    },

    # ── CLIENT-SIDE (se ejecutan en el dispositivo del usuario) ──
    {
        "name": "calcular_isr",
        "description": "Calcula el ISR por enajenación de inmueble y descarga el PDF en el dispositivo del usuario. Úsala SOLO cuando tengas TODOS los datos obligatorios. La pregunta de exención solo aplica a casa/departamento (para terreno/comercial usa 'no').",
        "input_schema": {
            "type": "object",
            "properties": {
                "precio_venta": {"type": "number"}, "precio_compra": {"type": "number"},
                "anio_venta": {"type": "integer"}, "mes_venta": {"type": "integer", "description": "1-12"},
                "anio_compra": {"type": "integer"}, "mes_compra": {"type": "integer", "description": "1-12"},
                "inmueble": {"type": "string", "enum": ["casa", "terreno", "comercial"]},
                "exencion": {"type": "string", "enum": ["no", "si", "nose"]},
                "mejoras": {"type": "number"}, "escrituracion": {"type": "number"}, "comision": {"type": "number"}
            },
            "required": ["precio_venta", "precio_compra", "anio_venta", "mes_venta", "anio_compra", "mes_compra", "inmueble"]
        }
    },
    {
        "name": "estimar_valor",
        "description": "Estima el valor de un inmueble buscando comparables reales en internet y descarga el PDF. Tarda 30s–2min. Úsala cuando tengas colonia, tipo, operación y superficie.",
        "input_schema": {
            "type": "object",
            "properties": {
                "colonia": {"type": "string"},
                "tipo_inmueble": {"type": "string", "enum": ["casa", "departamento", "terreno", "local", "oficina", "bodega"]},
                "operacion": {"type": "string", "enum": ["venta", "renta"]},
                "m2_construccion": {"type": "number"}, "m2_terreno": {"type": "number"},
                "recamaras": {"type": "integer"}, "banos": {"type": "number"},
                "estacionamientos": {"type": "integer"},
                "condicion_terreno": {"type": "string", "enum": ["plano", "pendiente", "irregular", ""]},
                "ciudad": {"type": "string", "description": "Default Morelia"}
            },
            "required": ["colonia", "tipo_inmueble", "operacion"]
        }
    },
    {
        "name": "generar_contrato",
        "description": "Genera y descarga un contrato (DOCX) en el dispositivo del usuario. subtipo 'arrendamiento' o 'promesa'. Úsala SOLO cuando tengas todos los datos obligatorios. Pon los nombres de las personas EN MAYÚSCULAS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subtipo": {"type": "string", "enum": ["arrendamiento", "promesa"]},
                "datos": {"type": "object", "description": "Objeto con todos los campos del contrato (direcciones, partes, montos, fechas en YYYY-MM-DD)."}
            },
            "required": ["subtipo", "datos"]
        }
    },
    {
        "name": "crear_contacto",
        "description": "Agrega un contacto/prospecto al CRM del usuario sin salir del chat. Solo 'nombre' es obligatorio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"}, "telefono": {"type": "string"},
                "email": {"type": "string"}, "empresa": {"type": "string"},
                "tipo_contacto": {"type": "string", "enum": ["prospecto", "vendedor", "comprador", "arrendatario"]},
                "notas": {"type": "string"}
            },
            "required": ["nombre"]
        }
    },
    {
        "name": "generar_ficha_tecnica",
        "description": "Genera el PDF de la ficha técnica de una propiedad que YA está en la cartera del usuario y lo entrega listo (se abre solo, sin que el usuario toque ningún módulo). Es la forma preferida para fichas de inmuebles propios. Pásale el id de la propiedad (el que devuelve buscar_propiedades) o un texto de búsqueda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "id de la propiedad (preferido)."},
                "query": {"type": "string", "description": "Texto si no tienes el id: colonia, calle o título."}
            }
        }
    },
    {
        "name": "crear_ficha_manual",
        "description": "Genera el PDF de la ficha técnica desde datos sueltos (para inmuebles que NO están en la cartera). Lo entrega listo, se abre solo. Mínimo: tipo_inmueble, operacion, precio, colonia.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo_inmueble": {"type": "string"}, "operacion": {"type": "string"},
                "precio": {"type": "number"}, "colonia": {"type": "string"}, "ciudad": {"type": "string"},
                "calle": {"type": "string"}, "recamaras": {"type": "integer"}, "banos": {"type": "number"},
                "m2_construccion": {"type": "number"}, "m2_terreno": {"type": "number"},
                "estacionamientos": {"type": "integer"}, "descripcion": {"type": "string"}
            },
            "required": ["tipo_inmueble", "operacion", "precio", "colonia"]
        }
    },
    {
        "name": "crear_campana_facebook",
        "description": "Prepara una campaña de Meta/Facebook Ads para una propiedad y la deja lista para confirmar. NUNCA la ejecutes sin que el usuario confirme presupuesto y objetivo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "objetivo": {"type": "string", "enum": ["OUTCOME_LEADS", "OUTCOME_TRAFFIC", "OUTCOME_AWARENESS"]},
                "presupuesto_diario_mxn": {"type": "number"},
                "ciudad": {"type": "string"}, "edad_min": {"type": "integer"}, "edad_max": {"type": "integer"},
                "url_destino": {"type": "string"}, "texto_anuncio": {"type": "string"}
            },
            "required": ["nombre", "objetivo", "presupuesto_diario_mxn"]
        }
    },
    {
        "name": "abrir_modulo",
        "description": "Lleva al usuario a un módulo de la plataforma. Úsala solo si el usuario pide explícitamente abrir/ir a un módulo, o si una acción requiere que edite datos a mano.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modulo": {"type": "string", "enum": ["isr", "avm", "contratos", "props", "ficha", "ficha-manual", "facebook-ads", "contactos", "image-cleaner", "whatsapp", "verificador"]}
            },
            "required": ["modulo"]
        }
    },
    {
        "name": "prellenar_formulario",
        "description": "Abre un módulo con el formulario YA pre-llenado para que el usuario revise/edite antes de ejecutar. Útil cuando faltan datos opcionales o el usuario quiere afinar a mano. modulo: 'isr', 'avm' o 'contrato'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modulo": {"type": "string", "enum": ["isr", "avm", "contrato"]},
                "datos": {"type": "object", "description": "Campos a pre-cargar."}
            },
            "required": ["modulo", "datos"]
        }
    },
]


# ── Traducción de tool client-side → client_action que entiende el frontend ──
def _to_client_action(name: str, args: dict) -> Optional[dict]:
    if name == "calcular_isr":
        a = {"tipo": "calcular_isr_directo"}; a.update(args); return a
    if name == "estimar_valor":
        a = {"tipo": "estimar_valor_directo"}; a.update(args); return a
    if name == "generar_contrato":
        return {"tipo": "generar_contrato_directo", "subtipo": args.get("subtipo", "arrendamiento"),
                "datos": args.get("datos", {})}
    if name == "crear_contacto":
        a = {"tipo": "agregar_contacto"}; a.update(args); return a
    if name == "crear_campana_facebook":
        a = {"tipo": "confirmar_campana"}; a.update(args); return a
    if name == "abrir_modulo":
        return {"tipo": "navegar", "modulo": args.get("modulo", "")}
    if name == "prellenar_formulario":
        modulo = args.get("modulo", ""); datos = args.get("datos", {})
        tipo = {"isr": "llenar_isr", "avm": "llenar_avm", "contrato": "llenar_contrato"}.get(modulo)
        if not tipo:
            return None
        a = {"tipo": tipo}; a.update(datos); return a
    return None


# Mensaje de "step" que el front muestra como burbuja de estado en vivo.
_STEP_LABELS = {
    "web_search":             "Buscando en internet…",
    "buscar_propiedades":     "Revisando tu cartera de propiedades…",
    "detalle_propiedad":      "Abriendo los datos de la propiedad…",
    "buscar_contactos":       "Buscando en tu CRM…",
    "resumen_cartera":        "Analizando tu inventario…",
    "calcular_isr":           "Calculando el ISR y preparando el PDF…",
    "estimar_valor":          "Buscando comparables y estimando el valor…",
    "generar_contrato":       "Generando el contrato…",
    "crear_contacto":         "Agregando el contacto a tu CRM…",
    "generar_ficha_tecnica":  "Armando la ficha técnica…",
    "crear_ficha_manual":     "Armando la ficha técnica…",
    "crear_campana_facebook": "Preparando tu campaña de anuncios…",
    "abrir_modulo":           "Abriendo el módulo…",
    "prellenar_formulario":   "Dejando el formulario listo para ti…",
}


# ── System prompt del agente ──────────────────────────────────────────────
def _build_system(context: str, nombre: str = "") -> str:
    base = """Eres Broquer, el copiloto operativo con inteligencia artificial para agentes inmobiliarios de México (especializado en Morelia y Michoacán). Eres un ASISTENTE QUE EJECUTA, no un chatbot que sugiere.

CÓMO ACTÚAS:
- Tienes herramientas reales. Cuando el usuario pide algo que puedes hacer, HAZLO con la herramienta correspondiente. No le digas "ve al módulo X y dale al botón Y": tú lo ejecutas.
- Puedes encadenar pasos: primero busca datos (buscar_propiedades, detalle_propiedad, buscar_contactos) y luego actúa (generar_contrato, generar_ficha_tecnica, estimar_valor). Usa los datos reales que obtengas; nunca inventes precios, m², direcciones ni nombres.
- Para fichas técnicas de inmuebles que ya están en la cartera: usa generar_ficha_tecnica con el id de buscar_propiedades. El PDF se genera completo en el servidor y se abre solo en el dispositivo del usuario; NO lo mandas a ningún módulo a terminarlo. Solo usa crear_ficha_manual cuando el inmueble NO esté en la cartera y tengas los datos sueltos.
- Antes de una acción que produce un documento o un cambio, reúne los datos OBLIGATORIOS preguntando de UNO EN UNO de forma conversacional. Nunca ejecutes con datos incompletos. Los opcionales que el usuario no sepa: déjalos en 0 o "".
- Las acciones que generan un archivo (ISR, estimación de valor, contrato, ficha) o que crean algo se ejecutan en el dispositivo del usuario. Cuando lances una de esas, NO digas "ya está descargado": di que la estás preparando y que aparecerá en un momento. El sistema le confirma al usuario cuando termina.
- Para campañas de Facebook Ads NUNCA ejecutes sin confirmación explícita de presupuesto y objetivo.

CONOCIMIENTO EXPERTO (úsalo al responder asesorías):
- Derecho inmobiliario mexicano: compraventa, arrendamiento, promesa de venta, escritura pública vs contrato privado, Registro Público de la Propiedad, LFPDPPP, LFPIORPI (PLD: umbrales en UMA, aviso al SAT), propiedad en condominio en Michoacán.
- Fiscal e ISR: LISR arts. 119 y 120, exención de 700,000 UDIS para casa habitación, deducciones (compra actualizada por INPC, mejoras, escrituración, comisiones), ISAI, régimen de arrendamiento (deducción ciega 35%).
- Valuación: comparables, costo, capitalización de rentas, cap rate, precio por m². Zonas de Morelia: Chapultepec, Altozano, Félix Ireta, Lomas del Estadio, Santa María, Lomas de Tzompantle, Vistas del Campestre, Villas del Pedregal, Las Américas, Torremolinos.
- Marketing inmobiliario: Facebook/Instagram Ads, fichas que venden, captación de exclusivas, manejo de la objeción de precio.
- Tecnología: portales inmobiliarios, firma electrónica (Mifiel, Docusign), y el flujo de captación digital.

REGLAS DE CARTERA:
- Las propiedades del usuario viven en su módulo «Mis Inmuebles» dentro de Broquer. Para trabajar con una, usa buscar_propiedades (para ubicarla y obtener su id) y luego generar_ficha_tecnica con ese id.
- Si una búsqueda no arroja coincidencias, NUNCA concluyas que el usuario no tiene inmuebles: vuelve a buscar sin filtros o pídele que precise. Solo di que no tiene propiedades si la herramienta lo confirma explícitamente.
- Si de verdad no tiene inmuebles cargados, ofrécele crearlos en Mis Inmuebles o pídele los datos para hacer la ficha manual. NUNCA menciones EasyBroker, importaciones externas ni integraciones de terceros: no son parte de tu discurso.

ESTILO:
- Español mexicano, natural, cercano y profesional. Directo, sin relleno ni redundancia.
- Si el usuario habla por voz (va manejando o en una cita), responde con oraciones cortas y claras.
- Nunca inventes cifras, leyes, artículos ni datos. Si no estás seguro, dilo y usa web_search para verificar.
- Nada de markdown en las respuestas conversacionales: sin asteriscos, sin numerales, sin listas con guiones. Frases naturales."""
    if nombre:
        base += f"\n\nEl usuario se llama {nombre}. Háblale por su nombre de pila cuando sea natural."
    if context:
        base += f"\n\nCONTEXTO ACTUAL: el usuario está en el módulo/pantalla «{context}». Adapta tus acciones a ese contexto cuando sea relevante."
    return base


class AgentRequest(BaseModel):
    messages: list
    context: str = ""
    nombre: str = ""
    max_tokens: int = MAX_TOKENS


@router.post("/agent")
async def agent(req: AgentRequest, request: Request):
    """Loop agéntico con tool-use nativo. Devuelve {reply, client_actions, steps}."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada en el servidor.")
    user_id = await _get_user_id(request)

    system = _build_system(req.context, req.nombre)
    # Solo mensajes de usuario/asistente (sin system embebido)
    messages = [m for m in req.messages if m.get("role") in ("user", "assistant")]

    client_actions: list = []
    steps: list = []
    reply_text = ""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90) as client:
        for _turn in range(MAX_TURNS):
            payload = {
                "model": AGENT_MODEL,
                "max_tokens": req.max_tokens,
                "system": system,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
            }
            try:
                r = await client.post(f"{ANTHROPIC_BASE}/messages", headers=headers, json=payload)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"No pude contactar al modelo: {str(e)[:120]}")
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"Error del modelo: {r.text[:300]}")

            data = r.json()
            content = data.get("content", []) or []
            stop = data.get("stop_reason")

            # Texto de ESTE turno. Nos quedamos con el del último turno con texto
            # (el cierre); los preámbulos intermedios ya se ven como "steps" en vivo.
            turn_text = "".join(
                b["text"] for b in content
                if b.get("type") == "text" and b.get("text")
            ).strip()
            if turn_text:
                reply_text = turn_text

            # Registra steps de búsqueda web que Claude ya resolvió solo
            for b in content:
                if b.get("type") == "server_tool_use" and b.get("name") == "web_search":
                    steps.append(_STEP_LABELS["web_search"])

            # Si no hay más herramientas que ejecutar, terminamos
            if stop != "tool_use":
                break

            # Preserva el turno del asistente completo (incluye bloques de web_search)
            messages.append({"role": "assistant", "content": content})

            # Procesa cada tool_use de NUESTRAS herramientas
            tool_results = []
            for b in content:
                if b.get("type") != "tool_use":
                    continue
                name = b.get("name")
                args = b.get("input") or {}
                tuid = b.get("id")

                if name in _STEP_LABELS:
                    steps.append(_STEP_LABELS[name])

                if name in SERVER_TOOLS:
                    # Ejecuta de verdad y devuelve datos reales. Una server tool
                    # puede devolver str (solo texto para el modelo) o un dict
                    # {"text":..., "client_action":...} cuando además produce algo
                    # que el navegador debe abrir/descargar (p. ej. un PDF de ficha).
                    try:
                        result = await SERVER_TOOLS[name](user_id, args)
                    except Exception as e:
                        result = f"Hubo un problema al ejecutar la herramienta: {str(e)[:120]}"
                    if isinstance(result, dict):
                        result_text = result.get("text") or "Listo."
                        ca = result.get("client_action")
                        if ca:
                            client_actions.append(ca)
                    else:
                        result_text = result
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tuid, "content": result_text
                    })
                else:
                    # Client-side: encola la acción para el navegador
                    ca = _to_client_action(name, args)
                    if ca:
                        client_actions.append(ca)
                        ack = ("Acción enviada al dispositivo del usuario; se está ejecutando ahí "
                               "y el resultado aparecerá en su pantalla en unos momentos. "
                               "Da un mensaje final breve confirmando que lo estás preparando.")
                    else:
                        ack = "No reconocí esa acción; explícale al usuario qué necesitas para continuar."
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tuid, "content": ack
                    })

            messages.append({"role": "user", "content": tool_results})

            # Si solo hubo acciones de cliente y ya no hace falta razonar más,
            # damos una vuelta más para que el modelo cierre con su mensaje hablado.
            # (El loop continúa naturalmente.)

    reply_text = reply_text.strip() or "Listo."

    return {
        "reply": reply_text,
        "client_actions": client_actions,
        "steps": steps,
        # compat con el front viejo por si acaso
        "choices": [{"message": {"role": "assistant", "content": reply_text}}],
    }


# ══════════════════════════════════════════════════════════════════════════
#  /transcribir — Voz de nivel profesional con Whisper (Groq)
# ══════════════════════════════════════════════════════════════════════════
# Recibe el audio grabado por el navegador (MediaRecorder) y lo transcribe con
# whisper-large-v3-turbo. Muy superior a webkitSpeechRecognition: entiende
# español mexicano, aguanta ruido de coche y funciona en iPhone.

_VOICE_FIXES = [
    ("broker", "Broquer"), ("brouker", "Broquer"), ("bróker", "Broquer"),
    ("shaark", "Broquer"), ("shark", "Broquer"), ("sharc", "Broquer"),
]


@router.post("/transcribir")
async def transcribir(request: Request, audio: UploadFile = File(...), idioma: str = Form("es")):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY no configurada en el servidor.")
    raw = await audio.read()
    if len(raw) < 600:
        return {"texto": ""}  # audio demasiado corto / silencio
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio demasiado largo.")

    filename = audio.filename or "audio.webm"
    ctype = audio.content_type or "audio/webm"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{GROQ_BASE}/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (filename, raw, ctype)},
                data={
                    "model": "whisper-large-v3-turbo",
                    "language": idioma or "es",
                    "temperature": "0",
                    "prompt": "Transcripción de un agente inmobiliario en México hablando de propiedades, colonias de Morelia, contratos, ISR y la app Broquer.",
                },
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No pude transcribir: {str(e)[:120]}")

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Error de transcripción: {r.text[:200]}")

    texto = (r.json().get("text") or "").strip()
    # Correcciones de marca comunes (reemplazo de palabra suelta, insensible a mayúsculas)
    for bad, good in _VOICE_FIXES:
        texto = re.sub(rf"\b{re.escape(bad)}\b", good, texto, flags=re.IGNORECASE)
    return {"texto": texto}


@router.get("/agent/health")
async def agent_health():
    return {
        "ok": True,
        "modelo": AGENT_MODEL,
        "anthropic": bool(ANTHROPIC_API_KEY),
        "groq_voz": bool(GROQ_API_KEY),
        "supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),
        "tools_servidor": list(SERVER_TOOLS.keys()),
    }
