# ──────────────────────────────────────────────────────────────────────────
# routers/sitios.py · Sitio web del agente o de la inmobiliaria
# ──────────────────────────────────────────────────────────────────────────
# Configuración (autenticada):
#   GET/PUT /sitios/...            sitio de la organización (sólo admin) o
#                                  del agente; código HEAD/BODY sólo admin.
#   páginas personalizadas         contenido limpio (core/html_limpio.py).
#   dominio propio                 Cloudflare for SaaS (custom hostnames).
# Público (sin sesión), HTML con título, descripción y Open Graph:
#   /s/{slug}[/venta|/renta|/rentas-temporales|/buscar|/inmueble/{id}|
#   /acerca|/contacto|/p/{pagina}|/sitemap.xml|/robots.txt]
#   /p/{propiedad}?a={agente}      ficha pública para compartir (alertas).
# Con dominio propio, el middleware traduce el Host al slug del sitio.
#
# Depende de: migracion-fase7-sitios.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel

from core import sitio_render as R
from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.html_limpio import limpiar_html
from routers.organizaciones import get_org_context

router = APIRouter(tags=["sitios"])
log = logging.getLogger("broquer.sitios")
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])?$")
_DOMINIO = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
RESERVADOS = {"api", "www", "app", "admin", "broquer", "sitios", "static", "s", "p"}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def base_publica(s: dict) -> str:
    """Dirección del sitio: dominio propio activo o la de prueba."""
    if s.get("dominio") and s.get("dominio_estado") == "activo":
        return "https://" + s["dominio"]
    return f"{settings.api_base_url}/s/{s['slug']}"


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════
async def _ctx(request: Request) -> Dict[str, Any]:
    uid = await get_user_id_from_token(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    ctx = await get_org_context(uid)
    if not ctx or not ctx.get("activo") or not ctx.get("org_id"):
        raise HTTPException(status_code=403, detail="No perteneces a ninguna cuenta.")
    ctx["user_id"] = uid
    ctx["es_admin"] = ctx.get("rol_org") in ("owner", "admin")
    return ctx


async def _mi_sitio(ctx: dict, tipo: str) -> Optional[dict]:
    p = {"org_id": f"eq.{ctx['org_id']}", "tipo": f"eq.{tipo}", "select": "*", "limit": "1"}
    if tipo == "agente":
        p["user_id"] = f"eq.{ctx['user_id']}"
    filas = await get_rows("sitios", p)
    return filas[0] if filas else None


async def _sitio_editable(ctx: dict, sitio_id: str) -> dict:
    filas = await get_rows("sitios", {"id": f"eq.{sitio_id}", "org_id": f"eq.{ctx['org_id']}", "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Sitio no encontrado.")
    s = filas[0]
    if s["tipo"] == "organizacion" and not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo el administrador edita el sitio de la inmobiliaria.")
    if s["tipo"] == "agente" and s.get("user_id") != ctx["user_id"] and not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Este sitio es de otro agente.")
    return s


@router.get("/sitios/mios")
async def mis_sitios(request: Request):
    ctx = await _ctx(request)
    try:
        org, agente = await _mi_sitio(ctx, "organizacion"), await _mi_sitio(ctx, "agente")
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=503, detail="Falta correr migracion-fase7-sitios.sql en Supabase.")
    for s in (org, agente):
        if s:
            s["url_publica"] = base_publica(s)
            s["url_prueba"] = f"{settings.api_base_url}/s/{s['slug']}"
    return {"organizacion": org, "agente": agente, "es_admin": ctx["es_admin"],
            "cname_destino": settings.sitios_cname_destino, "dominios_disponibles": bool(settings.cloudflare_api_token and settings.cloudflare_zone_id)}


class SitioIn(BaseModel):
    slug: str
    activo: bool = False
    nombre: Optional[str] = None
    eslogan: Optional[str] = None
    plantilla: str = "clasica"
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    hero_url: Optional[str] = None
    color_primario: str = "#0b2545"
    color_secundario: str = "#13a89e"
    whatsapp: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    redes: Dict[str, str] = {}
    ga4_id: Optional[str] = None
    meta_pixel_id: Optional[str] = None
    codigo_head: Optional[str] = None
    codigo_body: Optional[str] = None
    mostrar_asesor: bool = True
    incluir_bolsa: bool = False
    traductor: bool = False
    acerca_html: Optional[str] = None
    seo_titulo: Optional[str] = None
    seo_descripcion: Optional[str] = None


def _https(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return v if v.startswith("https://") and len(v) < 1000 else None


@router.put("/sitios/{tipo}")
async def guardar_sitio(tipo: str, body: SitioIn, request: Request):
    ctx = await _ctx(request)
    if tipo not in ("organizacion", "agente"):
        raise HTTPException(status_code=400, detail="Tipo de sitio inválido.")
    if tipo == "organizacion" and not ctx["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo el administrador configura el sitio de la inmobiliaria.")
    slug = body.slug.strip().lower()
    if not _SLUG.match(slug) or slug in RESERVADOS:
        raise HTTPException(status_code=400, detail="El link sólo puede tener minúsculas, números y guiones (3 a 50).")
    actual = await _mi_sitio(ctx, tipo)
    choque = await get_rows("sitios", {"slug": f"ilike.{slug}", "select": "id", "limit": "1"})
    if choque and (not actual or choque[0]["id"] != actual["id"]):
        raise HTTPException(status_code=409, detail="Ese link ya lo usa otro sitio.")
    fila = {
        "org_id": ctx["org_id"], "tipo": tipo, "user_id": ctx["user_id"] if tipo == "agente" else None,
        "slug": slug, "activo": body.activo, "nombre": (body.nombre or "").strip()[:120] or None,
        "eslogan": (body.eslogan or "").strip()[:200] or None,
        "plantilla": body.plantilla if body.plantilla in ("clasica", "moderna") else "clasica",
        "logo_url": _https(body.logo_url), "favicon_url": _https(body.favicon_url), "hero_url": _https(body.hero_url),
        "color_primario": R.color(body.color_primario, "#0b2545"), "color_secundario": R.color(body.color_secundario, "#13a89e"),
        "whatsapp": re.sub(r"[^\d+]", "", body.whatsapp or "")[:20] or None, "telefono": (body.telefono or "").strip()[:30] or None,
        "email": (body.email or "").strip()[:160] or None, "direccion": (body.direccion or "").strip()[:300] or None,
        "redes": {k: v for k, v in (body.redes or {}).items() if k in ("facebook", "instagram", "tiktok", "youtube", "linkedin", "x") and _https(v)},
        "ga4_id": re.sub(r"[^A-Za-z0-9-]", "", body.ga4_id or "")[:30] or None,
        "meta_pixel_id": re.sub(r"\D", "", body.meta_pixel_id or "")[:30] or None,
        "mostrar_asesor": body.mostrar_asesor, "incluir_bolsa": body.incluir_bolsa, "traductor": body.traductor,
        "acerca_html": limpiar_html(body.acerca_html or "") or None,
        "seo_titulo": (body.seo_titulo or "").strip()[:120] or None, "seo_descripcion": (body.seo_descripcion or "").strip()[:300] or None,
        "updated_at": _ahora(),
    }
    # Código propio en HEAD/BODY: sólo administradores (es código que corre
    # en el sitio público tal cual).
    if ctx["es_admin"]:
        fila["codigo_head"] = (body.codigo_head or "")[:20000] or None
        fila["codigo_body"] = (body.codigo_body or "")[:20000] or None
    if actual:
        res = await patch_rows("sitios", {"id": f"eq.{actual['id']}"}, fila, prefer="return=representation")
    else:
        res = await post_rows("sitios", fila)
    s = res[0]
    s["url_publica"] = base_publica(s)
    return s


class PaginaIn(BaseModel):
    titulo: str
    slug: str
    contenido_html: str = ""
    meta_titulo: Optional[str] = None
    meta_descripcion: Optional[str] = None
    publicada: bool = False
    en_menu: bool = False
    orden: int = 0


@router.get("/sitios/{sitio_id}/paginas")
async def paginas(sitio_id: str, request: Request):
    ctx = await _ctx(request)
    await _sitio_editable(ctx, sitio_id)
    return {"paginas": await get_rows("sitio_paginas", {"sitio_id": f"eq.{sitio_id}", "select": "*", "order": "orden.asc,titulo.asc"})}


def _pagina_fila(body: PaginaIn) -> dict:
    slug = re.sub(r"[^a-z0-9-]+", "-", body.slug.strip().lower()).strip("-")[:60]
    if not body.titulo.strip() or not slug:
        raise HTTPException(status_code=400, detail="Escribe título y link de la página.")
    return {"titulo": body.titulo.strip()[:120], "slug": slug, "contenido_html": limpiar_html(body.contenido_html),
            "meta_titulo": (body.meta_titulo or "").strip()[:120] or None,
            "meta_descripcion": (body.meta_descripcion or "").strip()[:300] or None,
            "publicada": body.publicada, "en_menu": body.en_menu, "orden": body.orden, "updated_at": _ahora()}


@router.post("/sitios/{sitio_id}/paginas")
async def crear_pagina(sitio_id: str, body: PaginaIn, request: Request):
    ctx = await _ctx(request)
    await _sitio_editable(ctx, sitio_id)
    try:
        return (await post_rows("sitio_paginas", {**_pagina_fila(body), "sitio_id": sitio_id}))[0]
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=409, detail="Ya hay una página con ese link.")


@router.patch("/sitios/{sitio_id}/paginas/{pagina_id}")
async def editar_pagina(sitio_id: str, pagina_id: str, body: PaginaIn, request: Request):
    ctx = await _ctx(request)
    await _sitio_editable(ctx, sitio_id)
    res = await patch_rows("sitio_paginas", {"id": f"eq.{pagina_id}", "sitio_id": f"eq.{sitio_id}"}, _pagina_fila(body), prefer="return=representation")
    if not res:
        raise HTTPException(status_code=404, detail="Página no encontrada.")
    return res[0]


@router.delete("/sitios/{sitio_id}/paginas/{pagina_id}")
async def borrar_pagina(sitio_id: str, pagina_id: str, request: Request):
    ctx = await _ctx(request)
    await _sitio_editable(ctx, sitio_id)
    await delete_rows("sitio_paginas", {"id": f"eq.{pagina_id}", "sitio_id": f"eq.{sitio_id}"})
    return {"ok": True}


# ── Dominio propio (Cloudflare for SaaS) ────────────────────────────────────
def _cf_headers() -> dict:
    return {"Authorization": f"Bearer {settings.cloudflare_api_token}", "Content-Type": "application/json"}


def instrucciones_dns(dominio: str) -> List[dict]:
    raiz = dominio.count(".") == 1
    destino = settings.sitios_cname_destino
    if raiz:
        return [{"tipo": "CNAME (o ALIAS/ANAME)", "nombre": "@", "valor": destino,
                 "nota": "Si tu proveedor no permite CNAME en la raíz, usa ALIAS/ANAME o pon el sitio en www y redirige la raíz a www."},
                {"tipo": "CNAME", "nombre": "www", "valor": destino, "nota": "Recomendado además de la raíz."}]
    sub = dominio.split(".")[0]
    return [{"tipo": "CNAME", "nombre": sub, "valor": destino, "nota": ""}]


class DominioIn(BaseModel):
    dominio: str


@router.post("/sitios/{sitio_id}/dominio")
async def conectar_dominio(sitio_id: str, body: DominioIn, request: Request):
    ctx = await _ctx(request)
    s = await _sitio_editable(ctx, sitio_id)
    dominio = body.dominio.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    if not _DOMINIO.match(dominio) or dominio.endswith("broquer.app"):
        raise HTTPException(status_code=400, detail="Escribe un dominio válido, por ejemplo www.miinmobiliaria.mx")
    otro = await get_rows("sitios", {"dominio": f"ilike.{dominio}", "select": "id", "limit": "1"})
    if otro and otro[0]["id"] != s["id"]:
        raise HTTPException(status_code=409, detail="Ese dominio ya está conectado a otro sitio.")
    cambios = {"dominio": dominio, "dominio_estado": "pendiente", "dominio_detalle": None, "updated_at": _ahora()}
    if settings.cloudflare_api_token and settings.cloudflare_zone_id:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"https://api.cloudflare.com/client/v4/zones/{settings.cloudflare_zone_id}/custom_hostnames",
                                 headers=_cf_headers(), json={"hostname": dominio, "ssl": {"method": "http", "type": "dv"}})
            d = r.json()
            if d.get("success"):
                cambios["cf_hostname_id"] = d["result"]["id"]
            else:
                errores = "; ".join(x.get("message", "") for x in d.get("errors", []))
                cambios["dominio_detalle"] = "Cloudflare: " + errores[:300]
        except Exception as e:
            cambios["dominio_detalle"] = f"No se pudo hablar con Cloudflare: {e}"[:300]
    else:
        cambios["dominio_detalle"] = "Falta configurar Cloudflare en el servidor (ver Pendientes)."
    res = await patch_rows("sitios", {"id": f"eq.{s['id']}"}, cambios, prefer="return=representation")
    return {"sitio": res[0], "dns": instrucciones_dns(dominio)}


