"""Prueba de navegador del sitio web (Fase 7): páginas públicas renderizadas
en servidor a 375 px y el editor dentro de Mi sitio."""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import uvicorn
from fastapi import FastAPI
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ORG_ID, USER_ID, FakeDB, instalar_mocks, nueva_pagina, servir_repo  # noqa: E402

import routers.sitios as S  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
fallas = []


def check(cond, msg):
    print(("OK   " if cond else "FALLA ") + msg)
    if not cond:
        fallas.append(msg)


P1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SITIO = {"id": "s1", "slug": "grupo-prueba", "org_id": ORG_ID, "tipo": "organizacion", "user_id": None, "activo": True,
         "nombre": "Grupo Prueba Inmobiliaria", "eslogan": "Tu casa en Morelia", "color_primario": "#0b2545", "color_secundario": "#13a89e",
         "mostrar_asesor": True, "traductor": True, "whatsapp": "4431234567", "telefono": "443 123 4567", "email": "hola@prueba.mx",
         "ga4_id": "G-TEST123", "redes": {"facebook": "https://facebook.com/prueba"}, "dominio": None, "dominio_estado": "sin_dominio"}
PROPS = [{"id": P1, "org_id": ORG_ID, "estatus": "activa", "titulo": "Casa con alberca en Altozano con jardín muy amplio", "tipo": "casa",
          "ciudad": "Morelia", "estado": "Michoacán", "colonia": "Altozano", "recamaras": 3, "banos": 2.5, "m2_construccion": 240,
          "descripcion": "Casa iluminada con alberca.", "fotos": [], "calle": "Privada Secreta 1", "notas": "NOTA INTERNA",
          "operaciones": [{"tipo": "venta", "precio": 4500000, "moneda": "MXN"}], "caracteristicas": ["alberca"], "user_id": USER_ID}]
for i in range(5):
    PROPS.append({"id": f"bbbbbbbb-bbbb-bbbb-bbbb-00000000000{i}", "org_id": ORG_ID, "estatus": "activa", "titulo": f"Departamento {i}",
                  "tipo": "departamento", "ciudad": "Morelia", "colonia": "Centro", "recamaras": 2, "fotos": [],
                  "operaciones": [{"tipo": "renta", "precio": 12000 + i, "moneda": "MXN"}]})
PAGINAS = [{"id": "pg1", "sitio_id": "s1", "titulo": "Vende con nosotros", "slug": "vende", "publicada": True, "en_menu": True,
            "contenido_html": "<h2>Te ayudamos a vender</h2><p>Avalúo sin costo.</p><ul><li>Fotos</li><li>Portales</li></ul>"}]
leads = []


async def get_rows(t, params, timeout=None):
    if t == "sitios":
        return [dict(SITIO)] if "dominio" not in params else []
    if t == "propiedades":
        return [dict(p) for p in PROPS if "id" not in params or p["id"] == params["id"][3:]]
    if t == "sitio_paginas":
        return [dict(p) for p in PAGINAS if "slug" not in params or p["slug"] == params["slug"].split(".", 1)[1]]
    if t == "organizacion_miembros":
        return [{"user_id": USER_ID, "org_id": ORG_ID}]
    if t == "usuarios":
        return [{"nombre": "Ana Asesora", "telefono": "4430000000"}]
    return []


async def registrar_lead(**kw):
    leads.append(kw)
    return {"ok": True}


def puerto():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


parches = [mock.patch.object(S, "get_rows", get_rows), mock.patch("core.buzon.registrar_lead", registrar_lead)]
for p in parches:
    p.start()
app = FastAPI()
app.include_router(S.router)
S.instalar_middleware(app)
PORT = puerto()
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)
API = f"http://127.0.0.1:{PORT}"

# ── Editor (mi-sitio.html) ──
llamadas = []
ESTADO = {"organizacion": dict(SITIO, url_publica=f"{API}/s/grupo-prueba", url_prueba=f"{API}/s/grupo-prueba"), "agente": None}


