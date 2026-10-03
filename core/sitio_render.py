"""HTML público de los sitios (servido por routers/sitios.py).

Funciones puras: reciben datos ya leídos y devuelven HTML completo con
título, descripción y Open Graph (para que la liga pegada en WhatsApp o
Facebook muestre foto, título y precio). Todo texto pasa por ``e()``.
"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from core.catalogo_inmuebles import CARACTERISTICAS, OPERACIONES, TIPOS, UNIDADES_PRECIO, tipo_label

OP_LABEL = {o["key"]: o["label"] for o in OPERACIONES}
UNIDAD = {u["key"]: u["label"] for u in UNIDADES_PRECIO}
_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_YT = re.compile(r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/))([A-Za-z0-9_-]{11})")


def e(v: Any) -> str:
    return escape("" if v is None else str(v), quote=True)


def color(v: Optional[str], defecto: str) -> str:
    return v if v and _COLOR.match(v) else defecto


def operaciones(p: dict) -> List[dict]:
    ops = [o for o in (p.get("operaciones") or []) if isinstance(o, dict) and o.get("tipo")]
    if ops:
        return ops
    if p.get("operacion"):
        return [{"tipo": p["operacion"], "precio": p.get("precio"), "moneda": p.get("moneda") or "MXN"}]
    return []


def precio_txt(p: dict, o: Optional[dict] = None) -> str:
    o = o or (operaciones(p) or [None])[0]
    if not o or p.get("mostrar_precio") is False:
        return "Precio a consultar"
    try:
        v = float(o.get("precio") or 0)
    except (TypeError, ValueError):
        v = 0
    if v <= 0:
        return "Precio a consultar"
    t = f"${v:,.0f} {o.get('moneda') or 'MXN'}"
    if o.get("unidad") and o["unidad"] != "total":
        t += " " + UNIDAD.get(o["unidad"], "")
    if o.get("tipo") == "renta":
        t += " / mes"
    if o.get("tipo") == "renta_temporal" and o.get("periodo"):
        t += {"noche": " por noche", "semana": " por semana", "mes": " por mes"}.get(o["periodo"], "")
    return t


def ubicacion(p: dict) -> str:
    return ", ".join(x for x in (p.get("colonia"), p.get("ciudad"), p.get("estado")) if x)


def titulo_prop(p: dict) -> str:
    return p.get("titulo") or f"{tipo_label(p.get('subtipo') or p.get('tipo'))} en {p.get('colonia') or ''}".strip()


# ══════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════
def layout(s: dict, *, titulo: str, descripcion: str, cuerpo: str, base: str, ruta: str,
           imagen: Optional[str] = None, paginas_menu: Optional[List[dict]] = None,
           tiene_temporal: bool = False, json_ld: Optional[dict] = None) -> str:
    c1, c2 = color(s.get("color_primario"), "#0b2545"), color(s.get("color_secundario"), "#13a89e")
    nombre = s.get("nombre") or "Inmobiliaria"
    canonica = (s.get("_base_publica") or base).rstrip("/") + (ruta if ruta != "/" else "/")
    menu = [("", "Inicio"), ("/venta", "Venta"), ("/renta", "Renta")]
    if tiene_temporal:
        menu.append(("/rentas-temporales", "Rentas temporales"))
    menu += [("/buscar", "Buscar"), ("/acerca", "Acerca de"), ("/contacto", "Contacto")]
    menu += [("/p/" + quote(pg["slug"]), pg["titulo"]) for pg in (paginas_menu or [])]
    actual = ' aria-current="page"'
    nav = "".join(f'<a href="{e(base + href)}"{actual if ruta == (href or "/") else ""}>{e(t)}</a>' for href, t in menu)
    redes = s.get("redes") or {}
    redes_html = "".join(f'<a href="{e(v)}" rel="noopener" target="_blank">{e(k.capitalize())}</a>'
                         for k, v in redes.items() if isinstance(v, str) and v.startswith("https://"))
    wa = re.sub(r"\D", "", s.get("whatsapp") or "")
    if len(wa) == 10:
        wa = "52" + wa
    ga = re.sub(r"[^A-Za-z0-9-]", "", s.get("ga4_id") or "")
    px = re.sub(r"\D", "", s.get("meta_pixel_id") or "")
    analitica = ""
    if ga:
        analitica += (f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>'
                      f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{ga}');</script>")
    if px:
        analitica += ("<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};"
                      "if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];"
                      f"s.parentNode.insertBefore(t,s)}}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','{px}');fbq('track','PageView');</script>")
    traductor = ""
    if s.get("traductor"):
        traductor = ('<div id="gt" class="gt"></div><script>function gtInit(){new google.translate.TranslateElement({pageLanguage:"es",'
                     'includedLanguages:"en,fr,de,it,pt,zh-CN",layout:google.translate.TranslateElement.InlineLayout.SIMPLE},"gt")}</script>'
                     '<script src="https://translate.google.com/translate_a/element.js?cb=gtInit" async></script>')
    og_img = f'<meta property="og:image" content="{e(imagen)}"/><meta name="twitter:image" content="{e(imagen)}"/>' if imagen else ""
    favicon = f'<link rel="icon" href="{e(s.get("favicon_url"))}"/>' if s.get("favicon_url") else ""
    ld = ""
    if json_ld:
        ld_txt = json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")
        ld = f'<script type="application/ld+json">{ld_txt}</script>'
    logo = (f'<img src="{e(s.get("logo_url"))}" alt="{e(nombre)}"/>' if s.get("logo_url") else f"<span>{e(nombre)}</span>")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>{e(titulo)}</title><meta name="description" content="{e(descripcion[:300])}"/>
<link rel="canonical" href="{e(canonica)}"/>
<meta property="og:type" content="website"/><meta property="og:site_name" content="{e(nombre)}"/>
<meta property="og:title" content="{e(titulo)}"/><meta property="og:description" content="{e(descripcion[:300])}"/>
<meta property="og:url" content="{e(canonica)}"/><meta name="twitter:card" content="summary_large_image"/>{og_img}{favicon}{ld}
<style>{_CSS.replace("__C1__", c1).replace("__C2__", c2)}</style>{analitica}{s.get("codigo_head") or ""}
</head><body>
<header class="hd"><div class="wrap hd__in"><a class="logo" href="{e(base or "/")}">{logo}</a>
<button class="menu-btn" aria-label="Menú" onclick="document.body.classList.toggle('menu-on')">☰</button>
<nav class="nav">{nav}</nav></div></header>
<main>{cuerpo}</main>
<footer class="ft"><div class="wrap"><div><strong>{e(nombre)}</strong>
{f"<div>{e(s.get('direccion'))}</div>" if s.get("direccion") else ""}
{f'<div><a href="tel:{e(s.get("telefono"))}">{e(s.get("telefono"))}</a></div>' if s.get("telefono") else ""}
{f'<div><a href="mailto:{e(s.get("email"))}">{e(s.get("email"))}</a></div>' if s.get("email") else ""}</div>
<div class="ft__redes">{redes_html}</div>{traductor}
<div class="ft__pie">Sitio hecho con <a href="https://broquer.app" rel="noopener">Broquer</a></div></div></footer>
{f'<a class="wa" href="https://wa.me/{wa}" target="_blank" rel="noopener" aria-label="WhatsApp">WhatsApp</a>' if wa else ""}
{s.get("codigo_body") or ""}</body></html>"""