@router.get("/sitios/{sitio_id}/dominio/verificar")
async def verificar_dominio(sitio_id: str, request: Request):
    ctx = await _ctx(request)
    s = await _sitio_editable(ctx, sitio_id)
    if not s.get("dominio"):
        raise HTTPException(status_code=400, detail="Este sitio no tiene dominio.")
    estado, detalle = s.get("dominio_estado"), s.get("dominio_detalle")
    if s.get("cf_hostname_id") and settings.cloudflare_api_token:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"https://api.cloudflare.com/client/v4/zones/{settings.cloudflare_zone_id}/custom_hostnames/{s['cf_hostname_id']}",
                                headers=_cf_headers())
            res = (r.json() or {}).get("result") or {}
            ssl = (res.get("ssl") or {}).get("status")
            if res.get("status") == "active" and ssl == "active":
                estado, detalle = "activo", "Tu dominio ya muestra el sitio con candado (HTTPS)."
            else:
                estado = "pendiente"
                detalle = f"Cloudflare: dominio «{res.get('status')}», certificado «{ssl}». Revisa el registro DNS; puede tardar hasta 24 h."
        except Exception as e:
            detalle = f"No se pudo verificar: {e}"[:300]
    res = await patch_rows("sitios", {"id": f"eq.{s['id']}"}, {"dominio_estado": estado, "dominio_detalle": detalle, "updated_at": _ahora()},
                           prefer="return=representation")
    return {"sitio": res[0], "dns": instrucciones_dns(s["dominio"])}


