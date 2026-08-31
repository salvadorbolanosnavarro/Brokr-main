# ──────────────────────────────────────────────────────────────────────────
# routers/bolsa.py · Broquer — Bolsa inmobiliaria
# ──────────────────────────────────────────────────────────────────────────
# La bolsa compartida entre agentes Broquer: cada agente publica inmuebles
# de su propio inventario declarando qué porcentaje de comisión comparte,
# y cualquier otro agente de la plataforma los explora y contacta al
# captador directo.
#
# POR QUÉ VA POR BACKEND Y NO POR RLS
#   Las políticas RLS de la tabla propiedades dicen "cada quien ve solo lo
#   suyo" y así se quedan. Abrir una política de lectura cruzada expondría
#   TODA la fila (calle exacta, número, notas internas) a cualquier cuenta.
#   Aquí el service key lee la fila completa pero el endpoint devuelve solo
#   los campos públicos de bolsa. El agente captador decide qué comparte.
#
# QUÉ SÍ SE EXPONE DE CADA PROPIEDAD EN BOLSA
#   Título, tipo, operación, precio, colonia/ciudad/estado, recámaras,
#   baños, m², estacionamientos, fotos, descripción, comisión compartida,
#   notas de bolsa y el contacto del agente captador (nombre y teléfono).
#   NUNCA: calle, número exterior/interior, CP, eb_public_id ni nada de
#   EasyBroker.
#
# Depende de: migracion-bolsa.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import rest_url, service_headers

router = APIRouter(prefix="/bolsa", tags=["bolsa"])
log = logging.getLogger("broquer.bolsa")

PAGINA = 24  # propiedades por página en el listado


async def _uid(request: Request) -> str:
    return await require_user_id(
        request,
        detail="Inicia sesión para continuar.",
    )


def _require_db() -> None:
    """Fail closed when privileged Supabase access is not configured."""
    try:
        settings.require_supabase_service()
    except RuntimeError as exc:
        raise HTTPException(
            500,
            "Supabase no está configurado en el servidor.",
        ) from exc


# ── Helpers ───────────────────────────────────────────────────────────────
def _limpia_filtro(v: str) -> str:
    """PostgREST usa comas y paréntesis como sintaxis en or=(...). Se quitan
    del texto del usuario para que un filtro raro no rompa la consulta."""
    return re.sub(r'[,()\\"]', " ", v or "").strip()


def _publica(fila: dict, agentes: dict, uid: str) -> dict:
    """Recorta una fila de propiedades a SOLO los campos públicos de bolsa."""
    ag = agentes.get(fila.get("user_id") or "", {})
    tel = re.sub(r"\D", "", str(ag.get("telefono") or ""))
    return {
        "id":               fila.get("id"),
        "titulo":           fila.get("titulo"),
        "tipo":             fila.get("tipo"),
        "operacion":        fila.get("operacion"),
        "precio":           fila.get("precio"),
        "moneda":           fila.get("moneda") or "MXN",
        "colonia":          fila.get("colonia"),
        "ciudad":           fila.get("ciudad"),
        "estado":           fila.get("estado"),
        "recamaras":        fila.get("recamaras"),
        "banos":            fila.get("banos"),
        "m2_construccion":  fila.get("m2_construccion"),
        "m2_terreno":       fila.get("m2_terreno"),
        "estacionamientos": fila.get("estacionamientos"),
        "descripcion":      fila.get("descripcion"),
        "fotos":            (fila.get("fotos") or [])[:12],
        "bolsa_comision":   fila.get("bolsa_comision"),
        "bolsa_notas":      fila.get("bolsa_notas"),
        "bolsa_fecha":      fila.get("bolsa_fecha"),
        "propia":           (fila.get("user_id") == uid),
        "agente": {
            "nombre":   ag.get("nombre") or "Agente Broquer",
            "telefono": tel or None,
        },
    }