_CSS = """
:root{--c1:__C1__;--c2:__C2__;--tx:#1b2733;--mu:#5c6b7a;--ln:#e3e8ee;--bg:#f6f8fa;--r:14px}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif;color:var(--tx);background:#fff;line-height:1.5}
a{color:var(--c1)}img{max-width:100%;display:block}.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
.hd{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid var(--ln)}.hd__in{display:flex;align-items:center;gap:16px;min-height:64px}
.logo{display:flex;align-items:center;font-weight:800;font-size:20px;color:var(--c1);text-decoration:none}.logo img{max-height:44px;width:auto}
.nav{display:flex;gap:4px;margin-left:auto;flex-wrap:wrap}.nav a{padding:8px 12px;border-radius:999px;text-decoration:none;color:var(--tx);font-size:15px}
.nav a[aria-current],.nav a:hover{background:var(--bg);color:var(--c1)}.menu-btn{display:none;margin-left:auto;font-size:22px;background:none;border:0;padding:8px;cursor:pointer}
@media(max-width:860px){.menu-btn{display:block}.nav{display:none;position:absolute;left:0;right:0;top:64px;background:#fff;flex-direction:column;padding:8px 16px 16px;border-bottom:1px solid var(--ln)}.menu-on .nav{display:flex}}
.hero{background:linear-gradient(135deg,var(--c1),var(--c2));color:#fff;padding:56px 0 64px;background-size:cover;background-position:center}
.hero h1{font-size:clamp(28px,5vw,44px);line-height:1.1;margin:0 0 8px}.hero p{opacity:.9;margin:0 0 20px;font-size:18px}
.buscador{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;background:#fff;padding:12px;border-radius:var(--r);box-shadow:0 10px 30px rgba(0,0,0,.12)}
.buscador select,.buscador input,.form input,.form textarea,.form select{width:100%;font-size:16px;padding:12px;border:1px solid var(--ln);border-radius:10px;background:#fff;color:var(--tx);font-family:inherit}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 18px;border-radius:999px;border:0;background:var(--c1);color:#fff;font-weight:700;font-size:16px;cursor:pointer;text-decoration:none}
.btn--2{background:var(--c2)}.btn--ghost{background:#fff;color:var(--c1);border:1px solid var(--ln)}
.sec{padding:40px 0}.sec h2{font-size:26px;margin:0 0 16px}.sub{color:var(--mu);margin:-8px 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px}
.card{border:1px solid var(--ln);border-radius:var(--r);overflow:hidden;text-decoration:none;color:inherit;background:#fff;display:flex;flex-direction:column;transition:box-shadow .2s}
.card:hover{box-shadow:0 10px 26px rgba(0,0,0,.08)}.card__img{aspect-ratio:4/3;background:var(--bg);position:relative}.card__img img{width:100%;height:100%;object-fit:cover}
.chip{position:absolute;left:10px;top:10px;background:var(--c1);color:#fff;font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px}
.card__b{padding:14px 16px 16px;display:flex;flex-direction:column;gap:4px}.card__p{font-weight:800;font-size:19px;color:var(--c1)}.card__t{font-weight:600}.card__u,.card__s{color:var(--mu);font-size:14px}
.filtros{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:20px;align-items:end}
.filtros label{font-size:13px;color:var(--mu);display:flex;flex-direction:column;gap:4px}.filtros select,.filtros input{font-size:16px;padding:10px;border:1px solid var(--ln);border-radius:10px;width:100%}
.galeria{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;border-radius:var(--r)}.galeria img{height:min(56vh,460px);width:auto;max-width:92vw;object-fit:cover;scroll-snap-align:start;border-radius:10px;flex-shrink:0}
.ficha{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:28px;align-items:start}@media(max-width:900px){.ficha{grid-template-columns:1fr}}
.ficha h1{font-size:clamp(24px,4vw,34px);line-height:1.15;margin:16px 0 4px}.precio{font-size:26px;font-weight:800;color:var(--c1)}
.datos{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:16px 0}.dato{background:var(--bg);border-radius:10px;padding:10px 12px}.dato b{display:block;font-size:13px;color:var(--mu);font-weight:500}
.tags{display:flex;flex-wrap:wrap;gap:6px}.tag{background:var(--bg);border:1px solid var(--ln);padding:4px 10px;border-radius:999px;font-size:14px}
.embed{position:relative;aspect-ratio:16/9;border-radius:var(--r);overflow:hidden;background:var(--bg);margin:10px 0}.embed iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.panel{border:1px solid var(--ln);border-radius:var(--r);padding:18px;position:sticky;top:84px;background:#fff}.form{display:flex;flex-direction:column;gap:10px}
.asesor{display:flex;gap:12px;align-items:center;margin-bottom:12px}.asesor img{width:56px;height:56px;border-radius:50%;object-fit:cover}
.mapa{height:320px;border-radius:var(--r);overflow:hidden;margin:12px 0}.prosa{max-width:760px}.prosa h2,.prosa h3{margin-top:28px}
.wa{position:fixed;right:16px;bottom:calc(16px + env(safe-area-inset-bottom));background:#25d366;color:#fff;font-weight:700;padding:14px 18px;border-radius:999px;text-decoration:none;box-shadow:0 8px 24px rgba(0,0,0,.2);z-index:30}
.ft{background:var(--c1);color:#fff;padding:32px 0 90px;margin-top:40px}.ft a{color:#fff}.ft .wrap{display:flex;flex-wrap:wrap;gap:24px;justify-content:space-between}.ft__redes{display:flex;gap:12px;flex-wrap:wrap}.ft__pie{width:100%;opacity:.7;font-size:13px}
.vacio{padding:40px;text-align:center;color:var(--mu);border:1px dashed var(--ln);border-radius:var(--r)}.ok{background:#e8f8f0;padding:12px;border-radius:10px}
.pag{display:flex;gap:8px;justify-content:center;margin-top:24px}.gt{margin-top:8px}
"""


