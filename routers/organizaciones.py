# ──────────────────────────────────────────────────────────────────────────
# routers/organizaciones.py · Broquer para empresas
# ──────────────────────────────────────────────────────────────────────────
# Todo lo de cuentas con varios usuarios vive aquí: miembros, invitaciones,
# roles y permisos.
#
# POR QUÉ ESTÁ AQUÍ Y NO EN main.py
#   Es autónomo (lee sus propias env vars) y se activa con 2 líneas en main.py,
#   igual que routers/agente.py. Así main.py casi no se toca.
#
# LA REGLA DE ORO DE ESTE ARCHIVO
#   El frontend NUNCA escribe en organizacion_miembros. Si pudiera, un agente
#   se auto-daría ver_telefonos desde la consola del navegador. Toda alta, baja
#   y cambio de permiso pasa por aquí, con service key y validando quién pide.
#
# Depende de: migracion-empresas.sql (paso 1) ya corrido.
# ──────────────────────────────────────────────────────────────────────────

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── Config (mismas env vars que main.py) ──────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").rstrip("/")
# La anon key en Railway se llama SUPABASE_ANON_KEY (igual que en main.py).
# Se deja SUPABASE_KEY como respaldo por si en otro entorno tiene ese nombre.
SUPABASE_KEY         = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
APP_URL              = os.getenv("APP_URL", "https://broquer.app").rstrip("/")

# Permisos que un admin de empresa puede prender o apagar por miembro.
# Si agregas uno aquí, agrégalo también en org_permiso() del SQL y en equipo.html.
PERMISOS_VALIDOS = {
    "ver_telefonos",
    "gestionar_integraciones",
    "ver_comisiones",
    "ver_inventario_completo",
    "ver_contactos_equipo",
    "exportar",
    "ver_estadisticas_equipo",
}

ROLES_ORG_VALIDOS = {"owner", "admin", "agente"}

# Defaults por rol. DEBEN coincidir con org_permiso() en Postgres. Si se
# desincronizan, la UI enseña una cosa y la base hace otra.
DEFAULTS_AGENTE = {
    "ver_telefonos": False,
    # Conectar/desconectar EasyBroker y Facebook. La cuenta es de la EMPRESA:
    # si un agente la desconecta, deja sin inventario a todo el equipo. Solo el
    # dueño y quien él designe.
    "gestionar_integraciones": False,
    "ver_comisiones": False,
    "ver_inventario_completo": True,
    "ver_contactos_equipo": True,
    "exportar": True,
    "ver_estadisticas_equipo": False,
}


