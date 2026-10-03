"""Prueba de navegador del calendario de Tareas (Fase 8)."""
from __future__ import annotations

import datetime as dt
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


AG2 = "10000000-0000-0000-0000-000000000002"
hoy = dt.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
lun = hoy - dt.timedelta(days=hoy.weekday())


def iso(d):
    return d.astimezone(dt.timezone.utc).isoformat()


TAREAS = [
    {"id": "t1", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Llamar a Pedro", "completada": False, "fecha_entrega": iso(lun + dt.timedelta(days=1)), "asignado_a": USER_ID},
    {"id": "t2", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Visita Altozano", "completada": False, "fecha_entrega": iso(lun + dt.timedelta(days=2, hours=6)), "asignado_a": AG2},
    {"id": "t3", "user_id": USER_ID, "org_id": ORG_ID, "titulo": "Sin fecha", "completada": False, "fecha_entrega": None},
]
db = FakeDB({"tareas": TAREAS, "contactos": [], "propiedades": [], "tareas_contactos": [], "tareas_propiedades": [],
             "organizacion_categorias": [{"id": "k1", "org_id": ORG_ID, "nombre": "Visitas", "ambito": "tareas"},
                                         {"id": "k2", "org_id": ORG_ID, "nombre": "Llamadas", "ambito": "tareas"}],
             "tareas_categorias": [{"tarea_id": "t2", "categoria_id": "k1"}, {"tarea_id": "t1", "categoria_id": "k2"}]})
srv, base = servir_repo()
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    for ancho in (375, 1280):
        page, errores = nueva_pagina(br, base, ancho=ancho, alto=812)
        instalar_mocks(page, db)
        page.goto(base + "/tareas.html")
        page.wait_for_selector(".tk-item", timeout=15000)
        page.click("#tk-tab-cal")
        page.wait_for_selector("#pane-calendario .tkc-ev", timeout=5000)
        page.click("#tkc-vistas [data-v=semana]")
        check(page.locator(".tkc-col").count() == 7, f"[{ancho}] vista semana con 7 días")
        check(page.locator(".tkc-ev").count() == 2, f"[{ancho}] tareas con fecha en la semana")
        c1 = page.locator('.tkc-ev[data-id="t1"]').evaluate("e => getComputedStyle(e).getPropertyValue('--c')")
        c2 = page.locator('.tkc-ev[data-id="t2"]').evaluate("e => getComputedStyle(e).getPropertyValue('--c')")
        check(c1 and c2 and c1 != c2, f"[{ancho}] color por categoría ({c1.strip()} / {c2.strip()})")
        check("Visitas" in page.locator("#tkc-leyenda").inner_text(), f"[{ancho}] leyenda de categorías")
        sw = page.evaluate("document.documentElement.scrollWidth")
        check(sw <= ancho + 1, f"[{ancho}] sin scroll horizontal ({sw})")
        page.screenshot(path=str(OUT / f"tareas-semana-{ancho}.png"), full_page=True)
        if ancho == 375:
            # Filtro por asignado
            page.select_option("#tk-filtro-asignado", AG2)
            page.wait_for_timeout(200)
            check(page.locator(".tkc-ev").count() == 1 and page.locator('.tkc-ev[data-id="t2"]').count() == 1, "filtro por asignado")
            page.select_option("#tk-filtro-asignado", "")
            page.wait_for_timeout(200)
        # Arrastrar t1 al viernes
        ev = page.locator('.tkc-ev[data-id="t1"]')
        destino = page.locator(".tkc-col").nth(4)
        destino.scroll_into_view_if_needed()
        ev.scroll_into_view_if_needed()
        a = ev.bounding_box()
        page.mouse.move(a["x"] + 10, a["y"] + 5)
        page.mouse.down()
        page.mouse.move(a["x"] + 30, a["y"] + 30, steps=4)
        b = destino.bounding_box()
        page.mouse.move(b["x"] + b["width"] / 2, b["y"] + min(b["height"] - 5, 40), steps=8)
        page.mouse.up()
        page.wait_for_timeout(500)
        patch = [x for x in db.log if x[0] == "PATCH" and x[1] == "tareas"] if hasattr(db, "log") else []
        t1 = next(t for t in db.t["tareas"] if t["id"] == "t1")
        nueva = dt.datetime.fromisoformat(t1["fecha_entrega"].replace("Z", "+00:00")).astimezone()
        check(nueva.date() == (lun + dt.timedelta(days=4)).date() and nueva.hour == 10, f"[{ancho}] arrastrar cambia la fecha y conserva la hora ({nueva})")
        TAREAS_RESET = next(t for t in db.t["tareas"] if t["id"] == "t1")
        TAREAS_RESET["fecha_entrega"] = iso(lun + dt.timedelta(days=1))
        # Mes y día
        page.click("#tkc-vistas [data-v=mes]")
        check(page.locator(".tkc-dia").count() >= 28, f"[{ancho}] vista mes")
        page.screenshot(path=str(OUT / f"tareas-mes-{ancho}.png"), full_page=True)
        sw = page.evaluate("document.documentElement.scrollWidth")
        check(sw <= ancho + 1, f"[{ancho}] mes sin scroll horizontal ({sw})")
        page.click("#tkc-vistas [data-v=dia]")
        check(page.locator(".tkc-hora").count() == 17, f"[{ancho}] vista día por horas")
        page.click('[data-mover="0"]')
        # Clic abre la tarea
        page.click("#tkc-vistas [data-v=semana]")
        page.locator('.tkc-ev[data-id="t2"]').click()
        page.wait_for_timeout(300)
        check(page.evaluate("document.getElementById('tke-titulo') && document.getElementById('tke-titulo').value") == "Visita Altozano", f"[{ancho}] tocar abre la tarea")
        errs = [e for e in errores if "Failed to load resource" not in e]
        check(not errs, f"[{ancho}] sin errores JS" + ("" if not errs else ": " + " | ".join(errs[:4])))
    br.close()
srv.shutdown()
print("\nRESULTADO:", "TODO BIEN" if not fallas else f"{len(fallas)} FALLAS")
sys.exit(1 if fallas else 0)
