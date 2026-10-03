# ──────────────────────────────────────────────────────────────────────────
# routers/buzon.py · Buzón: bandeja única de leads
# ──────────────────────────────────────────────────────────────────────────
# Lista, estados, asignación, nota interna, primera respuesta, captura manual,
# respuestas guardadas, reglas de asignación y el webhook de entrada para
# Zapier / EasyBroker / portales. La lógica de registro vive en core/buzon.py.
#
# Visibilidad: el dueño/admin y quien tiene "ver contactos del equipo" ven todo
# el buzón de su organización; los demás, sus leads y los sin asignar. Asignar
# a otra persona lo hace el admin; cualquiera puede tomar uno sin asignar.
#
# Depende de: migracion-fase4-buzon.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import buzon as B
from core.auth import get_user_id_from_token
from core.database import delete_rows, get_rows, patch_rows, post_rows
from routers.organizaciones import get_org_context, permiso_efectivo

router = APIRouter(prefix="/buzon", tags=["buzon"])
log = logging.getLogger("broquer.buzon")


async def _ctx(request: Request, *, admin: bool = False) -> Dict[str, Any]:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(uid)
    if not ctx or not ctx.get("activo") or not ctx.get("org_id"):
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    ctx["user_id"] = uid
    ctx["es_admin"] = ctx.get("rol_org") in ("owner", "admin")
    ctx["ve_todo"] = ctx["es_admin"] or permiso_efectivo(ctx, "ver_contactos_equipo")
    if admin and not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo el administrador de la cuenta puede cambiar esto.")
    return ctx


def _filtro_visibilidad(ctx: dict) -> Dict[str, str]:
    p = {"org_id": f"eq.{ctx['org_id']}"}
    if not ctx["ve_todo"]:
        p["or"] = f"(asignado_a.eq.{ctx['user_id']},asignado_a.is.null)"
    return p


async def _lead(ctx: dict, lead_id: str) -> dict:
    p = _filtro_visibilidad(ctx)
    p.update({"id": f"eq.{lead_id}", "select": "*", "limit": "1"})
    filas = await get_rows("buzon_leads", p)
    if not filas:
        raise HTTPException(status_code=404, detail="Lead no encontrado.")
    return filas[0]


