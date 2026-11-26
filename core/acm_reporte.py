"""Presentación del ACM para el propietario.

Un solo renderizador para las dos salidas: la liga pública que el asesor
manda por WhatsApp y el PDF (Playwright imprime este mismo HTML). Lleva la
marca del asesor, no la de Broquer, y sólo muestra lo que el asesor decidió
presentar: comparables incluidos, rango, estrategia y su nota. Nunca muestra
notas internas, comparables descartados ni de dónde salió cada dato técnico.

El mapa es un SVG propio (posición relativa de cada comparable con anillos
de distancia): no depende de ningún servicio externo ni expone llaves.
"""
from __future__ import annotations

import html
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.acm_mercado import numero
from core.pdf_design import theme_css_for_pdf

TIPO_LABEL = {"casa": "Casa", "departamento": "Departamento", "terreno": "Terreno", "local": "Local comercial",
              "oficina": "Oficina", "bodega": "Bodega", "otro": "Inmueble"}
CONSERVACION_LABEL = {"excelente": "Excelente", "bueno": "Bueno", "regular": "Regular", "remodelar": "Para remodelar"}
ESTRATEGIA_LABEL = {
    "rapido": ("Venta rápida", "Precio para vender pronto, por debajo de la mayoría de la oferta."),
    "mercado": ("Precio de mercado", "En línea con lo que se ofrece y se paga en la zona."),
    "aspiracional": ("Aspiracional", "Arriba del mercado: puede tardar más en venderse."),
    "propio": ("Precio acordado", "Precio de salida definido con tu asesor."),
}
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def dinero(v: Any, moneda: str = "MXN") -> str:
    n = numero(v)
    if n is None:
        return "—"
    if moneda == "UF":
        return f"UF {n:,.0f}"
    texto = f"${n:,.0f}"
    return texto if moneda == "MXN" else f"{texto} {moneda}"


def _num(v: Any, sufijo: str = "") -> str:
    n = numero(v)
    if n is None:
        return "—"
    return (f"{n:,.0f}" if n == int(n) else f"{n:,.1f}") + sufijo


def _fecha_larga(d: Optional[datetime] = None) -> str:
    d = d or datetime.now(timezone.utc)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def nombre_archivo(fila: Dict[str, Any]) -> str:
    s = fila.get("sujeto") or {}
    base = re.sub(r"[^A-Za-z0-9]+", "_", f"{s.get('colonia') or s.get('ciudad') or 'propiedad'}")[:30].strip("_")
    return f"ACM_{base or 'propiedad'}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"


# ── Piezas ──────────────────────────────────────────────────────────────────

def _mapa_svg(sujeto: Dict[str, Any], comps: List[Dict[str, Any]]) -> str:
    """Plano esquemático: el sujeto al centro, cada comparable en su
    dirección y distancia real (escala automática) y anillos de referencia."""
    lat0, lng0 = numero(sujeto.get("lat")), sujeto.get("lng")
    try:
        lng0 = float(lng0)
    except (TypeError, ValueError):
        lng0 = None
    if lat0 is None or lng0 is None:
        return ""
    puntos = []
    for i, c in enumerate(comps, 1):
        try:
            lat, lng = float(c.get("lat")), float(c.get("lng"))
        except (TypeError, ValueError):
            continue
        dx = (lng - lng0) * 111_320 * math.cos(math.radians(lat0))
        dy = (lat - lat0) * 111_320
        puntos.append((i, dx, dy, c.get("grupo") or "activo"))
    if not puntos:
        return ""
    alcance = max(400.0, max(math.hypot(dx, dy) for _, dx, dy, _ in puntos) * 1.15)
    anillos = [r for r in (250, 500, 1000, 2000, 4000, 8000) if r <= alcance][-3:] or [round(alcance)]
    w = h = 320
    k = (w / 2 - 18) / alcance
    partes = [f'<svg viewBox="0 0 {w} {h}" class="mapa" role="img" aria-label="Ubicación de los comparables">']
    partes.append(f'<rect x="0" y="0" width="{w}" height="{h}" rx="14" class="mapa-fondo"/>')
    for r in anillos:
        partes.append(f'<circle cx="{w/2}" cy="{h/2}" r="{r*k:.1f}" class="mapa-anillo"/>')
        etiqueta = f"{r/1000:g} km" if r >= 1000 else f"{r} m"
        partes.append(f'<text x="{w/2 + 4}" y="{h/2 - r*k - 3:.1f}" class="mapa-km">{etiqueta}</text>')
    for i, dx, dy, grupo in puntos:
        x, y = w / 2 + dx * k, h / 2 - dy * k
        partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="pt pt-{_e(grupo)}"/>'
                      f'<text x="{x:.1f}" y="{y + 3.5:.1f}" class="pt-n">{i}</text>')
    partes.append(f'<circle cx="{w/2}" cy="{h/2}" r="11" class="pt-sujeto"/>'
                  f'<path d="M{w/2-5} {h/2+1} L{w/2} {h/2-5} L{w/2+5} {h/2+1} L{w/2+3.5} {h/2+1} L{w/2+3.5} {h/2+5} '
                  f'L{w/2-3.5} {h/2+5} L{w/2-3.5} {h/2+1} Z" class="pt-casa"/>')
    partes.append("</svg>")
    return "".join(partes)