def api(method, path, q, body):
    llamadas.append((method, path, body))
    if path == "/sitios/mios":
        return (200, dict(ESTADO, es_admin=True, cname_destino="sitios.broquer.app", dominios_disponibles=False))
    if path == "/sitios/s1/paginas" and method == "GET":
        return (200, {"paginas": PAGINAS})
    if path == "/sitios/s1/paginas" and method == "POST":
        return (200, dict(body, id="pg2"))
    if path.startswith("/sitios/") and method == "PUT":
        ESTADO["organizacion"].update(body)
        return (200, ESTADO["organizacion"])
    if path == "/sitios/s1/dominio" and method == "POST":
        ESTADO["organizacion"].update({"dominio": body["dominio"], "dominio_estado": "pendiente"})
        return (200, {"sitio": ESTADO["organizacion"], "dns": [{"tipo": "CNAME", "nombre": "www", "valor": "sitios.broquer.app", "nota": ""}]})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")

    # Sitio público
    pg, errores = nueva_pagina(br, API)
    pg.goto(API + "/s/grupo-prueba")
    check(pg.locator('meta[property="og:title"]').count() == 1 and pg.locator('meta[property="og:image"]').count() <= 1, "Open Graph en la portada")
    check("Grupo Prueba Inmobiliaria" in pg.title(), "título de la portada")
    sw = pg.evaluate("document.documentElement.scrollWidth")
    check(sw <= 376, f"portada sin scroll horizontal a 375 px ({sw})")
    pg.screenshot(path=str(OUT / "sitio-inicio-375.png"), full_page=True)
    pg.goto(API + "/s/grupo-prueba/renta")
    check(pg.locator(".card").count() >= 5 or "Departamento 4" in pg.content(), "lista de renta")
    pg.goto(API + f"/s/grupo-prueba/inmueble/{P1}")
    check("NOTA INTERNA" not in pg.content() and "Privada Secreta" not in pg.content(), "ficha sin datos privados")
    check(pg.locator('meta[property="og:description"]').count() == 1, "Open Graph en la ficha")
    sw = pg.evaluate("document.documentElement.scrollWidth")
    check(sw <= 376, f"ficha sin scroll horizontal ({sw})")
    tam = pg.evaluate("Math.min(...[...document.querySelectorAll('form input:not([type=hidden]), form textarea, form select')].map(e => parseFloat(getComputedStyle(e).fontSize)))")
    check(tam >= 16, f"campos del formulario ≥16 px ({tam})")
    pg.screenshot(path=str(OUT / "sitio-ficha-375.png"), full_page=True)
    pg.fill('form [name="nombre"]', "Laura Cliente")
    pg.fill('form [name="telefono"]', "4439998877")
    pg.fill('form [name="mensaje"]', "Quiero verla")
    pg.locator('form [type="submit"]').first.click()
    pg.wait_for_load_state()
    check("Gracias" in pg.content(), "confirmación tras enviar")
    check(len(leads) == 1 and leads[0]["canal"] == "sitio" and leads[0]["propiedad_id"] == P1, "lead al Buzón con inmueble ligado")
    pg.goto(API + "/s/grupo-prueba/p/vende")
    check("Te ayudamos a vender" in pg.content() and "Vende con nosotros" in pg.locator("header nav").inner_html(), "página propia y en el menú")
    pg.goto(API + "/s/grupo-prueba/buscar?operacion=venta&rec=3")
    check("1 resultado" in pg.content(), "buscador del sitio")
    errs = [e for e in errores if "Failed to load resource" not in e and "googletagmanager" not in e and "translate" not in e]
    check(not errs, "sitio público sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Editor
    page, err2 = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB({"perfiles_publicos": [], "testimonios": []}), api)
    page.goto(base + "/mi-sitio.html?sitio=organizacion")
    page.wait_for_selector("#msw-guardar", timeout=15000)
    check(page.locator("#msw-head").count() == 1, "admin ve código propio")
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 376, f"editor sin scroll horizontal ({sw})")
    tam = page.evaluate("Math.min(...[...document.querySelectorAll('#msw-body input:not([type=hidden]):not([type=checkbox]):not([type=color]):not([type=file]), #msw-body textarea, #msw-body select')].map(e => parseFloat(getComputedStyle(e).fontSize)))")
    check(tam >= 16, f"campos del editor ≥16 px ({tam})")
    page.fill("#msw-ga4", "G-NUEVO1")
    page.evaluate("document.getElementById('msw-bolsa').click()")
    page.click("#msw-acerca")
    page.keyboard.type("Somos expertos.")
    page.click("#msw-guardar")
    page.wait_for_timeout(500)
    put = [c for c in llamadas if c[0] == "PUT"]
    check(put and put[-1][1] == "/sitios/organizacion" and put[-1][2]["ga4_id"] == "G-NUEVO1" and put[-1][2]["incluir_bolsa"] is True
          and "Somos expertos" in put[-1][2]["acerca_html"], "guarda configuración del sitio")
    page.wait_for_selector("#msw-nueva-pagina")
    page.click("#msw-nueva-pagina")
    page.wait_for_selector(".msw-modal #msw-pg-t")
    page.fill("#msw-pg-t", "Aviso de privacidad")
    page.click("#msw-pg-c")
    page.keyboard.type("Texto legal")
    page.click(".msw-modal [data-cmd=bold]")
    page.screenshot(path=str(OUT / "sitio-editor-pagina-375.png"))
    alto = page.evaluate("(() => { const m = document.querySelector('.msw-modal .bk-modal').getBoundingClientRect(); return m.bottom <= innerHeight + 1; })()")
    check(alto, "modal de página cabe en pantalla")
    page.click(".msw-modal [data-guardar]")
    page.wait_for_timeout(500)
    post = [c for c in llamadas if c[0] == "POST" and c[1] == "/sitios/s1/paginas"]
    check(post and post[-1][2]["slug"] == "aviso-de-privacidad" and "Texto legal" in post[-1][2]["contenido_html"], "crea página con editor")
    page.wait_for_selector("#msw-dom-conectar")
    page.fill("#msw-dominio", "www.miinmobiliaria.mx")
    page.click("#msw-dom-conectar")
    page.wait_for_selector(".msw-dns__fila")
    check("sitios.broquer.app" in page.locator(".msw-dns").inner_text(), "instrucciones DNS del dominio")
    page.screenshot(path=str(OUT / "sitio-editor-375.png"), full_page=True)
    errs = [e for e in err2 if "Failed to load resource" not in e]
    check(not errs, "editor sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
server.should_exit = True
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