def _segundos(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        return max(0, int((datetime.fromisoformat(b.replace("Z", "+00:00")) -
                           datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds()))
    except Exception:
        return None


async def _completar_primera_respuesta(leads: List[dict]) -> None:
    """Para WhatsApp, la primera respuesta es el primer mensaje del agente en
    la conversación después de que entró el lead."""
    for l in leads:
        if l.get("primera_respuesta_en") or l.get("canal") != "whatsapp" or not l.get("referencia"):
            continue
        try:
            msgs = await get_rows("wa2_mensajes", {
                "conversacion_id": f"eq.{l['referencia']}", "direction": "eq.out",
                "created_at": f"gte.{l['created_at']}", "select": "created_at",
                "order": "created_at.asc", "limit": "1"})
        except httpx.HTTPStatusError:
            continue
        if msgs:
            l["primera_respuesta_en"] = msgs[0]["created_at"]
            await patch_rows("buzon_leads", {"id": f"eq.{l['id']}", "primera_respuesta_en": "is.null"},
                             {"primera_respuesta_en": msgs[0]["created_at"]})


# ══════════════════════════════════════════════════════════════════════════
# LISTA
# ══════════════════════════════════════════════════════════════════════════
@router.get("")
async def listar(request: Request, estado: str = "sin_atender", canal: str = "", fuente_id: str = "",
                 asignado: str = "", propiedad_id: str = "", limit: int = 200):
    ctx = await _ctx(request)
    p = _filtro_visibilidad(ctx)
    p.update({"select": "*", "order": "ultimo_mensaje_en.desc", "limit": str(max(1, min(limit, 500)))})
    if estado in B.ESTADOS:
        p["estado"] = f"eq.{estado}"
    if canal:
        p["canal"] = f"eq.{canal[:30]}"
    if fuente_id:
        p["fuente_id"] = f"eq.{fuente_id[:64]}"
    if propiedad_id:
        p["propiedad_id"] = f"eq.{propiedad_id[:64]}"
    if asignado == "nadie":
        p["asignado_a"] = "is.null"
    elif asignado == "yo":
        p["asignado_a"] = f"eq.{ctx['user_id']}"
    elif asignado:
        p["asignado_a"] = f"eq.{asignado[:64]}"
    try:
        leads = await get_rows("buzon_leads", p, timeout=15)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=503, detail="Falta correr migracion-fase4-buzon.sql en Supabase.")
    await _completar_primera_respuesta(leads)
    # Títulos de inmuebles en una sola consulta.
    pids = sorted({l["propiedad_id"] for l in leads if l.get("propiedad_id")})
    titulos = {}
    if pids:
        for f in await get_rows("propiedades", {"id": f"in.({','.join(pids)})", "select": "id,titulo"}):
            titulos[f["id"]] = f.get("titulo")
    for l in leads:
        l["propiedad_titulo"] = titulos.get(l.get("propiedad_id"))
        l["primera_respuesta_seg"] = _segundos(l.get("created_at"), l.get("primera_respuesta_en"))
    return {"leads": leads, "es_admin": ctx["es_admin"]}


@router.get("/contador")
async def contador(request: Request):
    ctx = await _ctx(request)
    p = _filtro_visibilidad(ctx)
    p.update({"estado": "eq.sin_atender", "select": "id", "limit": "500"})
    try:
        filas = await get_rows("buzon_leads", p)
    except httpx.HTTPStatusError:
        return {"sin_atender": 0}
    return {"sin_atender": len(filas)}


@router.get("/estadisticas")
async def estadisticas(request: Request, desde: str = "", hasta: str = ""):
    """Tiempo de primera respuesta por agente y por canal (para Estadísticas)."""
    ctx = await _ctx(request)
    p = _filtro_visibilidad(ctx)
    p.update({"select": "id,canal,asignado_a,created_at,primera_respuesta_en,referencia,estado", "limit": "5000"})
    if desde:
        p["created_at"] = f"gte.{desde[:10]}"
    if hasta:
        p["and"] = f"(created_at.lte.{hasta[:10]}T23:59:59)"
    leads = await get_rows("buzon_leads", p, timeout=20)
    await _completar_primera_respuesta(leads)
    def resumen(grupo):
        tiempos = sorted(s for s in (_segundos(l["created_at"], l.get("primera_respuesta_en")) for l in grupo) if s is not None)
        return {"leads": len(grupo), "respondidos": len(tiempos),
                "mediana_seg": tiempos[len(tiempos) // 2] if tiempos else None,
                "promedio_seg": int(sum(tiempos) / len(tiempos)) if tiempos else None}
    por_agente, por_canal = {}, {}
    for l in leads:
        por_agente.setdefault(l.get("asignado_a") or "sin_asignar", []).append(l)
        por_canal.setdefault(l.get("canal"), []).append(l)
    return {"total": resumen(leads),
            "por_agente": {k: resumen(v) for k, v in por_agente.items()},
            "por_canal": {k: resumen(v) for k, v in por_canal.items()}}


# ══════════════════════════════════════════════════════════════════════════
# ACCIONES SOBRE UN LEAD
# ══════════════════════════════════════════════════════════════════════════
class CambioReq(BaseModel):
    estado: Optional[str] = None
    nota_interna: Optional[str] = None


@router.patch("/{lead_id}")
async def cambiar(lead_id: str, req: CambioReq, request: Request):
    ctx = await _ctx(request)
    lead = await _lead(ctx, lead_id)
    cambios: Dict[str, Any] = {"updated_at": B.ahora_iso()}
    if req.estado is not None:
        if req.estado not in B.ESTADOS:
            raise HTTPException(status_code=400, detail="Estado inválido.")
        cambios["estado"] = req.estado
        if req.estado == "atendida":
            cambios["atendido_en"] = B.ahora_iso()
            if not lead.get("primera_respuesta_en"):
                cambios["primera_respuesta_en"] = B.ahora_iso()
        if req.estado == "spam" and lead.get("contacto_id"):
            try:
                await patch_rows("contactos", {"id": f"eq.{lead['contacto_id']}"}, {"estatus": "spam", "es_potencial": True})
            except httpx.HTTPStatusError:
                pass
    if req.nota_interna is not None:
        cambios["nota_interna"] = req.nota_interna[:4000]
    res = await patch_rows("buzon_leads", {"id": f"eq.{lead_id}"}, cambios, prefer="return=representation")
    return (res or [lead])[0]


class AsignarReq(BaseModel):
    user_id: Optional[str] = None


@router.post("/{lead_id}/asignar")
async def asignar(lead_id: str, req: AsignarReq, request: Request):
    ctx = await _ctx(request)
    lead = await _lead(ctx, lead_id)
    destino = req.user_id or None
    if not ctx["es_admin"]:
        # Un agente sólo puede tomar para sí un lead sin asignar.
        if destino != ctx["user_id"] or lead.get("asignado_a"):
            raise HTTPException(status_code=403, detail="Sólo el administrador puede reasignar leads.")
    if destino and destino not in await B.miembros_activos(ctx["org_id"]):
        raise HTTPException(status_code=400, detail="Esa persona no es del equipo.")
    res = await patch_rows("buzon_leads", {"id": f"eq.{lead_id}"},
                           {"asignado_a": destino, "asignado_en": B.ahora_iso() if destino else None,
                            "updated_at": B.ahora_iso()}, prefer="return=representation")
    if destino and lead.get("contacto_id"):
        try:
            await patch_rows("contactos", {"id": f"eq.{lead['contacto_id']}"}, {"asignado_a": destino})
        except httpx.HTTPStatusError:
            pass
    if destino and destino != ctx["user_id"]:
        await B.avisar_asignacion(destino, (res or [lead])[0])
    return (res or [lead])[0]


@router.post("/{lead_id}/respondido")
async def respondido(lead_id: str, request: Request):
    """Lo llama la pantalla al responder por WhatsApp o correo desde el Buzón."""
    ctx = await _ctx(request)
    await _lead(ctx, lead_id)
    await patch_rows("buzon_leads", {"id": f"eq.{lead_id}", "primera_respuesta_en": "is.null"},
                     {"primera_respuesta_en": B.ahora_iso()})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# ALTA MANUAL ("lead de teléfono")
# ══════════════════════════════════════════════════════════════════════════
class ManualReq(BaseModel):
    nombre: str
    telefono: str = ""
    email: str = ""
    mensaje: str = ""
    fuente: str = ""
    canal: str = "telefono"
    propiedad_id: Optional[str] = None


@router.post("/manual")
async def alta_manual(req: ManualReq, request: Request):
    ctx = await _ctx(request)
    if not (req.nombre or "").strip():
        raise HTTPException(status_code=400, detail="El nombre es obligatorio.")
    if not (req.telefono.strip() or req.email.strip()):
        raise HTTPException(status_code=400, detail="Escribe un teléfono o un correo.")
    canal = req.canal if req.canal in ("telefono", "manual", "correo", "portal") else "telefono"
    return await B.registrar_lead(org_id=ctx["org_id"], user_id=ctx["user_id"], canal=canal,
                                  nombre=req.nombre.strip(), telefono=req.telefono.strip(), email=req.email.strip(),
                                  mensaje=req.mensaje.strip(), fuente=req.fuente.strip() or B.CANALES[canal],
                                  propiedad_id=req.propiedad_id or None)


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK DE ENTRADA (Zapier, EasyBroker vía Zapier, portales)
# ══════════════════════════════════════════════════════════════════════════
@router.post("/entrada/{token}")
async def entrada(token: str, request: Request):
    """Recibe un lead externo. El token secreto identifica a la organización
    (Ajustes de CRM → Asignación de leads). Acepta JSON o formulario con:
    nombre, telefono, email, mensaje, fuente, canal, propiedad (id, clave
    interna o ID de EasyBroker), referencia (id externo para no duplicar)."""
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="No encontrado.")
    reglas = await get_rows("buzon_reglas", {"token_entrada": f"eq.{token}", "select": "org_id", "limit": "1"})
    if not reglas:
        raise HTTPException(status_code=404, detail="No encontrado.")
    org_id = reglas[0]["org_id"]
    try:
        body = await request.json()
    except Exception:
        try:
            body = dict(await request.form())
        except Exception:
            body = {}
    if not isinstance(body, dict):
        body = {}
    def campo(*claves):
        for k in claves:
            v = body.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""
    nombre = campo("nombre", "name", "full_name", "contact_name")
    telefono = campo("telefono", "phone", "phone_number", "celular")
    email = campo("email", "correo", "mail")
    if not (nombre or telefono or email):
        raise HTTPException(status_code=400, detail="Falta nombre, teléfono o correo.")
    dueños = await get_rows("organizacion_miembros", {"org_id": f"eq.{org_id}", "rol_org": "eq.owner",
                                                      "activo": "eq.true", "select": "user_id", "limit": "1"})
    user_id = dueños[0]["user_id"] if dueños else None
    prop = campo("propiedad", "propiedad_id", "property_id", "public_id", "clave")
    propiedad_id = None
    if prop:
        for col in ("id", "eb_public_id", "clave_interna"):
            if col == "id" and len(prop) != 36:
                continue
            filas = await get_rows("propiedades", {col: f"eq.{prop}", "org_id": f"eq.{org_id}", "select": "id", "limit": "1"})
            if filas:
                propiedad_id = filas[0]["id"]
                break
    canal = (campo("canal") or "zapier").lower()
    if canal not in B.CANALES:
        canal = "zapier"
    lead = await B.registrar_lead(org_id=org_id, user_id=user_id, canal=canal, nombre=nombre, telefono=telefono,
                                  email=email, mensaje=campo("mensaje", "message", "comments", "comentarios"),
                                  fuente=campo("fuente", "source") or B.CANALES[canal], propiedad_id=propiedad_id,
                                  referencia=campo("referencia", "id", "lead_id") or None,
                                  datos={k: v for k, v in body.items() if isinstance(v, (str, int, float, bool))})
    return {"ok": True, "id": lead.get("id")}


# ══════════════════════════════════════════════════════════════════════════
# RESPUESTAS GUARDADAS
# ══════════════════════════════════════════════════════════════════════════
class RespuestaReq(BaseModel):
    titulo: str
    texto: str
    canal: str = "todos"


@router.get("/respuestas")
async def respuestas(request: Request):
    ctx = await _ctx(request)
    return {"respuestas": await get_rows("respuestas_guardadas", {"org_id": f"eq.{ctx['org_id']}",
                                                                   "select": "*", "order": "titulo.asc"})}


def _validar_respuesta(req: RespuestaReq) -> dict:
    if not req.titulo.strip() or not req.texto.strip():
        raise HTTPException(status_code=400, detail="Escribe título y texto.")
    return {"titulo": req.titulo.strip()[:80], "texto": req.texto.strip()[:2000],
            "canal": req.canal if req.canal in ("todos", "whatsapp", "correo") else "todos"}


@router.post("/respuestas")
async def crear_respuesta(req: RespuestaReq, request: Request):
    ctx = await _ctx(request)
    fila = _validar_respuesta(req)
    fila.update({"org_id": ctx["org_id"], "creado_por": ctx["user_id"]})
    return (await post_rows("respuestas_guardadas", fila))[0]


@router.patch("/respuestas/{rid}")
async def editar_respuesta(rid: str, req: RespuestaReq, request: Request):
    ctx = await _ctx(request)
    filtro = {"id": f"eq.{rid}", "org_id": f"eq.{ctx['org_id']}"}
    if not ctx["es_admin"]:
        filtro["creado_por"] = f"eq.{ctx['user_id']}"
    res = await patch_rows("respuestas_guardadas", filtro, {**_validar_respuesta(req), "updated_at": B.ahora_iso()},
                           prefer="return=representation")
    if not res:
        raise HTTPException(status_code=404, detail="No encontrada o no es tuya.")
    return res[0]


@router.delete("/respuestas/{rid}")
async def borrar_respuesta(rid: str, request: Request):
    ctx = await _ctx(request)
    filtro = {"id": f"eq.{rid}", "org_id": f"eq.{ctx['org_id']}"}
    if not ctx["es_admin"]:
        filtro["creado_por"] = f"eq.{ctx['user_id']}"
    await delete_rows("respuestas_guardadas", filtro)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# REGLAS DE ASIGNACIÓN
# ══════════════════════════════════════════════════════════════════════════
@router.get("/reglas")
async def ver_reglas(request: Request):
    ctx = await _ctx(request, admin=True)
    regla = await B.regla_de(ctx["org_id"])
    guardias = await get_rows("buzon_guardias", {"org_id": f"eq.{ctx['org_id']}", "select": "id,user_id,dia,hora_inicio,hora_fin",
                                                 "order": "dia.asc,hora_inicio.asc"})
    return {"regla": regla, "guardias": guardias}


class GuardiaIn(BaseModel):
    user_id: str
    dia: int
    hora_inicio: str
    hora_fin: str


class ReglasReq(BaseModel):
    modo: str
    ruleta_usuarios: List[str] = []
    guardias: Optional[List[GuardiaIn]] = None
    generar_token: bool = False


@router.put("/reglas")
async def guardar_reglas(req: ReglasReq, request: Request):
    ctx = await _ctx(request, admin=True)
    org = ctx["org_id"]
    if req.modo not in B.MODOS:
        raise HTTPException(status_code=400, detail="Modo inválido.")
    activos = set(await B.miembros_activos(org))
    ruleta = [u for u in dict.fromkeys(req.ruleta_usuarios) if u in activos]
    if req.modo == "ruleta" and not ruleta:
        raise HTTPException(status_code=400, detail="Elige al menos a una persona para la ruleta.")
    regla = await B.regla_de(org)
    cambios: Dict[str, Any] = {"modo": req.modo, "ruleta_usuarios": ruleta, "updated_at": B.ahora_iso()}
    if req.generar_token or not regla.get("token_entrada"):
        cambios["token_entrada"] = B.nuevo_token()
    res = await patch_rows("buzon_reglas", {"org_id": f"eq.{org}"}, cambios, prefer="return=representation")
    if req.guardias is not None:
        filas = []
        for g in req.guardias[:200]:
            if g.user_id not in activos or not 0 <= g.dia <= 6:
                continue
            filas.append({"org_id": org, "user_id": g.user_id, "dia": g.dia,
                          "hora_inicio": g.hora_inicio[:5], "hora_fin": g.hora_fin[:5]})
        await delete_rows("buzon_guardias", {"org_id": f"eq.{org}"})
        if filas:
            await post_rows("buzon_guardias", filas, prefer="return=minimal")
    return {"regla": (res or [regla])[0]}