@router.delete("/sitios/{sitio_id}/dominio")
async def quitar_dominio(sitio_id: str, request: Request):
    ctx = await _ctx(request)
    s = await _sitio_editable(ctx, sitio_id)
    if s.get("cf_hostname_id") and settings.cloudflare_api_token:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                await c.delete(f"https://api.cloudflare.com/client/v4/zones/{settings.cloudflare_zone_id}/custom_hostnames/{s['cf_hostname_id']}",
                               headers=_cf_headers())
        except Exception:
            pass
    await patch_rows("sitios", {"id": f"eq.{s['id']}"}, {"dominio": None, "dominio_estado": "sin_dominio", "dominio_detalle": None,
                                                        "cf_hostname_id": None, "updated_at": _ahora()})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# SITIO PÚBLICO
# ══════════════════════════════════════════════════════════════════════════
async def sitio_por_slug(slug: str) -> Optional[dict]:
    filas = await get_rows("sitios", {"slug": f"ilike.{slug}", "activo": "eq.true", "select": "*", "limit": "1"})
    return filas[0] if filas else None


async def inventario_sitio(s: dict) -> List[dict]:
    p = {"select": "*", "estatus": "eq.activa", "order": "updated_at.desc", "limit": "1000"}
    if s["tipo"] == "agente":
        p["or"] = f"(user_id.eq.{s['user_id']},asignado_a.eq.{s['user_id']})"
    else:
        p["org_id"] = f"eq.{s['org_id']}"
    props = [x for x in await get_rows("propiedades", p, timeout=20) if not x.get("archivada")]
    if s.get("incluir_bolsa"):
        try:
            bolsa = await get_rows("propiedades", {"select": "*", "en_bolsa": "eq.true", "estatus": "eq.activa", "limit": "500"}, timeout=20)
            ids = {x["id"] for x in props}
            props += [b for b in bolsa if b.get("org_id") != s["org_id"] and b["id"] not in ids and b.get("comision_compartida") is not False]
        except httpx.HTTPStatusError:
            pass
    for x in props:      # sin dirección exacta salvo que el agente la muestre
        if not x.get("mostrar_ubicacion_exacta"):
            for k in ("calle", "num_exterior", "num_interior", "lat", "lng"):
                x.pop(k, None)
        for k in ("notas", "descripcion_privada", "codigo_llave", "comision_venta_pct", "comision_renta_meses", "comision_real", "bolsa_notas"):
            x.pop(k, None)
    return props


