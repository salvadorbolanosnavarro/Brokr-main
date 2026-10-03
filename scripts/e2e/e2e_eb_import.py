"""Prueba de navegador: resumen de la importación de EasyBroker (Fase 9)."""
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


RESULTADO = {"total_easybroker": 12, "importadas": 8, "actualizadas": 3, "ya_existian": 3, "limite": 1000, "limite_alcanzado": False,
             "fotos_en_proceso": True, "propietarios_ligados": 6, "asignadas_agente": 9,
             "errores": [{"id": f"EB-{i}", "error": "EB status 404"} for i in range(6)] +
                        [{"id": "EB-9", "error": "Propietario «Juan» no ligado: 409"}]}


def api(method, path, q, body):
    if path == "/easybroker/import-all":
        return (200, RESULTADO)
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB({"propiedades": []}), api)
    page.goto(base + "/propiedades.html")
    page.wait_for_timeout(2500)
    page.evaluate("setTimeout(() => { importarDesdeEasyBroker(); setTimeout(() => ebEjecutarImport(), 300); }, 0)")
    page.wait_for_selector("#eb-import-summary >> text=propietario ligado", timeout=15000)
    txt = page.locator("#eb-import-summary").inner_text()
    check("8" in txt and "6 con su propietario ligado" in txt and "9 con su agente asignado" in txt, "resumen: nuevas, propietarios y agentes")
    check(page.locator("#eb-import-errs details").count() == 1, "lista completa de errores")
    page.click("#eb-import-errs summary")
    check("Propietario «Juan» no ligado" in page.locator("#eb-import-errs").inner_text(), "errores con motivo")
    page.screenshot(path=str(OUT / "eb-import-resumen-375.png"))
    errs = [e for e in errores if "Failed to load resource" not in e]
    check(not errs, "sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
