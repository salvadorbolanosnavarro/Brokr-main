# ──────────────────────────────────────────────────────────────────────────
# routers/alertas.py · Alertas de búsqueda y coincidencias
# ──────────────────────────────────────────────────────────────────────────
# El requerimiento ampliado de cada cliente (varias operaciones, tipos y
# zonas, presupuesto con moneda, mínimos, superficies, características,
# financiamiento y "sólo con comisión compartida") se cruza PRIMERO con el
# inventario propio y del equipo (según permisos) y con la Bolsa Broquer. La
# búsqueda en internet del Buscador queda como sección secundaria.
#
# Un ciclo diario detecta inmuebles nuevos o cambiados que coinciden y que no
# se le han mandado al cliente, y le avisa al agente por push. El envío al
# cliente (WhatsApp o correo, con liga a la ficha pública) queda registrado en
# alertas_enviadas y en la bitácora del contacto.
#
# Depende de: migracion-fase5-alertas.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.catalogo_inmuebles import tipo_label
from core.coincidencias import SELECT_PROPIEDADES, coincide, operaciones_de, puntaje
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, upsert_rows
from routers.organizaciones import get_org_context, permiso_efectivo

router = APIRouter(prefix="/alertas", tags=["alertas"])
log = logging.getLogger("broquer.alertas")
API_PUBLICA = "https://api.broquer.app"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ctx(request: Request) -> Dict[str, Any]:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(uid)
    if not ctx or not ctx.get("activo") or not ctx.get("org_id"):
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    ctx["user_id"] = uid
    ctx["es_admin"] = ctx.get("rol_org") in ("owner", "admin")
    return ctx


async def _contacto(ctx: dict, contacto_id: str) -> dict:
    from routers.crm import _contactos_de_org
    filas = await _contactos_de_org([contacto_id], ctx["org_id"], ctx["user_id"])
    if not filas:
        raise HTTPException(status_code=404, detail="Contacto no encontrado.")
    return filas[0]


async def _inventario(ctx: dict) -> List[dict]:
    """Inventario visible: de toda la organización si tiene 'ver inventario
    completo'; si no, el propio y lo que tiene asignado."""
    base = {"select": SELECT_PROPIEDADES, "estatus": "eq.activa", "limit": "3000"}
    if permiso_efectivo(ctx, "ver_inventario_completo") or ctx["es_admin"]:
        base["org_id"] = f"eq.{ctx['org_id']}"
    else:
        base["or"] = f"(user_id.eq.{ctx['user_id']},asignado_a.eq.{ctx['user_id']})"
    try:
        return await get_rows("propiedades", base, timeout=20)
    except httpx.HTTPStatusError:       # columnas nuevas aún sin migrar
        base["select"] = "*"
        return await get_rows("propiedades", base, timeout=20)


async def _bolsa(org_id: str) -> List[dict]:
    try:
        filas = await get_rows("propiedades", {"select": SELECT_PROPIEDADES, "en_bolsa": "eq.true",
                                               "estatus": "eq.activa", "limit": "3000"}, timeout=20)
    except httpx.HTTPStatusError:
        return []
    return [f for f in filas if f.get("org_id") != org_id]


def _resumen(p: dict, origen: str) -> dict:
    ops = operaciones_de(p)
    return {
        "id": p["id"], "titulo": p.get("titulo"), "origen": origen,
        "tipo": tipo_label(p.get("subtipo") or p.get("tipo")),
        "colonia": p.get("colonia"), "ciudad": p.get("ciudad"),
        "operaciones": ops, "recamaras": p.get("recamaras"), "banos": p.get("banos"),
        "m2_construccion": p.get("m2_construccion"), "foto": (p.get("fotos") or [None])[0],
        "bolsa_comision": p.get("bolsa_comision") if origen == "bolsa" else None,
        "updated_at": p.get("updated_at"),
    }


async def coincidencias_para(ctx: dict, req: dict) -> List[dict]:
    inv, bolsa = await asyncio.gather(_inventario(ctx), _bolsa(ctx["org_id"]))
    out = []
    for p in inv:
        if coincide(req, p)[0]:
            out.append((puntaje(req, p), _resumen(p, "propio" if p.get("user_id") == ctx["user_id"] else "equipo")))
    for p in bolsa:
        if coincide(req, p)[0]:
            out.append((puntaje(req, p) - 1, _resumen(p, "bolsa")))
    out.sort(key=lambda x: (x[0], x[1].get("updated_at") or ""), reverse=True)
    return [x[1] for x in out]


