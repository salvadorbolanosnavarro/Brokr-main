"""Prueba de navegador: errores amables en Correo y buscador de contactos en Firmas."""
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


estado = {"bandeja": (409, {"detail": {"codigo": "reconectar", "mensaje": "Tu proveedor rechazó la contraseña de aplicación."}})}


def api(method, path, q, body):
    if path == "/correo/estado":
        return (200, {"conectado": True, "email": "chava@gruponavarro.mx"})
    if path == "/correo/bandeja":
        return estado["bandeja"]
    if path.startswith("/firmas"):
        return (200, {"documentos": [], "ok": True})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB(), api)
    page.goto(base + "/correo.html")
    page.wait_for_selector("text=Hay que volver a conectar tu correo", timeout=15000)
    check("rechazó la contraseña" in page.locator("#co-lista").inner_text(), "correo: mensaje amable si la contraseña se revocó")
    page.screenshot(path=str(OUT / "correo-reconectar-375.png"))
    page.click("button:has-text(\"Volver a conectar\")")
    check(page.locator("#co-view-conectar").is_visible() and page.input_value("#co-email") == "chava@gruponavarro.mx",
          "correo: volver a conectar con el correo ya escrito")
    estado["bandeja"] = (504, {"detail": {"codigo": "proveedor_lento", "mensaje": "Tu proveedor de correo tardó demasiado."}})
    page.evaluate("coVista('bandeja'); coCargarBandeja()")
    page.wait_for_selector("text=Reintentar")
    check("tardó demasiado" in page.locator("#co-lista").inner_text(), "correo: proveedor lento ofrece reintentar")
    estado["bandeja"] = (404, {"detail": "No tienes un correo conectado."})
    errs = [e for e in errores if "Failed to load resource" not in e]
    check(not errs, "correo sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:3])))

    p2, e2 = nueva_pagina(br, base)
    rutas = []
    p2.on("request", lambda r: rutas.append(r.url) if "contactos" in r.url else None)
    instalar_mocks(p2, FakeDB({"contactos": [{"id": "c_1", "user_id": USER_ID, "org_id": ORG_ID, "nombre": "ANA PEREZ"}]}), api)
    p2.goto(base + "/firmas.html")
    p2.wait_for_timeout(3500)
    p2.evaluate("typeof cargarContactos === 'function' && cargarContactos()")
    p2.wait_for_timeout(800)
    check(rutas and all("/rest/v1/rest/v1/" not in u for u in rutas) and any("/rest/v1/contactos" in u for u in rutas),
          "firmas: contactos por /rest/v1/contactos (sin ruta duplicada) " + str(rutas[:1]))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
