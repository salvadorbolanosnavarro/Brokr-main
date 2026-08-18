from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.database import get_rows
from core.property_photos import foto_migrable, fotos_en_proceso
from routers.organizaciones import get_org_id_for_user


router = APIRouter()


@router.get("/easybroker/fotos-pendientes")
async def easybroker_fotos_pendientes(request: Request):
    """Cuántas propiedades de la empresa siguen con fotos fuera de Broquer."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return {"pendientes": 0, "en_proceso": False}
    pendientes = 0
    try:
        filas_pendientes = await get_rows(
            "propiedades",
            {"org_id": f"eq.{org_id}", "select": "fotos"},
            timeout=30,
        )
        for fila in filas_pendientes:
            fotos = fila.get("fotos") or []
            if isinstance(fotos, list) and any(foto_migrable(f) for f in fotos):
                pendientes += 1
    except Exception:
        pass
    return {"pendientes": pendientes, "en_proceso": org_id in fotos_en_proceso}