def _fila_comp(i: int, c: Dict[str, Any], moneda: str) -> str:
    sup = c.get("superficie")
    detalles = []
    if numero(c.get("recamaras")):
        detalles.append(f"{_num(c['recamaras'])} rec")
    if numero(c.get("banos")):
        detalles.append(f"{_num(c['banos'])} baños")
    if numero(c.get("estacionamientos")):
        detalles.append(f"{_num(c['estacionamientos'])} est")
    distancia = c.get("distancia_m")
    if distancia is not None:
        distancia_txt = f"{distancia/1000:.1f} km" if distancia >= 1000 else f"{int(distancia)} m"
        if c.get("precision_ubicacion") == "colonia":
            distancia_txt = "≈ " + distancia_txt
    else:
        distancia_txt = "—"
    extra = ""
    if c.get("grupo") == "vendido":
        precio = c.get("precio_cierre") or c.get("precio")
        etiqueta = {"cierre": "Vendida", "manual": "Vendida o retirada"}.get(c.get("origen"), "Retirada")
        dias = f" · {c['dias_mercado']} días" if c.get("dias_mercado") is not None else ""
        extra = f'<span class="tag tag-vendido">{etiqueta}{dias}</span>'
    else:
        precio = c.get("precio")
        tags = []
        inicial = numero(c.get("precio_inicial"))
        if inicial and numero(precio) and numero(precio) < inicial * 0.995:
            tags.append(f'<span class="tag tag-bajas">Bajó {(1 - numero(precio) / inicial) * 100:.0f}%</span>')
        if c.get("dias_mercado") is not None:
            tags.append(f'<span class="tag">{c["dias_mercado"]} días publicada</span>')
        extra = "".join(tags)
    titulo = c.get("titulo") or f"{TIPO_LABEL.get(c.get('tipo'), 'Inmueble')} en {c.get('colonia') or 'la zona'}"
    return (
        f'<tr><td class="n">{i}</td>'
        f'<td><div class="c-tit">{_e(titulo)}</div><div class="c-sub">{_e(c.get("colonia") or "")}'
        f'{" · " if c.get("colonia") and detalles else ""}{_e(" · ".join(detalles))}</div>{extra}</td>'
        f'<td class="num">{_num(sup, " m²")}</td>'
        f'<td class="num">{dinero(precio, moneda)}</td>'
        f'<td class="num">{dinero(c.get("precio_m2"), moneda)}</td>'
        f'<td class="num">{_e(distancia_txt)}</td></tr>'
    )


def _tabla(comps: List[Dict[str, Any]], numeros: Dict[str, int], moneda: str) -> str:
    filas = "".join(_fila_comp(numeros[c["id"]], c, moneda) for c in comps)
    return (
        '<table class="comps"><thead><tr><th></th><th>Inmueble</th><th class="num">Superficie</th>'
        '<th class="num">Precio</th><th class="num">Precio/m²</th><th class="num">Distancia</th></tr></thead>'
        f"<tbody>{filas}</tbody></table>"
    )


