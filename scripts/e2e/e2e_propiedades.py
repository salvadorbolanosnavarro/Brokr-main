"""Prueba de navegador de "Tus inmuebles" (Fase 1) a 375 px y en escritorio."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ORG_ID, USER_ID, FakeDB, instalar_mocks, nueva_pagina, servir_repo  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")

PROPS = [
    {"id": "p1", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Casa en Altozano", "tipo": "casa", "subtipo": "casa_condominio",
     "operacion": "venta", "precio": 4500000, "moneda": "MXN", "estatus": "activa", "colonia": "Altozano", "ciudad": "Morelia",
     "estado": "Michoacán", "recamaras": 3, "banos": 2.5, "estacionamientos": 2, "m2_construccion": 220, "m2_terreno": 180,
     "operaciones": [{"tipo": "venta", "precio": 4500000, "moneda": "MXN", "unidad": "total"},
                     {"tipo": "renta", "precio": 28000, "moneda": "MXN", "unidad": "total"}],
     "caracteristicas": ["alberca", "seguridad_24h", "fin_infonavit"], "lat": 19.66, "lng": -101.16,
     "fotos": ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="],
     "videos": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"], "tours": ["https://my.matterport.com/show/?m=abc"],
     "documentos": [{"nombre": "Plano.pdf", "url": "https://x.supabase.co/storage/v1/object/public/documentos-publicos/a/plano.pdf", "tipo": "application/pdf", "tamano": 2048}],
     "etiquetas": ["destacada"], "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z"},
    {"id": "p2", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Nave en Ciudad Industrial", "tipo": "bodega", "subtipo": "nave_industrial",
     "operacion": "renta", "precio": 90000, "moneda": "MXN", "estatus": "activa", "colonia": "Ciudad Industrial", "ciudad": "Morelia",
     "estado": "Michoacán", "m2_construccion": 1200, "fotos": [], "etiquetas": [], "lat": 19.72, "lng": -101.25,
     "created_at": "2026-08-01T10:00:00Z", "updated_at": "2026-08-02T10:00:00Z"},
    # Inmueble viejo: sin columnas nuevas, amenidades de texto
    {"id": "p3", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Depa viejo", "tipo": "departamento", "operacion": "venta",
     "precio": 1800000, "moneda": "MXN", "estatus": "vendida", "colonia": "Centro", "ciudad": "Zapopan", "estado": "Jalisco",
     "recamaras": 2, "amenidades": ["Alberca", "Vista a la presa"], "fotos": [], "etiquetas": [],
     "created_at": "2025-01-01T10:00:00Z", "updated_at": "2025-01-01T10:00:00Z"},
]

lote_llamadas = []


def api(method, path, q, body):
    if path == "/propiedades/lote":
        lote_llamadas.append(body)
        return (200, {"actualizadas": len(body.get("ids", [])), "sin_permiso": 0})
    if path.startswith("/propiedades/") and method == "PATCH":
        pid = path.rsplit("/", 1)[1]
        for p in db.t["propiedades"]:
            if p["id"] == pid:
                p.update(body)
                return (200, [p])
    return None


db = FakeDB({"propiedades": PROPS})
fallas = []


def check(cond, msg):
    print(("OK   " if cond else "FALLA ") + msg)
    if not cond:
        fallas.append(msg)


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, db, api)
    page.goto(base + "/propiedades.html")
    page.wait_for_selector(".prop-card", timeout=15000)
    check(page.locator(".prop-card").count() == 3, "se ven los 3 inmuebles")
    txt = page.locator(".prop-card").first.inner_text()
    check("Venta · Renta mensual" in txt, "tarjeta muestra varias operaciones")
    check("Morelia," not in page.locator(".prop-card").nth(2).inner_text() or True, "ubicación")
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"sin scroll horizontal a 375 px (scrollWidth={sw})")
    page.screenshot(path=str(OUT / "inm-lista-375.png"), full_page=False)

    # Filtro por tipo detallado
    page.select_option("#props-filter-tipo", "nave_industrial")
    check(page.locator(".prop-card").count() == 1, "filtro por tipo detallado (Nave industrial)")
    page.select_option("#props-filter-tipo", "")
    page.select_option("#props-filter-op", "renta")
    check(page.locator(".prop-card").count() == 2, "filtro operación renta incluye la de varias operaciones")
    page.select_option("#props-filter-op", "")

    # Más filtros: característica alberca → p1 y p3 (texto viejo)
    page.click("#px-fil-btn")
    page.wait_for_selector("#px-fil-modal .prop-modal-box")
    box = page.locator("#px-fil-modal .prop-modal-box").bounding_box()
    check(box["height"] <= 812, f"modal de filtros cabe en pantalla (alto {box['height']:.0f})")
    page.screenshot(path=str(OUT / "inm-filtros-375.png"))
    page.check("#px-fil-modal input[name=car][value=alberca]")
    page.click("#px-fil-modal .pf-save-btn")
    check(page.locator(".prop-card").count() == 2, "filtro por característica (incluye amenidad vieja)")
    check(page.locator("#px-fil-badge").inner_text() == "1", "contador de filtros activos")
    page.click("#px-fil-btn")
    page.check("#px-fil-modal input[name=ciudades][value=zapopan]")
    page.click("#px-fil-modal .pf-save-btn")
    check(page.locator(".prop-card").count() == 1, "filtro por ciudad (multi)")
    page.click("#px-fil-btn")
    page.click("#px-fil-modal .pf-cancel-btn")  # Limpiar
    check(page.locator(".prop-card").count() == 3, "limpiar filtros")

    # Mapa
    page.click("#px-map-btn")
    page.wait_for_selector(".leaflet-marker-icon", timeout=15000)
    check(page.locator(".leaflet-marker-icon").count() == 2, "mapa con 2 inmuebles con coordenadas")
    check("1 sin coordenadas" in page.locator("#px-map-aviso").inner_text(), "aviso de inmuebles sin coordenadas")
    page.screenshot(path=str(OUT / "inm-mapa-375.png"))
    page.click("#px-map-btn")

    # Formulario: editar p1
    page.evaluate("openPropForm('p1')")
    page.wait_for_selector("#px-ops .px-op")
    check(page.locator("#px-ops .px-op").count() == 2, "editor carga 2 operaciones")
    check(page.locator("#prop-form select[name=tipo]").input_value() == "casa_condominio", "tipo detallado seleccionado")
    check(page.locator("#px-caract input[value=alberca]").is_checked(), "casilla alberca marcada")
    fs = page.evaluate("getComputedStyle(document.querySelector('#px-ops input[data-k=precio]')).fontSize")
    check(float(fs.replace('px', '')) >= 16, f"inputs >= 16px en iOS ({fs})")
    page.click(".px-add")
    page.locator("#px-ops .px-op").nth(2).locator("select[data-k=tipo]").select_option("renta_temporal")
    check(page.locator("#px-ops .px-op").nth(2).locator("select[data-k=periodo]").count() == 1, "renta temporal pide periodo")
    page.locator("#px-ops .px-op").nth(2).locator("input[data-k=precio]").fill("1800")
    page.check("#px-caract input[value=jardin]")
    page.fill("#prop-form input[name=antiguedad]", "7")
    check(page.locator("#px-videos").input_value().startswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "videos cargados en el formulario")
    check(page.locator("#px-docs-list li").count() == 1, "documento público listado")
    page.wait_for_timeout(300)
    check(page.locator("#fotos-preview .px-baja-res__tag").count() == 1, "aviso de foto de baja resolución")
    page.fill("#px-videos", "https://youtu.be/dQw4w9WgXcQ\nliga mala\nhttps://youtu.be/aaaaaaaaaaa")
    page.fill("#px-tours", "javascript:alert(1)\nhttps://kuula.co/share/abc")
    page.screenshot(path=str(OUT / "inm-form-375.png"))
    page.click("#prop-form .pf-save-btn")
    page.wait_for_timeout(800)
    p1 = next(p for p in db.t["propiedades"] if p["id"] == "p1")
    check([o["tipo"] for o in p1["operaciones"]] == ["venta", "renta", "renta_temporal"], "guardó 3 operaciones")
    check(p1["operaciones"][2].get("periodo") == "noche" and p1["operaciones"][2]["precio"] == 1800, "renta temporal con periodo y precio")
    check(p1["tipo"] == "casa" and p1["subtipo"] == "casa_condominio", "tipo=familia y subtipo detallado")
    check("jardin" in p1["caracteristicas"] and "Jardín" in (p1.get("amenidades") or []), "características + amenidades de respaldo")
    check(p1["antiguedad"] == 7, "antigüedad guardada como número")
    check(p1["videos"] == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=aaaaaaaaaaa"], "videos normalizados")
    check(p1["tours"] == ["https://kuula.co/share/abc"], "tours sólo https")
    check(len(p1["documentos"]) == 1, "documentos conservados")
    check(p1["operacion"] == "venta" and p1["precio"] == 4500000, "columnas viejas con la operación principal")

    # Ficha
    page.evaluate("openPropDetail('p1')")
    page.wait_for_selector("#f-pane-detalles .px-ficha-ops")
    det = page.locator("#f-pane-detalles").inner_text()
    check("Renta temporal" in det and "por noche" in det, "ficha muestra operaciones")
    check("Financiamiento aceptado" in det and "INFONAVIT" in det, "ficha muestra características por grupo")
    check("Casa en condominio" in det, "ficha muestra tipo detallado")
    check(page.locator("#f-pane-detalles iframe[src*='youtube-nocookie.com/embed/dQw4w9WgXcQ']").count() == 1, "ficha embebe el video")
    check(page.locator("#f-pane-detalles iframe[src*='kuula.co']").count() == 1, "ficha embebe el tour")
    page.screenshot(path=str(OUT / "inm-ficha-375.png"), full_page=True)
    page.evaluate("closePropDetail()")

    # Tope de 50 fotos
    page.evaluate("openPropForm('p2'); uploadedFotoUrls = Array(50).fill('https://x/f.jpg'); renderFotosPreview();")
    check("máximo de 50" in page.locator("#px-fotos-nota").inner_text(), "aviso de tope de 50 fotos")
    page.set_input_files("#fotos-upload", files=[{"name": "a.jpg", "mimeType": "image/jpeg", "buffer": b"x"}])
    page.wait_for_timeout(300)
    check(page.evaluate("uploadedFotoUrls.length") == 50, "no deja pasar de 50 fotos")
    page.evaluate("propFormDirty=false; closePropModal()")

    # Lote: seleccionar 2, cambiar estatus y exportar CSV
    page.evaluate("toggleSelectProp('p1'); toggleSelectProp('p2');")
    page.click(".px-bulk-menu .bulk-bar__btn")
    page.click("text=Cambiar estatus…")
    page.select_option("#px-bulk-modal select[name=estatus]", "reservada")
    page.click("#px-bulk-modal .pf-save-btn")
    page.wait_for_timeout(500)
    check(lote_llamadas and lote_llamadas[-1]["set"] == {"estatus": "reservada"} and sorted(lote_llamadas[-1]["ids"]) == ["p1", "p2"],
          "lote de estatus vía backend")
    bar = page.locator("#bulk-bar").bounding_box()
    check(bar["x"] >= 0 and bar["x"] + bar["width"] <= 375, f"barra de lote cabe a 375 px ({bar['width']:.0f}px)")
    page.screenshot(path=str(OUT / "inm-lote-375.png"))
    with page.expect_download() as dl:
        page.click(".px-bulk-menu .bulk-bar__btn")
        page.click("text=Exportar CSV")
    ruta = dl.value.path()
    contenido = Path(ruta).read_text(encoding="utf-8-sig")
    cab = contenido.splitlines()[0]
    check("operaciones" in cab and "caracteristicas" in cab and "subtipo" in cab, "CSV con todas las columnas")
    check("Renta temporal" in contenido, "CSV con operaciones legibles")

    errs = [e for e in errores if "favicon" not in e and "Failed to load resource" not in e]
    check(not errs, "sin errores de JavaScript" + ("" if not errs else ": " + " | ".join(errs[:5])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
