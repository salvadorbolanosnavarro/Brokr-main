"""Prueba de navegador de Contactos (Fase 3): Lista, Pipeline y Ajustes de CRM."""
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


ETAPAS = [{"id": "e1", "clave": "nuevo", "nombre": "Nuevo", "color": "var(--etapa-nuevo)", "orden": 10},
          {"id": "e2", "clave": "activo", "nombre": "Visita agendada", "color": "#d97706", "orden": 20},
          {"id": "e3", "clave": "spam", "nombre": "Basura/Spam", "color": "var(--mute-2)", "orden": 30}]
TIPOS = [{"id": "t1", "clave": "comprador", "nombre": "Comprador"}, {"id": "t2", "clave": "valuador", "nombre": "Valuador"},
         {"id": "t3", "clave": "otro", "nombre": "Otro"}]
FUENTES = [{"id": "f1", "nombre": "Facebook", "nombre_norm": "facebook"}, {"id": "f2", "nombre": "Referido", "nombre_norm": "referido"}]
CONTACTOS = [
    {"id": "c1", "user_id": USER_ID, "org_id": ORG_ID, "nombre": "ANA PEREZ", "telefono": "443 123 4567", "email": "ana@x.mx",
     "tipo": "comprador", "estatus": "activo", "es_potencial": True, "fuente": "Facebook", "etiquetas": ["vip"],
     "telefonos": [{"numero": "443 555 0000", "tipo": "oficina"}], "puesto": "Gerente", "redes": {"instagram": "@ana"},
     "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-02T10:00:00Z"},
    {"id": "c2", "user_id": USER_ID, "org_id": ORG_ID, "nombre": "ANA P", "telefono": "+52 1 443 123 4567", "tipo": "valuador",
     "estatus": "spam", "es_potencial": True, "fuente": "Referido", "etiquetas": [], "created_at": "2026-09-05T10:00:00Z", "updated_at": "2026-09-05T10:00:00Z"},
    {"id": "c3", "user_id": USER_ID, "org_id": ORG_ID, "nombre": "LUIS", "telefono": "4439998888", "tipo": "comprador",
     "estatus": "nuevo", "es_potencial": False, "etiquetas": [], "created_at": "2026-09-06T10:00:00Z", "updated_at": "2026-09-06T10:00:00Z"},
]
llamadas = []