# ══════════════════════════════════════════════════════════════════════════
# REQUERIMIENTO
# ══════════════════════════════════════════════════════════════════════════
class RequerimientoIn(BaseModel):
    activo: bool = True
    operaciones: List[str] = []
    tipos: List[str] = []
    zonas: List[str] = []
    estado: str = ""
    moneda: str = "MXN"
    precio_min: float = 0
    precio_max: float = 0
    recamaras_min: int = 0
    banos_min: float = 0
    estacionamientos_min: int = 0
    m2_construccion_min: float = 0
    m2_construccion_max: float = 0
    m2_terreno_min: float = 0
    m2_terreno_max: float = 0
    caracteristicas: List[str] = []
    solo_comision_compartida: bool = False
    notas: str = ""


async def _requerimiento(contacto_id: str) -> Optional[dict]:
    filas = await get_rows("requerimientos_busqueda", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    return filas[0] if filas else None


@router.get("/requerimiento/{contacto_id}")
async def ver_requerimiento(contacto_id: str, request: Request):
    ctx = await _ctx(request)
    await _contacto(ctx, contacto_id)
    return await _requerimiento(contacto_id) or {}


@router.put("/requerimiento/{contacto_id}")
async def guardar_requerimiento(contacto_id: str, body: RequerimientoIn, request: Request):
    ctx = await _ctx(request)
    await _contacto(ctx, contacto_id)
    previo = await _requerimiento(contacto_id)
    zonas = [z.strip()[:80] for z in body.zonas if z.strip()][:20]
    ops = [o for o in body.operaciones if o][:5] or ["venta"]
    tipos = [t for t in body.tipos if t][:10]
    fila = {
        "user_id": (previo or {}).get("user_id") or ctx["user_id"], "org_id": ctx["org_id"],
        "contacto_id": contacto_id, "activo": body.activo,
        # Campos de siempre (los usa la búsqueda en internet del Buscador).
        "operacion": "renta" if ops[0] in ("renta", "renta_temporal") else "venta",
        "tipo_inmueble": tipos[0] if tipos else "casa",
        "colonia": zonas[0] if zonas else None, "ciudad": zonas[1] if len(zonas) > 1 else None,
        "estado": body.estado.strip() or None,
        "precio_min": body.precio_min or None, "precio_max": body.precio_max or None,
        "recamaras_min": body.recamaras_min or None, "notas": body.notas.strip()[:1000] or None,
        # Requerimiento ampliado.
        "operaciones": ops, "tipos": tipos, "zonas": zonas, "moneda": (body.moneda or "MXN").upper()[:3],
        "banos_min": body.banos_min or None, "estacionamientos_min": body.estacionamientos_min or None,
        "m2_construccion_min": body.m2_construccion_min or None, "m2_construccion_max": body.m2_construccion_max or None,
        "m2_terreno_min": body.m2_terreno_min or None, "m2_terreno_max": body.m2_terreno_max or None,
        "caracteristicas": [c for c in body.caracteristicas if c][:60],
        "solo_comision_compartida": body.solo_comision_compartida,
        "actualizado_en": _ahora(),
    }
    try:
        guardadas = await upsert_rows("requerimientos_busqueda", [fila], conflict="contacto_id")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="No se pudo guardar el requerimiento: " + exc.response.text[:160])
    return guardadas[0] if guardadas else fila


@router.get("/coincidencias/{contacto_id}")
async def ver_coincidencias(contacto_id: str, request: Request):
    ctx = await _ctx(request)
    await _contacto(ctx, contacto_id)
    req = await _requerimiento(contacto_id)
    if not req:
        return {"coincidencias": [], "requerimiento": None}
    lista = await coincidencias_para(ctx, req)
    enviadas = {}
    try:
        for a in await get_rows("alertas_enviadas", {"requerimiento_id": f"eq.{req['id']}", "select": "propiedad_id,estado,enviada_en,canal"}):
            enviadas[a["propiedad_id"]] = a
    except httpx.HTTPStatusError:
        pass
    for p in lista:
        a = enviadas.get(p["id"]) or {}
        p["enviada_en"] = a.get("enviada_en") if a.get("estado") == "enviada" else None
        p["canal_envio"] = a.get("canal")
    return {"coincidencias": lista, "requerimiento": req}


# ══════════════════════════════════════════════════════════════════════════
# ENVÍO AL CLIENTE
# ══════════════════════════════════════════════════════════════════════════
def liga_publica(propiedad_id: str, agente_id: str) -> str:
    return f"{API_PUBLICA}/p/{propiedad_id}?a={agente_id}"