def _seccion_grupo(titulo: str, explicacion: str, comps: List[Dict[str, Any]], numeros: Dict[str, int],
                   moneda: str) -> str:
    if not comps:
        return ""
    return (f'<section class="sec"><h2>{_e(titulo)}</h2><p class="sec-exp">{_e(explicacion)}</p>'
            f"{_tabla(comps, numeros, moneda)}</section>")


def _tabla_ajustes(comps: List[Dict[str, Any]], numeros: Dict[str, int], moneda: str) -> str:
    filas = []
    for c in comps:
        conceptos = ", ".join(
            f"{a['concepto']} {a['pct']:+.1f}%" for a in c.get("ajustes") or [] if abs(float(a.get("pct") or 0)) >= 0.1
        ) or "Sin ajustes"
        filas.append(
            f'<tr><td class="n">{numeros[c["id"]]}</td><td class="num">{dinero(c.get("precio_m2"), moneda)}</td>'
            f'<td class="aj">{_e(conceptos)}</td><td class="num">{c.get("ajuste_total_pct", 0):+.1f}%</td>'
            f'<td class="num fuerte">{dinero(c.get("precio_m2_ajustado"), moneda)}</td></tr>'
        )
    return (
        '<section class="sec evita-corte"><h2>Cómo se compararon</h2>'
        '<p class="sec-exp">Cada comparable se ajusta para parecerse a tu propiedad: si tiene más '
        'recámaras, se le descuenta; si es más chico, su precio por m² se corrige; a los precios '
        'publicados se les resta un margen de negociación porque rara vez se vende al precio de oferta.</p>'
        '<table class="comps"><thead><tr><th></th><th class="num">Precio/m²</th><th>Ajustes</th>'
        '<th class="num">Total</th><th class="num">Precio/m² ajustado</th></tr></thead>'
        f'<tbody>{"".join(filas)}</tbody></table></section>'
    )


def _barra_rango(r: Dict[str, Any], moneda: str) -> str:
    pm2 = r.get("precio_m2") or {}
    lo, hi = numero(pm2.get("min")), numero(pm2.get("max"))
    p25, p50, p75 = numero(pm2.get("p25")), numero(pm2.get("mediana")), numero(pm2.get("p75"))
    if not (lo and hi and p25 and p75 and p50) or hi <= lo:
        return ""
    pos = lambda v: max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))  # noqa: E731
    return (
        '<div class="barra"><div class="barra-pista"></div>'
        f'<div class="barra-rango" style="left:{pos(p25):.1f}%;width:{max(2.0, pos(p75) - pos(p25)):.1f}%"></div>'
        f'<div class="barra-med" style="left:{pos(p50):.1f}%"></div></div>'
        f'<div class="barra-eti"><span>{dinero(lo, moneda)}/m²</span><span>{dinero(p50, moneda)}/m² mediana</span>'
        f'<span>{dinero(hi, moneda)}/m²</span></div>'
    )


def _estrategia(e: Dict[str, Any], moneda: str) -> str:
    precios = e.get("precios") or {}
    dias = e.get("dias") or {}
    elegida = e.get("elegida") or "mercado"
    tarjetas = []
    for clave in ("rapido", "mercado", "aspiracional"):
        if not precios.get(clave):
            continue
        nombre, texto = ESTRATEGIA_LABEL[clave]
        d = dias.get(clave)
        tarjetas.append(
            f'<div class="est{" est-on" if clave == elegida else ""}"><div class="est-n">{_e(nombre)}</div>'
            f'<div class="est-p">{dinero(precios[clave], moneda)}</div><div class="est-t">{_e(texto)}</div>'
            f'{f"<div class=est-d>Referencia: ~{d} días en el mercado</div>" if d else ""}</div>'
        )
    propio = ""
    if elegida == "propio" and e.get("precio_salida"):
        propio = (f'<div class="est est-on est-ancha"><div class="est-n">{_e(ESTRATEGIA_LABEL["propio"][0])}</div>'
                  f'<div class="est-p">{dinero(e["precio_salida"], moneda)}</div>'
                  f'<div class="est-t">{_e(ESTRATEGIA_LABEL["propio"][1])}</div></div>')
    if not tarjetas and not propio:
        return ""
    return f'<section class="sec evita-corte"><h2>Estrategia de precio</h2><div class="ests">{"".join(tarjetas)}</div>{propio}</section>'