async def _agentes_por_id(client: httpx.AsyncClient, ids: list) -> dict:
    """Trae nombre y teléfono de los captadores en UNA sola consulta."""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    try:
        r = await client.get(
            rest_url("usuarios"),
            headers=service_headers(),
            params={"id": f"in.({','.join(ids)})", "select": "id,nombre,telefono"},
        )
        if r.status_code == 200:
            return {u["id"]: u for u in (r.json() or [])}
    except Exception:
        pass
    return {}


# ══════════════════════════════════════════════════════════════════════════
# EXPLORAR LA BOLSA
# ══════════════════════════════════════════════════════════════════════════
def _patron_sin_acentos(token: str) -> str:
    """Vuelve el token insensible a acentos para ilike: cada vocal (con o sin
    acento) y la n/ñ se sustituyen por el comodín de UN carácter (_ en LIKE).
    Así "michoacan" encuentra "Michoacán" y "penon" encuentra "Peñón" aunque
    Postgres no tenga unaccent habilitado. Al ser comodín de un solo carácter,
    no abre la búsqueda de más."""
    return re.sub(r"[aeiouáéíóúüñn]", "_", token, flags=re.IGNORECASE)


_COLS_BUSQUEDA = ("titulo", "colonia", "ciudad", "estado", "descripcion", "tipo")

_ORDENES = {
    "reciente":     "bolsa_fecha.desc.nullslast",
    "precio_asc":   "precio.asc.nullslast",
    "precio_desc":  "precio.desc.nullslast",
    "comision":     "bolsa_comision.desc.nullslast",
}


@router.get("/propiedades")
async def bolsa_propiedades(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = "",
    ciudad: str = "",
    estado: str = "",
    tipo: str = "",
    operacion: str = "",
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    recamaras_min: Optional[int] = None,
    banos_min: Optional[float] = None,
    m2_min: Optional[float] = None,
    orden: str = "reciente",
):
    """Listado nacional de propiedades en bolsa, con filtros y paginación."""
    uid = await _uid(request)
    _require_db()

    params = {
        "en_bolsa": "eq.true",
        "estatus":  "eq.activa",
        "select":   "*",
        "order":    _ORDENES.get(orden, _ORDENES["reciente"]),
        "limit":    str(PAGINA),
        "offset":   str((page - 1) * PAGINA),
    }
    if ciudad:
        params["ciudad"] = f"ilike.*{_patron_sin_acentos(_limpia_filtro(ciudad))}*"
    if estado:
        params["estado"] = f"ilike.*{_patron_sin_acentos(_limpia_filtro(estado))}*"
    if tipo:
        params["tipo"] = f"eq.{_limpia_filtro(tipo)}"
    if operacion:
        params["operacion"] = f"eq.{_limpia_filtro(operacion)}"
    if recamaras_min is not None and recamaras_min > 0:
        params["recamaras"] = f"gte.{recamaras_min}"
    if banos_min is not None and banos_min > 0:
        params["banos"] = f"gte.{banos_min}"
    if m2_min is not None and m2_min > 0:
        params["m2_construccion"] = f"gte.{m2_min}"

    condiciones = []
    if precio_min is not None:
        condiciones.append(f"precio.gte.{precio_min}")
    if precio_max is not None:
        condiciones.append(f"precio.lte.{precio_max}")
    if q:
        tokens = [t for t in _limpia_filtro(q).split() if len(t) >= 2][:6]
        for t in tokens:
            pat = _patron_sin_acentos(t)
            grupo = ",".join(f"{col}.ilike.*{pat}*" for col in _COLS_BUSQUEDA)
            condiciones.append(f"or({grupo})")
    if condiciones:
        params["and"] = f"({','.join(condiciones)})"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                rest_url("propiedades"),
                headers=service_headers(prefer="count=exact"),
                params=params,
            )
            if r.status_code not in (200, 206):
                log.error("bolsa listado %s: %s", r.status_code, r.text[:300])
                raise HTTPException(500, "No se pudo cargar la bolsa. Intenta de nuevo.")
            filas = r.json() or []
            total = 0
            cr = r.headers.get("content-range", "")
            if "/" in cr:
                try:
                    total = int(cr.split("/")[-1])
                except Exception:
                    total = len(filas)
            agentes = await _agentes_por_id(client, [f.get("user_id") for f in filas])
    except HTTPException:
        raise
    except Exception as e:
        log.error("bolsa listado: %s", e)
        raise HTTPException(500, "No se pudo cargar la bolsa. Intenta de nuevo.")

    return {
        "propiedades": [_publica(f, agentes, uid) for f in filas],
        "total": total,
        "page": page,
        "paginas": max(1, -(-total // PAGINA)),
    }


# ══════════════════════════════════════════════════════════════════════════
# MIS PUBLICACIONES — el inventario propio con su estado de bolsa
# ══════════════════════════════════════════════════════════════════════════
@router.get("/mis")
async def bolsa_mis(request: Request):
    uid = await _uid(request)
    _require_db()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                rest_url("propiedades"),
                headers=service_headers(),
                params={
                    "user_id": f"eq.{uid}",
                    "estatus": "eq.activa",
                    "select":  "*",
                    "order":   "updated_at.desc.nullslast",
                    "limit":   "300",
                },
            )
            if r.status_code != 200:
                raise HTTPException(500, "No se pudo leer tu inventario.")
            filas = r.json() or []
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "No se pudo leer tu inventario.")

    props = []
    for f in filas:
        props.append({
            "id":             f.get("id"),
            "titulo":         f.get("titulo"),
            "tipo":           f.get("tipo"),
            "operacion":      f.get("operacion"),
            "precio":         f.get("precio"),
            "moneda":         f.get("moneda") or "MXN",
            "colonia":        f.get("colonia"),
            "ciudad":         f.get("ciudad"),
            "fotos":          (f.get("fotos") or [])[:1],
            "en_bolsa":       bool(f.get("en_bolsa")),
            "bolsa_comision": f.get("bolsa_comision"),
            "bolsa_notas":    f.get("bolsa_notas"),
        })
    return {"propiedades": props}