def _precio(p: dict) -> str:
    ops = p.get("operaciones") or []
    if not ops:
        return ""
    o = ops[0]
    try:
        return f"${float(o.get('precio')):,.0f} {o.get('moneda') or 'MXN'}"
    except (TypeError, ValueError):
        return ""


class PrepararReq(BaseModel):
    contacto_id: str
    propiedad_ids: List[str]


@router.post("/preparar")
async def preparar_envio(req: PrepararReq, request: Request):
    """Arma el mensaje con las ligas a la ficha pública. La pantalla lo manda
    por WhatsApp (conversación abierta o tu WhatsApp) o por correo."""
    ctx = await _ctx(request)
    contacto = await _contacto(ctx, req.contacto_id)
    ids = [i for i in req.propiedad_ids if len(i) == 36][:10]
    if not ids:
        raise HTTPException(status_code=400, detail="Elige al menos un inmueble.")
    props = await get_rows("propiedades", {"id": f"in.({','.join(ids)})", "select": SELECT_PROPIEDADES})
    nombre = (contacto.get("nombre") or "").split(" ")[0].title()
    lineas = [f"Hola {nombre}, te comparto opciones que coinciden con lo que buscas:" if nombre else
              "Hola, te comparto opciones que coinciden con lo que buscas:", ""]
    for p in props:
        res = _resumen(p, "")
        partes = [res["titulo"] or res["tipo"], ", ".join(x for x in (res["colonia"], res["ciudad"]) if x), _precio(res)]
        lineas.append("• " + " · ".join(x for x in partes if x))
        lineas.append("  " + liga_publica(p["id"], ctx["user_id"]))
    lineas += ["", "¿Te gustaría visitar alguna?"]
    conv = None
    try:
        wa = await get_rows("wa2_contactos", {"contacto_crm_id": f"eq.{req.contacto_id}", "select": "id", "limit": "1"})
        if wa:
            cs = await get_rows("wa2_conversaciones", {"contacto_id": f"eq.{wa[0]['id']}", "select": "id,last_inbound_at", "limit": "1"})
            conv = cs[0] if cs else None
    except httpx.HTTPStatusError:
        conv = None
    ventana = False
    if conv and conv.get("last_inbound_at"):
        try:
            ventana = datetime.now(timezone.utc) - datetime.fromisoformat(conv["last_inbound_at"].replace("Z", "+00:00")) < timedelta(hours=24)
        except Exception:
            ventana = False
    return {"mensaje": "\n".join(lineas), "asunto": "Opciones de inmuebles para ti",
            "telefono": contacto.get("wa") or contacto.get("telefono"), "email": contacto.get("email"),
            "conversacion_id": (conv or {}).get("id"), "ventana_24h": ventana}


class RegistrarEnvioReq(BaseModel):
    contacto_id: str
    propiedad_ids: List[str]
    canal: str


@router.post("/registrar-envio")
async def registrar_envio(req: RegistrarEnvioReq, request: Request):
    ctx = await _ctx(request)
    await _contacto(ctx, req.contacto_id)
    r = await _requerimiento(req.contacto_id)
    canal = req.canal if req.canal in ("whatsapp", "correo") else "whatsapp"
    ids = [i for i in req.propiedad_ids if len(i) == 36][:10]
    ahora = _ahora()
    if r:
        filas = [{"org_id": ctx["org_id"], "requerimiento_id": r["id"], "contacto_id": req.contacto_id, "propiedad_id": pid,
                  "estado": "enviada", "canal": canal, "enviada_en": ahora, "enviada_por": ctx["user_id"]} for pid in ids]
        try:
            await upsert_rows("alertas_enviadas", filas, conflict="requerimiento_id,propiedad_id")
        except httpx.HTTPStatusError as e:
            log.warning("alertas_enviadas: %s", e.response.text[:160])
    titulos = [p.get("titulo") or "inmueble" for p in await get_rows("propiedades", {"id": f"in.({','.join(ids)})", "select": "titulo"})] if ids else []
    try:
        await post_rows("actividades", {"user_id": ctx["user_id"], "contacto_id": req.contacto_id, "tipo": "nota",
                                        "texto": f"Se le enviaron por {'WhatsApp' if canal == 'whatsapp' else 'correo'} "
                                                 f"{len(ids)} inmueble(s): " + "; ".join(titulos)})
    except httpx.HTTPStatusError:
        pass
    return {"ok": True, "registradas": len(ids)}


