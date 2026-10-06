"""Prueba de navegador: sección "Fuentes consultadas" del AVM."""
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


RES = {"valor_estimado": 4200000, "resumen_ejecutivo": "Rango de mercado razonable.", "comparables": [], "recomendaciones": [],
       "fuentes_consultadas": [
           {"titulo": "Casa en Jesús del Monte", "url": "https://www.inmuebles24.com/p/1", "portal": "Inmuebles24", "lectura": "leído con Firecrawl"},
           {"titulo": "Casa 3 rec", "url": "https://www.lamudi.com.mx/p/2", "portal": "Lamudi", "lectura": "bloqueado"},
           {"titulo": "Venta casa", "url": "https://casas.ejemplo.mx/3", "portal": "", "lectura": "leído"},
           {"titulo": "Maps", "url": "https://google.com/maps", "portal": "", "lectura": "omitido"}],
       "firecrawl": {"activo": True, "intentos": 2, "leidas": 1, "cache": 0, "motivo_no_uso": ""}}


def api(method, path, q, body):
    if path == "/api/avm-websearch":
        return (200, RES)
    if path.startswith("/api/colonias"):
        return (200, {"colonias": []})
    return None


srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page, errores = nueva_pagina(br, base)
    instalar_mocks(page, FakeDB(), api)
    page.goto(base + "/avm.html")
    page.wait_for_selector("#btn-analizar-ia", timeout=20000)
    page.wait_for_function("typeof window.__avmIAFill === 'function'")
    page.evaluate("window.__BK_SUB_ACTIVE = true")      # cuenta con Broquer Max
    page.evaluate("window.__avmIAFill({tipo_inmueble: 'casa', colonia: 'Jesús del Monte', ciudad: 'Morelia', estado: 'Michoacán', m2_construccion: 280, m2_terreno: 240})")
    page.wait_for_timeout(400)
    page.click("#btn-analizar-ia")
    page.wait_for_selector("text=Fuentes consultadas", timeout=15000)
    sec = page.locator(".opinion-section", has_text="Fuentes consultadas").inner_text()
    check("Firecrawl activo" in sec and "1 página(s) leída(s) con Firecrawl" in sec and "1 intento(s) fallido(s)" in sec, "línea de estado de Firecrawl")
    check("leído con Firecrawl" in sec and "bloqueado" in sec and "casas.ejemplo.mx" in sec, "cada portal con su estado")
    check("google.com" not in sec, "omite dominios no útiles")
    sw = page.evaluate("document.documentElement.scrollWidth")
    check(sw <= 376, f"sin scroll horizontal ({sw})")
    page.locator(".opinion-section", has_text="Fuentes consultadas").screenshot(path=str(OUT / "avm-fuentes-375.png"))
    errs = [e for e in errores if "Failed to load resource" not in e and "babel" not in e.lower()]
    check(not errs, "sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:3])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
