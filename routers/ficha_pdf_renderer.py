"""HTML renderer for the Ficha PDF domain."""
from __future__ import annotations

import base64

from core.pdf_design import theme_css_for_pdf


def build_ficha_html(p: dict, images_b64: dict) -> str:
    """Plantilla editorial Broquer para la ficha técnica en PDF — edición Sky.
    Portada con tarjeta flotante sobre la foto, franja de specs con
    iconografía propia, galería en cuadrícula, características agrupadas
    por categoría, y footer de marca "Powered by Broquer" en cada página.
    """
    import re as _re
    id_prop  = p.get("public_id") or p.get("id") or ""
    titulo_base = p.get("title") or p.get("property_type") or "Propiedad"
    ops      = p.get("operations") or []
    sale_op   = next((o for o in ops if o.get("type") == "sale"), None)
    rental_op = next((o for o in ops if o.get("type") == "rental"), None)
    if not sale_op and not rental_op and ops:
        sale_op = ops[0]  # fallback: operación sin type explícito

    def fmt_money(op):
        if not op or not op.get("amount"):
            return None
        monto  = op.get("amount", 0)
        moneda = op.get("currency", "MXN")
        base = "${:,.0f}".format(monto)
        return base if moneda == "MXN" else base + " " + moneda

    es_venta_renta = bool(sale_op and rental_op)
    precio_venta = fmt_money(sale_op)
    precio_renta = fmt_money(rental_op)
    precio_principal = precio_venta or precio_renta or "—"
    if es_venta_renta:
        tipo_op = "Venta y renta"
    elif rental_op:
        tipo_op = "Renta"
    else:
        tipo_op = "Venta"

    loc      = p.get("location") or {}
    colonia  = (loc.get("name") or "").strip()
    ciudad   = (loc.get("city") or "").strip()
    direccion= (p.get("address") or "").strip()
    ubicacion= ", ".join(filter(None, [colonia, ciudad])) or direccion or "—"

    rec      = p.get("bedrooms")
    ban      = p.get("bathrooms")
    mban     = p.get("half_bathrooms")
    m2c      = p.get("construction_size")
    m2t      = p.get("lot_size")
    parking  = p.get("parking_spaces")
    niveles  = p.get("floors")
    anio     = p.get("age")
    desc     = (p.get("description") or "").replace("<br>", " ").replace("<br/>", " ")
    desc     = _re.sub(r"<[^>]+>", "", desc).strip()
    fotos    = p.get("property_images") or []
    amenids  = p.get("amenities") or []
    tipo_inmueble = (p.get("property_type") or "").strip()
    titulo   = titulo_base

    def asset_data_uri(filename: str, mime: str = "image/png") -> str:
        try:
            with open(filename, "rb") as fh:
                return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
        except Exception:
            return ""

    logo_white = asset_data_uri("logotipo-white.png")

    def fmt_m2(n):
        if not n:
            return None
        s = "{:,.2f}".format(n).rstrip("0").rstrip(".")
        return s + " m²"

    # ── Iconografía propia (línea 1.5px, redondeada, grid 24×24) ──
    ICO = {
        "bed":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a3 3 0 013-3h12a3 3 0 013 3v6"/><path d="M3 18h18M3 18v2m18-2v2"/><path d="M7 12V9a1 1 0 011-1h3a1 1 0 011 1v3"/></svg>',
        "bath":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12V6.5A2.5 2.5 0 017.5 4a2.5 2.5 0 012.5 2.5"/><path d="M3 12h18v2a5 5 0 01-5 5H8a5 5 0 01-5-5v-2z"/><path d="M6 19v2m12-2v2"/></svg>',
        "toilet":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h6a1 1 0 011 1V8H6V4.5a1 1 0 011-1z"/><path d="M5.5 8h9a2 2 0 012 2c0 6-3 10.5-6.5 10.5S3.5 16 3.5 10a2 2 0 012-2z"/></svg>',
        "area":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M15 4h5v9M20 15v5h-5M9 20H4v-5"/></svg>',
        "land":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3L3 5.5v15L9 18l6 3 6-2.5v-15L15 6 9 3z"/><path d="M9 3v15M15 6v15"/></svg>',
        "parking": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 11l1.4-4.4A2 2 0 018.3 5h7.4a2 2 0 011.9 1.6L19 11"/><path d="M5 11h14a1 1 0 011 1v4a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H7v1a1 1 0 01-1 1H5a1 1 0 01-1-1v-4a1 1 0 011-1z"/><circle cx="7.5" cy="16.5" r="1.3"/><circle cx="16.5" cy="16.5" r="1.3"/></svg>',
        "levels":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5l8.5 4.5-8.5 4.5-8.5-4.5L12 2.5z"/><path d="M3.5 12l8.5 4.5 8.5-4.5"/><path d="M3.5 16.5L12 21l8.5-4.5"/></svg>',
        "calendar":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M16 3v4M8 3v4M3.5 10h17"/></svg>',
        "tag":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.7 2.6a1.8 1.8 0 00-1.3-.5H4.3A1.8 1.8 0 002.5 3.9v6.1c0 .5.2.9.5 1.3l8 8a2.2 2.2 0 003 0l6-6a2.2 2.2 0 000-3.1l-8-8z"/><circle cx="7" cy="7.2" r="1.4"/></svg>',
        "pin":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21.3S5.5 14.8 5.5 9.8a6.5 6.5 0 0113 0c0 5-6.5 11.5-6.5 11.5z"/><circle cx="12" cy="9.8" r="2.4"/></svg>',
        "route":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18h7a4 4 0 004-4V9"/></svg>',
        "home":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 11.2L12 4l8.5 7.2"/><path d="M5.5 9.8v9.7a1 1 0 001 1H9v-6h6v6h2.5a1 1 0 001-1V9.8"/></svg>',
        "swap":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13l-3.5-3.5M20 16H7l3.5 3.5"/></svg>',
        "photo":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.5" cy="10" r="1.6"/><path d="M21 15.5l-5.2-5.2a1.5 1.5 0 00-2.1 0L5 19"/></svg>',
        "sparkles":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3z"/><path d="M19 15l.7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3z"/></svg>',
        "list":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg>',
    }

    # ── Specs de portada (hasta 6) ──
    specs = []
    if rec:    specs.append((ICO["bed"], str(int(rec)) if float(rec).is_integer() else str(rec), "Recámaras"))
    if ban:    specs.append((ICO["bath"], str(int(ban)) if float(ban).is_integer() else str(ban), "Baños"))
    if mban:   specs.append((ICO["toilet"], str(int(mban)) if float(mban).is_integer() else str(mban), "Medios baños"))
    def fmt_num(n):
        if not n:
            return None
        s = "{:,.2f}".format(n).rstrip("0").rstrip(".")
        return s

    if m2c:    specs.append((ICO["area"], fmt_num(m2c), "m² const."))
    if m2t:    specs.append((ICO["land"], fmt_num(m2t), "m² terreno"))
    if parking and len(specs) < 6: specs.append((ICO["parking"], str(int(parking)) if float(parking).is_integer() else str(parking), "Estac."))
    if niveles and len(specs) < 6: specs.append((ICO["levels"], str(int(niveles)) if float(niveles).is_integer() else str(niveles), "Niveles"))
    specs = specs[:6]

    specs_items = "".join(
        '<div class="spec-item"><div class="spec-ico">{}</div><div class="spec-val">{}</div><div class="spec-lbl">{}</div></div>'.format(i, v, l)
        for i, v, l in specs
    )
    specs_html = '<div class="cover-specs" style="--spec-cols:{}">{}</div>'.format(len(specs), specs_items) if specs_items else ""

    foto_urls = [f.get("url") or f.get("original") or "" for f in fotos if f]
    foto_urls = [u for u in foto_urls if u]
    hero_src  = images_b64.get(foto_urls[0], foto_urls[0]) if foto_urls else ""
    hero_html = '<img class="cover-hero" src="{}" alt="portada"/>'.format(hero_src) if hero_src else '<div class="cover-hero-placeholder">{}</div>'.format(ICO["home"])
    total_fotos = len(foto_urls)
    photocount_html = ''
    if total_fotos:
        photocount_html = '<div class="cover-photocount">{}{} foto{}</div>'.format(ICO["photo"], total_fotos, "" if total_fotos == 1 else "s")
    brandmark_html = '<div class="cover-brandmark"><img src="{}" alt="Broquer"/></div>'.format(logo_white) if logo_white else '<div class="cover-brandmark"><strong style="color:#fff">Broquer</strong></div>'

    def footer(page_num, total_pages):
        logo = '<img src="{}" alt="Broquer"/>'.format(logo_white) if logo_white else '<strong>Broquer</strong>'
        id_html = '<span class="ft-id">{}</span>'.format(id_prop) if id_prop else ''
        return (
            '<div class="ficha-footer">'
            '<div class="ft-brand">{}<span>Powered by Broquer</span></div>'
            '<div class="ft-meta">{}<span>{} / {}</span></div>'
            '</div>'
        ).format(logo, id_html, page_num, total_pages)

    precio_sec_html = ""
    if es_venta_renta and precio_renta:
        precio_sec_html = '<div class="cover-precio-sec">También disponible en renta: <b>{}/mes</b></div>'.format(precio_renta)

    cover_content = (
        '<div class="cover-hero-wrap">{}{}{}</div>'
        '<div class="cover-card">'
        '<div class="cover-card-top">'
        '<div class="cover-precio-block">'
        '<div class="cover-badge">{}</div>'
        '<div class="cover-precio">{}</div>{}'
        '</div>'
        '<div class="cover-tipo-pill">{}</div>'
        '</div>'
        '<div class="cover-titulo">{}</div>'
        '<div class="cover-ubicacion">{}{}</div>'
        '{}'
        '</div>'
        '{}'
    ).format(
        hero_html, brandmark_html, photocount_html,
        tipo_op, precio_principal, precio_sec_html,
        ICO["home"],
        titulo,
        ICO["pin"], ubicacion,
        specs_html,
        '<div class="cover-desc-wrap"><div class="cover-desc-ttl">Descripción</div><div class="cover-desc">{}</div></div>'.format(desc) if desc else '<div style="flex:1"></div>'
    )

    # ── Páginas de galería (6 fotos por página, igual que en el frontend) ──
    gallery_fotos = foto_urls[1:]
    gallery_contents = []
    for i in range(0, len(gallery_fotos), 6):
        batch = gallery_fotos[i:i+6]
        batch = batch + [None] * (6 - len(batch))
        imgs = "".join(
            '<img src="{}" alt="foto"/>'.format(images_b64.get(u, u)) if u else '<div class="ph-empty"></div>'
            for u in batch
        )
        gallery_contents.append(
            '<div class="fp-kicker"><div class="fp-kicker-left"><div class="fp-kicker-ico">{}</div><h2>Galería fotográfica</h2></div>'
            '<div class="fp-kicker-id">{}</div></div>'
            '<div class="photo-grid">{}</div>'.format(ICO["photo"], ubicacion, imgs)
        )

    # ── Características agrupadas por categoría ──
    def char_item(icon, lbl, val):
        return '<div class="char-item"><div class="char-ico">{}</div><div class="char-txt"><div class="char-lbl">{}</div><div class="char-val">{}</div></div></div>'.format(icon, lbl, val)

    prec_rows = []
    prec_rows.append(char_item(ICO["swap"], "Operación", tipo_op))
    if precio_venta: prec_rows.append(char_item(ICO["tag"], "Precio de venta" if es_venta_renta else "Precio", precio_venta))
    if es_venta_renta and precio_renta: prec_rows.append(char_item(ICO["tag"], "Precio de renta", precio_renta + "/mes"))
    if not precio_venta and not es_venta_renta and precio_renta: pass  # ya cubierto como precio principal arriba

    dist_rows = []
    if tipo_inmueble: dist_rows.append(char_item(ICO["home"], "Tipo de inmueble", tipo_inmueble))
    if rec:  dist_rows.append(char_item(ICO["bed"], "Recámaras", rec))
    if ban:  dist_rows.append(char_item(ICO["bath"], "Baños completos", ban))
    if mban: dist_rows.append(char_item(ICO["toilet"], "Medios baños", mban))
    if niveles: dist_rows.append(char_item(ICO["levels"], "Niveles", niveles))
    if anio: dist_rows.append(char_item(ICO["calendar"], "Año de construcción", anio))

    sup_rows = []
    if fmt_m2(m2c): sup_rows.append(char_item(ICO["area"], "Superficie construida", fmt_m2(m2c)))
    if fmt_m2(m2t): sup_rows.append(char_item(ICO["land"], "Superficie de terreno", fmt_m2(m2t)))
    if parking: sup_rows.append(char_item(ICO["parking"], "Estacionamientos", parking))

    ub_rows = []
    if colonia: ub_rows.append(char_item(ICO["pin"], "Colonia", colonia))
    if ciudad:  ub_rows.append(char_item(ICO["pin"], "Ciudad", ciudad))
    if direccion: ub_rows.append(char_item(ICO["route"], "Dirección", direccion))
    if id_prop: ub_rows.append(char_item(ICO["tag"], "Clave", id_prop))

    def group_html(titulo_grupo, rows):
        if not rows:
            return ""
        return '<div class="chars-group"><div class="chars-group-ttl">{}</div><div class="chars-grid">{}</div></div>'.format(titulo_grupo, "".join(rows))

    amen_html = ""
    if amenids:
        items = "".join('<div class="amen-item">{}{}</div>'.format(ICO["sparkles"], a.get("name") or a) for a in amenids)
        amen_html = '<div class="chars-group amen-section"><div class="chars-group-ttl">Amenidades y extras</div><div class="amen-grid">{}</div></div>'.format(items)

    chars_content = (
        '<div class="fp-kicker"><div class="fp-kicker-left"><div class="fp-kicker-ico">{}</div><h2>Características del inmueble</h2></div>'
        '<div class="fp-kicker-id">{}</div></div>'
        '<div class="chars-body">{}{}{}{}{}</div>'
    ).format(
        ICO["list"], id_prop,
        group_html("Operación y precio", prec_rows),
        group_html("Distribución", dist_rows),
        group_html("Superficie y estacionamiento", sup_rows),
        group_html("Ubicación", ub_rows),
        amen_html,
    )

    all_contents = [cover_content] + gallery_contents + [chars_content]
    total_pages = len(all_contents)
    pages_html = "".join(
        '<div class="ficha-page">{}{}</div>'.format(content, footer(i + 1, total_pages))
        for i, content in enumerate(all_contents)
    )

    # ── Sistema de diseño ──
    # Los colores salen de brokr-theme.css vía theme_css_for_pdf(): este
    # archivo ya no los duplica. Cero JetBrains Mono, cero mayúsculas
    # decorativas.
    # Tokens desde brokr-theme.css. Radios y sombras propios del
    # documento: la ficha es un impreso, no una pantalla.
    CSS = theme_css_for_pdf(
        "--r:14px; --r-sm:8px; --r-lg:28px; --r-pill:999px;"
        "--shadow-sm:0 1px 3px rgba(0,20,59,.10),0 1px 2px rgba(0,20,59,.06);"
        "--shadow-lg:0 18px 44px rgba(0,20,59,.18),0 4px 12px rgba(0,20,59,.10);"
    ) + """
*{box-sizing:border-box;margin:0;padding:0;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;color-adjust:exact!important}
html,body{width:210mm}
body{font-family:var(--font-sans);background:var(--paper);color:var(--ink);-webkit-font-smoothing:antialiased}
.ficha-page{position:relative;width:210mm;height:297mm;background:var(--paper);display:flex;flex-direction:column;overflow:hidden;page-break-after:always}
.ficha-page:last-child{page-break-after:avoid}

.fp-kicker{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;border-bottom:1px solid var(--line)}
.fp-kicker-left{display:flex;align-items:center;gap:10px}
.fp-kicker-ico{width:20px;height:20px;color:var(--sky-blue);flex-shrink:0}.fp-kicker-ico svg{width:100%;height:100%}
.fp-kicker h2{font-family:var(--font-display);font-size:17px;font-weight:700;color:var(--ink);letter-spacing:-.02em}
.fp-kicker-id{font-size:11px;color:var(--mute-2)}

.cover-hero-wrap{width:100%;height:128mm;position:relative;flex-shrink:0;background:linear-gradient(135deg,var(--sky-navy),var(--ink-2))}
.cover-hero{width:100%;height:100%;object-fit:cover;display:block}
.cover-hero-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.cover-hero-placeholder svg{width:56px;height:56px;color:rgba(255,255,255,.35)}
.cover-brandmark{position:absolute;top:16px;left:20px;height:20px}.cover-brandmark img{height:100%;width:auto;display:block}
.cover-photocount{position:absolute;top:16px;right:20px;background:rgba(5,32,60,.55);color:#fff;font-size:11px;font-weight:500;padding:5px 11px;border-radius:var(--r-pill);display:flex;align-items:center;gap:5px}
.cover-photocount svg{width:13px;height:13px}

.cover-card{margin:-22mm 16mm 0;background:var(--bone);border-radius:var(--r-lg);box-shadow:var(--shadow-lg);border:1px solid var(--line);padding:20px 24px 4px;position:relative;z-index:2}
.cover-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}
.cover-badge{display:inline-flex;align-items:center;background:var(--sky-navy);color:#fff;font-size:12px;font-weight:600;padding:5px 12px;border-radius:var(--r-pill);margin-bottom:10px}
.cover-precio-block{display:flex;flex-direction:column}
.cover-precio{font-family:var(--font-display);font-size:34px;font-weight:700;letter-spacing:-.03em;color:var(--ink);line-height:1.05}
.cover-precio-sec{font-size:12.5px;color:var(--mute);margin-top:4px;font-weight:500}
.cover-precio-sec b{color:var(--ink-2);font-weight:600}
.cover-tipo-pill{flex-shrink:0;width:46px;height:46px;border-radius:var(--r);background:var(--paper-2);display:flex;align-items:center;justify-content:center;color:var(--sky-navy)}
.cover-tipo-pill svg{width:22px;height:22px}
.cover-titulo{font-family:var(--font-display);font-size:16px;font-weight:700;color:var(--ink);margin-bottom:5px;letter-spacing:-.015em}
.cover-ubicacion{font-size:12.5px;color:var(--mute);display:flex;align-items:center;gap:5px;padding-bottom:16px}
.cover-ubicacion svg{width:13px;height:13px;flex-shrink:0;color:var(--mute-2)}
.cover-specs{display:grid;grid-template-columns:repeat(var(--spec-cols,4),1fr);border-top:1px solid var(--line);margin:0 -24px;padding:0 24px}
.spec-item{padding:13px 6px 12px;text-align:center;border-right:1px solid var(--line)}
.spec-item:last-child{border-right:none}
.spec-ico{width:20px;height:20px;margin:0 auto 6px;color:var(--sky-blue)}.spec-ico svg{width:100%;height:100%}
.spec-val{font-family:var(--font-display);font-size:16px;font-weight:700;color:var(--ink);line-height:1.1;letter-spacing:-.02em}
.spec-lbl{font-size:10.5px;color:var(--mute);margin-top:3px;font-weight:500}
.cover-desc-wrap{padding:18px 24px 14px;flex:1}
.cover-desc-ttl{font-family:var(--font-display);font-size:13px;font-weight:700;color:var(--ink);margin-bottom:8px;letter-spacing:-.01em}
.cover-desc{font-size:11.5px;color:var(--ink-2);line-height:1.7}

.photo-grid{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:4px;padding:4px;flex:1;overflow:hidden;background:var(--paper-2)}
.photo-grid img{width:100%;height:100%;object-fit:cover;display:block}
.photo-grid .ph-empty{width:100%;height:100%;background:var(--paper-2)}

.chars-body{padding:20px 24px 8px;flex:1}
.chars-group{margin-bottom:18px}
.chars-group-ttl{font-size:11px;font-weight:700;color:var(--mute);text-transform:uppercase;letter-spacing:.06em;margin-bottom:9px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.chars-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.char-item{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--paper-2);border-radius:var(--r-sm)}
.char-ico{width:18px;height:18px;color:var(--sky-blue);flex-shrink:0}.char-ico svg{width:100%;height:100%}
.char-txt{min-width:0}
.char-lbl{font-size:10px;color:var(--mute);margin-bottom:1px}
.char-val{font-size:13px;font-weight:600;color:var(--ink);letter-spacing:-.01em;overflow-wrap:anywhere}
.amen-grid{display:flex;flex-wrap:wrap;gap:7px}
.amen-item{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;padding:6px 12px;background:var(--paper-2);border-radius:var(--r-pill);color:var(--ink-2);border:1px solid var(--line);font-weight:500}
.amen-item svg{width:12px;height:12px;color:var(--sky-blue);flex-shrink:0}

.ficha-footer{width:100%;height:42px;background:var(--sky-navy);display:flex;align-items:center;justify-content:space-between;padding:0 22px;flex-shrink:0;margin-top:auto}
.ft-brand{display:flex;align-items:center;gap:8px}
.ft-brand img{height:16px;width:auto;display:block;opacity:.95}
.ft-brand span{font-size:10px;font-weight:500;color:rgba(255,255,255,.6);letter-spacing:.01em}
.ft-meta{display:flex;align-items:center;gap:10px;font-size:10px;color:rgba(255,255,255,.5)}
.ft-id{letter-spacing:.03em}
@page{size:A4 portrait;margin:0}
"""

    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'/>"
        "<style>{}</style></head><body>{}</body></html>"
    ).format(CSS, pages_html)