# ══════════════════════════════════════════════════════════════════════════
# COMPONENTES
# ══════════════════════════════════════════════════════════════════════════
def tarjeta(p: dict, base: str) -> str:
    foto = (p.get("fotos") or [None])[0]
    ops = operaciones(p)
    chip = " · ".join(OP_LABEL.get(o["tipo"], o["tipo"]).replace(" mensual", "") for o in ops[:2])
    specs = []
    if p.get("recamaras"):
        specs.append(f"{e(p['recamaras'])} rec")
    if p.get("banos"):
        specs.append(f"{e(p['banos'])} baños")
    if p.get("m2_construccion"):
        specs.append(f"{e(round(float(p['m2_construccion'])))} m²")
    return (f'<a class="card" href="{e(base)}/inmueble/{e(p["id"])}"><div class="card__img">'
            + (f'<img src="{e(foto)}" alt="" loading="lazy"/>' if foto else "")
            + (f'<span class="chip">{e(chip)}</span>' if chip else "")
            + f'</div><div class="card__b"><div class="card__p">{e(precio_txt(p))}</div><div class="card__t">{e(titulo_prop(p))}</div>'
            f'<div class="card__u">{e(ubicacion(p))}</div><div class="card__s">{" · ".join(specs)}</div></div></a>')


