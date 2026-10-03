"""Prueba de navegador de alertas de búsqueda (Fase 5)."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ORG_ID, USER_ID, FakeDB, instalar_mocks, nueva_pagina, servir_repo  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
fallas = []


def check(cond, msg):
    print(("OK   " if cond else "FALLA ") + msg)
    if not cond:
        fallas.append(msg)


PID = "11111111-1111-1111-1111-111111111111"
REQ = {"id": "r1", "contacto_id": "c1", "activo": True, "operaciones": ["venta"], "tipos": ["casa"], "zonas": ["Altozano"],
       "precio_max": 5000000, "moneda": "MXN", "caracteristicas": ["fin_infonavit"]}
llamadas = []


def api(method, path, q, body):
    llamadas.append((method, path, body))
    if path == "/alertas/requerimiento/c1":
        return (200, REQ if method == "GET" else dict(REQ, **body))
    if path == "/alertas/coincidencias/c1":
        return (200, {"coincidencias": [{"id": PID, "titulo": "Casa en Altozano", "tipo": "Casa en condominio", "origen": "equipo",
                                         "colonia": "Altozano", "ciudad": "Morelia",
                                         "operaciones": [{"tipo": "venta", "precio": 4500000, "moneda": "MXN"}], "enviada_en": None},
                                        {"id": "22222222-2222-2222-2222-222222222222", "titulo": "Casa Bolsa", "origen": "bolsa", "bolsa_comision": 50,
                                         "operaciones": [{"tipo": "venta", "precio": 4900000, "moneda": "MXN"}]}], "requerimiento": REQ})
    if path == "/alertas/preparar":
        return (200, {"mensaje": "Hola Ana, te comparto opciones…", "asunto": "Opciones", "telefono": "4431234567", "email": "ana@x.mx",
                      "conversacion_id": "conv1", "ventana_24h": True})
    if path in ("/alertas/registrar-envio", "/whatsapp2/mensajes", "/alertas/ligar-interesado"):
        return (200, {"ok": True})
    if path.startswith("/api/buscador/"):
        return (200, {"resultados": [], "requerimiento": None})
    if path == "/crm/catalogos":
        return (200, {"etapas": [], "tipos": [], "fuentes": [], "es_admin": True})
    if path == f"/alertas/clientes-potenciales/{PID}":
        return (200, {"clientes": [{"contacto_id": "c1", "nombre": "ANA PEREZ", "motivos": ["en la zona", "en presupuesto"], "ligado": False}]})
    if path == "/alertas/requerimientos":
        return (200, {"requerimientos": [dict(REQ, contacto_nombre="ANA PEREZ", agente_id=USER_ID, nuevas=2)], "es_admin": True})
    if path.startswith("/alertas/requerimientos/"):
        return (200, {"ok": True})
    return None


CONTACTOS = [{"id": "c1", "user_id": USER_ID, "org_id": ORG_ID, "nombre": "ANA PEREZ", "telefono": "4431234567", "tipo": "comprador",
              "estatus": "activo", "es_potencial": True, "etiquetas": [], "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T10:00:00Z"}]
srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    for vista in ("contactos", "clientes"):
        page, errores = nueva_pagina(br, base)
        instalar_mocks(page, FakeDB({"contactos": CONTACTOS}), api)
        page.goto(base + f"/{vista}.html?id=c1&tab=requerimiento")
        page.wait_for_selector("#crm-vistas", timeout=15000)
        page.wait_for_timeout(1000)
        page.evaluate("abrirDetalle('c1'); setDetTab('requerimiento')")
        page.wait_for_selector(".frq-prop", timeout=10000)
        check(page.locator("#frq-form input[name=frq-op][value=venta]").is_checked(), f"[{vista}] requerimiento cargado (operación)")
        check(page.locator("#frq-form input[name=frq-car][value=fin_infonavit]").is_checked(), f"[{vista}] financiamiento marcado")
        check(page.locator(".frq-prop").count() == 2 and "Bolsa Broquer" in page.locator("#frq-coinc").inner_text(), f"[{vista}] coincidencias propias y de la Bolsa")
        if vista == "contactos":
            page.check("#frq-form input[name=frq-op][value=preventa]")
            page.fill("#frq-zonas", "Altozano, Tres Marías")
            page.click("#frq-guardar")
            page.wait_for_timeout(400)
            put = [c for c in llamadas if c[0] == "PUT" and c[1] == "/alertas/requerimiento/c1"]
            check(put and put[-1][2]["operaciones"] == ["venta", "preventa"] and put[-1][2]["zonas"] == ["Altozano", "Tres Marías"], "guarda requerimiento ampliado")
            page.locator(".frq-prop input").first.check()
            page.click("#frq-enviar")
            page.wait_for_selector(".crm-modal [data-wa]")
            page.screenshot(path=str(OUT / "alertas-enviar-375.png"))
            page.click(".crm-modal [data-wa]")
            page.wait_for_timeout(500)
            check(any(c[1] == "/whatsapp2/mensajes" and c[2]["conversacion_id"] == "conv1" for c in llamadas), "envía por WhatsApp de Broquer (ventana abierta)")
            reg = [c for c in llamadas if c[1] == "/alertas/registrar-envio"]
            check(reg and reg[-1][2]["propiedad_ids"] == [PID] and reg[-1][2]["canal"] == "whatsapp", "registra el envío en bitácora")
            page.screenshot(path=str(OUT / "alertas-req-375.png"), full_page=True)
        errs = [e for e in errores if "Failed to load resource" not in e]
        check(not errs, f"[{vista}] sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Inmueble → clientes potenciales
    p2, e2 = nueva_pagina(br, base)
    instalar_mocks(p2, FakeDB({"propiedades": [{"id": PID, "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Casa en Altozano", "tipo": "casa",
                                                "operacion": "venta", "precio": 4500000, "estatus": "activa", "colonia": "Altozano", "fotos": [], "etiquetas": []}]}), api)
    p2.goto(base + "/propiedades.html")
    p2.wait_for_selector(".prop-card", timeout=15000)
    p2.evaluate(f"openPropDetail('{PID}')")
    p2.wait_for_selector("#px-pot-btn")
    p2.click("#px-pot-btn")
    p2.wait_for_selector("[data-ligar]")
    check("ANA PEREZ" in p2.locator("#px-pot-lista").inner_text(), "clientes potenciales desde el inmueble")
    p2.click("[data-ligar]")
    p2.wait_for_timeout(300)
    check(any(c[1] == "/alertas/ligar-interesado" for c in llamadas), "liga como interesado")

    # Página de alertas
    p3, e3 = nueva_pagina(br, base)
    instalar_mocks(p3, FakeDB(), api)
    p3.goto(base + "/alertas.html")
    p3.wait_for_selector("[data-pausa]", timeout=15000)
    check("2 nuevas" in p3.locator("#al-lista").inner_text(), "página de alertas con coincidencias nuevas")
    p3.click("[data-pausa]")
    p3.wait_for_timeout(300)
    check(any(c[0] == "PATCH" and c[1] == "/alertas/requerimientos/r1" and c[2] == {"activo": False} for c in llamadas), "pausar alerta")
    sw = p3.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"alertas sin scroll horizontal ({sw})")
    p3.screenshot(path=str(OUT / "alertas-pagina-375.png"))
    errs = [e for e in e2 + e3 if "Failed to load resource" not in e]
    check(not errs, "inmueble/alertas sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
