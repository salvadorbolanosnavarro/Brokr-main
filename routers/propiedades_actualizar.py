# ──────────────────────────────────────────────────────────────────────────
# routers/propiedades_actualizar.py · Guardar cambios en un inmueble
# ──────────────────────────────────────────────────────────────────────────
# Por qué existe:
#   El frontend (propiedades.html) editaba un inmueble con un PATCH directo
#   a Postgrest, usando el token del propio usuario. La política de RLS de
#   "propiedades" solo deja escribir al dueño original de la fila
#   (user_id = auth.uid()), un modelo de antes de que existiera Broquer para
#   Empresas. Cualquier agente del equipo puede VER todo el inventario de su
#   organización (permiso "ver_inventario_completo", true por defecto), pero
#   al intentar editar un inmueble que otro compañero dio de alta, el PATCH
#   no tocaba ninguna fila y Postgrest respondía 200 con un arreglo vacío —
#   de ahí el "no tienes permiso sobre este registro o ya no existe" que veía
#   el usuario aunque el inmueble sí existiera y sí fuera de su empresa.
#
#   Este endpoint usa la service key (como ya hace /propiedades/eliminar-masivo
#   para borrar) y valida el permiso en Python en vez de depender de RLS.
#
# CÓMO decide el permiso (importante — esto ya causó una regresión real):
#   1. Si quien edita es el DUEÑO de la fila (user_id = quien edita), se
#      deja pasar sin más — es exactamente lo que la RLS vieja ya permitía,
#      y NO depende de que su cuenta tenga membresía de organización bien
#      configurada. La primera versión de este endpoint exigía
#      get_org_context() ANTES de intentar esto, y cualquier cuenta sin esa
#      membresía (legacy, o con algún hueco de datos) se quedaba sin poder
#      editar ni sus propios inmuebles — "Tu cuenta no está configurada",
#      un candado más estricto que el que había antes de este endpoint.
#   2. Solo si lo anterior no tocó ninguna fila (no es el dueño) se consulta
#      la organización: si pertenece activamente a la misma organización
#      dueña del inmueble, también puede editarlo — la colaboración de
#      equipo que este endpoint vino a arreglar. El borrado sigue siendo
#      solo para el dueño/admin de la cuenta; editar es colaborativo.
#
# Qué NO hace:
#   No permite cambiar id/user_id/org_id/created_at desde el body: esos son
#   de administración interna, no campos que el formulario de edición deba
#   poder tocar.
# ──────────────────────────────────────────────────────────────────────────

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.catalogo_inmuebles import es_error_columna_faltante, quitar_columnas_paridad
from core.database import get_rows, patch_rows
from routers.organizaciones import get_org_context

router = APIRouter()

# Columnas que este endpoint nunca deja tocar desde el body, sin importar lo
# que mande el formulario.
_CAMPOS_PROTEGIDOS = {"id", "user_id", "org_id", "created_at"}

_MSG_SIN_PERMISO = ("El cambio no se guardó: no tienes permiso sobre este registro "
                    "o ya no existe. Recarga la página.")


async def _patch_tolerante(params: dict, cambios: dict) -> list:
    """PATCH que, si la base aún no tiene las columnas de paridad (migración
    pendiente), reintenta sin ellas en vez de perder todo el guardado."""
    try:
        return await patch_rows("propiedades", params, cambios,
                                prefer="return=representation", timeout=20)
    except httpx.HTTPStatusError as e:
        if not es_error_columna_faltante(e.response.text):
            raise
        base = quitar_columnas_paridad(cambios)
        if not base:
            return []
        return await patch_rows("propiedades", params, base,
                                prefer="return=representation", timeout=20)