# ══════════════════════════════════════════════════════════════════════════
# CLIENTES POTENCIALES (desde la ficha del inmueble)
# ══════════════════════════════════════════════════════════════════════════
@router.get("/clientes-potenciales/{propiedad_id}")
async def clientes_potenciales(propiedad_id: str, request: Request):
    ctx = await _ctx(request)
    props = await get_rows("propiedades", {"id": f"eq.{propiedad_id}", "select": SELECT_PROPIEDADES, "limit": "1"})
    if not props or (props[0].get("org_id") not in (ctx["org_id"], None) and not props[0].get("en_bolsa")):
        raise HTTPException(status_code=404, detail="Inmueble no encontrado.")
    prop = dict(props[0], estatus="activa")      # también para inmuebles aún no publicados
    reqs = await get_rows("requerimientos_busqueda", {"org_id": f"eq.{ctx['org_id']}", "activo": "eq.true", "select": "*", "limit": "3000"})
    ligados = {l["contacto_id"] for l in await get_rows("contactos_propiedades", {"propiedad_id": f"eq.{propiedad_id}", "select": "contacto_id"})}
    candidatos = [r for r in reqs if coincide(r, prop)[0]]
    if not candidatos:
        return {"clientes": []}
    ids = ",".join(dict.fromkeys(r["contacto_id"] for r in candidatos))
    contactos = {c["id"]: c for c in await get_rows("contactos", {"id": f"in.({ids})", "select": "id,nombre,telefono,email,asignado_a,estatus"})}
    out = []
    for r in candidatos:
        c = contactos.get(r["contacto_id"])
        if not c:
            continue
        out.append({"contacto_id": c["id"], "nombre": c.get("nombre"), "telefono": c.get("telefono"),
                    "asignado_a": c.get("asignado_a"), "etapa": c.get("estatus"),
                    "motivos": coincide(r, prop)[1], "ligado": c["id"] in ligados})
    return {"clientes": out}


class LigarReq(BaseModel):
    contacto_id: str
    propiedad_id: str


@router.post("/ligar-interesado")
async def ligar_interesado(req: LigarReq, request: Request):
    ctx = await _ctx(request)
    await _contacto(ctx, req.contacto_id)
    ya = await get_rows("contactos_propiedades", {"contacto_id": f"eq.{req.contacto_id}", "propiedad_id": f"eq.{req.propiedad_id}",
                                                  "select": "id", "limit": "1"})
    if not ya:
        await post_rows("contactos_propiedades", {"contacto_id": req.contacto_id, "propiedad_id": req.propiedad_id,
                                                  "relacion": "interes", "user_id": ctx["user_id"]})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# PÁGINA "ALERTAS DE BÚSQUEDA"
# ══════════════════════════════════════════════════════════════════════════
@router.get("/requerimientos")
async def listar(request: Request, agente: str = ""):
    ctx = await _ctx(request)
    p = {"org_id": f"eq.{ctx['org_id']}", "select": "*", "order": "actualizado_en.desc", "limit": "2000"}
    reqs = await get_rows("requerimientos_busqueda", p)
    if not reqs:
        return {"requerimientos": [], "es_admin": ctx["es_admin"]}
    ids = ",".join(dict.fromkeys(r["contacto_id"] for r in reqs))
    contactos = {c["id"]: c for c in await get_rows("contactos", {"id": f"in.({ids})", "select": "id,nombre,telefono,asignado_a,user_id"})}
    pendientes: Dict[str, int] = {}
    try:
        for a in await get_rows("alertas_enviadas", {"org_id": f"eq.{ctx['org_id']}", "estado": "eq.pendiente", "select": "requerimiento_id"}):
            pendientes[a["requerimiento_id"]] = pendientes.get(a["requerimiento_id"], 0) + 1
    except httpx.HTTPStatusError:
        pass
    ve_todo = ctx["es_admin"] or permiso_efectivo(ctx, "ver_contactos_equipo")
    out = []
    for r in reqs:
        c = contactos.get(r["contacto_id"]) or {}
        agente_id = c.get("asignado_a") or r.get("user_id")
        if not ve_todo and agente_id != ctx["user_id"]:
            continue
        if agente and agente != agente_id:
            continue
        out.append({**r, "contacto_nombre": c.get("nombre") or "Contacto", "agente_id": agente_id,
                    "nuevas": pendientes.get(r["id"], 0)})
    return {"requerimientos": out, "es_admin": ctx["es_admin"]}


class EstadoReq(BaseModel):
    activo: bool


