from __future__ import annotations

from fastapi import APIRouter


def create_router(get_context):
    router = APIRouter()

    @router.post("/avm-pdf")
    async def generar_avm_pdf(p: dict):
        """Recibe el resultado del AVM websearch y genera un PDF profesional con Playwright.

        Sistema de diseño: los mismos tokens de brokr-theme.css (navy, azul,
        Manrope, radios, sombras) que usa el resto de Broquer — para que este
        documento se sienta hermano de la Ficha técnica y del ISR, no un
        invitado con otra identidad visual.
        """
        from playwright.async_api import async_playwright

        deps = get_context()
        HTTPException = deps["HTTPException"]
        theme_css_for_pdf = deps["theme_css_for_pdf"]
        pdf_store = deps["_pdf_store"]
        uuid_mod = deps["_uuid"]
        time_mod = deps["time"]

        resultado = p.get("resultado", {})
        agente = p.get("agente", "Agente Broquer")

        if not resultado:
            raise HTTPException(status_code=400, detail="Resultado vacío")

        def fmt_mx(n):
            try:
                return "${:,.0f}".format(float(n))
            except Exception:
                return str(n)

        def _esc(s):
            return (str(s) if s is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

        # Comparables
        comps_html = ""
        for c in resultado.get("comparables", []):
            fuente = c.get("fuente","—") or "—"
            url = c.get("url","") or ""
            src_cell = (
                f'<a href="{_esc(url)}" target="_blank" rel="noopener" class="link">{_esc(fuente)}</a>'
                if url else _esc(fuente)
            )
            comps_html += f"""
            <tr>
              <td>{_esc(c.get('descripcion','—'))}</td>
              <td class="num">{_esc(c.get('superficie_m2','—'))} m²</td>
              <td class="num">{fmt_mx(c.get('precio',0))}</td>
              <td class="num">{fmt_mx(c.get('precio_m2',0))}/m²</td>
              <td class="src">{src_cell}</td>
            </tr>"""

        # Factores de ajuste — badge con punto, mismo patrón que .bk-badge del app
        factores_html = ""
        for f in resultado.get("factores_ajuste", []):
            imp = f.get("impacto", "neutro")
            badge_cls = "badge--success" if imp == "positivo" else "badge--danger" if imp == "negativo" else "badge--mute"
            etiqueta = "Favorable" if imp == "positivo" else "Desfavorable" if imp == "negativo" else "Neutro"
            factores_html += f"""
            <tr>
              <td>
                <div class="factor-nombre">{_esc(f.get('factor','—'))}</div>
                <span class="badge {badge_cls}"><span class="dot"></span>{etiqueta}</span>
              </td>
              <td class="factor-desc">{_esc(f.get('descripcion','—'))}</td>
            </tr>"""

        recs_html = "".join(f"<li>{_esc(r)}</li>" for r in resultado.get("recomendaciones", []))

        m2c = resultado.get("m2_construccion", 0)
        m2t = resultado.get("m2_terreno", 0)
        sup_parts = []
        if m2t: sup_parts.append(f"{m2t} m² terreno")
        if m2c: sup_parts.append(f"{m2c} m² construcción")
        superficie_str = " · ".join(sup_parts) if sup_parts else "—"

        fecha_hoy = resultado.get("fecha", time_mod.strftime("%d/%m/%Y"))
        operacion = (resultado.get('operacion','venta') or 'venta').capitalize()

        # Tokens desde brokr-theme.css. Radios propios del documento.
        _AVM_TOKENS = theme_css_for_pdf(
            "--r-xs:4px; --r-sm:8px; --r:14px; --r-lg:28px; --r-pill:999px;"
        )
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<style>
{_AVM_TOKENS}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font-sans); color: var(--ink); background: var(--paper); font-size: 13px; line-height: 1.55; -webkit-font-smoothing: antialiased; letter-spacing: -0.01em; }}
  .page {{ padding: 48px 52px 40px; max-width: 780px; margin: 0 auto; }}

  /* ── Encabezado de documento ── */
  .doc-head {{ display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 20px; border-bottom: 1px solid var(--line); margin-bottom: 28px; }}
  .doc-head__brand {{ font-size: 15px; font-weight: 700; color: var(--sky-navy); letter-spacing: -0.01em; }}
  .doc-head__title {{ font-size: 12px; color: var(--mute); margin-top: 2px; }}
  .doc-head__date {{ font-size: 11px; color: var(--mute); }}

  /* ── Bloque de valor — tarjeta navy, no negro genérico ── */
  .valor-card {{
    background: linear-gradient(155deg, var(--sky-navy), var(--sky-navy-mid));
    border-radius: var(--r-lg);
    padding: 26px 28px 22px;
    margin-bottom: 22px;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }}
  .valor-lbl {{ font-size: 11px; color: rgba(255,255,255,.65); font-weight: 600; letter-spacing: 0.02em; margin-bottom: 6px; }}
  .valor-num {{ font-family: var(--font-sans); font-size: 34px; font-weight: 700; color: #fff; line-height: 1.05; letter-spacing: -0.02em; }}
  .valor-meta {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 18px; margin-top: 20px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.14); }}
  .meta-item .meta-lbl {{ font-size: 10px; color: rgba(255,255,255,.55); font-weight: 600; letter-spacing: 0.02em; margin-bottom: 4px; }}
  .meta-item .meta-val {{ font-size: 13px; font-weight: 700; color: #fff; letter-spacing: -0.005em; }}

  /* ── Secciones ── */
  .seccion {{ margin-bottom: 26px; }}
  .sec-titulo {{ font-size: 11px; font-weight: 700; color: var(--mute); letter-spacing: 0.02em; margin-bottom: 12px; }}
  .resumen {{ font-size: 12.5px; color: var(--ink-2); line-height: 1.7; text-align: justify; }}

  /* ── Badge con punto — idéntico a .bk-badge del app ── */
  .badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: var(--r-pill);
    font-size: 11px; font-weight: 700; letter-spacing: 0.02em;
    background: var(--paper-2); color: var(--mute);
  }}
  .badge .dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
  .badge--success {{ background: var(--success-soft); color: var(--success); }}
  .badge--danger  {{ background: var(--danger-soft);  color: var(--danger); }}
  .badge--mute    {{ background: var(--paper-2);       color: var(--mute); }}

  /* ── Tablas ── */
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ font-weight: 700; color: var(--mute); text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line-2); font-size: 10px; letter-spacing: 0.02em; }}
  td {{ padding: 12px 6px; border-bottom: 1px solid var(--line); color: var(--ink); vertical-align: top; }}
  td.num {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); }}
  .link {{ color: var(--forest); text-decoration: underline; }}
  tr:last-child td {{ border-bottom: none; }}

  .factor-nombre {{ font-weight: 700; font-size: 12.5px; margin-bottom: 5px; }}
  .factor-desc {{ color: var(--mute); font-size: 11.5px; line-height: 1.5; }}

  .recs {{ padding-left: 18px; }}
  .recs li {{ font-size: 12.5px; color: var(--ink-2); line-height: 1.7; margin-bottom: 4px; }}

  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line); text-align: center; font-size: 10px; color: var(--mute-2); letter-spacing: 0.02em; }}