# ══════════════════════════════════════════════════════════════════════════
# PUBLICAR / RETIRAR
# ══════════════════════════════════════════════════════════════════════════
class PublicarBody(BaseModel):
    propiedad_id: str
    comision: float
    notas: Optional[str] = None


class RetirarBody(BaseModel):
    propiedad_id: str


async def _patch_propia(uid: str, propiedad_id: str, cambios: dict) -> None:
    """PATCH con doble candado: id Y user_id. Si la propiedad no es del que
    pide, PostgREST no encuentra fila y no toca nada."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            rest_url("propiedades"),
            headers=service_headers(prefer="return=representation"),
            params={"id": f"eq.{propiedad_id}", "user_id": f"eq.{uid}"},
            json=cambios,
        )
        if r.status_code not in (200, 201):
            log.error("bolsa patch %s: %s", r.status_code, r.text[:300])
            raise HTTPException(500, "No se pudo actualizar la propiedad.")
        if not (r.json() or []):
            raise HTTPException(404, "Esa propiedad no está en tu inventario.")


@router.post("/publicar")
async def bolsa_publicar(body: PublicarBody, request: Request):
    uid = await _uid(request)
    _require_db()
    if body.comision < 0 or body.comision > 100:
        raise HTTPException(400, "La comisión compartida debe estar entre 0 y 100.")
    notas = (body.notas or "").strip()[:600] or None
    await _patch_propia(uid, body.propiedad_id, {
        "en_bolsa":       True,
        "bolsa_comision": body.comision,
        "bolsa_notas":    notas,
        "bolsa_fecha":    datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True}


@router.post("/retirar")
async def bolsa_retirar(body: RetirarBody, request: Request):
    uid = await _uid(request)
    _require_db()
    await _patch_propia(uid, body.propiedad_id, {"en_bolsa": False})
    return {"ok": True}