@router.patch("/propiedades/{prop_id}")
async def actualizar_propiedad(prop_id: str, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")

    try:
        cambios = await request.json()
    except Exception:
        cambios = None
    if not isinstance(cambios, dict) or not cambios:
        raise HTTPException(status_code=400, detail="No se recibieron cambios para guardar.")

    cambios = {k: v for k, v in cambios.items() if k not in _CAMPOS_PROTEGIDOS}
    if not cambios:
        raise HTTPException(status_code=400, detail="No se recibieron cambios para guardar.")

    # 1) ¿Es el dueño de la fila? Funciona siempre, sin importar el estado
    #    de su membresía de organización.
    try:
        filas = await _patch_tolerante(
            {"id": f"eq.{prop_id}", "user_id": f"eq.{user_id}"},
            cambios,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo guardar el cambio. Intenta de nuevo.")

    # 2) No era el dueño (o esa fila no existe) — ¿es un compañero activo de
    #    la misma organización dueña del inmueble?
    if not filas:
        ctx = await get_org_context(user_id)
        if ctx and ctx.get("activo") and ctx.get("org_id"):
            try:
                filas = await _patch_tolerante(
                    {"id": f"eq.{prop_id}", "org_id": f"eq.{ctx['org_id']}"},
                    cambios,
                )
            except Exception:
                raise HTTPException(status_code=500, detail="No se pudo guardar el cambio. Intenta de nuevo.")

    if not filas:
        raise HTTPException(status_code=404, detail=_MSG_SIN_PERMISO)

    return filas


# ── Acciones en lote ─────────────────────────────────────────────────────────
# Misma regla que el PATCH individual: el dueño de la fila, o un compañero
# activo de la organización dueña del inmueble. Sólo campos de lote.
_CAMPOS_LOTE = {"estatus", "archivada"}
_ESTATUS_VALIDOS = {"activa", "reservada", "en_proceso", "vendida", "rentada",
                    "suspendida", "no_activa", "ajena"}


def _ids_validos(ids) -> list:
    out = []
    for i in ids or []:
        s = str(i).strip()
        if s and len(s) <= 64 and all(c.isalnum() or c == "-" for c in s):
            out.append(s)
    return list(dict.fromkeys(out))[:1000]


@router.post("/propiedades/lote")
async def propiedades_lote(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Solicitud inválida.")

    ids = _ids_validos(body.get("ids"))
    if not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste inmuebles.")
    cambios = {k: v for k, v in (body.get("set") or {}).items() if k in _CAMPOS_LOTE}
    if "estatus" in cambios and cambios["estatus"] not in _ESTATUS_VALIDOS:
        raise HTTPException(status_code=400, detail="Estatus inválido.")
    if "archivada" in cambios:
        cambios["archivada"] = bool(cambios["archivada"])
    agregar = [str(t).strip()[:60] for t in (body.get("etiquetas_agregar") or []) if str(t).strip()]
    quitar = {str(t).strip() for t in (body.get("etiquetas_quitar") or []) if str(t).strip()}
    if not cambios and not agregar and not quitar:
        raise HTTPException(status_code=400, detail="No hay cambios que aplicar.")

    ctx = await get_org_context(user_id)
    org_id = ctx.get("org_id") if ctx and ctx.get("activo") else None

    filas = []
    for i in range(0, len(ids), 150):
        grupo = ids[i:i + 150]
        filas += await get_rows("propiedades", {
            "id": f"in.({','.join(grupo)})",
            "select": "id,user_id,org_id,etiquetas",
        }, timeout=20)
    permitidas = [f for f in filas
                  if f.get("user_id") == user_id or (org_id and f.get("org_id") == org_id)]

    ahora = datetime.now(timezone.utc).isoformat()
    actualizadas = 0
    if cambios and permitidas:
        cambios["updated_at"] = ahora
        for i in range(0, len(permitidas), 150):
            grupo = [f["id"] for f in permitidas[i:i + 150]]
            res = await patch_rows("propiedades", {"id": f"in.({','.join(grupo)})"}, cambios,
                                   prefer="return=representation", timeout=20)
            actualizadas += len(res or [])
    if agregar or quitar:
        tocadas = 0
        for f in permitidas:
            et = [t for t in (f.get("etiquetas") or []) if t not in quitar]
            for t in agregar:
                if t not in et:
                    et.append(t)
            if et == (f.get("etiquetas") or []):
                tocadas += 1
                continue
            res = await patch_rows("propiedades", {"id": f"eq.{f['id']}"},
                                   {"etiquetas": et, "updated_at": ahora},
                                   prefer="return=representation", timeout=20)
            tocadas += 1 if res else 0
        actualizadas = max(actualizadas, tocadas)

    return {
        "actualizadas": actualizadas,
        "sin_permiso": len(ids) - len(permitidas),
    }