</style>
</head>
<body>
<div class="page">

  <div class="doc-head">
    <div>
      <div class="doc-head__brand">Broquer</div>
      <div class="doc-head__title">Estimación de valor</div>
    </div>
    <div class="doc-head__date">{fecha_hoy}</div>
  </div>

  <div class="valor-card">
    <div class="valor-lbl">Valor estimado</div>
    <div class="valor-num">{fmt_mx(resultado.get('valor_estimado',0))}</div>
    <div class="valor-meta">
      <div class="meta-item">
        <div class="meta-lbl">Inmueble</div>
        <div class="meta-val">{_esc(resultado.get('tipo_inmueble','—'))}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Superficie</div>
        <div class="meta-val">{_esc(superficie_str)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Ubicación</div>
        <div class="meta-val">{_esc(resultado.get('colonia','—'))}, {_esc(resultado.get('ciudad','Morelia'))}</div>
      </div>
      <div class="meta-item">
        <div class="meta-lbl">Operación</div>
        <div class="meta-val">{_esc(operacion)}</div>
      </div>
    </div>
  </div>

  <div class="seccion">
    <div class="sec-titulo">Análisis</div>
    <div class="resumen">{_esc(resultado.get('resumen_ejecutivo','—'))}</div>
  </div>

  <div class="seccion">
    <div class="sec-titulo">Comparables de mercado</div>
    <table>
      <thead>
        <tr>
          <th>Propiedad</th>
          <th style="text-align:right">Superficie</th>
          <th style="text-align:right">Precio</th>
          <th style="text-align:right">$/m²</th>
          <th>Fuente</th>
        </tr>
      </thead>
      <tbody>{comps_html}</tbody>
    </table>
  </div>

  {"" if not factores_html else f'''
  <div class="seccion">
    <div class="sec-titulo">Factores de ajuste</div>
    <table>
      <tbody>{factores_html}</tbody>
    </table>
  </div>
  '''}

  {"" if not recs_html else f'''
  <div class="seccion">
    <div class="sec-titulo">Recomendaciones</div>
    <ul class="recs">{recs_html}</ul>
  </div>
  '''}

  <div class="footer">Powered by Broquer</div>

</div>
</body>
</html>"""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page()
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(400)
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
            )
            await browser.close()

        token = str(uuid_mod.uuid4()).replace("-", "")[:16]
        colonia_slug = resultado.get("colonia", "propiedad").replace(" ", "_")[:20]
        filename = f"Estimacion_Valor_{colonia_slug}_{time_mod.strftime('%Y%m%d')}.pdf"
        pdf_store[token] = (pdf_bytes, filename)
        if len(pdf_store) > 50:
            oldest = list(pdf_store.keys())[0]
            del pdf_store[oldest]

        from fastapi.responses import JSONResponse
        return JSONResponse({"token": token, "filename": filename})

    return router