def _tiene_temporal(props: List[dict]) -> bool:
    return any(o.get("tipo") == "renta_temporal" for p in props for o in R.operaciones(p))


def _con_operacion(props: List[dict], op: str) -> List[dict]:
    return [p for p in props if any(o.get("tipo") == op for o in R.operaciones(p))]


async def _menu(s: dict) -> List[dict]:
    try:
        return await get_rows("sitio_paginas", {"sitio_id": f"eq.{s['id']}", "publicada": "eq.true", "en_menu": "eq.true",
                                                "select": "titulo,slug", "order": "orden.asc"})
    except httpx.HTTPStatusError:
        return []


def _html(contenido: str, max_age: int = 120) -> HTMLResponse:
    return HTMLResponse(contenido, headers={"Cache-Control": f"public, max-age={max_age}"})


def _base(request: Request, s: dict) -> str:
    """Prefijo de las ligas internas: '' con dominio propio, /s/slug si no."""
    return "" if request.scope.get("sitio_por_dominio") else f"/s/{s['slug']}"


async def _render_lista(request: Request, s: dict, *, titulo: str, descripcion: str, ruta: str, props: List[dict],
                        todas: List[dict], cabecera: str = "") -> HTMLResponse:
    base = _base(request, s)
    cuerpo = cabecera + f'<div class="wrap sec"><h2>{R.e(titulo)}</h2>{R.grid(props, base)}</div>'
    foto = next((p["fotos"][0] for p in props if p.get("fotos")), s.get("hero_url") or s.get("logo_url"))
    return _html(R.layout(s, titulo=titulo + " · " + (s.get("nombre") or ""), descripcion=descripcion, cuerpo=cuerpo,
                          base=base, ruta=ruta, imagen=foto, paginas_menu=await _menu(s), tiene_temporal=_tiene_temporal(todas)))


async def _sitio_o_404(slug: str) -> dict:
    s = await sitio_por_slug(slug)
    if not s:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    s["_base_publica"] = base_publica(s)
    return s


