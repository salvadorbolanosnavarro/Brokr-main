# ──────────────────────────────────────────────────────────────────────────
# routers/crm.py · Ajustes de CRM y operaciones de contactos
# ──────────────────────────────────────────────────────────────────────────
# Catálogos por organización (etapas del pipeline, tipos de contacto, fuentes
# de captación), etiquetas de contactos e inmuebles, fusión de contactos
# duplicados y acciones en lote sobre contactos.
#
# Igual que routers/organizaciones.py: el frontend sólo LEE estos catálogos
# (RLS de lectura por organización); toda escritura pasa por aquí con la
# service key y validando quién pide. Los catálogos y las etiquetas sólo los
# cambia el dueño o un administrador; fusionar y el lote los puede usar
# cualquier miembro activo, sobre contactos de su propia organización.
#
# Depende de: migracion-fase3-contactos.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.database import call_service_rpc, delete_rows, get_rows, patch_rows, post_rows
from routers.organizaciones import get_org_context

router = APIRouter(prefix="/crm", tags=["crm"])
log = logging.getLogger("broquer.crm")

ETAPAS_DEFAULT = [
    ("futuro", "Futuro", "var(--etapa-futuro)"),
    ("nuevo", "Nuevo", "var(--etapa-nuevo)"),
    ("activo", "Activo", "var(--etapa-activo)"),
    ("contactado", "Contactado", "var(--etapa-contactado)"),
    ("cerrado", "Cerrado", "var(--etapa-cerrado)"),
    ("descartado", "Descartado", "var(--etapa-descartado)"),
    ("spam", "Basura/Spam", "var(--mute-2)"),
]
TIPOS_DEFAULT = [
    ("arrendador", "Propietario / Arrendador"), ("arrendatario", "Inquilino / Arrendatario"),
    ("comprador", "Comprador"), ("vendedor", "Vendedor"), ("obligado_solidario", "Obligado solidario"),
    ("colega", "Colega / Agente"), ("notario", "Notario"), ("valuador", "Valuador"),
    ("juridico", "Jurídico"), ("agente_externo", "Agente externo"), ("otro", "Otro"),
]
_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|var\(--[a-z0-9-]+\))$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def normaliza(texto: Any) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clave_de(nombre: str) -> str:
    return normaliza(nombre).replace(" ", "_")[:40] or "etapa"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(v: Any) -> str:
    s = str(v or "").strip()
    if not _ID_RE.match(s):
        raise HTTPException(status_code=400, detail="Identificador inválido.")
    return s


async def _ctx(request: Request, *, admin: bool) -> Dict[str, Any]:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx or not ctx.get("activo") or not ctx.get("org_id"):
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    if admin and ctx.get("rol_org") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Sólo el administrador de la cuenta puede cambiar los ajustes del CRM.")
    ctx["user_id"] = user_id
    return ctx


async def _body(request: Request) -> Dict[str, Any]:
    try:
        b = await request.json()
    except Exception:
        b = None
    if not isinstance(b, dict):
        raise HTTPException(status_code=400, detail="Solicitud inválida.")
    return b


# ══════════════════════════════════════════════════════════════════════════
# CATÁLOGOS
# ══════════════════════════════════════════════════════════════════════════
async def _etapas(org_id: str) -> List[dict]:
    filas = await get_rows("pipeline_etapas", {
        "org_id": f"eq.{org_id}", "select": "id,clave,nombre,orden,color,es_sistema",
        "order": "orden.asc,created_at.asc",
    }, timeout=10)
    vistas, out = set(), []
    for f in filas:
        k = f.get("clave") or (f.get("nombre") or "").lower().strip()
        if not k or k in vistas:
            continue
        vistas.add(k)
        f["clave"] = k
        out.append(f)
    if not out:
        # Organización nueva (creada después de la migración): se siembran.
        filas = [{"org_id": org_id, "clave": k, "nombre": n, "color": c, "orden": (i + 1) * 10, "es_sistema": True}
                 for i, (k, n, c) in enumerate(ETAPAS_DEFAULT)]
        out = await post_rows("pipeline_etapas", filas, timeout=10)
    return out