async def _req_de_org(ctx: dict, rid: str) -> dict:
    filas = await get_rows("requerimientos_busqueda", {"id": f"eq.{rid}", "org_id": f"eq.{ctx['org_id']}", "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Requerimiento no encontrado.")
    return filas[0]


@router.patch("/requerimientos/{rid}")
async def pausar(rid: str, req: EstadoReq, request: Request):
    ctx = await _ctx(request)
    await _req_de_org(ctx, rid)
    await patch_rows("requerimientos_busqueda", {"id": f"eq.{rid}"}, {"activo": req.activo, "actualizado_en": _ahora()})
    return {"ok": True}


@router.delete("/requerimientos/{rid}")
async def eliminar(rid: str, request: Request):
    ctx = await _ctx(request)
    r = await _req_de_org(ctx, rid)
    if not ctx["es_admin"] and r.get("user_id") != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="Sólo quien lo creó o un administrador lo puede eliminar.")
    await delete_rows("alertas_enviadas", {"requerimiento_id": f"eq.{rid}"})
    await delete_rows("requerimientos_busqueda", {"id": f"eq.{rid}"})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# CICLO DIARIO
# ══════════════════════════════════════════════════════════════════════════
async def revisar_alertas() -> int:
    """Por cada requerimiento activo sin revisar en 20 h: detecta inmuebles
    nuevos o cambiados que coinciden y no se han registrado, y avisa al
    agente por push. Devuelve cuántas coincidencias nuevas encontró."""
    limite = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    try:
        reqs = await get_rows("requerimientos_busqueda", {
            "select": "*", "activo": "eq.true", "org_id": "not.is.null",
            "or": f"(ultima_alerta_en.is.null,ultima_alerta_en.lt.{limite})", "limit": "200"})
    except httpx.HTTPStatusError as e:
        log.warning("alertas: requerimientos no disponibles (%s)", e.response.status_code)
        return 0
    total = 0
    cache_inv: Dict[str, List[dict]] = {}
    for r in reqs:
        try:
            org = r["org_id"]
            if org not in cache_inv:
                inv = await get_rows("propiedades", {"select": SELECT_PROPIEDADES, "estatus": "eq.activa",
                                                     "org_id": f"eq.{org}", "limit": "3000"}, timeout=20)
                cache_inv[org] = inv + await _bolsa(org)
            desde = r.get("ultima_alerta_en") or r.get("actualizado_en") or r.get("creado_en")
            nuevas = [p for p in cache_inv[org]
                      if (p.get("updated_at") or p.get("created_at") or "") >= (desde or "") and coincide(r, p)[0]]
            registradas = 0
            if nuevas:
                ya = {a["propiedad_id"] for a in await get_rows("alertas_enviadas", {"requerimiento_id": f"eq.{r['id']}", "select": "propiedad_id"})}
                filas = [{"org_id": org, "requerimiento_id": r["id"], "contacto_id": r["contacto_id"], "propiedad_id": p["id"],
                          "origen": "bolsa" if p.get("org_id") != org else "propio", "estado": "pendiente"}
                         for p in nuevas if p["id"] not in ya]
                if filas:
                    await post_rows("alertas_enviadas", filas, prefer="return=minimal")
                    registradas = len(filas)
            await patch_rows("requerimientos_busqueda", {"id": f"eq.{r['id']}"}, {"ultima_alerta_en": _ahora()})
            if registradas:
                total += registradas
                contacto = await get_rows("contactos", {"id": f"eq.{r['contacto_id']}", "select": "nombre,asignado_a", "limit": "1"})
                c = contacto[0] if contacto else {}
                agente = c.get("asignado_a") or r.get("user_id")
                try:
                    from push import enviar_push
                    await enviar_push(agente, "Coincidencias nuevas",
                                      f"{registradas} inmueble(s) para {(c.get('nombre') or 'tu cliente').title()}",
                                      {"tipo": "alerta", "url": f"contactos.html?id={r['contacto_id']}&tab=requerimiento"})
                except Exception as e:
                    log.info("push de alerta no enviado: %s", e)
        except Exception as e:
            log.warning("alerta de requerimiento %s falló: %s", r.get("id"), e)
    return total


async def _ciclo_alertas() -> None:
    while True:
        try:
            n = await revisar_alertas()
            if n:
                log.info("Alertas de búsqueda: %d coincidencias nuevas", n)
        except Exception as e:
            log.error("Fallo el ciclo de alertas: %s", e)
        await asyncio.sleep(3600)


@router.on_event("startup")
async def _iniciar_alertas() -> None:
    # Manda push reales: igual que los recordatorios, sólo en UNA instancia.
    if not settings.reminders_enabled:
        log.warning("Ciclo de alertas de búsqueda DESACTIVADO por RECORDATORIOS_ACTIVOS.")
        return
    asyncio.create_task(_ciclo_alertas())
