"""Personalized DOCX contract-template workflows (machotes)."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json as _json
import re
import tempfile
from typing import Any, Dict
import uuid as _uuid

import httpx
from fastapi import APIRouter, File, Form as FastAPIForm, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

import machotes as _mach
from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.executors import _thread_pool
from core.telemetry import _track_anthropic
from routers.organizaciones import get_org_id_for_user


router = APIRouter()
MACHOTES_BUCKET = "machotes-contrato"
MACHOTE_MAX_BYTES = 12 * 1024 * 1024

_MACHOTE_SELECT = (
    "id,titulo,tipo,campos,motor,patron_usado,descartados,"
    "storage_path,texto_preview,created_at,updated_at"
)
_CAMPO_EDITABLE = (
    "label", "tipo_input", "grupo", "ayuda", "default",
    "fijo", "obligatorio", "orden",
)


def _sb_headers(extra: dict = None) -> dict:
    service_key = settings.supabase_service_key
    h = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    if extra:
        h.update(extra)
    return h


async def _machote_o_404(machote_id: str, user_id: str, select: str = _MACHOTE_SELECT) -> dict:
    try:
        rows = await get_rows(
            "machotes_contrato",
            {
                "id": f"eq.{machote_id}",
                "user_id": f"eq.{user_id}",
                "select": select,
                "limit": "1",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    if not rows:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    return rows[0]


async def _descargar_plantilla(storage_path: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{storage_path}",
            headers=_sb_headers(),
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudo leer el archivo de tu machote.")
    return r.content


async def _subir_a_storage(client: httpx.AsyncClient, path: str, content: bytes):
    r = await client.post(
        f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{path}",
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


@router.post("/contrato/machote/abrir")
async def abrir_machote(request: Request, file: UploadFile = File(...)):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    content = await file.read()
    _leer_docx_subido(file, content)
    try:
        return await asyncio.get_event_loop().run_in_executor(_thread_pool, _mach.abrir, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[machotes] error al abrir: {e}")
        raise HTTPException(status_code=400, detail="No pudimos leer tu archivo. Ábrelo en Word y guárdalo otra vez como .docx.")


@router.post("/contrato/machote/sugerir")
async def sugerir_campos_machote(
    request: Request,
    file: UploadFile = File(...),
    tipo: str = FastAPIForm(default=""),
):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    content = await file.read()
    _leer_docx_subido(file, content)
    try:
        res = await _mach.sugerir_ia(
            content,
            tipo=(tipo or "").strip(),
            api_key=settings.anthropic_api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[machotes] error al sugerir: {e}")
        raise HTTPException(status_code=500, detail="No pudimos revisar tu contrato. Márcalo tú y quedará igual de bien.")

    for raw in res.get("raws") or []:
        try:
            _track_anthropic(
                user_id,
                "contratos",
                "/contrato/machote/sugerir",
                raw,
                modelo=(raw or {}).get("model") or _mach.MODELO_DEFAULT,
            )
        except Exception:
            pass

    return {
        "campos": res["campos"],
        "marcas": res["marcas"],
        "descartados": res["descartados"],
    }


@router.post("/contrato/machote/crear")
async def crear_machote(
    request: Request,
    file: UploadFile = File(...),
    titulo: str = FastAPIForm(...),
    tipo: str = FastAPIForm(default=""),
    campos: str = FastAPIForm(...),
    marcas: str = FastAPIForm(...),
):
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
            _thread_pool,
            _mach.crear_plantilla,
            content,
            campos_in,
            marcas_in,
        )
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
        try:
            await post_rows(
                "machotes_contrato",
                fila,
                prefer="return=representation",
                timeout=60,
                accepted_statuses=(200, 201),
            )
        except httpx.HTTPStatusError as e:
            for p in (storage_path, storage_path_original):
                if not p:
                    continue
                try:
                    await client.delete(
                        f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{p}",
                        headers=_sb_headers(),
                    )
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"No se pudo guardar tu machote: {e.response.text[:200]}")

    return {"id": machote_id, "titulo": titulo, "tipo": fila["tipo"], "campos": campos_final}


@router.get("/contrato/machotes")
async def listar_machotes(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    try:
        rows = await get_rows(
            "machotes_contrato",
            {
                "user_id": f"eq.{user_id}",
                "select": "id,titulo,tipo,campos,motor,created_at",
                "order": "created_at.desc",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")
    return {"machotes": rows}


@router.get("/contrato/machote/{machote_id}")
async def obtener_machote(machote_id: str, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")
    return await _machote_o_404(machote_id, user_id)


@router.patch("/contrato/machote/{machote_id}")
async def actualizar_machote(machote_id: str, request: Request):
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
            fusion["label"] = str(fusion.get("label") or "").strip() or _mach.humanizar(fusion["id"])
            fusion["grupo"] = str(fusion.get("grupo") or "").strip() or "Datos del contrato"
            fusion["fijo"] = bool(fusion.get("fijo"))
            nuevos.append(fusion)
        if not nuevos:
            raise HTTPException(status_code=400, detail="Tu machote necesita al menos un campo.")
        faltantes = [c for cid, c in actuales.items() if cid not in {n["id"] for n in nuevos}]
        parche["campos"] = nuevos + faltantes

    if not parche:
        raise HTTPException(status_code=400, detail="No hay nada que actualizar.")
    parche["updated_at"] = datetime.utcnow().isoformat()

    try:
        rows = await patch_rows(
            "machotes_contrato",
            {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},
            parche,
            prefer="return=representation",
            timeout=15,
            accepted_statuses=(200, 204),
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")
    if not rows:
        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")
    return rows[0]


def _aplicar_fijos(datos: dict, campos: list) -> dict:
    datos = dict(datos or {})
    for c in campos or []:
        if c.get("fijo") and c.get("default") is not None:
            datos[c["id"]] = c["default"]
        elif not str(datos.get(c["id"], "")).strip() and c.get("default"):
            datos[c["id"]] = c["default"]
    return datos


@router.post("/contrato/machote/{machote_id}/preview")
async def previsualizar_machote(machote_id: str, request: Request):
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
            _thread_pool,
            _mach.previsualizar,
            contenido,
            datos,
            machote.get("campos") or [],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo generar la vista previa: {e}")
    return {"parrafos": parrafos}


@router.post("/contrato/machote/{machote_id}/generar")
async def generar_desde_machote_guardado(machote_id: str, request: Request):
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
            _thread_pool,
            _mach.rellenar,
            contenido,
            datos,
            campos,
        )
    except Exception as e:
        print(f"[machotes] error al rellenar: {e}")
        raise HTTPException(status_code=500, detail="No se pudo generar el contrato. Vuelve a intentarlo.")

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.write(docx_bytes)
        output_path = f.name

    titulo_limpio = re.sub(r"[^A-Za-z0-9_\- ]", "", machote.get("titulo") or "Contrato").strip() or "Contrato"
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{titulo_limpio}.docx",
    )


@router.delete("/contrato/machote/{machote_id}")
async def eliminar_machote(machote_id: str, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión.")

    machote = await _machote_o_404(
        machote_id,
        user_id,
        "id,storage_path,storage_path_original",
    )
    async with httpx.AsyncClient(timeout=15) as client:
        for p in (machote.get("storage_path"), machote.get("storage_path_original")):
            if not p:
                continue
            try:
                await client.delete(
                    f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{p}",
                    headers=_sb_headers(),
                )
            except Exception:
                pass
        try:
            await delete_rows(
                "machotes_contrato",
                {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},
                prefer="return=minimal",
                timeout=15,
                accepted_statuses=(200, 204),
            )
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=500, detail="No se pudo eliminar el machote.")
    return {"ok": True}