def grid(props: List[dict], base: str, vacio: str = "Por ahora no hay inmuebles aquí. Vuelve pronto.") -> str:
    if not props:
        return f'<div class="vacio">{e(vacio)}</div>'
    return '<div class="grid">' + "".join(tarjeta(p, base) for p in props) + "</div>"


def opciones_tipos(sel: str) -> str:
    out = '<option value="">Cualquier tipo</option>'
    for g in TIPOS:
        out += f'<optgroup label="{e(g["grupo"])}">' + "".join(
            f'<option value="{e(t["key"])}"{" selected" if t["key"] == sel else ""}>{e(t["label"])}</option>' for t in g["items"]) + "</optgroup>"
    return out


def formulario_busqueda(base: str, f: Dict[str, str], ciudades: List[str], compacto: bool = False) -> str:
    def sel(nombre, opciones, vacio):
        return (f'<select name="{nombre}" aria-label="{e(vacio)}"><option value="">{e(vacio)}</option>'
                + "".join(f'<option value="{e(k)}"{" selected" if f.get(nombre) == k else ""}>{e(v)}</option>' for k, v in opciones) + "</select>")
    ops = [(o["key"], o["label"]) for o in OPERACIONES]
    if compacto:
        return (f'<form class="buscador" action="{e(base)}/buscar" method="get">{sel("operacion", ops, "Operación")}'
                f'<select name="tipo" aria-label="Tipo">{opciones_tipos(f.get("tipo", ""))}</select>'
                f'{sel("ciudad", [(c, c) for c in ciudades], "Ciudad")}'
                f'<input name="q" placeholder="Colonia o palabra clave" value="{e(f.get("q", ""))}"/><button class="btn btn--2">Buscar</button></form>')
    caract = "".join(f'<option value="{e(c["key"])}"{" selected" if f.get("car") == c["key"] else ""}>{e(c["label"])}</option>'
                     for g in CARACTERISTICAS for c in g["items"])
    return (f'<form class="filtros" action="{e(base)}/buscar" method="get">'
            f'<label>Operación{sel("operacion", ops, "Cualquiera")}</label>'
            f'<label>Tipo<select name="tipo">{opciones_tipos(f.get("tipo", ""))}</select></label>'
            f'<label>Ciudad{sel("ciudad", [(c, c) for c in ciudades], "Cualquiera")}</label>'
            f'<label>Colonia o palabra<input name="q" value="{e(f.get("q", ""))}"/></label>'
            f'<label>Precio mín.<input name="pmin" type="number" inputmode="numeric" value="{e(f.get("pmin", ""))}"/></label>'
            f'<label>Precio máx.<input name="pmax" type="number" inputmode="numeric" value="{e(f.get("pmax", ""))}"/></label>'
            f'<label>Recámaras mín.<input name="rec" type="number" inputmode="numeric" value="{e(f.get("rec", ""))}"/></label>'
            f'<label>Baños mín.<input name="ban" type="number" inputmode="numeric" value="{e(f.get("ban", ""))}"/></label>'
            f'<label>m² mín.<input name="m2" type="number" inputmode="numeric" value="{e(f.get("m2", ""))}"/></label>'
            f'<label>Característica<select name="car"><option value="">Cualquiera</option>{caract}</select></label>'
            f'<button class="btn">Buscar</button></form>')


