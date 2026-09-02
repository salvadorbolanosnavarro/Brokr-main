"""WhatsApp training configuration API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get, sb_patch, sb_post
from routers.whatsapp_time import now_iso as _now
from routers.whatsapp_training import TRAINING_DEFAULTS
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter()


class TrainingReq(BaseModel):
    numero_id: str | None = None
    nombre_ia: str | None = None
    tono: str | None = None
    identidad: str | None = None
    puede: str | None = None
    debe: str | None = None
    no_debe: str | None = None
    especialidad: str | None = None
    conocimiento: str | None = None
    objetivo: str | None = None
    datos_calificar: list[str] = []
    preguntas_extra: list[str] = []
    escalar_palabras: list[str] = []
    horario_activo: bool = False
    hora_inicio: str = "08:00"
    hora_fin: str = "21:00"
    fuera_horario_msg: str | None = None
    max_mensajes_ia: int = 0
    activo: bool = True
    zona_horaria: str = "America/Mexico_City"
    modo_ia: str = "siempre_encendida"
    pausa_al_responder: bool = True
    pausa_duracion_min: int = 0
    nuevos_meses: int = 3


@router.get("/entrenamiento")
async def wa2_training_get(request: Request, numero_id: str | None = None):
    user_id = await _require_user(request)
    if numero_id:
        ids = await _ids_visibles(user_id)
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                                    "select": "id", "limit": "1"})
        if not numero_rows:
            raise HTTPException(status_code=404, detail="Número no encontrado")
        rows = await sb_get("wa2_entrenamiento", {"numero_id": f"eq.{numero_id}", "select": "*", "limit": "1"})
    else:
        rows = await sb_get("wa2_entrenamiento", {"user_id": f"eq.{user_id}", "numero_id": "is.null",
                                                  "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    return dict(TRAINING_DEFAULTS, numero_id=numero_id)


@router.put("/entrenamiento")
async def wa2_training_put(req: TrainingReq, request: Request):
    user_id = await _require_user(request)
    fila = req.dict()
    if fila.get("modo_ia") not in ("siempre_encendida", "siempre_apagada", "solo_nuevos"):
        fila["modo_ia"] = "siempre_encendida"
    fila["pausa_duracion_min"] = max(0, min(int(fila.get("pausa_duracion_min") or 0), 60 * 24 * 30))
    fila["nuevos_meses"] = max(1, min(int(fila.get("nuevos_meses") or 3), 24))
    fila["updated_at"] = _now()

    if req.numero_id:
        ids = await _ids_visibles(user_id)
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{req.numero_id}", "user_id": _in_filter(ids),
                                                    "select": "user_id", "limit": "1"})
        if not numero_rows:
            raise HTTPException(status_code=404, detail="Número no encontrado o no tienes permiso sobre él")
        fila["user_id"] = numero_rows[0]["user_id"]
        existing = await sb_get("wa2_entrenamiento", {"numero_id": f"eq.{req.numero_id}", "select": "id", "limit": "1"})
    else:
        fila["user_id"] = user_id
        existing = await sb_get("wa2_entrenamiento", {"user_id": f"eq.{user_id}", "numero_id": "is.null",
                                                      "select": "id", "limit": "1"})

    if existing:
        guardado = await sb_patch("wa2_entrenamiento", {"id": f"eq.{existing[0]['id']}"}, fila)
    else:
        fila["created_at"] = _now()
        guardado = await sb_post("wa2_entrenamiento", fila)
    if not guardado:
        raise HTTPException(status_code=500,
            detail="No se pudo guardar el entrenamiento. Vuelve a intentar en un momento; "
                   "si sigue sin guardar, es un problema de conexión con la base de datos.")
    return {"ok": True}