async def _tipos(org_id: str) -> List[dict]:
    filas = await get_rows("contacto_tipos", {
        "org_id": f"eq.{org_id}", "select": "id,clave,nombre,orden,es_sistema", "order": "orden.asc,nombre.asc",
    }, timeout=10)
    if not filas:
        filas = await post_rows("contacto_tipos", [
            {"org_id": org_id, "clave": k, "nombre": n, "orden": (i + 1) * 10, "es_sistema": True}
            for i, (k, n) in enumerate(TIPOS_DEFAULT)], timeout=10)
    return filas


async def _fuentes(org_id: str) -> List[dict]:
    return await get_rows("fuentes_captacion", {
        "org_id": f"eq.{org_id}", "select": "id,nombre,nombre_norm", "order": "nombre.asc",
    }, timeout=10)


@router.get("/catalogos")
async def catalogos(request: Request):
    ctx = await _ctx(request, admin=False)
    org = ctx["org_id"]
    try:
        return {
            "etapas": await _etapas(org),
            "tipos": await _tipos(org),
            "fuentes": await _fuentes(org),
            "es_admin": ctx.get("rol_org") in ("owner", "admin"),
        }
    except httpx.HTTPStatusError as e:
        log.warning("catalogos CRM no disponibles: %s", e.response.text[:200])
        raise HTTPException(status_code=503, detail="Falta correr migracion-fase3-contactos.sql en Supabase.")


# ── Etapas ───────────────────────────────────────────────────────────────
class EtapaReq(BaseModel):
    nombre: str
    color: Optional[str] = None


