"""Prueba de navegador: Bolsa (detalle con multimedia) y micrositio público."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import FakeDB, instalar_mocks, nueva_pagina, servir_repo  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
fallas = []


def check(cond, msg):
    print(("OK   " if cond else "FALLA ") + msg)
    if not cond:
        fallas.append(msg)


PROP = {"id": "p1", "titulo": "Casa con alberca", "tipo": "casa", "subtipo": "casa_condominio", "operacion": "venta",
        "precio": 4500000, "moneda": "MXN", "colonia": "Altozano", "ciudad": "Morelia", "estado": "Michoacán",
        "recamaras": 3, "banos": 2, "fotos": [], "descripcion": "Bonita",
        "operaciones": [{"tipo": "venta", "precio": 4500000, "moneda": "MXN"}, {"tipo": "preventa", "precio": 4000000, "moneda": "MXN"}],
        "caracteristicas": ["alberca", "fin_fovissste"], "videos": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        "tours": ["https://kuula.co/share/abc"],
        "documentos": [{"nombre": "Lista de precios.pdf", "url": "https://x.supabase.co/storage/v1/object/public/documentos-publicos/a.pdf"}],
        "bolsa_comision": 50, "propia": False, "agente": {"nombre": "Ana", "telefono": "4431234567"}}


def api(method, path, q, body):
    if path == "/bolsa/propiedades":
        return (200, {"propiedades": [PROP], "total": 1, "page": 1, "paginas": 1})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    # ── Bolsa ──
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB(), api)
    page.goto(base + "/bolsa.html")
    page.wait_for_selector(".bl-card", timeout=15000)
    card = page.locator(".bl-card").first.inner_text()
    check("Venta" in card and "Preventa" in card, "tarjeta de Bolsa con varias operaciones")
    check("Casa en condominio" in card, "tarjeta con tipo detallado")
    check("Alberca" in card, "tarjeta con características")
    opts = page.locator("#bl-f-tipo optgroup").count()
    check(opts == 4, f"filtro de tipos agrupado ({opts} grupos)")
    page.locator(".bl-card").first.click()
    page.wait_for_selector("#bl-detalle.is-open")
    check(page.locator("#bl-detalle iframe[src*='youtube-nocookie']").count() == 1, "detalle de Bolsa embebe video")
    check(page.locator("#bl-detalle iframe[src*='kuula']").count() == 1, "detalle de Bolsa embebe tour")
    check("Lista de precios.pdf" in page.locator("#bl-detalle").inner_text(), "detalle de Bolsa con documento")
    check("Financiamiento aceptado" in page.locator("#bl-detalle").inner_text(), "detalle con financiamiento")
    page.screenshot(path=str(OUT / "bolsa-detalle-375.png"))
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"Bolsa sin scroll horizontal ({sw})")

    # ── Micrositio ──
    db = FakeDB({
        "usuarios_publicos": [{"id": "u1", "slug": "chava", "nombre_publico": "Chava", "whatsapp_publico": "4431234567"}],
        "propiedades_publicas": [{"id": "p1", "user_id": "u1", "titulo": "Casa con alberca", "tipo": "casa", "operacion": "venta",
                                  "precio": 4500000, "colonia": "Altozano", "ciudad": "Morelia", "estatus": "activa", "fotos": []}],
        "propiedades_publicas_extra": [{k: PROP[k] for k in ("id", "subtipo", "operaciones", "caracteristicas", "videos", "tours", "documentos")}],
        "testimonios_publicos": [],
    })
    page2, err2 = nueva_pagina(br, base)
    instalar_mocks(page2, db)
    page2.goto(base + "/sitio.html?slug=chava")
    page2.wait_for_selector(".st-card", timeout=15000)
    check("Preventa" in page2.locator(".st-card").first.inner_text(), "micrositio muestra operaciones")
    check(page2.locator(".st-tab[data-op=preventa]").count() == 1, "micrositio con pestaña Preventa")
    page2.locator(".st-card").first.click()
    page2.wait_for_selector(".st-modal")
    check(page2.locator(".st-modal iframe[src*='youtube-nocookie']").count() == 1, "micrositio embebe video")
    check("Lista de precios.pdf" in page2.locator(".st-modal").inner_text(), "micrositio con documento descargable")
    page2.screenshot(path=str(OUT / "sitio-detalle-375.png"))
    errs = [e for e in errores + err2 if "Failed to load resource" not in e and "favicon" not in e]
    check(not errs, "sin errores de JavaScript" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