def formulario_contacto(base: str, propiedad: Optional[dict] = None) -> str:
    pid = f'<input type="hidden" name="propiedad_id" value="{e(propiedad["id"])}"/>' if propiedad else ""
    msg = f"Hola, me interesa «{titulo_prop(propiedad)}»." if propiedad else ""
    return (f'<form class="form" method="post" action="{e(base)}/contacto">{pid}'
            '<input name="nombre" placeholder="Tu nombre" required autocomplete="name"/>'
            '<input name="telefono" type="tel" inputmode="tel" placeholder="Teléfono" autocomplete="tel"/>'
            '<input name="email" type="email" placeholder="Correo" autocomplete="email"/>'
            f'<textarea name="mensaje" rows="3" placeholder="Mensaje">{e(msg)}</textarea>'
            '<input name="sitio_web" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true"/>'
            '<button class="btn" type="submit">Enviar</button></form>')


def _embed_video(url: str) -> str:
    m = _YT.search(url or "")
    return f'<div class="embed"><iframe src="https://www.youtube-nocookie.com/embed/{m.group(1)}" title="Video" loading="lazy" allowfullscreen></iframe></div>' if m else ""


def _embed_tour(url: str) -> str:
    return (f'<div class="embed"><iframe src="{e(url)}" title="Tour virtual" loading="lazy" allowfullscreen '
            'allow="xr-spatial-tracking; fullscreen"></iframe></div>') if str(url or "").startswith("https://") else ""