@router.post("/etapas")
async def crear_etapa(req: EtapaReq, request: Request):
    ctx = await _ctx(request, admin=True)
    nombre = (req.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la etapa.")
    actuales = await _etapas(ctx["org_id"])
    clave = clave_de(nombre)
    base, i = clave, 2
    while any(e["clave"] == clave for e in actuales):
        clave, i = f"{base}_{i}", i + 1
    color = req.color if req.color and _COLOR_RE.match(req.color) else "var(--etapa-activo)"
    filas = await post_rows("pipeline_etapas", {
        "org_id": ctx["org_id"], "clave": clave, "nombre": nombre, "color": color,
        "orden": max([e.get("orden") or 0 for e in actuales] + [0]) + 10, "user_id": ctx["user_id"],
    })
    return filas[0] if filas else {}


@router.patch("/etapas/{etapa_id}")
async def editar_etapa(etapa_id: str, req: EtapaReq, request: Request):
    ctx = await _ctx(request, admin=True)
    cambios: Dict[str, Any] = {}
    if req.nombre and req.nombre.strip():
        cambios["nombre"] = req.nombre.strip()[:60]
    if req.color:
        if not _COLOR_RE.match(req.color):
            raise HTTPException(status_code=400, detail="Color inválido.")
        cambios["color"] = req.color
    if not cambios:
        raise HTTPException(status_code=400, detail="No hay cambios.")
    filas = await patch_rows("pipeline_etapas", {"id": f"eq.{_id(etapa_id)}", "org_id": f"eq.{ctx['org_id']}"},
                             cambios, prefer="return=representation")
    if not filas:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")
    return filas[0]


class OrdenReq(BaseModel):
    ids: List[str]


@router.post("/etapas/orden")
async def ordenar_etapas(req: OrdenReq, request: Request):
    ctx = await _ctx(request, admin=True)
    for i, eid in enumerate(req.ids[:100]):
        await patch_rows("pipeline_etapas", {"id": f"eq.{_id(eid)}", "org_id": f"eq.{ctx['org_id']}"},
                         {"orden": (i + 1) * 10})
    return {"ok": True}


@router.delete("/etapas/{etapa_id}")
async def eliminar_etapa(etapa_id: str, request: Request, mover_a: str = ""):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    etapas = await _etapas(org)
    etapa = next((e for e in etapas if str(e["id"]) == etapa_id), None)
    if not etapa:
        raise HTTPException(status_code=404, detail="Etapa no encontrada.")
    destino = next((e for e in etapas if e["clave"] == mover_a and e["clave"] != etapa["clave"]), None)
    if not destino:
        raise HTTPException(status_code=400, detail="Elige a qué etapa mover a sus contactos.")
    movidos = await patch_rows("contactos", {"org_id": f"eq.{org}", "estatus": f"eq.{etapa['clave']}"},
                               {"estatus": destino["clave"], "updated_at": _ahora()}, prefer="return=representation")
    await delete_rows("pipeline_etapas", {"id": f"eq.{_id(etapa_id)}", "org_id": f"eq.{org}"})
    return {"movidos": len(movidos or [])}


# ── Tipos de contacto ────────────────────────────────────────────────────
class NombreReq(BaseModel):
    nombre: str


@router.post("/tipos")
async def crear_tipo(req: NombreReq, request: Request):
    ctx = await _ctx(request, admin=True)
    nombre = (req.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Escribe el nombre del tipo.")
    actuales = await _tipos(ctx["org_id"])
    clave = clave_de(nombre)
    if any(t["clave"] == clave for t in actuales):
        raise HTTPException(status_code=409, detail="Ya existe un tipo con ese nombre.")
    filas = await post_rows("contacto_tipos", {
        "org_id": ctx["org_id"], "clave": clave, "nombre": nombre,
        "orden": max([t.get("orden") or 0 for t in actuales] + [0]) + 10,
    })
    return filas[0] if filas else {}


@router.patch("/tipos/{tipo_id}")
async def renombrar_tipo(tipo_id: str, req: NombreReq, request: Request):
    ctx = await _ctx(request, admin=True)
    nombre = (req.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Escribe el nombre del tipo.")
    filas = await patch_rows("contacto_tipos", {"id": f"eq.{_id(tipo_id)}", "org_id": f"eq.{ctx['org_id']}"},
                             {"nombre": nombre}, prefer="return=representation")
    if not filas:
        raise HTTPException(status_code=404, detail="Tipo no encontrado.")
    return filas[0]


@router.delete("/tipos/{tipo_id}")
async def eliminar_tipo(tipo_id: str, request: Request, mover_a: str = "otro"):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    tipos = await _tipos(org)
    tipo = next((t for t in tipos if str(t["id"]) == tipo_id), None)
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo no encontrado.")
    destino = next((t for t in tipos if t["clave"] == mover_a and t["clave"] != tipo["clave"]), None)
    if not destino:
        raise HTTPException(status_code=400, detail="Elige a qué tipo pasar a sus contactos.")
    movidos = await patch_rows("contactos", {"org_id": f"eq.{org}", "tipo": f"eq.{tipo['clave']}"},
                               {"tipo": destino["clave"]}, prefer="return=representation")
    await delete_rows("contacto_tipos", {"id": f"eq.{_id(tipo_id)}", "org_id": f"eq.{org}"})
    return {"movidos": len(movidos or [])}


# ── Fuentes de captación ─────────────────────────────────────────────────
async def fuente_para(org_id: str, nombre: str) -> Optional[dict]:
    """Busca (o crea) la fuente del catálogo para un texto libre, sin duplicar
    por mayúsculas, acentos o espacios. La usan el Buzón y los importadores."""
    nombre = (nombre or "").strip()[:80]
    norm = normaliza(nombre)
    if not norm:
        return None
    filas = await get_rows("fuentes_captacion", {"org_id": f"eq.{org_id}", "nombre_norm": f"eq.{norm}",
                                                 "select": "id,nombre", "limit": "1"})
    if filas:
        return filas[0]
    try:
        nuevas = await post_rows("fuentes_captacion", {"org_id": org_id, "nombre": nombre, "nombre_norm": norm})
        return nuevas[0] if nuevas else None
    except httpx.HTTPStatusError:
        filas = await get_rows("fuentes_captacion", {"org_id": f"eq.{org_id}", "nombre_norm": f"eq.{norm}",
                                                     "select": "id,nombre", "limit": "1"})
        return filas[0] if filas else None


@router.post("/fuentes")
async def crear_fuente(req: NombreReq, request: Request):
    ctx = await _ctx(request, admin=False)
    f = await fuente_para(ctx["org_id"], req.nombre)
    if not f:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la fuente.")
    return f


@router.patch("/fuentes/{fuente_id}")
async def renombrar_fuente(fuente_id: str, req: NombreReq, request: Request):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    nombre = (req.nombre or "").strip()[:80]
    norm = normaliza(nombre)
    if not norm:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la fuente.")
    choque = await get_rows("fuentes_captacion", {"org_id": f"eq.{org}", "nombre_norm": f"eq.{norm}",
                                                  "id": f"neq.{_id(fuente_id)}", "select": "id", "limit": "1"})
    if choque:
        raise HTTPException(status_code=409, detail="Ya existe una fuente con ese nombre: mejor fusiónalas.")
    filas = await patch_rows("fuentes_captacion", {"id": f"eq.{_id(fuente_id)}", "org_id": f"eq.{org}"},
                             {"nombre": nombre, "nombre_norm": norm}, prefer="return=representation")
    if not filas:
        raise HTTPException(status_code=404, detail="Fuente no encontrada.")
    await patch_rows("contactos", {"org_id": f"eq.{org}", "fuente_id": f"eq.{fuente_id}"}, {"fuente": nombre})
    return filas[0]


class FusionarFuentesReq(BaseModel):
    origen_ids: List[str]
    destino_id: str


# Tablas que guardan una fuente (contactos hoy; el Buzón de la Fase 4).
_TABLAS_CON_FUENTE = ("contactos", "buzon_leads")


@router.post("/fuentes/fusionar")
async def fusionar_fuentes(req: FusionarFuentesReq, request: Request):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    destino_id = _id(req.destino_id)
    origen = [_id(i) for i in req.origen_ids if str(i) != destino_id][:50]
    if not origen:
        raise HTTPException(status_code=400, detail="Elige al menos una fuente para fusionar.")
    dest = await get_rows("fuentes_captacion", {"id": f"eq.{destino_id}", "org_id": f"eq.{org}", "select": "id,nombre"})
    if not dest:
        raise HTTPException(status_code=404, detail="La fuente destino no existe.")
    ids = ",".join(origen)
    reasignados = 0
    for tabla in _TABLAS_CON_FUENTE:
        try:
            res = await patch_rows(tabla, {"org_id": f"eq.{org}", "fuente_id": f"in.({ids})"},
                                   {"fuente_id": destino_id, "fuente": dest[0]["nombre"]}, prefer="return=representation")
            reasignados += len(res or [])
        except httpx.HTTPStatusError as e:
            # buzon_leads aún no existe si la Fase 4 no se ha migrado.
            log.info("fusionar fuentes: %s no disponible (%s)", tabla, e.response.status_code)
    await delete_rows("fuentes_captacion", {"id": f"in.({ids})", "org_id": f"eq.{org}"})
    return {"reasignados": reasignados, "fusionadas": len(origen)}


@router.delete("/fuentes/{fuente_id}")
async def eliminar_fuente(fuente_id: str, request: Request):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    usados = await get_rows("contactos", {"org_id": f"eq.{org}", "fuente_id": f"eq.{_id(fuente_id)}",
                                          "select": "id", "limit": "1"})
    if usados:
        raise HTTPException(status_code=409, detail="Hay contactos con esta fuente: fusiónala con otra en vez de borrarla.")
    await delete_rows("fuentes_captacion", {"id": f"eq.{_id(fuente_id)}", "org_id": f"eq.{org}"})
    return {"ok": True}


# ── Etiquetas (contactos e inmuebles) ────────────────────────────────────
_TABLAS_ETIQUETAS = {"contactos", "propiedades"}


@router.get("/etiquetas")
async def etiquetas(request: Request, tabla: str = "contactos"):
    ctx = await _ctx(request, admin=False)
    if tabla not in _TABLAS_ETIQUETAS:
        raise HTTPException(status_code=400, detail="Tabla inválida.")
    filas = await call_service_rpc("bk_etiquetas_conteo", {"p_tabla": tabla, "p_org": ctx["org_id"]})
    return {"etiquetas": filas or []}


class EtiquetaReq(BaseModel):
    tabla: str
    de: str
    a: Optional[str] = None


@router.post("/etiquetas/renombrar")
async def renombrar_etiqueta(req: EtiquetaReq, request: Request):
    """Renombrar. Si el nuevo nombre ya existe, es una fusión."""
    ctx = await _ctx(request, admin=True)
    if req.tabla not in _TABLAS_ETIQUETAS or not (req.de or "").strip() or not (req.a or "").strip():
        raise HTTPException(status_code=400, detail="Datos incompletos.")
    n = await call_service_rpc("bk_etiqueta_renombrar", {"p_tabla": req.tabla, "p_org": ctx["org_id"],
                                                          "p_de": req.de, "p_a": req.a.strip()[:60]})
    return {"actualizados": n}


@router.post("/etiquetas/eliminar")
async def eliminar_etiqueta(req: EtiquetaReq, request: Request):
    ctx = await _ctx(request, admin=True)
    if req.tabla not in _TABLAS_ETIQUETAS or not (req.de or "").strip():
        raise HTTPException(status_code=400, detail="Datos incompletos.")
    n = await call_service_rpc("bk_etiqueta_eliminar", {"p_tabla": req.tabla, "p_org": ctx["org_id"],
                                                         "p_etiqueta": req.de})
    return {"actualizados": n}


# ── Categorías de tareas/notas (organizacion_categorias) ─────────────────
@router.patch("/categorias/{cat_id}")
async def renombrar_categoria(cat_id: str, req: NombreReq, request: Request):
    ctx = await _ctx(request, admin=True)
    nombre = (req.nombre or "").strip()[:60]
    if not nombre:
        raise HTTPException(status_code=400, detail="Escribe el nombre.")
    filas = await patch_rows("organizacion_categorias", {"id": f"eq.{_id(cat_id)}", "org_id": f"eq.{ctx['org_id']}"},
                             {"nombre": nombre}, prefer="return=representation")
    if not filas:
        raise HTTPException(status_code=404, detail="Categoría no encontrada.")
    return filas[0]


@router.delete("/categorias/{cat_id}")
async def eliminar_categoria(cat_id: str, request: Request):
    ctx = await _ctx(request, admin=True)
    await delete_rows("organizacion_categorias", {"id": f"eq.{_id(cat_id)}", "org_id": f"eq.{ctx['org_id']}"})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# CONTACTOS: fusión de duplicados y acciones en lote
# ══════════════════════════════════════════════════════════════════════════
def tel10(v: Any) -> str:
    """Teléfono MX normalizado a 10 dígitos (quita +52, 52, 1, 044, 045)."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) > 10:
        d = d[-10:]
    return d if len(d) == 10 else ""


async def _contactos_de_org(ids: List[str], org_id: str, user_id: str) -> List[dict]:
    filas = await get_rows("contactos", {"id": f"in.({','.join(ids)})", "select": "*"}, timeout=15)
    miembros = await get_rows("organizacion_miembros", {"org_id": f"eq.{org_id}", "select": "user_id"})
    del_equipo = {m["user_id"] for m in miembros}
    return [f for f in filas
            if f.get("org_id") == org_id or f.get("user_id") == user_id
            or (not f.get("org_id") and f.get("user_id") in del_equipo)]


# Tablas con contacto_id que se re-apuntan al fusionar. Si una tabla no
# existe en esta base, se salta.
_TABLAS_LIGADAS = ("actividades", "tareas_contactos", "contactos_propiedades", "requerimientos_busqueda",
                   "busqueda_resultados", "wa2_conversaciones", "wa2_contactos", "wa2_agenda",
                   "fin_movimientos", "firma_documentos", "firma_firmantes", "buzon_leads")


def _unir_lista(a: Any, b: Any, clave: str) -> list:
    out, vistos = [], set()
    for x in list(a or []) + list(b or []):
        if not isinstance(x, dict):
            continue
        k = tel10(x.get(clave)) if clave == "numero" else str(x.get(clave) or "").strip().lower()
        if k and k not in vistos:
            vistos.add(k)
            out.append(x)
    return out


def combinar_contactos(conservar: dict, eliminar: dict) -> dict:
    """Campos del contacto que queda: los suyos y, donde estén vacíos, los del
    otro. Teléfonos, correos, etiquetas y notas se suman sin duplicar."""
    cambios: Dict[str, Any] = {}
    for k, v in eliminar.items():
        if k in ("id", "user_id", "org_id", "created_at", "updated_at"):
            continue
        if conservar.get(k) in (None, "", [], {}) and v not in (None, "", [], {}):
            cambios[k] = v
    telefonos = list(conservar.get("telefonos") or [])
    for t in (eliminar.get("telefono"), eliminar.get("wa")):
        if tel10(t) and tel10(t) not in {tel10(conservar.get("telefono")), tel10(conservar.get("wa"))}:
            telefonos.append({"numero": t, "tipo": "celular"})
    cambios["telefonos"] = _unir_lista(telefonos, eliminar.get("telefonos"), "numero")
    correos = list(conservar.get("correos") or [])
    if eliminar.get("email") and str(eliminar["email"]).lower() != str(conservar.get("email") or "").lower():
        correos.append({"correo": eliminar["email"], "tipo": "personal"})
    cambios["correos"] = _unir_lista(correos, eliminar.get("correos"), "correo")
    cambios["etiquetas"] = sorted({*(conservar.get("etiquetas") or []), *(eliminar.get("etiquetas") or [])})
    notas = [n for n in (conservar.get("notas"), eliminar.get("notas")) if n]
    if len(notas) == 2 and notas[0] != notas[1]:
        cambios["notas"] = notas[0] + "\n\n— Fusionado de " + (eliminar.get("nombre") or "contacto") + " —\n" + notas[1]
    if eliminar.get("es_potencial") and not conservar.get("es_potencial"):
        cambios["es_potencial"] = True
    cambios["updated_at"] = _ahora()
    return cambios


class FusionarReq(BaseModel):
    conservar_id: str
    eliminar_id: str


@router.post("/contactos/fusionar")
async def fusionar_contactos(req: FusionarReq, request: Request):
    ctx = await _ctx(request, admin=False)
    a, b = _id(req.conservar_id), _id(req.eliminar_id)
    if a == b:
        raise HTTPException(status_code=400, detail="Elige dos contactos distintos.")
    filas = {f["id"]: f for f in await _contactos_de_org([a, b], ctx["org_id"], ctx["user_id"])}
    if a not in filas or b not in filas:
        raise HTTPException(status_code=404, detail="Alguno de los contactos no existe o no es de tu cuenta.")
    conservar, eliminar = filas[a], filas[b]

    movidos: Dict[str, int] = {}
    for tabla in _TABLAS_LIGADAS:
        try:
            res = await patch_rows(tabla, {"contacto_id": f"eq.{b}"}, {"contacto_id": a}, prefer="return=representation")
            movidos[tabla] = len(res or [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                # Vínculo repetido (p. ej. el mismo inmueble ligado a los dos):
                # se mueve uno por uno y el repetido se descarta.
                n = 0
                for fila in await get_rows(tabla, {"contacto_id": f"eq.{b}", "select": "*"}):
                    if fila.get("id") is None:
                        continue
                    filtro = {"id": f"eq.{fila['id']}"}
                    try:
                        await patch_rows(tabla, filtro, {"contacto_id": a})
                        n += 1
                    except httpx.HTTPStatusError:
                        await delete_rows(tabla, filtro)
                movidos[tabla] = n
            # 400/404: la tabla o la columna no existen en esta base; se salta.

    await patch_rows("contactos", {"id": f"eq.{a}"}, combinar_contactos(conservar, eliminar))
    await delete_rows("contactos", {"id": f"eq.{b}"})
    try:
        await post_rows("actividades", {
            "user_id": ctx["user_id"], "contacto_id": a, "tipo": "nota",
            "texto": f"Se fusionó con el contacto duplicado «{eliminar.get('nombre') or b}».",
        })
    except httpx.HTTPStatusError:
        pass
    return {"ok": True, "conservado": a, "movidos": movidos}


class LoteContactosReq(BaseModel):
    ids: List[str]
    asignado_a: Optional[str] = None
    quitar_asignado: bool = False
    estatus: Optional[str] = None
    etiquetas_agregar: List[str] = []
    etiquetas_quitar: List[str] = []


@router.post("/contactos/lote")
async def contactos_lote(req: LoteContactosReq, request: Request):
    ctx = await _ctx(request, admin=False)
    ids = list(dict.fromkeys(i for i in (str(x).strip() for x in req.ids) if _ID_RE.match(i)))[:1000]
    if not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste contactos.")
    org = ctx["org_id"]
    cambios: Dict[str, Any] = {}
    if req.estatus:
        etapas = {e["clave"] for e in await _etapas(org)}
        if req.estatus not in etapas:
            raise HTTPException(status_code=400, detail="Etapa inválida.")
        cambios["estatus"] = req.estatus
        cambios["es_potencial"] = True
    if req.asignado_a or req.quitar_asignado:
        if ctx.get("rol_org") not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Sólo el administrador puede asignar.")
        if req.asignado_a:
            miembro = await get_rows("organizacion_miembros", {"org_id": f"eq.{org}", "user_id": f"eq.{_id(req.asignado_a)}",
                                                               "activo": "eq.true", "select": "user_id"})
            if not miembro:
                raise HTTPException(status_code=400, detail="Ese agente no es de tu equipo.")
        cambios["asignado_a"] = req.asignado_a or None
    agregar = [t.strip()[:60] for t in req.etiquetas_agregar if t.strip()]
    quitar = {t.strip() for t in req.etiquetas_quitar if t.strip()}
    if not cambios and not agregar and not quitar:
        raise HTTPException(status_code=400, detail="No hay cambios que aplicar.")

    permitidas = []
    for i in range(0, len(ids), 150):
        permitidas += await _contactos_de_org(ids[i:i + 150], org, ctx["user_id"])
    actualizados = 0
    if cambios and permitidas:
        cambios["updated_at"] = _ahora()
        for i in range(0, len(permitidas), 150):
            grupo = ",".join(f["id"] for f in permitidas[i:i + 150])
            res = await patch_rows("contactos", {"id": f"in.({grupo})"}, cambios, prefer="return=representation")
            actualizados += len(res or [])
    if agregar or quitar:
        n = 0
        for f in permitidas:
            et = [t for t in (f.get("etiquetas") or []) if t not in quitar]
            et += [t for t in agregar if t not in et]
            if et != (f.get("etiquetas") or []):
                await patch_rows("contactos", {"id": f"eq.{f['id']}"}, {"etiquetas": et, "updated_at": _ahora()})
            n += 1
        actualizados = max(actualizados, n)
    return {"actualizados": actualizados, "sin_permiso": len(ids) - len(permitidas)}