def api(method, path, q, body):
    llamadas.append((method, path, body))
    if path == "/crm/catalogos":
        return (200, {"etapas": ETAPAS, "tipos": TIPOS, "fuentes": FUENTES, "es_admin": True})
    if path == "/crm/contactos/fusionar":
        return (200, {"ok": True})
    if path == "/crm/contactos/lote":
        return (200, {"actualizados": len(body["ids"]), "sin_permiso": 0})
    if path == "/crm/etiquetas":
        return (200, {"etiquetas": [{"etiqueta": "vip", "n": 1}]})
    if path.startswith("/crm/etapas"):
        return (200, {"ok": True})
    if path.startswith("/api/buscador/"):
        return (200, {"operacion": "venta", "tipo_inmueble": "casa", "resultados": []})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    db = FakeDB({"contactos": CONTACTOS, "pipeline_etapas": ETAPAS})
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, db, api)
    page.goto(base + "/contactos.html")
    page.wait_for_selector("#crm-vistas", timeout=15000)
    page.wait_for_timeout(1200)
    check(page.locator(".page-head__row h1").inner_text() == "Contactos", "título único 'Contactos'")
    check(page.locator("#crm-vistas a[href^='clientes.html']").count() == 1, "selector Lista/Pipeline")
    check(not page.locator("#crm-gear").is_hidden(), "acceso a Ajustes de CRM para admin")
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"Lista sin scroll horizontal ({sw})")
    page.screenshot(path=str(OUT / "contactos-lista-375.png"))

    # Filtro posibles duplicados
    page.click("#crm-fil-btn")
    page.wait_for_selector(".crm-modal.is-open")
    page.select_option(".crm-modal select[name=dups]", "1")
    page.click(".crm-modal [data-ok]")
    page.wait_for_timeout(400)
    visibles = page.evaluate("contactosFiltrados().map(c => c.id).sort().join(',')")
    check(visibles == "c1,c2", f"filtro posibles duplicados (mismo teléfono a 10 dígitos) → {visibles}")
    page.click("#crm-fil-btn"); page.click(".crm-modal [data-limpiar]")

    # Ficha: datos extra, aviso de duplicado y requerimiento
    page.evaluate("abrirDetalle('c1')")
    page.wait_for_selector("#crm-dup-banner")
    info = page.locator("#f-pane-info").inner_text()
    check("443 555 0000" in info and "Gerente" in info and "@ana" in info, "ficha con teléfonos, puesto y redes")
    check(page.locator("#f-tab-requerimiento").count() == 1, "ficha de la vista Lista tiene Requerimiento")
    page.click("#f-tab-requerimiento")
    page.wait_for_timeout(300)
    check(not page.locator("#f-pane-requerimiento").is_hidden() and page.locator("#f-pane-info").is_hidden(), "pestaña Requerimiento abre")
    page.screenshot(path=str(OUT / "contactos-ficha-375.png"))
    page.click("#crm-dup-banner button")
    page.wait_for_selector(".crm-dup-opc")
    page.click(".crm-modal [data-ok]")
    page.wait_for_timeout(500)
    fus = [c for c in llamadas if c[1] == "/crm/contactos/fusionar"]
    check(fus and fus[-1][2] == {"conservar_id": "c1", "eliminar_id": "c2"}, "fusión llama al backend con el que se queda")

    # Modal: sexo en 'Datos para contratos', tipos del catálogo, guardar extras
    page.evaluate("try{cerrarDetalle()}catch(e){}")
    page.evaluate("abrirModal('c3')")
    page.wait_for_selector("#crm-extra-form")
    check(page.locator("#crm-contratos .sexo-row").count() == 1, "sexo dentro de 'Datos para contratos'")
    check(page.locator("#m-tipo option[value=valuador]").count() == 1, "tipos de contacto del catálogo (Valuador)")
    page.click("text=+ Agregar teléfono")
    page.fill("#crm-tels .crm-mv", "443 111 2222")
    page.fill("#crm-puesto", "Notario 5")
    page.fill("#m-fuente", "facebook ")
    page.screenshot(path=str(OUT / "contactos-modal-375.png"))
    page.evaluate("guardarContacto()")
    page.wait_for_timeout(800)
    c3 = next(c for c in db.t["contactos"] if c["id"] == "c3")
    check(c3.get("telefonos") == [{"tipo": "celular", "numero": "443 111 2222"}], f"guardó teléfonos extra ({c3.get('telefonos')})")
    check(c3.get("puesto") == "Notario 5", "guardó puesto")
    check(c3.get("fuente") == "Facebook" and c3.get("fuente_id") == "f1", "fuente al catálogo sin duplicar por mayúsculas/espacios")

    # Lote
    page.evaluate("cSel.add('c1'); cSel.add('c3'); cActualizarBarra()")
    page.click("#crm-lote-btn")
    page.click("#crm-lote-pop [data-a=etapa]")
    page.select_option(".crm-modal #crm-l-v", "spam")
    page.click(".crm-modal [data-ok]")
    page.wait_for_timeout(400)
    lote = [c for c in llamadas if c[1] == "/crm/contactos/lote"]
    check(lote and lote[-1][2]["estatus"] == "spam" and sorted(lote[-1][2]["ids"]) == ["c1", "c3"], "lote: cambiar etapa")
    errs = [e for e in errores if "Failed to load resource" not in e]
    check(not errs, "Lista sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Pipeline
    p2, e2 = nueva_pagina(br, base)
    instalar_mocks(p2, FakeDB({"contactos": CONTACTOS, "pipeline_etapas": ETAPAS}), api)
    p2.goto(base + "/clientes.html")
    p2.wait_for_selector("#crm-vistas", timeout=15000)
    p2.wait_for_timeout(1200)
    cols = p2.evaluate("Array.from(document.querySelectorAll('.kb-col')).map(c => c.dataset.etapa).join(',')")
    check(cols == "nuevo,activo,spam", f"pipeline con etapas del catálogo ({cols})")
    check("Visita agendada" in p2.locator("#kanban").inner_text(), "etapa renombrada conserva sus contactos (por clave)")
    p2.screenshot(path=str(OUT / "contactos-pipeline-375.png"))
    errs = [e for e in e2 if "Failed to load resource" not in e]
    check(not errs, "Pipeline sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Ajustes de CRM
    p3, e3 = nueva_pagina(br, base)
    instalar_mocks(p3, FakeDB({"organizacion_categorias": [{"id": "k1", "nombre": "Visitas", "org_id": ORG_ID}]}), api)
    p3.goto(base + "/crm-ajustes.html")
    p3.wait_for_selector("#crm-etapas .crm-fila", timeout=15000)
    check(p3.locator("#crm-etapas .crm-fila").count() == 3, "Ajustes: etapas listadas")
    check(p3.locator("#crm-tabs .bk-tab").count() == 5, "Ajustes: 5 pestañas")
    p3.screenshot(path=str(OUT / "crm-ajustes-375.png"))
    p3.click("[data-tab=fuentes]")
    p3.wait_for_selector("#crm-fuentes")
    p3.check("#crm-fuentes .crm-check >> nth=0"); p3.check("#crm-fuentes .crm-check >> nth=1")
    check(p3.locator("#crm-fusionar").is_enabled(), "Ajustes: fusionar fuentes se habilita con 2")
    p3.click("[data-tab=etiquetas]")
    p3.wait_for_selector("#crm-et")
    check("vip" in p3.locator("#crm-et").inner_text(), "Ajustes: etiquetas con conteo")
    p3.click("[data-tab=categorias]")
    p3.wait_for_selector("#crm-cats")
    check("Visitas" in p3.locator("#crm-cats").inner_text(), "Ajustes: categorías de tareas")
    sw = p3.evaluate("document.documentElement.scrollWidth")
    check(sw <= 380, f"Ajustes sin scroll horizontal ({sw})")
    errs = [e for e in e3 if "Failed to load resource" not in e]
    check(not errs, "Ajustes sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