@router.get("/s/{slug}", response_class=HTMLResponse)
async def sitio_inicio(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    base = _base(request, s)
    ciudades = sorted({p["ciudad"] for p in props if p.get("ciudad")})
    estilo = f' style="background-image:linear-gradient(135deg,rgba(0,0,0,.55),rgba(0,0,0,.35)),url({R.e(s["hero_url"])})"' if s.get("hero_url") else ""
    hero = (f'<section class="hero"{estilo}><div class="wrap"><h1>{R.e(s.get("nombre") or "Encuentra tu próximo hogar")}</h1>'
            f'<p>{R.e(s.get("eslogan") or "Casas, departamentos, terrenos y locales.")}</p>'
            f'{R.formulario_busqueda(base, {}, ciudades, compacto=True)}</div></section>')
    secciones = ""
    for op, t in (("venta", "En venta"), ("renta", "En renta"), ("renta_temporal", "Rentas temporales")):
        lista = _con_operacion(props, op)[:6]
        if lista:
            ruta = {"venta": "/venta", "renta": "/renta", "renta_temporal": "/rentas-temporales"}[op]
            secciones += (f'<div class="wrap sec"><h2>{t}</h2>{R.grid(lista, base)}'
                          f'<p style="margin-top:16px"><a class="btn btn--ghost" href="{R.e(base + ruta)}">Ver todas</a></p></div>')
    if not secciones:
        secciones = f'<div class="wrap sec">{R.grid([], base)}</div>'
    titulo = s.get("seo_titulo") or s.get("nombre") or "Inmobiliaria"
    desc = s.get("seo_descripcion") or s.get("eslogan") or f"Inmuebles de {s.get('nombre') or 'nuestra inmobiliaria'}."
    org_ld = {"@context": "https://schema.org", "@type": "RealEstateAgent", "name": s.get("nombre"), "url": base_publica(s),
              "telephone": s.get("telefono"), "email": s.get("email"), "address": s.get("direccion"), "logo": s.get("logo_url")}
    return _html(R.layout(s, titulo=titulo, descripcion=desc, cuerpo=hero + secciones, base=base, ruta="/",
                          imagen=s.get("hero_url") or s.get("logo_url") or next((p["fotos"][0] for p in props if p.get("fotos")), None),
                          paginas_menu=await _menu(s), tiene_temporal=_tiene_temporal(props),
                          json_ld={k: v for k, v in org_ld.items() if v}))


@router.get("/s/{slug}/venta", response_class=HTMLResponse)
async def sitio_venta(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    return await _render_lista(request, s, titulo="Inmuebles en venta", descripcion=f"Inmuebles en venta de {s.get('nombre') or ''}.",
                               ruta="/venta", props=_con_operacion(props, "venta") + _con_operacion(props, "preventa"), todas=props)


@router.get("/s/{slug}/renta", response_class=HTMLResponse)
async def sitio_renta(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    return await _render_lista(request, s, titulo="Inmuebles en renta", descripcion=f"Inmuebles en renta de {s.get('nombre') or ''}.",
                               ruta="/renta", props=_con_operacion(props, "renta"), todas=props)


@router.get("/s/{slug}/rentas-temporales", response_class=HTMLResponse)
async def sitio_temporales(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    return await _render_lista(request, s, titulo="Rentas temporales", descripcion="Rentas por noche, semana o mes.",
                               ruta="/rentas-temporales", props=_con_operacion(props, "renta_temporal"), todas=props)


def filtrar(props: List[dict], f: Dict[str, str]) -> List[dict]:
    from core.catalogo_inmuebles import normaliza
    from core.coincidencias import caracteristicas_de
    def num(k):
        try:
            return float(f.get(k) or 0)
        except ValueError:
            return 0
    q = normaliza(f.get("q"))
    out = []
    for p in props:
        ops = R.operaciones(p)
        if f.get("operacion") and not any(o.get("tipo") == f["operacion"] for o in ops):
            continue
        if f.get("tipo") and f["tipo"] not in (p.get("subtipo"), p.get("tipo")):
            continue
        if f.get("ciudad") and normaliza(p.get("ciudad")) != normaliza(f["ciudad"]):
            continue
        if q and q not in normaliza(" ".join(str(p.get(k) or "") for k in ("titulo", "colonia", "ciudad", "descripcion"))):
            continue
        precios = [float(o.get("precio") or 0) for o in ops if (not f.get("operacion") or o.get("tipo") == f["operacion"])]
        if num("pmin") and not any(x >= num("pmin") for x in precios):
            continue
        if num("pmax") and not any(0 < x <= num("pmax") for x in precios):
            continue
        if num("rec") and float(p.get("recamaras") or 0) < num("rec"):
            continue
        if num("ban") and float(p.get("banos") or 0) < num("ban"):
            continue
        if num("m2") and float(p.get("m2_construccion") or 0) < num("m2"):
            continue
        if f.get("car") and f["car"] not in caracteristicas_de(p):
            continue
        out.append(p)
    return out


@router.get("/s/{slug}/buscar", response_class=HTMLResponse)
async def sitio_buscar(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    f = {k: str(v)[:80] for k, v in request.query_params.items()}
    res = filtrar(props, f)
    base = _base(request, s)
    ciudades = sorted({p["ciudad"] for p in props if p.get("ciudad")})
    cuerpo = (f'<div class="wrap sec"><h2>Buscar inmuebles</h2>{R.formulario_busqueda(base, f, ciudades)}'
              f'<p class="sub">{len(res)} resultado(s)</p>{R.grid(res, base, "Ningún inmueble coincide. Prueba con menos filtros.")}</div>')
    return _html(R.layout(s, titulo="Buscar · " + (s.get("nombre") or ""), descripcion="Busca casas, departamentos, terrenos y locales.",
                          cuerpo=cuerpo, base=base, ruta="/buscar", imagen=s.get("logo_url"), paginas_menu=await _menu(s),
                          tiene_temporal=_tiene_temporal(props)), max_age=60)


async def _asesor(p: dict) -> Optional[dict]:
    uid = p.get("asignado_a") or p.get("user_id")
    if not uid:
        return None
    try:
        filas = await get_rows("usuarios", {"id": f"eq.{uid}", "select": "nombre,nombre_publico,telefono,whatsapp_publico,foto_url", "limit": "1"})
    except httpx.HTTPStatusError:
        return None
    if not filas:
        return None
    u = filas[0]
    return {"nombre": u.get("nombre_publico") or u.get("nombre"), "telefono": u.get("whatsapp_publico") or u.get("telefono"), "foto_url": u.get("foto_url")}


def _wa(numero: Optional[str]) -> str:
    d = re.sub(r"\D", "", numero or "")
    return "52" + d if len(d) == 10 else d


def _json_ld_prop(p: dict, url: str) -> dict:
    ops = R.operaciones(p)
    ld = {"@context": "https://schema.org", "@type": "RealEstateListing", "name": R.titulo_prop(p), "url": url,
          "description": (p.get("descripcion") or "")[:500], "image": (p.get("fotos") or [])[:5]}
    if ops and p.get("mostrar_precio") is not False and ops[0].get("precio"):
        ld["offers"] = {"@type": "Offer", "price": ops[0]["precio"], "priceCurrency": ops[0].get("moneda") or "MXN"}
    return ld


async def _render_ficha(request: Request, s: dict, p: dict, *, base: str, asesor: Optional[dict]) -> HTMLResponse:
    props_todas = await inventario_sitio(s)
    url = base_publica(s) + f"/inmueble/{p['id']}"
    desc = f"{R.precio_txt(p)} · {R.ubicacion(p)}. " + (p.get("descripcion") or "")[:200]
    cuerpo = ""
    if request.query_params.get("enviado"):
        cuerpo = '<div class="wrap" style="padding-top:16px"><div class="ok">¡Gracias! Recibimos tu mensaje y te contactaremos pronto.</div></div>'
    cuerpo += R.ficha(p, base, asesor, bool(s.get("mostrar_asesor")), _wa(s.get("whatsapp") or (asesor or {}).get("telefono")))
    return _html(R.layout(s, titulo=R.titulo_prop(p) + " · " + R.precio_txt(p), descripcion=desc, cuerpo=cuerpo, base=base,
                          ruta=f"/inmueble/{p['id']}", imagen=(p.get("fotos") or [s.get("logo_url")])[0],
                          paginas_menu=await _menu(s), tiene_temporal=_tiene_temporal(props_todas), json_ld=_json_ld_prop(p, url)))


@router.get("/s/{slug}/inmueble/{pid}", response_class=HTMLResponse)
async def sitio_inmueble(slug: str, pid: str, request: Request):
    s = await _sitio_o_404(slug)
    props = await inventario_sitio(s)
    p = next((x for x in props if x["id"] == pid), None)
    if not p:
        raise HTTPException(status_code=404, detail="Este inmueble ya no está disponible")
    return await _render_ficha(request, s, p, base=_base(request, s), asesor=await _asesor(p))


@router.get("/s/{slug}/acerca", response_class=HTMLResponse)
async def sitio_acerca(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    base = _base(request, s)
    texto = s.get("acerca_html") or f"<p>{R.e(s.get('eslogan') or '')}</p>"
    return _html(R.layout(s, titulo="Acerca de · " + (s.get("nombre") or ""), descripcion=s.get("seo_descripcion") or s.get("eslogan") or "",
                          cuerpo=f'<div class="wrap sec prosa"><h2>Acerca de {R.e(s.get("nombre") or "nosotros")}</h2>{texto}</div>',
                          base=base, ruta="/acerca", imagen=s.get("logo_url"), paginas_menu=await _menu(s)))


@router.get("/s/{slug}/contacto", response_class=HTMLResponse)
async def sitio_contacto(slug: str, request: Request):
    s = await _sitio_o_404(slug)
    base = _base(request, s)
    ok = '<div class="ok">¡Gracias! Recibimos tu mensaje y te contactaremos pronto.</div>' if request.query_params.get("enviado") else ""
    datos = "".join(f"<p>{x}</p>" for x in (
        R.e(s.get("direccion")) if s.get("direccion") else "",
        f'<a href="tel:{R.e(s.get("telefono"))}">{R.e(s.get("telefono"))}</a>' if s.get("telefono") else "",
        f'<a href="mailto:{R.e(s.get("email"))}">{R.e(s.get("email"))}</a>' if s.get("email") else "") if x)
    cuerpo = f'<div class="wrap sec prosa"><h2>Contacto</h2>{ok}{datos}{R.formulario_contacto(base)}</div>'
    return _html(R.layout(s, titulo="Contacto · " + (s.get("nombre") or ""), descripcion="Escríbenos y te contactamos.",
                          cuerpo=cuerpo, base=base, ruta="/contacto", imagen=s.get("logo_url"), paginas_menu=await _menu(s)), max_age=0)


_RL: Dict[str, List[float]] = {}


def _permitido(clave: str, limite: int, ventana: int) -> bool:
    ahora = time.time()
    lst = [t for t in _RL.get(clave, []) if ahora - t < ventana]
    if len(lst) >= limite:
        _RL[clave] = lst
        return False
    _RL[clave] = lst + [ahora]
    if len(_RL) > 5000:
        _RL.clear()
    return True


@router.post("/s/{slug}/contacto")
async def sitio_lead(slug: str, request: Request):
    """Formulario del sitio → Buzón (canal "Sitio web", fuente = dominio)."""
    s = await _sitio_o_404(slug)
    try:
        form = dict(await request.form())
    except Exception:
        form = {}
    base = _base(request, s)
    destino = base + "/contacto?enviado=1"
    pid = str(form.get("propiedad_id") or "")[:36]
    if pid:
        destino = base + f"/inmueble/{pid}?enviado=1"
    if str(form.get("sitio_web") or "").strip():          # trampa para bots
        return RedirectResponse(destino or "/", status_code=303)
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not _permitido(f"ip:{ip}", 6, 3600) or not _permitido(f"sitio:{s['id']}", 60, 3600):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes, intenta más tarde")
    nombre = str(form.get("nombre") or "").strip()[:120]
    telefono = re.sub(r"[^\d+ ]", "", str(form.get("telefono") or ""))[:25]
    email = str(form.get("email") or "").strip()[:160]
    if not nombre or not (telefono or email):
        raise HTTPException(status_code=400, detail="Escribe tu nombre y un teléfono o correo.")
    dueno = s.get("user_id")
    if not dueno:
        filas = await get_rows("organizacion_miembros", {"org_id": f"eq.{s['org_id']}", "rol_org": "eq.owner", "activo": "eq.true",
                                                         "select": "user_id", "limit": "1"})
        dueno = filas[0]["user_id"] if filas else None
    from core.buzon import registrar_lead
    dominio = s.get("dominio") if s.get("dominio_estado") == "activo" else None
    try:
        await registrar_lead(org_id=s["org_id"], user_id=dueno, canal="sitio", nombre=nombre, telefono=telefono, email=email,
                             mensaje=str(form.get("mensaje") or "")[:1500], fuente=dominio or f"Sitio web ({s['slug']})",
                             propiedad_id=pid if len(pid) == 36 else None, datos={"sitio": s["slug"], "propiedad_externa": pid})
    except Exception as e:
        log.error("lead del sitio %s no registrado: %s", s["slug"], e)
        raise HTTPException(status_code=502, detail="No pudimos registrar tu mensaje. Intenta por WhatsApp.")
    return RedirectResponse(destino, status_code=303)


@router.get("/s/{slug}/p/{pagina}", response_class=HTMLResponse)
async def sitio_pagina(slug: str, pagina: str, request: Request):
    s = await _sitio_o_404(slug)
    filas = await get_rows("sitio_paginas", {"sitio_id": f"eq.{s['id']}", "slug": f"ilike.{pagina}", "publicada": "eq.true", "select": "*", "limit": "1"})
    if not filas:
        raise HTTPException(status_code=404, detail="Página no encontrada")
    pg = filas[0]
    base = _base(request, s)
    return _html(R.layout(s, titulo=pg.get("meta_titulo") or (pg["titulo"] + " · " + (s.get("nombre") or "")),
                          descripcion=pg.get("meta_descripcion") or re.sub(r"<[^>]+>", " ", pg.get("contenido_html") or "")[:200],
                          cuerpo=f'<div class="wrap sec prosa"><h1>{R.e(pg["titulo"])}</h1>{pg.get("contenido_html") or ""}</div>',
                          base=base, ruta=f"/p/{pg['slug']}", imagen=s.get("logo_url"), paginas_menu=await _menu(s)))


@router.get("/s/{slug}/sitemap.xml")
async def sitio_sitemap(slug: str):
    s = await _sitio_o_404(slug)
    url = base_publica(s)
    rutas = ["", "/venta", "/renta", "/buscar", "/acerca", "/contacto"]
    props = await inventario_sitio(s)
    if _tiene_temporal(props):
        rutas.append("/rentas-temporales")
    rutas += [f"/inmueble/{p['id']}" for p in props if p.get("org_id") == s["org_id"] or s["tipo"] == "agente"]
    try:
        rutas += [f"/p/{pg['slug']}" for pg in await get_rows("sitio_paginas", {"sitio_id": f"eq.{s['id']}", "publicada": "eq.true", "select": "slug"})]
    except httpx.HTTPStatusError:
        pass
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + \
          "".join(f"<url><loc>{R.e(url + r)}</loc></url>" for r in rutas) + "</urlset>"
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/s/{slug}/robots.txt")
async def sitio_robots(slug: str):
    s = await _sitio_o_404(slug)
    return PlainTextResponse(f"User-agent: *\nAllow: /\nSitemap: {base_publica(s)}/sitemap.xml\n")


# ── Ficha pública para compartir (ligas que mandan las alertas) ─────────────
@router.get("/p/{pid}", response_class=HTMLResponse)
async def ficha_compartida(pid: str, request: Request, a: str = ""):
    if not re.match(r"^[0-9a-f-]{36}$", pid):
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")
    filas = await get_rows("propiedades", {"id": f"eq.{pid}", "estatus": "eq.activa", "select": "*", "limit": "1"})
    if not filas or filas[0].get("archivada"):
        raise HTTPException(status_code=404, detail="Este inmueble ya no está disponible")
    p = filas[0]
    if not p.get("mostrar_ubicacion_exacta"):
        for k in ("calle", "num_exterior", "num_interior", "lat", "lng"):
            p.pop(k, None)
    for k in ("notas", "descripcion_privada", "codigo_llave", "comision_venta_pct", "comision_renta_meses", "comision_real", "bolsa_notas"):
        p.pop(k, None)
    # El sitio y el asesor son los de quien comparte (si tiene sitio activo),
    # no los del captador: así el cliente siempre habla con su agente.
    agente = a if re.match(r"^[0-9a-f-]{36}$", a or "") else (p.get("asignado_a") or p.get("user_id"))
    s = None
    try:
        org_ag = await get_rows("organizacion_miembros", {"user_id": f"eq.{agente}", "activo": "eq.true", "select": "org_id", "limit": "1"})
        if org_ag:
            cand = await get_rows("sitios", {"org_id": f"eq.{org_ag[0]['org_id']}", "activo": "eq.true", "select": "*"})
            s = next((x for x in cand if x["tipo"] == "agente" and x.get("user_id") == agente), None) or \
                next((x for x in cand if x["tipo"] == "organizacion"), None)
    except httpx.HTTPStatusError:
        s = None
    asesor = await _asesor({"user_id": agente})
    if not s:
        s = {"id": "", "slug": "", "org_id": p.get("org_id"), "tipo": "agente", "user_id": agente,
             "nombre": (asesor or {}).get("nombre") or "Broquer", "mostrar_asesor": True, "whatsapp": (asesor or {}).get("telefono")}
        cuerpo = R.ficha(p, "", asesor, True, _wa((asesor or {}).get("telefono")))
        return _html(R.layout(s, titulo=R.titulo_prop(p) + " · " + R.precio_txt(p), descripcion=f"{R.precio_txt(p)} · {R.ubicacion(p)}",
                              cuerpo=cuerpo.replace('action="/contacto"', 'action="#" onsubmit="return false"'), base=settings.api_base_url,
                              ruta=f"/p/{pid}", imagen=(p.get("fotos") or [None])[0], json_ld=_json_ld_prop(p, f"{settings.api_base_url}/p/{pid}")))
    s["_base_publica"] = base_publica(s)
    return await _render_ficha(request, s, p, base=f"{settings.api_base_url}/s/{s['slug']}", asesor=asesor)


# ══════════════════════════════════════════════════════════════════════════
# DOMINIO PROPIO → SLUG (middleware)
# ══════════════════════════════════════════════════════════════════════════
_CACHE_DOM: Dict[str, Any] = {}


def _hosts_propios() -> set:
    hosts = {"localhost", "127.0.0.1", "testserver", "api.broquer.app", "broquer.app", "staging.broquer.app"}
    for u in (settings.api_base_url, settings.frontend_url):
        h = urlparse(u).hostname
        if h:
            hosts.add(h)
    return hosts


async def _slug_de_dominio(host: str) -> Optional[str]:
    ahora = time.time()
    c = _CACHE_DOM.get(host)
    if c and ahora - c[1] < 60:
        return c[0]
    slug = None
    try:
        filas = await get_rows("sitios", {"dominio": f"ilike.{host}", "activo": "eq.true", "select": "slug", "limit": "1"})
        if not filas and host.startswith("www."):
            filas = await get_rows("sitios", {"dominio": f"ilike.{host[4:]}", "activo": "eq.true", "select": "slug", "limit": "1"})
        if not filas and not host.startswith("www."):
            filas = await get_rows("sitios", {"dominio": f"ilike.www.{host}", "activo": "eq.true", "select": "slug", "limit": "1"})
        slug = filas[0]["slug"] if filas else None
    except Exception:
        slug = None
    if len(_CACHE_DOM) > 2000:
        _CACHE_DOM.clear()
    _CACHE_DOM[host] = (slug, ahora)
    return slug


def instalar_middleware(app) -> None:
    """Con dominio propio, el Host (o X-Sitio-Host desde el Worker de
    Cloudflare, firmado con SITIOS_WORKER_CLAVE) se traduce a /s/{slug}."""
    propios = _hosts_propios()

    @app.middleware("http")
    async def _sitios_por_dominio(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower()
        reenviado = request.headers.get("x-sitio-host")
        if reenviado and settings.sitios_worker_clave and request.headers.get("x-sitio-clave") == settings.sitios_worker_clave:
            host = reenviado.split(":")[0].lower()
        if host and host not in propios and not host.endswith((".railway.app", ".up.railway.app")) and not request.url.path.startswith("/s/"):
            slug = await _slug_de_dominio(host)
            if slug:
                ruta = request.url.path if request.url.path != "/" else ""
                request.scope["path"] = f"/s/{slug}{ruta}"
                request.scope["raw_path"] = request.scope["path"].encode()
                request.scope["sitio_por_dominio"] = True
        return await call_next(request)
