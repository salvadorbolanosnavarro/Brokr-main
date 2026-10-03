"""Prueba de navegador del Buzón (Fase 4)."""
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


U2 = "10000000-0000-0000-0000-000000000002"
LEADS = [
    {"id": "l1", "canal": "whatsapp", "estado": "sin_atender", "nombre": "Ana Pérez", "telefono": "5214431234567",
     "mensaje": "¿Sigue disponible la casa?", "referencia": "conv1", "fuente": "WhatsApp", "propiedad_id": "p1",
     "propiedad_titulo": "Casa en Altozano", "contacto_id": "c1", "created_at": "2026-10-03T10:00:00Z",
     "ultimo_mensaje_en": "2026-10-03T10:05:00Z", "primera_respuesta_seg": None},
    {"id": "l2", "canal": "sitio", "estado": "sin_atender", "nombre": "Luis", "telefono": "4430000000", "email": "luis@x.mx",
     "mensaje": "Quiero agendar visita", "fuente": "gruponavarro.mx", "asignado_a": U2, "created_at": "2026-10-02T10:00:00Z",
     "ultimo_mensaje_en": "2026-10-02T10:00:00Z", "primera_respuesta_seg": 1800},
]
llamadas = []


def api(method, path, q, body):
    llamadas.append((method, path, body))
    if path == "/buzon":
        est = q.get("estado", "sin_atender")
        return (200, {"leads": [l for l in LEADS if l["estado"] == est], "es_admin": True})
    if path == "/buzon/contador":
        return (200, {"sin_atender": len([l for l in LEADS if l["estado"] == "sin_atender"])})
    if path == "/buzon/respuestas":
        return (200, {"respuestas": [{"id": "r1", "titulo": "Saludo", "texto": "Hola {nombre}, gracias por escribir sobre {inmueble}.", "canal": "todos"}]})
    if path == "/whatsapp2/mensajes" and method == "GET":
        return (200, {"mensajes": [{"direction": "in", "body": "¿Sigue disponible la casa?", "created_at": "2026-10-03T10:00:00Z"}]})
    if path == "/whatsapp2/mensajes" and method == "POST":
        return (200, {"ok": True})
    if path.endswith("/respondido"):
        return (200, {"ok": True})
    if path.endswith("/asignar"):
        for l in LEADS:
            if l["id"] == path.split("/")[2]:
                l["asignado_a"] = body["user_id"]
        return (200, {"ok": True})
    if path.startswith("/buzon/l") and method == "PATCH":
        for l in LEADS:
            if l["id"] == path.split("/")[2] and body.get("estado"):
                l["estado"] = body["estado"]
        return (200, {"ok": True})
    if path == "/buzon/manual":
        nuevo = dict(body, id="l3", estado="sin_atender", created_at="2026-10-03T11:00:00Z", ultimo_mensaje_en="2026-10-03T11:00:00Z", asignado_a=U2)
        LEADS.append(nuevo)
        return (200, nuevo)
    if path == "/crm/catalogos":
        return (200, {"etapas": [], "tipos": [], "fuentes": [{"id": "f1", "nombre": "Facebook"}], "es_admin": True})
    if path == "/buzon/reglas" and method == "GET":
        return (200, {"regla": {"modo": "manual", "token_entrada": "tok_abcdefghijklmnopqrstuvwx"}, "guardias": []})
    if path == "/buzon/reglas" and method == "PUT":
        return (200, {"regla": {"modo": body["modo"], "token_entrada": "tok_abcdefghijklmnopqrstuvwx"}})
    if path == "/buzon/estadisticas":
        return (200, {"total": {"leads": 2, "respondidos": 1, "mediana_seg": 1800, "promedio_seg": 1800},
                      "por_agente": {U2: {"leads": 1, "respondidos": 1, "mediana_seg": 1800, "promedio_seg": 1800}},
                      "por_canal": {"sitio": {"leads": 1, "respondidos": 1, "mediana_seg": 1800, "promedio_seg": 1800}}})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB({"propiedades": [{"id": "p1", "titulo": "Casa en Altozano"}]}), api)
    page.goto(base + "/buzon.html")
    page.wait_for_selector(".bz-item", timeout=15000)
    check(page.locator(".bz-item").count() == 2, "lista con 2 leads sin atender")
    check("Sin asignar" in page.locator(".bz-item").first.inner_text(), "chip 'Sin asignar'")
    page.wait_for_timeout(600)
    check(page.locator("#bk-sheet-buzon-badge, #bk-rail-buzon-badge").count() >= 1, "contador del Buzón en el menú")
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"sin scroll horizontal ({sw})")
    page.screenshot(path=str(OUT / "buzon-lista-375.png"))

    page.locator(".bz-item").first.click()
    page.wait_for_selector(".bz-msg")
    check(page.locator(".bz-lista").is_hidden(), "en celular el detalle ocupa la pantalla")
    page.select_option("#bz-resp", "r1")
    check(page.locator("#bz-texto").input_value() == "Hola Ana, gracias por escribir sobre Casa en Altozano.", "respuesta guardada con {nombre} e {inmueble}")
    page.screenshot(path=str(OUT / "buzon-detalle-375.png"))
    page.click("#bz-enviar-wa")
    page.wait_for_timeout(400)
    env = [c for c in llamadas if c[1] == "/whatsapp2/mensajes" and c[0] == "POST"]
    check(env and env[-1][2]["conversacion_id"] == "conv1", "responde por WhatsApp desde el Buzón")
    check(any(c[1] == "/buzon/l1/respondido" for c in llamadas), "registra primera respuesta")
    page.select_option("#bz-asignar", U2)
    page.wait_for_timeout(300)
    check(LEADS[0].get("asignado_a") == U2, "asignar desde la conversación")
    page.fill("#bz-nota", "Llamar mañana")
    page.click("#bz-nota-ok")
    page.wait_for_timeout(200)
    check(any(c[0] == "PATCH" and c[2] == {"nota_interna": "Llamar mañana"} for c in llamadas), "guarda nota interna")
    page.click("#bz-detalle [data-estado=atendida]")
    page.wait_for_timeout(500)
    check(LEADS[0]["estado"] == "atendida" and page.locator(".bz-item").count() == 1, "marcar atendida lo saca de 'Sin atender'")

    page.click("#bz-nuevo")
    page.wait_for_selector(".crm-modal.is-open")
    page.fill(".crm-modal [name=nombre]", "Pedro")
    page.fill(".crm-modal [name=telefono]", "4431112233")
    page.select_option(".crm-modal [name=propiedad_id]", "p1")
    page.click(".crm-modal [data-ok]")
    page.wait_for_timeout(500)
    man = [c for c in llamadas if c[1] == "/buzon/manual"]
    check(man and man[-1][2]["propiedad_id"] == "p1" and man[-1][2]["canal"] == "telefono", "lead de teléfono con inmueble")
    check(page.locator(".bz-item").count() == 2, "el lead manual aparece en la lista")
    errs = [e for e in errores if "Failed to load resource" not in e]
    check(not errs, "Buzón sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Ajustes → asignación
    p2, e2 = nueva_pagina(br, base)
    instalar_mocks(p2, FakeDB(), api)
    p2.goto(base + "/crm-ajustes.html#asignacion")
    p2.wait_for_selector("[data-tab=asignacion]", timeout=15000)
    p2.click("[data-tab=asignacion]")
    p2.wait_for_selector("input[name=modo]")
    p2.check("input[name=modo][value=guardias]")
    check(not p2.locator("#crm-guardias").is_hidden(), "guardias visibles al elegir ese modo")
    p2.click("#crm-guardia-add")
    p2.click("#crm-reglas-ok")
    p2.wait_for_timeout(400)
    put = [c for c in llamadas if c[1] == "/buzon/reglas" and c[0] == "PUT"]
    check(put and put[-1][2]["modo"] == "guardias" and len(put[-1][2]["guardias"]) == 1, "guarda modo guardias con calendario")
    check("/buzon/entrada/tok_" in p2.locator("#crm-webhook").input_value(), "muestra la liga del webhook para Zapier")
    p2.screenshot(path=str(OUT / "crm-asignacion-375.png"))

    # Estadísticas → Buzón
    p3, e3 = nueva_pagina(br, base)
    instalar_mocks(p3, FakeDB(), api)
    p3.goto(base + "/estadisticas.html")
    p3.wait_for_selector("[data-tab=buzon]", timeout=15000)
    p3.click("[data-tab=buzon]")
    p3.wait_for_selector(".es-table")
    txt = p3.locator("#es-body").inner_text()
    check("30 min" in txt and "Sitio web" in txt, "Estadísticas: primera respuesta por canal")
    errs = [e for e in e2 + e3 if "Failed to load resource" not in e]
    check(not errs, "Ajustes/Estadísticas sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
