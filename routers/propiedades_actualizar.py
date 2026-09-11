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
#   para borrar) y valida el permiso en Python en vez de depender de RLS:
#   cualquier miembro activo de la organización dueña del inmueble puede
#   editarlo. El borrado sigue siendo solo para el dueño/admin — editar es
#   colaborativo, borrar es más delicado — así que aquí no se exige rol.
#
# Qué NO hace:
#   No permite cambiar id/user_id/org_id/created_at desde el body: esos son
#   de administración interna, no campos que el formulario de edición deba
#   poder tocar.
# ──────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.database import patch_rows
from routers.organizaciones import get_org_context

router = APIRouter()

# Columnas que este endpoint nunca deja tocar desde el body, sin importar lo
# que mande el formulario.
_CAMPOS_PROTEGIDOS = {"id", "user_id", "org_id", "created_at"}


@router.patch("/propiedades/{prop_id}")
async def actualizar_propiedad(prop_id: str, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")

    ctx = await get_org_context(user_id)
    if not ctx or not ctx.get("org_id") or not ctx.get("activo"):
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")

    try:
        cambios = await request.json()
    except Exception:
        cambios = None
    if not isinstance(cambios, dict) or not cambios:
        raise HTTPException(status_code=400, detail="No se recibieron cambios para guardar.")

    cambios = {k: v for k, v in cambios.items() if k not in _CAMPOS_PROTEGIDOS}
    if not cambios:
        raise HTTPException(status_code=400, detail="No se recibieron cambios para guardar.")

    try:
        filas = await patch_rows(
            "propiedades",
            {"id": f"eq.{prop_id}", "org_id": f"eq.{ctx['org_id']}"},
            cambios,
            prefer="return=representation",
            timeout=20,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo guardar el cambio. Intenta de nuevo.")

    if not filas:
        raise HTTPException(
            status_code=404,
            detail="El cambio no se guardó: no tienes permiso sobre este registro o ya no existe. Recarga la página.",
        )

    return filas
