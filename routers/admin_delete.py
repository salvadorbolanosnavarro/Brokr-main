"""Legacy destructive admin account deletion, isolated from the bootstrap.

This module preserves the historical endpoint contract. Refactoring and tests
must never invoke the endpoint against real data.
"""
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.database import call_service_rpc, get_rows, get_service_json
from core.legacy_admin import require_legacy_admin


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key


class AdminEliminarReq(BaseModel):
    user_id: str
    email_confirmacion: str


@router.post("/admin/user/eliminar")
async def admin_eliminar_usuario(req: AdminEliminarReq, request: Request):
    caller_id = await require_legacy_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")
    if target_id == caller_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta de admin.")

    try:
        filas = await get_service_json(
            "usuarios",
            {"id": f"eq.{target_id}", "select": "id,email,rol", "limit": "1"},
            timeout=10,
            accepted_statuses=(200,),
        )
    except httpx.HTTPStatusError:
        filas = []
    if not filas:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    objetivo = filas[0]
    if (objetivo.get("rol") or "agente") == "admin":
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar a un admin. Primero cámbiale el rol a agente.",
        )
    email_real = (objetivo.get("email") or "").strip().lower()
    if (req.email_confirmacion or "").strip().lower() != email_real:
        raise HTTPException(
            status_code=400,
            detail="El correo de confirmación no coincide con el de la cuenta.",
        )

    rutas_fotos = await _storage_rutas_fotos_de_usuario(target_id)

    try:
        resultado = await call_service_rpc(
            "admin_eliminar_usuario_total",
            {"p_user_id": target_id},
            timeout=60,
            accepted_statuses=(200,),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {exc.response.text}")
    if not (isinstance(resultado, dict) and resultado.get("ok")):
        detalle = resultado.get("error") if isinstance(resultado, dict) else str(resultado)
        raise HTTPException(status_code=500, detail=f"La eliminación no se completó: {detalle}")

    borrado = dict(resultado.get("borrado", {}))
    archivos_borrados = await _storage_borrar_carpeta_usuario(target_id, rutas_fotos)
    if archivos_borrados > 0:
        borrado["storage (archivos)"] = archivos_borrados
    elif archivos_borrados < 0:
        borrado["storage (archivos)"] = "revisar logs — no se pudieron borrar todos"

    return {"ok": True, "user_id": target_id, "email": email_real, "borrado": borrado}


async def _storage_rutas_fotos_de_usuario(user_id: str) -> dict:
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
            buckets = [
                b.get("name")
                for b in (r.json() if r.status_code == 200 else [])
                if isinstance(b, dict) and b.get("name")
            ]

            for bucket in buckets:
                pendientes = [f"{user_id}/"]
                archivos: list = []
                pasos = 0
                while pendientes and pasos < 500:
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

            for bucket, rutas in (rutas_extra or {}).items():
                if rutas and not await _borrar_lote(client, bucket, list(rutas)):
                    hubo_error = True
    except Exception as e:
        print(f"[eliminar-usuario] Error limpiando Storage de {user_id}: {e}")
        hubo_error = True

    return -1 if hubo_error else total