def _headers(prefer: str = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code != 200:
            return []
        return r.json()


async def _sb_post(tabla: str, payload, prefer="return=representation") -> Optional[list]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(prefer), json=payload)
        if r.status_code not in (200, 201, 204):
            raise HTTPException(status_code=500, detail=f"Supabase {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except Exception:
            return None


async def _sb_patch(tabla: str, params: dict, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers("return=minimal"),
                          params=params, json=payload)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Supabase {r.status_code}: {r.text[:200]}")


async def _sb_delete(tabla: str, params: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as c:
        await c.delete(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)


# ══════════════════════════════════════════════════════════════════════════
# HELPERS PÚBLICOS — main.py y agente.py importan de aquí
# ══════════════════════════════════════════════════════════════════════════

async def get_user_id_from_token(request: Request) -> Optional[str]:
    """Igual que el de main.py. Duplicado a propósito: este router es autónomo."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth[7:]}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


async def get_org_context(user_id: str) -> Optional[Dict[str, Any]]:
    """El contexto de organización de un usuario. Esto es lo que main.py necesita
    para saber a qué org pertenece cada registro que crea.

    Devuelve {org_id, rol_org, permisos, activo, org_nombre, org_tipo, org_activo}
    o None si el usuario no tiene membresía (no debería pasar tras la migración).
    """
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    rows = await _sb_get("organizacion_miembros", {
        "user_id": f"eq.{user_id}",
        "activo": "eq.true",
        "select": "org_id,rol_org,permisos,activo",
        "limit": "1",
    })
    if not rows:
        return None
    m = rows[0]

    # Segunda query en vez de join embebido: PostgREST necesita tener la FK en
    # su cache de esquema para resolver organizaciones(...), y recién creada la
    # tabla a veces no la reconoce hasta un reload. Dos queries simples nunca
    # fallan por eso.
    org = {}
    if m.get("org_id"):
        orows = await _sb_get("organizaciones", {
            "id": f"eq.{m['org_id']}",
            "select": "nombre,tipo,activo,plan,asientos_max,vence_el",
            "limit": "1",
        })
        if orows:
            org = orows[0]

    return {
        "org_id": m.get("org_id"),
        "rol_org": m.get("rol_org") or "agente",
        "permisos": m.get("permisos") or {},
        "activo": bool(m.get("activo")),
        "org_nombre": org.get("nombre"),
        "org_tipo": org.get("tipo") or "personal",
        "org_activo": bool(org.get("activo", True)),
        "org_plan": org.get("plan"),
        "asientos_max": org.get("asientos_max"),
        "vence_el": org.get("vence_el"),
    }


async def get_org_id_for_user(user_id: str) -> Optional[str]:
    """Atajo: solo el org_id. Esto es lo que va en cada INSERT de main.py."""
    ctx = await get_org_context(user_id)
    return ctx["org_id"] if ctx else None


def permiso_efectivo(ctx: Dict[str, Any], clave: str) -> bool:
    """Espejo en Python de org_permiso() de Postgres. Se usa para decisiones del
    backend (ej. si un PDF lleva comisiones). NO es el candado — el candado real
    es la base de datos. Esto es conveniencia, no seguridad.
    """
    if not ctx or not ctx.get("activo"):
        return False
    if ctx.get("rol_org") in ("owner", "admin"):
        return True
    override = (ctx.get("permisos") or {}).get(clave)
    if isinstance(override, bool):
        return override
    return DEFAULTS_AGENTE.get(clave, False)


async def exigir_gestion_integraciones(request: Request) -> str:
    """Portero de EasyBroker y Facebook. Lo importa main.py.

    Estas cuentas son de la empresa, no de la persona: si un agente cualquiera
    pudiera desconectarlas, deja al equipo entero sin inventario ni anuncios.
    Pasan el dueño, los admins, y el agente a quien el dueño le haya prendido
    `gestionar_integraciones`.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")
    if not permiso_efectivo(ctx, "gestionar_integraciones"):
        raise HTTPException(
            status_code=403,
            detail="Solo el dueño de la cuenta puede conectar o desconectar EasyBroker y Facebook. "
                   "Pídele que te dé el permiso desde Equipo.")
    return user_id


async def _exigir_admin_org(request: Request) -> Dict[str, Any]:
    """Verifica que quien pide sea owner o admin de su org. Devuelve su contexto."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    if ctx["rol_org"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Solo el administrador de la cuenta puede hacer esto.")
    ctx["user_id"] = user_id
    return ctx


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/org")
async def mi_organizacion(request: Request):
    """Contexto de la org del usuario + sus permisos ya resueltos.
    El frontend lo usa para pintar la UI (esconder columnas, etc). Recuerda:
    esconder en la UI es cosmético; el candado de verdad está en Postgres.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        return {"tiene_org": False}

    return {
        "tiene_org": True,
        "org_id": ctx["org_id"],
        "nombre": ctx["org_nombre"],
        "tipo": ctx["org_tipo"],
        "plan": ctx["org_plan"],
        "es_empresa": ctx["org_tipo"] == "empresa",
        "rol_org": ctx["rol_org"],
        "es_admin": ctx["rol_org"] in ("owner", "admin"),
        "permisos": {k: permiso_efectivo(ctx, k) for k in PERMISOS_VALIDOS},
    }


@router.get("/org/miembros")
async def listar_miembros(request: Request):
    """Lista del equipo. Cualquier miembro puede ver quiénes son sus compañeros;
    solo el admin ve el detalle de permisos de cada quien.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(user_id)
    if not ctx:
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")

    es_admin = ctx["rol_org"] in ("owner", "admin")

    miembros = await _sb_get("organizacion_miembros", {
        "org_id": f"eq.{ctx['org_id']}",
        "select": "id,user_id,rol_org,permisos,activo,created_at",
        "order": "created_at.asc",
    })
    if not miembros:
        return {"miembros": [], "es_admin": es_admin}

    ids = ",".join(m["user_id"] for m in miembros)
    perfiles = await _sb_get("usuarios", {
        "id": f"in.({ids})",
        "select": "id,nombre,email,telefono",
    })
    by_id = {p["id"]: p for p in perfiles}

    out = []
    for m in miembros:
        p = by_id.get(m["user_id"], {})
        fila = {
            "id": m["id"],
            "user_id": m["user_id"],
            "nombre": p.get("nombre") or "",
            "email": p.get("email") or "",
            "rol_org": m["rol_org"],
            "activo": m["activo"],
            "soy_yo": m["user_id"] == user_id,
        }
        if es_admin:
            ctx_m = {"rol_org": m["rol_org"], "permisos": m.get("permisos") or {}, "activo": m["activo"]}
            fila["permisos"] = {k: permiso_efectivo(ctx_m, k) for k in PERMISOS_VALIDOS}
        out.append(fila)

    return {"miembros": out, "es_admin": es_admin, "asientos_max": ctx.get("asientos_max")}


@router.get("/auth/correo-existe")
async def correo_existe(email: str = ""):
    """Público. Lo usa la pantalla de registro para avisar en el momento si el
    correo ya tiene cuenta, en lugar del mensaje ambiguo de "revisa tu correo".
    Solo responde sí/no — no expone ningún dato de la cuenta.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"existe": False}
    filas = await _sb_get("usuarios", {"email": f"eq.{email}", "select": "id", "limit": "1"})
    return {"existe": bool(filas)}


class InvitarReq(BaseModel):
    email: str
    rol_org: str = "agente"
    permisos: Optional[Dict[str, bool]] = None
    traer_datos: bool = False


@router.post("/org/invitar")
async def invitar(req: InvitarReq, request: Request):
    """Crea una invitación y devuelve el link para compartirlo.
    No manda correo todavía — el admin copia el link y lo pasa por donde quiera.
    """
    ctx = await _exigir_admin_org(request)

    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Correo inválido.")

    if req.rol_org not in ("admin", "agente"):
        raise HTTPException(status_code=400, detail="El rol debe ser admin o agente.")

    # Solo las cuentas de empresa tienen equipo.
    if ctx["org_tipo"] != "empresa":
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta es individual. Contáctanos para cambiar a Broquer para empresas.")

    # Límite de asientos contratados.
    if ctx.get("asientos_max"):
        actuales = await _sb_get("organizacion_miembros", {
            "org_id": f"eq.{ctx['org_id']}", "activo": "eq.true", "select": "id",
        })
        pendientes = await _sb_get("organizacion_invitaciones", {
            "org_id": f"eq.{ctx['org_id']}", "aceptada_el": "is.null", "select": "id",
        })
        if len(actuales) + len(pendientes) >= int(ctx["asientos_max"]):
            raise HTTPException(
                status_code=400,
                detail=f"Ya usaste tus {ctx['asientos_max']} lugares. Contáctanos para ampliar.")

    # ¿Ya es miembro de alguna cuenta? Un usuario pertenece a UNA sola.
    # Con cuenta individual (org personal propia) SÍ se puede invitar: al
    # aceptar, su membresía se mueve a esta empresa sin recrear nada.
    # Solo se bloquea si ya pertenece a OTRA empresa.
    ya = await _sb_get("usuarios", {"email": f"eq.{email}", "select": "id", "limit": "1"})
    if ya:
        m = await _sb_get("organizacion_miembros", {"user_id": f"eq.{ya[0]['id']}", "select": "org_id", "limit": "1"})
        if m and m[0]["org_id"] == ctx["org_id"]:
            raise HTTPException(status_code=400, detail="Esa persona ya está en tu equipo.")
        if m and m[0].get("org_id"):
            su_org = await _sb_get("organizaciones", {
                "id": f"eq.{m[0]['org_id']}", "select": "tipo,owner_id", "limit": "1",
            })
            if su_org and su_org[0].get("tipo") == "empresa":
                raise HTTPException(
                    status_code=400,
                    detail="Ese correo ya pertenece a otra empresa en Broquer. Debe salir de esa organización primero.")

    permisos = {}
    for k, v in (req.permisos or {}).items():
        if k in PERMISOS_VALIDOS and isinstance(v, bool):
            permisos[k] = v

    # Reemplaza cualquier invitación pendiente al mismo correo.
    await _sb_delete("organizacion_invitaciones", {
        "org_id": f"eq.{ctx['org_id']}", "email": f"eq.{email}", "aceptada_el": "is.null",
    })

    token = secrets.token_urlsafe(24)
    filas = await _sb_post("organizacion_invitaciones", {
        "org_id": ctx["org_id"],
        "email": email,
        "rol_org": req.rol_org,
        "permisos": permisos,
        "traer_datos": bool(req.traer_datos),
        "token": token,
        "invitado_por": ctx["user_id"],
        "expira_el": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
    })

    inv = (filas or [{}])[0]
    return {
        "ok": True,
        "email": email,
        "link": f"{APP_URL}/unirse.html?inv={token}",
        "expira_el": inv.get("expira_el"),
    }


@router.get("/org/invitaciones")
async def listar_invitaciones(request: Request):
    ctx = await _exigir_admin_org(request)
    filas = await _sb_get("organizacion_invitaciones", {
        "org_id": f"eq.{ctx['org_id']}",
        "aceptada_el": "is.null",
        "select": "id,email,rol_org,token,expira_el,created_at",
        "order": "created_at.desc",
    })
    ahora = datetime.now(timezone.utc)
    out = []
    for f in filas:
        try:
            vencida = datetime.fromisoformat(f["expira_el"].replace("Z", "+00:00")) < ahora
        except Exception:
            vencida = False
        out.append({
            "id": f["id"],
            "email": f["email"],
            "rol_org": f["rol_org"],
            "link": f"{APP_URL}/unirse.html?inv={f['token']}",
            "expira_el": f["expira_el"],
            "vencida": vencida,
        })
    return {"invitaciones": out}


@router.delete("/org/invitacion/{inv_id}")
async def cancelar_invitacion(inv_id: str, request: Request):
    ctx = await _exigir_admin_org(request)
    await _sb_delete("organizacion_invitaciones", {
        "id": f"eq.{inv_id}", "org_id": f"eq.{ctx['org_id']}", "aceptada_el": "is.null",
    })
    return {"ok": True}


class AceptarReq(BaseModel):
    token: str


@router.get("/org/invitacion/{token}")
async def ver_invitacion(token: str):
    """Público: registro.html lo llama para mostrar 'Te invitó Inmobiliaria X'
    antes de que la persona se registre. No expone nada sensible.
    """
    filas = await _sb_get("organizacion_invitaciones", {
        "token": f"eq.{token}",
        "aceptada_el": "is.null",
        "select": "org_id,email,rol_org,traer_datos,expira_el",
        "limit": "1",
    })
    if not filas:
        return {"valida": False}
    f = filas[0]
    try:
        if datetime.fromisoformat(f["expira_el"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
            return {"valida": False, "razon": "vencida"}
    except Exception:
        pass

    empresa = None
    if f.get("org_id"):
        orows = await _sb_get("organizaciones", {"id": f"eq.{f['org_id']}", "select": "nombre", "limit": "1"})
        if orows:
            empresa = orows[0].get("nombre")

    return {
        "valida": True,
        "email": f["email"],
        "empresa": empresa,
        "rol_org": f["rol_org"],
        "traer_datos": bool(f.get("traer_datos")),
    }


@router.post("/org/aceptar-invitacion")
async def aceptar_invitacion(req: AceptarReq, request: Request):
    """Lo llama registro.html justo después de crear la cuenta en Supabase Auth.

    OJO: el usuario recién registrado ya tiene su org personal (la crea el mismo
    flujo de registro). Al aceptar, lo movemos a la org de la empresa y su org
    personal queda vacía y huérfana — se borra aquí mismo.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Inicia sesión.")

    filas = await _sb_get("organizacion_invitaciones", {
        "token": f"eq.{req.token}", "aceptada_el": "is.null",
        "select": "id,org_id,email,rol_org,permisos,traer_datos,expira_el", "limit": "1",
    })
    if not filas:
        raise HTTPException(status_code=400, detail="Esa invitación ya no es válida.")
    inv = filas[0]

    try:
        if datetime.fromisoformat(inv["expira_el"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="La invitación venció. Pide una nueva.")
    except HTTPException:
        raise
    except Exception:
        pass

    # El correo debe coincidir: si no, cualquiera con el link entra al equipo.
    perfil = await _sb_get("usuarios", {"id": f"eq.{user_id}", "select": "email", "limit": "1"})
    if not perfil or (perfil[0].get("email") or "").strip().lower() != inv["email"].strip().lower():
        raise HTTPException(status_code=403, detail="Esta invitación es para otro correo.")

    # Su org actual (si tiene). Solo se puede mover una org PERSONAL propia;
    # si es dueño de otra empresa o miembro de otra empresa, no puede unirse.
    actual = await _sb_get("organizacion_miembros", {
        "user_id": f"eq.{user_id}", "select": "id,org_id,rol_org", "limit": "1",
    })
    org_previa = None
    if actual:
        if actual[0].get("org_id") == inv["org_id"]:
            raise HTTPException(status_code=400, detail="Ya eres parte de este equipo.")
        prev = await _sb_get("organizaciones", {
            "id": f"eq.{actual[0]['org_id']}", "select": "id,tipo,owner_id", "limit": "1",
        })
        if prev and prev[0]["tipo"] == "empresa":
            if prev[0].get("owner_id") == user_id:
                raise HTTPException(
                    status_code=400,
                    detail="Tu cuenta es dueña de una empresa. No puede unirse a otra.")
            raise HTTPException(
                status_code=400,
                detail="Ya perteneces a otra empresa. Debes salir de esa organización primero.")
        if prev and prev[0]["tipo"] == "personal" and prev[0]["owner_id"] == user_id:
            org_previa = prev[0]["id"]

        await _sb_patch("organizacion_miembros", {"id": f"eq.{actual[0]['id']}"}, {
            "org_id": inv["org_id"],
            "rol_org": inv["rol_org"],
            "permisos": inv.get("permisos") or {},
            "activo": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        await _sb_post("organizacion_miembros", {
            "org_id": inv["org_id"],
            "user_id": user_id,
            "rol_org": inv["rol_org"],
            "permisos": inv.get("permisos") or {},
        }, prefer="return=minimal")

    await _sb_patch("organizacion_invitaciones", {"id": f"eq.{inv['id']}"}, {
        "aceptada_el": datetime.now(timezone.utc).isoformat(),
    })

    # ── Sus datos ──
    # Si el dueño de la empresa marcó "traer datos", el inventario y los
    # contactos del invitado se mueven a la empresa. Si no, se quedan en su
    # org personal, que se CONSERVA (en pausa) por si algún día sale del
    # equipo — nada se borra.
    trae = bool(inv.get("traer_datos"))
    if org_previa and trae:
        await _sb_patch("propiedades", {"org_id": f"eq.{org_previa}"},
                        {"org_id": inv["org_id"]})
        await _sb_patch("contactos", {"org_id": f"eq.{org_previa}"},
                        {"org_id": inv["org_id"]})

    # La org personal solo se borra cuando quedó realmente vacía.
    if org_previa:
        restos = await _sb_get("propiedades", {"org_id": f"eq.{org_previa}", "select": "id", "limit": "1"})
        contactos = await _sb_get("contactos", {"org_id": f"eq.{org_previa}", "select": "id", "limit": "1"})
        if not restos and not contactos:
            await _sb_delete("organizaciones", {"id": f"eq.{org_previa}"})

    return {"ok": True, "org_id": inv["org_id"], "traer_datos": trae}


class RolReq(BaseModel):
    user_id: str
    rol_org: str


@router.post("/org/miembro/rol")
async def cambiar_rol(req: RolReq, request: Request):
    ctx = await _exigir_admin_org(request)

    if req.rol_org not in ("admin", "agente"):
        raise HTTPException(status_code=400, detail="El rol debe ser admin o agente.")

    objetivo = await _sb_get("organizacion_miembros", {
        "user_id": f"eq.{req.user_id}", "org_id": f"eq.{ctx['org_id']}",
        "select": "id,rol_org", "limit": "1",
    })
    if not objetivo:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")

    if objetivo[0]["rol_org"] == "owner":
        raise HTTPException(status_code=400, detail="No se puede cambiar el rol del dueño de la cuenta.")
    if req.user_id == ctx["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol.")

    await _sb_patch("organizacion_miembros", {"id": f"eq.{objetivo[0]['id']}"}, {
        "rol_org": req.rol_org,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True}


class PermisosReq(BaseModel):
    user_id: str
    permisos: Dict[str, bool]


@router.post("/org/miembro/permisos")
async def cambiar_permisos(req: PermisosReq, request: Request):
    """Aquí es donde el admin decide quién ve los teléfonos de los propietarios."""
    ctx = await _exigir_admin_org(request)

    limpios = {}
    for k, v in (req.permisos or {}).items():
        if k not in PERMISOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Permiso desconocido: {k}")
        if not isinstance(v, bool):
            raise HTTPException(status_code=400, detail=f"El permiso {k} debe ser verdadero o falso.")
        limpios[k] = v

    objetivo = await _sb_get("organizacion_miembros", {
        "user_id": f"eq.{req.user_id}", "org_id": f"eq.{ctx['org_id']}",
        "select": "id,rol_org", "limit": "1",
    })
    if not objetivo:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")

    if req.user_id == ctx["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes cambiarte tus propios permisos.")
    if objetivo[0]["rol_org"] in ("owner", "admin"):
        raise HTTPException(
            status_code=400,
            detail="Los administradores ven todo por definición. Bájalo a agente si quieres limitarlo.")

    await _sb_patch("organizacion_miembros", {"id": f"eq.{objetivo[0]['id']}"}, {
        "permisos": limpios,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "permisos": limpios}


class ActivoReq(BaseModel):
    user_id: str
    activo: bool


@router.post("/org/miembro/activo")
async def cambiar_activo(req: ActivoReq, request: Request):
    """Dar de baja a alguien sin borrar su historial. Al quedar inactivo,
    mi_org() le devuelve null y deja de ver TODO al instante.
    """
    ctx = await _exigir_admin_org(request)

    objetivo = await _sb_get("organizacion_miembros", {
        "user_id": f"eq.{req.user_id}", "org_id": f"eq.{ctx['org_id']}",
        "select": "id,rol_org", "limit": "1",
    })
    if not objetivo:
        raise HTTPException(status_code=404, detail="Esa persona no está en tu equipo.")
    if objetivo[0]["rol_org"] == "owner":
        raise HTTPException(status_code=400, detail="No se puede dar de baja al dueño de la cuenta.")
    if req.user_id == ctx["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes darte de baja a ti mismo.")

    await _sb_patch("organizacion_miembros", {"id": f"eq.{objetivo[0]['id']}"}, {
        "activo": bool(req.activo),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "activo": bool(req.activo)}


class NombreReq(BaseModel):
    nombre: str


@router.post("/org/nombre")
async def cambiar_nombre(req: NombreReq, request: Request):
    ctx = await _exigir_admin_org(request)
    nombre = (req.nombre or "").strip()
    if len(nombre) < 2:
        raise HTTPException(status_code=400, detail="El nombre es muy corto.")
    await _sb_patch("organizaciones", {"id": f"eq.{ctx['org_id']}"}, {
        "nombre": nombre[:120],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "nombre": nombre[:120]}


# ══════════════════════════════════════════════════════════════════════════
# ADMIN DE BROQUER (staff interno) — convertir una cuenta en empresa
# Como el precio se negocia por cliente, no hay checkout: tú activas la empresa
# a mano desde admin.html. Exige usuarios.rol = 'admin' (staff de Broquer),
# que NO es lo mismo que rol_org = 'admin' (admin de una empresa cliente).
# ══════════════════════════════════════════════════════════════════════════

async def _exigir_staff_broquer(request: Request) -> str:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    filas = await _sb_get("usuarios", {"id": f"eq.{user_id}", "select": "rol", "limit": "1"})
    if not filas or filas[0].get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores de Broquer.")
    return user_id


class ConvertirReq(BaseModel):
    user_id: str
    nombre: str
    asientos_max: Optional[int] = None
    plan: Optional[str] = "Empresas"
    dias: Optional[int] = None


@router.post("/admin/org/convertir")
async def convertir_a_empresa(req: ConvertirReq, request: Request):
    """Convierte la cuenta de alguien en una empresa. Su org personal se vuelve
    de tipo 'empresa' y ya puede invitar a su equipo.
    """
    await _exigir_staff_broquer(request)

    ctx = await get_org_context(req.user_id)
    if not ctx:
        # Sin membresía activa. Pasa cuando alguien estuvo en un equipo y fue
        # dado de baja (su org personal se borró al unirse), o cuando su cuenta
        # es previa a la migración de organizaciones. Aquí se le aprovisiona
        # su org sobre la marcha en vez de tronar.
        perfil = await _sb_get("usuarios", {"id": f"eq.{req.user_id}", "select": "id", "limit": "1"})
        if not perfil:
            raise HTTPException(status_code=404, detail="Ese usuario no existe en Broquer.")

        ahora = datetime.now(timezone.utc).isoformat()
        memb = await _sb_get("organizacion_miembros", {
            "user_id": f"eq.{req.user_id}", "select": "id,org_id", "limit": "1",
        })

        org_id = None
        if memb and memb[0].get("org_id"):
            # ¿Su membresía (inactiva) apunta a una org que es suya? Reactívala.
            orows = await _sb_get("organizaciones", {
                "id": f"eq.{memb[0]['org_id']}", "select": "id,owner_id", "limit": "1",
            })
            if orows and orows[0].get("owner_id") == req.user_id:
                org_id = orows[0]["id"]

        if not org_id:
            # Org nueva para él. Si su membresía vieja apunta a la empresa de
            # otro, NO se toca esa empresa: se le crea la suya propia.
            creada = await _sb_post("organizaciones", {
                "nombre": (req.nombre or "").strip()[:120] or "Mi inmobiliaria",
                "tipo": "empresa",
                "owner_id": req.user_id,
                "activo": True,
            })
            if not creada:
                raise HTTPException(status_code=500, detail="No se pudo crear la organización.")
            org_id = creada[0]["id"]

        if memb:
            await _sb_patch("organizacion_miembros", {"id": f"eq.{memb[0]['id']}"}, {
                "org_id": org_id, "rol_org": "owner", "activo": True, "updated_at": ahora,
            })
        else:
            await _sb_post("organizacion_miembros", {
                "org_id": org_id, "user_id": req.user_id, "rol_org": "owner",
            }, prefer="return=minimal")

        ctx = {"org_id": org_id, "org_nombre": (req.nombre or "").strip()[:120] or None}

    payload = {
        "tipo": "empresa",
        "nombre": (req.nombre or "").strip()[:120] or ctx["org_nombre"],
        "plan": req.plan or "Empresas",
        "activo": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if req.asientos_max is not None:
        payload["asientos_max"] = int(req.asientos_max)
    if req.dias:
        payload["vence_el"] = (datetime.now(timezone.utc) + timedelta(days=int(req.dias))).isoformat()

    await _sb_patch("organizaciones", {"id": f"eq.{ctx['org_id']}"}, payload)

    # El titular debe ser owner para poder invitar.
    await _sb_patch("organizacion_miembros", {"user_id": f"eq.{req.user_id}"}, {"rol_org": "owner"})

    return {"ok": True, "org_id": ctx["org_id"], "nombre": payload["nombre"]}


class DesconvertirReq(BaseModel):
    user_id: str


@router.post("/admin/org/desconvertir")
async def quitar_estatus_empresa(req: DesconvertirReq, request: Request):
    """Regresa la empresa de alguien a cuenta individual. El dueño conserva
    TODO lo que vive en la org (inventario, contactos); los demás miembros
    quedan dados de baja y pierden acceso al instante — igual que una baja
    normal del equipo. Las invitaciones pendientes se cancelan.
    """
    await _exigir_staff_broquer(request)

    ctx = await get_org_context(req.user_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Ese usuario no tiene cuenta.")
    if (ctx.get("org_tipo") or "personal") != "empresa":
        raise HTTPException(status_code=400, detail="Esa cuenta ya es individual.")

    org = await _sb_get("organizaciones", {
        "id": f"eq.{ctx['org_id']}", "select": "id,owner_id", "limit": "1",
    })
    if not org or org[0].get("owner_id") != req.user_id:
        raise HTTPException(status_code=400, detail="Ese usuario no es el dueño de la empresa.")

    ahora = datetime.now(timezone.utc).isoformat()

    # Baja de todos los miembros menos el dueño.
    miembros = await _sb_get("organizacion_miembros", {
        "org_id": f"eq.{ctx['org_id']}", "activo": "eq.true", "select": "id,user_id",
    })
    dados_de_baja = 0
    for m in miembros:
        if m.get("user_id") == req.user_id:
            continue
        await _sb_patch("organizacion_miembros", {"id": f"eq.{m['id']}"}, {
            "activo": False, "updated_at": ahora,
        })
        dados_de_baja += 1

    # Invitaciones pendientes fuera.
    await _sb_delete("organizacion_invitaciones", {
        "org_id": f"eq.{ctx['org_id']}", "aceptada_el": "is.null",
    })

    # La org regresa a personal. El plan y los asientos se limpian.
    await _sb_patch("organizaciones", {"id": f"eq.{ctx['org_id']}"}, {
        "tipo": "personal",
        "plan": None,
        "asientos_max": None,
        "vence_el": None,
        "updated_at": ahora,
    })

    return {"ok": True, "org_id": ctx["org_id"], "miembros_dados_de_baja": dados_de_baja}


@router.get("/admin/org/lista")
async def listar_organizaciones(request: Request):
    """Todas las empresas, con su conteo de miembros. Para admin.html."""
    await _exigir_staff_broquer(request)

    orgs = await _sb_get("organizaciones", {
        "tipo": "eq.empresa",
        "select": "id,nombre,owner_id,plan,asientos_max,activo,vence_el,created_at",
        "order": "created_at.desc",
    })
    if not orgs:
        return {"organizaciones": []}

    ids = ",".join(o["id"] for o in orgs)
    miembros = await _sb_get("organizacion_miembros", {"org_id": f"in.({ids})", "select": "org_id,activo"})

    conteo = {}
    for m in miembros:
        if m.get("activo"):
            conteo[m["org_id"]] = conteo.get(m["org_id"], 0) + 1

    for o in orgs:
        o["miembros"] = conteo.get(o["id"], 0)

    return {"organizaciones": orgs}


# ═══════════════════════════════════════════════════════════════════════════
# ASIGNACIÓN DE AGENTE RESPONSABLE (Broquer para Empresas)
# Solo owner/admin pueden asignar o reasignar. La columna asignado_a es una
# etiqueta de responsabilidad: no cambia el dueño (user_id) ni la visibilidad.
# ═══════════════════════════════════════════════════════════════════════════

_TABLAS_ASIGNABLES = ("contactos", "propiedades")


class AsignarReq(BaseModel):
    tabla: str
    ids: List[str]
    agente_user_id: Optional[str] = None  # None = quitar asignación


@router.post("/org/asignar")
async def asignar_agente(req: AsignarReq, request: Request):
    """Asigna (o desasigna con agente_user_id=null) registros a un agente."""
    ctx = await _exigir_admin_org(request)

    if req.tabla not in _TABLAS_ASIGNABLES:
        raise HTTPException(status_code=400, detail="Tabla no válida.")
    ids = [str(i).strip() for i in (req.ids or []) if str(i).strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No hay registros que asignar.")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="Máximo 500 registros por operación.")

    # El agente destino debe ser miembro ACTIVO de la misma empresa
    if req.agente_user_id:
        m = await _sb_get("organizacion_miembros", {
            "org_id": f"eq.{ctx['org_id']}",
            "user_id": f"eq.{req.agente_user_id}",
            "activo": "eq.true",
            "select": "user_id", "limit": "1",
        })
        if not m:
            raise HTTPException(status_code=400, detail="Ese agente no pertenece a tu empresa o está desactivado.")

    # PATCH acotado SIEMPRE a la org del admin: imposible tocar filas ajenas
    lista = ",".join(f'"{i}"' for i in ids)
    await _sb_patch(req.tabla, {
        "id": f"in.({lista})",
        "org_id": f"eq.{ctx['org_id']}",
    }, {
        "asignado_a": req.agente_user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "asignados": len(ids)}