def ficha(p: dict, base: str, asesor: Optional[dict], mostrar_asesor: bool, wa: str) -> str:
    fotos = [f for f in (p.get("fotos") or []) if f][:50]
    ops = operaciones(p)
    datos = []
    for k, etiqueta, suf in (("recamaras", "Recámaras", ""), ("banos", "Baños", ""), ("medio_bano", "Medios baños", ""),
                             ("estacionamientos", "Estacionamientos", ""), ("m2_construccion", "Construcción", " m²"),
                             ("m2_terreno", "Terreno", " m²"), ("antiguedad", "Antigüedad", " años"), ("anio_construccion", "Año", ""),
                             ("pisos_edificio", "Pisos del edificio", ""), ("nivel", "Nivel", "")):
        v = p.get(k)
        if v not in (None, "", 0):
            datos.append(f'<div class="dato"><b>{etiqueta}</b>{e(v)}{suf}</div>')
    datos.insert(0, f'<div class="dato"><b>Tipo</b>{e(tipo_label(p.get("subtipo") or p.get("tipo")))}</div>')
    car = set(p.get("caracteristicas") or [])
    grupos = ""
    for g in CARACTERISTICAS:
        items = [c["label"] for c in g["items"] if c["key"] in car]
        if items:
            grupos += f'<h3>{e(g["grupo"])}</h3><div class="tags">' + "".join(f'<span class="tag">{e(i)}</span>' for i in items) + "</div>"
    if p.get("otras_caracteristicas"):
        grupos += '<h3>Otras</h3><div class="tags">' + "".join(
            f'<span class="tag">{e(x.strip())}</span>' for x in str(p["otras_caracteristicas"]).split(",") if x.strip()) + "</div>"
    if not grupos and p.get("amenidades"):
        grupos = '<div class="tags">' + "".join(f'<span class="tag">{e(a)}</span>' for a in p["amenidades"]) + "</div>"
    precios = "".join(f'<div>{e(OP_LABEL.get(o["tipo"], o["tipo"]))}: <strong>{e(precio_txt(p, o))}</strong></div>' for o in ops[1:])
    mm = "".join(_embed_video(v) for v in (p.get("videos") or [])[:3]) + "".join(_embed_tour(t) for t in (p.get("tours") or [])[:2])
    docs = [d for d in (p.get("documentos") or []) if isinstance(d, dict) and str(d.get("url", "")).startswith("https://")]
    docs_html = ("<h2>Documentos</h2><ul>" + "".join(f'<li><a href="{e(d["url"])}" target="_blank" rel="noopener" download>{e(d.get("nombre") or "Documento")}</a></li>' for d in docs) + "</ul>") if docs else ""
    mapa = ""
    if p.get("mostrar_ubicacion_exacta") and p.get("lat") and p.get("lng"):
        mapa = (f'<div id="mapa" class="mapa" data-lat="{e(p["lat"])}" data-lng="{e(p["lng"])}"></div>'
                '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>'
                '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>'
                '<script>(function(){var m=document.getElementById("mapa");var la=+m.dataset.lat,ln=+m.dataset.lng;'
                'var map=L.map(m,{scrollWheelZoom:false}).setView([la,ln],15);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",'
                '{attribution:"&copy; OpenStreetMap"}).addTo(map);L.marker([la,ln]).addTo(map);})();</script>')
    asesor_html = ""
    if mostrar_asesor and asesor:
        tel = re.sub(r"\D", "", asesor.get("telefono") or "")
        asesor_html = ('<div class="asesor">' + (f'<img src="{e(asesor.get("foto_url"))}" alt=""/>' if asesor.get("foto_url") else "")
                       + f'<div><strong>{e(asesor.get("nombre") or "")}</strong>'
                       + (f'<div><a href="tel:{e(tel)}">{e(asesor.get("telefono"))}</a></div>' if tel else "") + "</div></div>")
    wa_link = ""
    if wa:
        wa_link = f'<a class="btn btn--2" style="width:100%;margin-top:8px" target="_blank" rel="noopener" href="https://wa.me/{wa}?text={quote("Hola, me interesa: " + titulo_prop(p))}">Preguntar por WhatsApp</a>'
    desc = "".join(f"<p>{e(par)}</p>" for par in str(p.get("descripcion") or "").split("\n") if par.strip())
    return (f'<div class="wrap sec"><div class="galeria">' + "".join(f'<img src="{e(f)}" alt="" loading="lazy"/>' for f in fotos) + "</div>"
            f'<div class="ficha"><div><h1>{e(titulo_prop(p))}</h1><div style="color:var(--mu)">{e(ubicacion(p))}</div>'
            f'<div class="precio">{e(OP_LABEL.get(ops[0]["tipo"], "") + " · " if ops else "")}{e(precio_txt(p))}</div>{precios}'
            f'<div class="datos">{"".join(datos)}</div>{desc}{grupos}{mm}{docs_html}{mapa}</div>'
            f'<aside class="panel">{asesor_html}<h3 style="margin-top:0">¿Te interesa?</h3>{formulario_contacto(base, p)}{wa_link}</aside></div></div>')