def _agente_html(agente: Dict[str, Any], compacto: bool = False) -> str:
    if not agente.get("nombre"):
        return ""
    foto = (f'<img class="ag-foto" src="{_e(agente["foto_url"])}" alt=""/>'
            if str(agente.get("foto_url") or "").startswith("https://") else "")
    contacto = " · ".join(_e(x) for x in (agente.get("telefono"), agente.get("email")) if x)
    empresa = f'<div class="ag-e">{_e(agente["empresa"])}</div>' if agente.get("empresa") else ""
    return (f'<div class="ag{" ag-c" if compacto else ""}">{foto}<div><div class="ag-n">{_e(agente["nombre"])}</div>'
            f'{empresa}<div class="ag-c2">{contacto}</div></div></div>')


def _boton_whatsapp(agente: Dict[str, Any], titulo: str) -> str:
    digitos = re.sub(r"\D", "", str(agente.get("telefono") or ""))
    if len(digitos) == 10:
        digitos = "52" + digitos
    if len(digitos) < 11:
        return ""
    from urllib.parse import quote

    texto = quote(f"Hola, vi el análisis de mercado de mi propiedad ({titulo}).")
    return f'<a class="btn-wa" href="https://wa.me/{digitos}?text={texto}" target="_blank" rel="noopener">Escribir a mi asesor</a>'


