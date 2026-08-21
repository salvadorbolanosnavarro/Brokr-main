"""WhatsApp automation recipe CRUD; execution stays in the flow engine."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_delete, sb_get, sb_patch, sb_post
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])
_AUTO_TIPOS = ("mensaje", "etiqueta", "humano", "ia", "pregunta", "opciones")
_FLUJO_CAMPOS = ("nombre", "presupuesto", "interes", "nota")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutomatizacionReq(BaseModel):
    nombre: str
    numero_id: str | None = None
    disparador: str = "palabra"
    palabras: list[str] = []
    acciones: list[dict] = []
    activa: bool = True


def _limpiar_automatizacion(req: AutomatizacionReq) -> dict:
    nombre = (req.nombre or "").strip()[:80]
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle un nombre a la automatización.")
    disparador = req.disparador if req.disparador in ("palabra", "nuevo", "nuevo_3m") else "palabra"
    palabras = []
    for p in (req.palabras or []):
        t = str(p).strip().lower()[:60]
        if t and t not in palabras:
            palabras.append(t)
    palabras = palabras[:15]
    if disparador == "palabra" and not palabras:
        raise HTTPException(status_code=400, detail="Escribe al menos una palabra que la dispare.")
    acciones = []
    for a in (req.acciones or []):
        tipo = str((a or {}).get("tipo") or "").strip()
        valor = str((a or {}).get("valor") or "").strip()
        if tipo not in _AUTO_TIPOS:
            continue
        paso: dict = {"tipo": tipo, "valor": valor}
        if tipo == "mensaje":
            paso["valor"] = valor[:1000]
            if not paso["valor"]:
                continue
        elif tipo == "etiqueta":
            paso["valor"] = valor[:40]
            if not paso["valor"]:
                continue
        elif tipo == "pregunta":
            paso["valor"] = valor[:1000]
            if not paso["valor"]:
                continue
            g = str((a or {}).get("guardar") or "nota").strip().lower()
            paso["guardar"] = g if g in _FLUJO_CAMPOS else "nota"
        elif tipo == "opciones":
            paso["valor"] = valor[:1000]
            ops = []
            for o in ((a or {}).get("opciones") or [])[:6]:
                txt = str((o or {}).get("texto") or "").strip()[:60]
                if not txt:
                    continue
                op: dict = {"texto": txt}
                try:
                    ir = int((o or {}).get("ir") or 0)
                except Exception:
                    ir = 0
                if ir > 0:
                    op["ir"] = ir
                ops.append(op)
            if len(ops) < 2:
                continue
            paso["opciones"] = ops
        else:
            paso["valor"] = ""
        acciones.append(paso)
    acciones = acciones[:12]
    if not acciones:
        raise HTTPException(status_code=400, detail="Agrega al menos un paso a la automatización.")
    return {
        "nombre": nombre,
        "numero_id": req.numero_id or None,
        "disparador": disparador,
        "palabras": palabras,
        "acciones": acciones,
        "activa": bool(req.activa),
    }


@router.get("/automatizaciones")
async def wa2_automatizaciones_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_automatizaciones",
        {"user_id": _in_filter(ids), "select": "*", "order": "created_at.desc", "limit": "100"},
    )
    return {"automatizaciones": rows}


@router.post("/automatizaciones")
async def wa2_automatizacion_crear(req: AutomatizacionReq, request: Request):
    user_id = await _require_user(request)
    fila = _limpiar_automatizacion(req)
    if fila["numero_id"]:
        ids = await _ids_visibles(user_id)
        n = await sb_get(
            "wa2_numeros",
            {"id": f"eq.{fila['numero_id']}", "user_id": _in_filter(ids), "select": "id", "limit": "1"},
        )
        if not n:
            raise HTTPException(status_code=404, detail="Número no encontrado")
    fila.update({"user_id": user_id, "veces_usada": 0, "created_at": _now(), "updated_at": _now()})
    creado = await sb_post("wa2_automatizaciones", fila)
    if not creado:
        raise HTTPException(status_code=500, detail="No se pudo guardar. ¿Ya corriste la migración de automatizaciones?")
    return {"ok": True}


@router.patch("/automatizaciones/{auto_id}")
async def wa2_automatizacion_patch(auto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {}
    if "activa" in body:
        permitido["activa"] = bool(body["activa"])
    if any(k in body for k in ("nombre", "disparador", "palabras", "acciones", "numero_id")):
        actual_rows = await sb_get(
            "wa2_automatizaciones",
            {"id": f"eq.{auto_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
        )
        if not actual_rows:
            raise HTTPException(status_code=404, detail="Automatización no encontrada")
        actual = actual_rows[0]
        req = AutomatizacionReq(
            nombre=body.get("nombre", actual.get("nombre") or ""),
            numero_id=body.get("numero_id", actual.get("numero_id")),
            disparador=body.get("disparador", actual.get("disparador") or "palabra"),
            palabras=body.get("palabras", actual.get("palabras") or []),
            acciones=body.get("acciones", actual.get("acciones") or []),
            activa=bool(body.get("activa", actual.get("activa", True))),
        )
        permitido.update(_limpiar_automatizacion(req))
    if not permitido:
        return {"ok": True}
    permitido["updated_at"] = _now()
    await sb_patch("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}


@router.delete("/automatizaciones/{auto_id}")
async def wa2_automatizacion_delete(auto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    await sb_delete("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)})
    return {"ok": True}
