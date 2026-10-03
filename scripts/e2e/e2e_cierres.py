"""Prueba de navegador de cierres y comisiones (Fase 6)."""
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
U2 = "10000000-0000-0000-0000-000000000002"
llamadas = []
permisos = {"es_admin": True, "ver": True}


def api(method, path, q, body):
    llamadas.append((method, path, body))
    if path == "/org":
        return (200, {"tiene_org": True, "org_id": ORG_ID, "es_empresa": True, "es_admin": permisos["es_admin"], "rol_org": "owner" if permisos["es_admin"] else "agente",
                      "permisos": {"exportar": True, "ver_comisiones": permisos["ver"]}})
    if path == f"/cierres/propiedad/{PID}":
        return (200, {"cierre": None, "propiedad": {"id": PID, "titulo": "Casa en Altozano", "precio": 4500000, "moneda": "MXN",
                                                    "operacion": "venta", "comision_venta_pct": 5}})
    if path == "/cierres" and method == "POST":
        return (200, {"cierre": {"id": "k1"}, "movimientos": [{"id": "m1"}, {"id": "m2"}], "pld": {"genera_aviso": True}})
    if path == "/cierres/por-cobrar":
        return (200, {"por_cobrar": [{"id": "m1", "monto": 100000, "fecha": "2026-10-03", "concepto": "Comisión de venta por cobrar — Casa"}]})
    if path.startswith("/cierres/cobrado/"):
        return (200, {"ok": True})
    if path == "/cierres/reporte":
        return (200, {"columnas": [["id", "ID"], ["tipo_operacion", "Tipo de operación"], ["inmueble", "Inmueble"], ["dias_publicada", "Días publicada"],
                                   ["precio_publicacion", "Precio de publicación"], ["precio_cierre", "Precio de cierre"], ["pct_precio", "% del precio de publicación"],
                                   ["comision_total", "Comisión total"]],
                      "filas": [{"id": "MOR-1", "tipo_operacion": "venta", "inmueble": "Casa en Altozano", "dias_publicada": 45, "precio_publicacion": 4500000,
                                 "precio_cierre": 4000000, "pct_precio": 88.9, "comision_total": 200000, "propiedad_id": PID}]})
    return None


PROPS = [{"id": PID, "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Casa en Altozano", "tipo": "casa", "operacion": "venta",
          "precio": 4500000, "moneda": "MXN", "estatus": "activa", "colonia": "Altozano", "fotos": [], "etiquetas": [], "comision_venta_pct": 5}]
srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    db = FakeDB({"propiedades": [dict(PROPS[0])], "contactos": [{"id": "c1", "nombre": "PEDRO COMPRADOR"}]})
    instalar_mocks(page, db, api)
    page.goto(base + "/propiedades.html")
    page.wait_for_selector(".prop-card", timeout=15000)
    page.wait_for_function("typeof window.pxAbrirCierre === 'function'", timeout=10000)
    page.evaluate(f"openPropDetail('{PID}')")
    page.evaluate("setTimeout(() => pdCambiarEstatus('vendida'), 0)")
    page.wait_for_selector("#ci-modal .prop-modal-box", timeout=10000)
    check(page.locator("#ci-ctipo").input_value() == "pct", "comisión precargada como % del inmueble")
    page.fill("#ci-precio", "4000000")
    page.fill("#ci-cvalor", "5")
    page.wait_for_timeout(100)
    check(page.locator("#ci-ctotal").input_value() == "$200,000", "calcula comisión total")
    page.fill("#ci-comprador", "PEDRO COMPRADOR")
    page.fill("#ci-cinmo", "100000")
    page.select_option("#ci-opcionador-user", U2)
    page.fill("#ci-opcionador-com", "50000")
    page.select_option("#ci-asesor-tipo", "externo")
    page.fill("#ci-asesor-nombre", "Agencia X")
    page.fill("#ci-asesor-com", "30000")
    page.wait_for_timeout(100)
    check("suman $180,000" in page.locator("#ci-aviso").inner_text(), "aviso (sin bloquear) cuando las partes no suman el total")
    box = page.locator("#ci-modal .prop-modal-box").bounding_box()
    check(box["height"] <= 812, "modal de cierre cabe en la pantalla con scroll interno")
    page.screenshot(path=str(OUT / "cierre-modal-375.png"))
    page.on("dialog", lambda d: d.accept())
    page.click("#ci-ok")
    page.wait_for_timeout(800)
    env = [c for c in llamadas if c[1] == "/cierres" and c[0] == "POST"]
    b = env[-1][2] if env else {}
    check(b.get("estatus") == "vendida" and b.get("comprador_contacto_id") == "c1" and b.get("opcionador_user_id") == U2
          and b.get("asesor_nombre") == "Agencia X" and b.get("comision_tipo") == "pct", "guarda el cierre completo")
    errs = [e for e in errores if "Failed to load resource" not in e]
    check(not errs, "propiedades sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Finanzas: comisiones por cobrar
    p2, e2 = nueva_pagina(br, base)
    instalar_mocks(p2, FakeDB(), api)
    p2.goto(base + "/finanzas.html")
    p2.wait_for_selector("[data-cobrar]", timeout=15000)
    check("Comisiones por cobrar" in p2.locator("#fin-por-cobrar").inner_text(), "Finanzas muestra comisiones por cobrar")
    p2.click("[data-cobrar]")
    p2.wait_for_timeout(300)
    check(any(c[1] == "/cierres/cobrado/m1" for c in llamadas), "marcar cobrada")

    # Estadísticas: operaciones cerradas
    p3, e3 = nueva_pagina(br, base)
    instalar_mocks(p3, FakeDB(), api)
    p3.goto(base + "/estadisticas.html")
    p3.wait_for_selector("[data-tab=cierres]", timeout=15000)
    p3.click("[data-tab=cierres]")
    p3.wait_for_selector(".es-table")
    t = p3.locator("#es-body").inner_text()
    check("MOR-1" in t and "88.9%" in t and "45" in t, "reporte de operaciones cerradas")
    p3.screenshot(path=str(OUT / "cierres-reporte-375.png"))
    errs = [e for e in e2 + e3 if "Failed to load resource" not in e]
    check(not errs, "Finanzas/Estadísticas sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))

    # Agente sin permiso: cambia estatus sin modal ni montos
    permisos.update({"es_admin": False, "ver": False})
    p4, e4 = nueva_pagina(br, base)
    db4 = FakeDB({"propiedades": [dict(PROPS[0])]})
    instalar_mocks(p4, db4, api)
    p4.goto(base + "/propiedades.html")
    p4.wait_for_selector(".prop-card", timeout=15000)
    p4.wait_for_function("typeof window.pxAbrirCierre === 'function'", timeout=10000)
    p4.evaluate(f"openPropDetail('{PID}')")
    det = p4.locator("#f-pane-detalles").inner_text()
    check("5%" not in det, "sin permiso no ve la comisión en la ficha")
    p4.evaluate("setTimeout(() => pdCambiarEstatus('vendida'), 0)")
    p4.wait_for_timeout(600)
    check(p4.locator("#ci-modal").count() == 0 or p4.locator("#ci-modal").is_hidden(), "sin permiso no aparece el modal de cierre")
    check(db4.t["propiedades"][0]["estatus"] == "vendida", "sin permiso el estatus cambia normal")
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