# ── Documento ───────────────────────────────────────────────────────────────

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);color:var(--ink);background:var(--paper);font-size:13px;line-height:1.55;-webkit-font-smoothing:antialiased}
.pag{max-width:860px;margin:0 auto;padding:32px 20px 48px}
.port{background:linear-gradient(155deg,var(--sky-navy),var(--sky-navy-mid));color:#fff;border-radius:var(--r-lg);padding:28px;margin-bottom:22px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.port-top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:26px}
.port-logo{max-height:44px;max-width:180px;object-fit:contain;background:#fff;border-radius:8px;padding:4px 8px}
.port-fecha{font-size:12px;opacity:.75}
.port-eti{font-size:12px;opacity:.7;font-weight:600;letter-spacing:.02em}
.port h1{font-size:26px;line-height:1.2;margin:4px 0 6px;font-weight:700;letter-spacing:-.02em}
.port-dir{font-size:14px;opacity:.85}
.port-valor{margin-top:22px;padding-top:18px;border-top:1px solid rgba(255,255,255,.18);display:flex;flex-wrap:wrap;gap:22px;align-items:flex-end}
.port-valor .lbl{font-size:11px;opacity:.7;font-weight:600}
.port-valor .big{font-size:30px;font-weight:700;letter-spacing:-.02em}
.port-valor .mid{font-size:15px;font-weight:600}
.ag{display:flex;gap:12px;align-items:center;margin-top:22px}
.ag-foto{width:46px;height:46px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,.4)}
.ag-n{font-weight:700;font-size:14px}.ag-e,.ag-c2{font-size:12px;opacity:.8}
.sec{margin:26px 0}
.sec h2{font-size:17px;font-weight:700;color:var(--sky-navy);letter-spacing:-.01em;margin-bottom:4px}
.sec-exp{font-size:12.5px;color:var(--mute);margin-bottom:12px;max-width:640px}
.ficha{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px}
.dato{background:var(--paper-2);border-radius:var(--r-sm);padding:10px 12px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.dato .lbl{font-size:11px;color:var(--mute);font-weight:600}.dato .val{font-size:14px;font-weight:700}
.dos{display:grid;grid-template-columns:320px 1fr;gap:22px;align-items:start}
.mapa{width:100%;max-width:320px;height:auto;display:block}
.mapa-fondo{fill:var(--paper-2)}.mapa-anillo{fill:none;stroke:var(--line-3);stroke-dasharray:3 4}
.mapa-km{font-size:9px;fill:var(--mute);font-family:var(--font-sans)}
.pt{stroke:#fff;stroke-width:1.5}.pt-activo{fill:var(--sky-blue)}.pt-vendido{fill:var(--success)}.pt-bajas{fill:var(--warn)}
.pt-n{font-size:9px;fill:#fff;text-anchor:middle;font-weight:700;font-family:var(--font-sans)}
.pt-sujeto{fill:var(--sky-navy);stroke:#fff;stroke-width:2}.pt-casa{fill:#fff}
.ley{display:flex;flex-direction:column;gap:8px;font-size:12.5px}
.ley span{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px;vertical-align:middle}
.k{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}
table.comps{width:100%;border-collapse:collapse;font-size:12px}
.comps th{text-align:left;font-size:10.5px;color:var(--mute);font-weight:700;padding:6px 8px;border-bottom:1px solid var(--line-2)}
.comps td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.comps tr{break-inside:avoid}
.comps .num{text-align:right;white-space:nowrap}.comps .n{color:var(--mute);font-weight:700;width:22px}
.comps .fuerte{font-weight:700;color:var(--sky-navy)}.comps .aj{font-size:11.5px;color:var(--ink-3)}
.c-tit{font-weight:600}.c-sub{font-size:11.5px;color:var(--mute)}
.tag{display:inline-block;margin:4px 4px 0 0;padding:1px 8px;border-radius:var(--r-pill);font-size:10.5px;font-weight:600;background:var(--paper-2);color:var(--ink-3)}
.tag-vendido{background:var(--success-soft);color:var(--success)}.tag-bajas{background:var(--warn-soft);color:var(--warn)}
.rango{background:var(--paper-2);border-radius:var(--r);padding:18px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.rango-v{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center;margin-top:16px}
.rango-v .lbl{font-size:11px;color:var(--mute);font-weight:600}.rango-v .val{font-size:17px;font-weight:700}
.rango-v .med .val{color:var(--sky-blue);font-size:20px}
.barra{position:relative;height:14px;margin:6px 0}
.barra-pista{position:absolute;inset:5px 0;background:var(--line-2);border-radius:4px}
.barra-rango{position:absolute;top:2px;height:10px;background:var(--sky-blue-lift);border-radius:5px}
.barra-med{position:absolute;top:0;width:3px;height:14px;margin-left:-1.5px;background:var(--sky-navy);border-radius:2px}
.barra-eti{display:flex;justify-content:space-between;font-size:10.5px;color:var(--mute)}
.ests{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.est{border:1px solid var(--line-2);border-radius:var(--r);padding:14px}
.est-on{border:2px solid var(--sky-blue);background:var(--sky-canvas);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.est-ancha{margin-top:10px}
.est-n{font-size:12px;font-weight:700;color:var(--mute)}.est-p{font-size:19px;font-weight:700;margin:2px 0 6px}
.est-t{font-size:11.5px;color:var(--ink-3)}.est-d{font-size:11px;color:var(--mute);margin-top:6px}
.nota{border-left:3px solid var(--sky-blue);background:var(--paper-2);padding:14px 16px;border-radius:0 var(--r-sm) var(--r-sm) 0;white-space:pre-line;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.legal{margin-top:30px;padding-top:14px;border-top:1px solid var(--line);font-size:10.5px;color:var(--mute)}
.acciones{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
.btn-wa,.btn-print{display:inline-block;padding:11px 18px;border-radius:var(--r-pill);font-weight:700;font-size:13px;text-decoration:none;border:0;cursor:pointer;font-family:var(--font-sans)}
.btn-wa{background:#25d366;color:#fff}.btn-print{background:var(--paper-2);color:var(--sky-navy)}
.evita-corte{break-inside:avoid}
@media (max-width:640px){.dos{grid-template-columns:1fr}.ests,.rango-v{grid-template-columns:1fr}.port h1{font-size:21px}
 .comps th:nth-child(3),.comps td:nth-child(3),.comps th:nth-child(6),.comps td:nth-child(6){display:none}}
@media print{.acciones{display:none}.pag{padding:0}.sec{margin:20px 0}}
"""


def render(fila: Dict[str, Any], agente: Dict[str, Any], *, para_pdf: bool) -> str:
    s = fila.get("sujeto") or {}
    r = fila.get("resultado") or {}
    e = fila.get("estrategia") or {}
    moneda = r.get("moneda") or s.get("moneda") or "MXN"
    incluidos = [c for c in fila.get("comparables") or [] if c.get("incluido") and c.get("precio_m2_ajustado")]
    incluidos.sort(key=lambda c: ({"activo": 0, "bajas": 1, "vendido": 2}.get(c.get("grupo"), 3), -(c.get("similitud") or 0)))
    numeros = {c["id"]: i for i, c in enumerate(incluidos, 1)}
    grupos = {g: [c for c in incluidos if c.get("grupo") == g] for g in ("activo", "vendido", "bajas")}
    m = r.get("mercado") or {}
    v = r.get("valor") or {}
    tipo = TIPO_LABEL.get(s.get("tipo"), "Inmueble")
    titulo = f"{tipo} en {s.get('operacion') or 'venta'}"
    lugar = ", ".join(p for p in (s.get("colonia"), s.get("ciudad"), s.get("estado")) if p)

    logo = (f'<img class="port-logo" src="{_e(agente["logo_url"])}" alt=""/>'
            if str(agente.get("logo_url") or "").startswith("https://") else
            f'<div class="port-eti">{_e(agente.get("empresa") or agente.get("nombre") or "")}</div>')
    precio_salida = e.get("precio_salida")
    valor_portada = (
        f'<div><div class="lbl">Precio de salida sugerido</div><div class="big">{dinero(precio_salida, moneda)}</div></div>'
        if precio_salida else ""
    ) + (
        f'<div><div class="lbl">Rango de mercado</div><div class="mid">{dinero(v.get("bajo"), moneda)} – {dinero(v.get("alto"), moneda)}</div></div>'
        if v.get("bajo") and v.get("alto") else ""
    )

    datos = [("Tipo", tipo), ("Operación", (s.get("operacion") or "").capitalize())]
    if numero(s.get("m2_terreno")):
        datos.append(("Terreno", _num(s.get("m2_terreno"), " m²")))
    if numero(s.get("m2_construccion")):
        datos.append(("Construcción", _num(s.get("m2_construccion"), " m²")))
    for campo, etiqueta in (("recamaras", "Recámaras"), ("banos", "Baños"), ("estacionamientos", "Estacionamientos")):
        if numero(s.get(campo)):
            datos.append((etiqueta, _num(s.get(campo))))
    if s.get("antiguedad") is not None:
        datos.append(("Antigüedad", f"{s['antiguedad']} años" if s["antiguedad"] else "A estrenar"))
    datos.append(("Conservación", CONSERVACION_LABEL.get(s.get("conservacion"), "Bueno")))
    ficha = "".join(f'<div class="dato"><div class="lbl">{_e(a)}</div><div class="val">{_e(b)}</div></div>' for a, b in datos)

    mapa = _mapa_svg(s, incluidos)
    kpis = []
    if m.get("en_venta") is not None:
        kpis.append(("En venta en la zona", _num(m.get("en_venta"))))
    if m.get("vendidos"):
        kpis.append(("Vendidos o retirados", _num(m.get("vendidos"))))
    if m.get("dias_mercado_mediana") is not None:
        kpis.append(("Días publicados (mediana)", _num(m.get("dias_mercado_mediana"))))
    if m.get("pct_con_bajas") is not None:
        kpis.append(("Con bajas de precio", f"{m['pct_con_bajas']}%"))
    kpi_html = "".join(f'<div class="dato"><div class="lbl">{_e(a)}</div><div class="val">{_e(b)}</div></div>' for a, b in kpis)
    bloque_mapa = ""
    if mapa or kpis:
        bloque_mapa = (
            '<section class="sec evita-corte"><h2>Tu propiedad en el mercado</h2>'
            f'<p class="sec-exp">Se compararon {len(incluidos)} inmuebles parecidos en la zona.</p>'
            f'<div class="dos"><div>{mapa}</div><div><div class="ley">'
            '<div><span style="background:var(--sky-navy)"></span>Tu propiedad</div>'
            '<div><span style="background:var(--sky-blue)"></span>En venta: tu competencia</div>'
            '<div><span style="background:var(--success)"></span>Vendidos o retirados</div>'
            '<div><span style="background:var(--warn)"></span>Con bajas de precio o mucho tiempo publicados</div>'
            f'</div><div class="k">{kpi_html}</div></div></div></section>'
        )

    pm2 = r.get("precio_m2") or {}
    rango = ""
    if v.get("medio"):
        rango = (
            '<section class="sec evita-corte"><h2>Rango de precio</h2>'
            f'<p class="sec-exp">Con los precios por m² ya ajustados de los comparables, aplicados a los '
            f'{_num(r.get("superficie"))} m² de {"terreno" if r.get("base_superficie") == "terreno" else "construcción"} '
            'de tu propiedad. El centro del rango es donde se concentra el mercado.</p>'
            f'<div class="rango">{_barra_rango(r, moneda)}<div class="rango-v">'
            f'<div><div class="lbl">Parte baja</div><div class="val">{dinero(v.get("bajo"), moneda)}</div></div>'
            f'<div class="med"><div class="lbl">Centro del mercado</div><div class="val">{dinero(v.get("medio"), moneda)}</div></div>'
            f'<div><div class="lbl">Parte alta</div><div class="val">{dinero(v.get("alto"), moneda)}</div></div>'
            f'</div></div><p class="sec-exp" style="margin-top:10px">Precio por m² de referencia: '
            f'{dinero(pm2.get("p25"), moneda)} a {dinero(pm2.get("p75"), moneda)}.</p></section>'
        )

    nota = (f'<section class="sec evita-corte"><h2>Comentario de tu asesor</h2><div class="nota">{_e(fila.get("nota_propietario"))}</div></section>'
            if (fila.get("nota_propietario") or "").strip() else "")
    acciones = ""
    if not para_pdf:
        acciones = (f'<div class="acciones">{_boton_whatsapp(agente, titulo)}'
                    '<button class="btn-print" onclick="window.print()">Guardar como PDF</button></div>')

    cuerpo = (
        f'<div class="port"><div class="port-top">{logo}<div class="port-fecha">{_fecha_larga()}</div></div>'
        f'<div class="port-eti">Análisis comparativo de mercado</div><h1>{_e(titulo)}</h1>'
        f'<div class="port-dir">{_e(s.get("direccion") or lugar)}</div>'
        f'{f"<div class=port-valor>{valor_portada}</div>" if valor_portada else ""}'
        f'{_agente_html(agente)}</div>'
        f'{acciones}'
        f'<section class="sec"><h2>Tu propiedad</h2><div class="ficha">{ficha}</div></section>'
        f'{bloque_mapa}'
        + _seccion_grupo("Tu competencia", "Inmuebles parecidos que están en venta ahora mismo: son las opciones "
                         "que un comprador verá junto a la tuya.", grupos["activo"], numeros, moneda)
        + _seccion_grupo("Lo que el mercado sí pagó", "Inmuebles parecidos que ya se vendieron o dejaron de "
                         "anunciarse. Los marcados «Vendida» son operaciones reales con su precio de cierre.",
                         grupos["vendido"], numeros, moneda)
        + _seccion_grupo("Lo que pasa cuando se sale caro", "Inmuebles que tuvieron que bajar su precio o llevan "
                         "muchos meses publicados sin venderse.", grupos["bajas"], numeros, moneda)
        + (_tabla_ajustes(incluidos, numeros, moneda) if incluidos else "")
        + rango + _estrategia(e, moneda) + nota
        + '<div class="legal">Este documento es un análisis comparativo de mercado elaborado por tu asesor '
          'inmobiliario con información de inmuebles comparables. No es un avalúo. Los precios de oferta '
          'pueden diferir del precio final de venta.</div>'
    )
    tokens = theme_css_for_pdf("--r-xs:4px; --r-sm:8px; --r:12px; --r-lg:20px; --r-pill:999px;")
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        '<meta name="robots" content="noindex,nofollow"/>'
        f'<title>{_e(titulo)} · Análisis de mercado</title>'
        f"<style>{tokens}{_CSS}</style></head>"
        f'<body><div class="pag">{cuerpo}</div></body></html>'
    )


def render_no_disponible() -> str:
    tokens = theme_css_for_pdf("")
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/><meta name="robots" content="noindex"/>'
        f"<title>Análisis no disponible</title><style>{tokens}{_CSS}</style></head>"
        '<body><div class="pag"><section class="sec"><h2>Este análisis ya no está disponible</h2>'
        '<p class="sec-exp">Pídele a tu asesor una liga actualizada.</p></section></div></body></html>'
    )
