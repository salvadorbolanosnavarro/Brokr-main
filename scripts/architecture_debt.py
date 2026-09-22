#!/usr/bin/env python3
"""Measure Broquer architecture debt and prevent it from growing.

The baseline is ratcheted down as cleanup lands in PR #44. These limits are
ceilings, not targets: cleanup should make every number go down. CI fails if a
legacy pattern count grows beyond the latest verified baseline or if any known
large code file grows beyond its verified size ceiling.
"""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", "tests", "core", "scripts", "migrations"}
CODE_SUFFIXES = {".py", ".js", ".html", ".css"}

PATTERNS = {
    "direct_env_reads": re.compile(r"\bos\.(?:getenv|environ)\b"),
    "duplicated_auth_helpers": re.compile(
        r"(?:async\s+def\s+get_user_id_from_token|async\s+def\s+_get_user_id|async\s+def\s+_user_id_desde_token)\s*\("
    ),
    "service_key_fallbacks": re.compile(
        r"SUPABASE_SERVICE_KEY\s*=.*\bor\b.*(?:SUPABASE_KEY|SUPABASE_ANON_KEY)"
    ),
    "direct_supabase_rest": re.compile(r"/rest/v1/"),
    "embedded_jwt_secrets": re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "fail_open_webhook_secrets": re.compile(r"\bif\s+CORREO_WEBHOOK_TOKEN\s*:"),
    "fail_open_entitlements": re.compile(r"Falla\s+ABIERTO", re.IGNORECASE),
}

PATTERN_EXEMPTIONS = {
    "direct_supabase_rest": {"routers/agente.py"},
}

BASELINE_MAX = {
    "direct_env_reads": 0,
    "duplicated_auth_helpers": 0,
    "service_key_fallbacks": 0,
    "direct_supabase_rest": 0,
    "embedded_jwt_secrets": 0,
    "fail_open_webhook_secrets": 0,
    "fail_open_entitlements": 0,
}

# Verified again after integrating the current Frontend Canon into PR #44.
# A file may shrink or disappear, but none of these legacy giants may grow.
LARGE_FILE_MAX_BYTES = {
    "main.py": 595_635,
    # Bumped 13 bytes for `hidden:true` on the 'bolsa' MODS entry — hides
    # Bolsa inmobiliaria from the sidebar/search, a real product change,
    # not debt to pay down.
    # Bumped 27 bytes: --vvh (alto real visible en iOS sin el teclado
    # tapándolo) + el reacomodo de overlays abiertos que dependen de él —
    # corrige modales cuyo botón de guardar quedaba oculto detrás del
    # teclado (había que voltear el teléfono para alcanzarlo), bug real.
    # Bumped 2,690 bytes: se deshicieron los menús del rail de escritorio
    # (crm/seguimiento/documentos/números/marketing) — cada módulo ahora es
    # su propio ícono suelto, con nombre revelado al pasar el mouse; "Más"
    # es la única excepción que conserva su flyout. De paso se quitó CSS
    # muerto de un acordeón anterior (.bk-sb-block/.bk-sb-group/etc., nunca
    # usado por el JS) — rediseño de producto pedido por el usuario, no
    # deuda nueva.
    # Bumped 1,145 bytes: el nombre del ícono ahora aparece vertical,
    # encima del propio sidebar (writing-mode), tapando solo los íconos
    # vecinos que le hagan falta según lo largo de la palabra — pedido
    # explícito del usuario en vez de la pastilla horizontal anterior.
    # Bumped 2,789 bytes: quitado el recuadro/fondo de esa etiqueta (texto
    # del mismo color que los íconos, sin caja) y los íconos que tapa
    # ahora desaparecen de verdad (no solo se cubren) — incluida la
    # pastilla blanca del módulo activo, que si no dejaba el nombre
    # blanco ilegible encima de su propio fondo blanco.
    # Bumped 676 bytes: Sentry.setTag/setUser se movieron dentro de
    # Sentry.onLoad() — el shim del Loader Script no garantiza esos
    # métodos en el "onload" del <script>, solo onLoad/forceLoad, y por
    # eso tiraba "Sentry.setTag is not a function" en cada carga. Bug
    # real corregido con una explicación de por qué, no deuda nueva.
    "app-shell.js": 260_690,
    "whatsapp.py": 223_594,
    "contratos.html": 156_081,
    # Bumped 5,747 bytes: los cambios de estatus, notas, comisión real y
    # archivar se guardaban "en silencio" — Postgrest responde 200 con un
    # arreglo vacío cuando un PATCH no toca ninguna fila (RLS o id ya no
    # existe), y el código nunca lo revisaba, así que el cambio se perdía
    # sin avisar y solo se notaba al recargar. Ahora todo PATCH a una fila
    # existente verifica que sí volvió una fila. Junto con reordenar fotos
    # arrastrando (o con los botones ‹ ›) al crear o editar un inmueble —
    # corrección de bug real + funcionalidad de producto, no debt.
    # Bumped 134 bytes: max-height del modal usa --vvh (alto real visible)
    # en vez de vh fijo — el teclado de iOS no encoge vh/dvh, así que el
    # botón de guardar podía quedar tapado. Bug real, no debt.
    # Bumped 493 bytes: abrir un inmueble o generar su ficha ahora usa
    # window.open en una pestaña propia por id (en vez de reusar la misma
    # pestaña o navegar con location.href) para que la lista de Mis
    # Inmuebles, con los filtros que el agente haya puesto, nunca se
    # recargue ni se pierda al ver el detalle o generar fichas de varias
    # propiedades filtradas — bug de UX real, no debt.
    # Bumped 4,122 bytes: al hacer clic en una foto de un inmueble ahora se
    # abre un lightbox con carrusel (flechas, contador, teclado, clic fuera
    # para cerrar) en vez de una pestaña nueva por foto — funcionalidad de
    # producto real, no debt.
    # Bumped 1,247 bytes: el historial de un inmueble ahora acepta adjuntar
    # fotos, videos y archivos a cada nota (botón de clip con ícono SVG,
    # como el resto de la app, + previsualización junto al composer; el
    # resto de la lógica vive en historial-adjuntos.js compartido con
    # Contactos y Clientes) — funcionalidad de producto real, no debt.
    # Baja 29,512 bytes: la ficha del inmueble salió a propiedades-ficha.js y
    # su CSS (cabecera, pestañas, bitácora, filas) al bloque FICHA de
    # brokr-theme.css, compartido con Clientes y Directorio. Deuda pagada.
    # Bumped 705 bytes: selector de categorías (chips + "+ Nueva") en el
    # composer de notas de la bitácora, para poder etiquetar notas igual que
    # las tareas — funcionalidad de producto real, no debt.
    "propiedades.html": 132_377,
    # Bumped 1,844 bytes for the "Revisar webhook de la app" button in
    # Administrar números (fija el webhook de WhatsApp a nivel app) — a real
    # product change, not debt to pay down.
    # Bumped 542 more bytes: w2CargarNumeros() silently treated any failed
    # GET /whatsapp2/numeros (e.g. an expired session, 401) as "no numbers
    # connected" — a real production bug fix, not debt.
    # Bumped 2,844 bytes: aviso discreto y descartable sobre el cambio de
    # cobro de Meta a mensajes de WhatsApp del 1 de octubre de 2026 (banner
    # + nota de sistema visible en el hilo cuando Recepción se pausa sola) —
    # producto/legal real, no debt.
    # Bumped 74 bytes: el ícono de "eliminar conversación" ahora es el
    # mismo bote de basura canónico que usa el resto de la app (antes traía
    # su propio dibujo distinto), pedido explícito de consistencia visual.
    "whatsapp.html": 132_296,
    # Bumped 5,201 bytes: reemplazo de Mifiel por Firmame Bienes Raíces como
    # PSC de NOM-151 (PR #149) más el endpoint POST
    # /firmas/documentos/{documento_id}/nom151 para reintentar la emisión de
    # la constancia a mano cuando el sellado automático falla (PR #150) —
    # funcionalidad de producto real, no debt.
    "routers/firmas.py": 124_394,
    # Bumped 80 bytes: se agregó la etapa "Futuro" al pipeline por defecto
    # (ETAPAS_DEFAULT) — un estatus nuevo para contactos/leads, no debt.
    # Bumped 18 bytes: se agregó "ajena" (inmueble de otro colega externo)
    # al mapa de etiquetas de estatus de inmuebles — estatus nuevo, no debt.
    "estadisticas.html": 117_027,
    # Bumped 825 bytes total: confirmaciones ("toast") al guardar etapa/
    # probabilidad, notas, vínculos y borrado masivo que antes eran
    # silenciosos, más una confirmación antes de descartar cambios sin
    # guardar al cerrar el modal con un clic fuera — mejora real de UX,
    # no debt.
    # Bumped 622 bytes: aviso visible si falla la carga real y solo queda
    # mostrando el cache viejo (antes fallaba en silencio) — corrige el bug
    # real de "se ve cargado pero está congelado en datos viejos", no debt.
    # (Historia: Leads se fusionó aquí en 2026 como la pestaña "Pipeline" —
    # ver el comentario arriba de leads.html en LARGE_FILE_MAX_BYTES para
    # esa etapa. Se deshizo la fusión a pedido del usuario: la confundía con
    # Directorio. El kanban y todo lo exclusivo de él (ETAPAS_DEFAULT,
    # renderPipeline/kbCard/kbDrag*, cambiarEstatus, contactosPotenciales)
    # salió a clientes.html, un módulo propio otra vez con su propia
    # identidad visual — así que el techo baja, no es deuda pagada, es la
    # reversión del merge.)
    # Bumped 82 bytes: crearTareaVinculada() y vincularTareaExistente()
    # llamaban a userId(), una función que nunca existió (el helper real es
    # _userId()) — probablemente un resto de cuando esta pestaña se calcó de
    # Propiedades. El ReferenceError ocurría antes del try/catch, así que
    # tronaba en silencio: dar clic en "Crear" o "Vincular existente" en
    # Tareas no hacía nada, sin error visible. Bug real, no debt.
    # Bumped 170 bytes: .sheet/#detail-ov usan --vvh (alto real visible)
    # en vez de vh/dvh fijos — mismo arreglo de teclado que arriba.
    # Bumped 5,741 bytes: el <select> de hasta 500 propiedades para
    # vincular a un contacto (sin filtro, ir "una por una") se reemplazó
    # por un buscador con sugerencias en vivo por título/colonia/ciudad —
    # arregla una usabilidad real, no es deuda.
    # Bumped 1,215 bytes: el historial de un contacto ahora acepta adjuntar
    # fotos, videos y archivos a cada nota (botón de clip con ícono SVG,
    # como el resto de la app, + previsualización junto al composer; el
    # resto de la lógica vive en historial-adjuntos.js compartido con
    # Clientes e Inmuebles) — funcionalidad de producto real, no debt.
    # Fuera del inventario: la ficha del contacto salió a contactos-ficha.js y
    # su CSS al bloque FICHA del theme; el archivo bajó de 123,745 a ~94 KB y
    # ya no cruza los 100 KB. (clientes.html salió igual, en el PR anterior.)
    # Bumped for the Profeco/IA-generativa disclosure clauses (9.9 Bis /
    # 5.6 Bis) — legitimate legal content, not debt to pay down.
    # Bumped 1,985 bytes: Anexo de WhatsApp ampliado con el cambio de cobro
    # de Meta a partir del 1 de octubre de 2026 y el requisito de método de
    # pago en el WABA, deslindando a Broquer de la interrupción del
    # servicio si el Usuario no lo configura a tiempo — legal real, no debt.
    # Bumped 1,213 bytes: cláusula 5.4 Bis sobre firma electrónica y la
    # Constancia de Conservación NOM-151 (servicio adicional y opcional del
    # PSC contratado, que no afecta la validez de la firma ya recabada ni
    # genera responsabilidad de Broquer por sus actos u omisiones) — legal
    # real, no debt.
    "legal.html": 116_939,
    # Nuevo en el inventario: el detalle de usuario de la Consola de admin
    # incorporó "Acceso completo fuera del equipo" y "Módulos habilitados
    # para esta cuenta" (PR #79), lo que cruzó admin.html el umbral de
    # 100 KB. Es funcionalidad real de producto, no deuda por pagar; queda
    # registrada con techo para que no siga creciendo sin revisión.
    "admin.html": 100_009,
    # El sistema canónico creció al absorber la ficha de detalle que vivía
    # copiada en Clientes, Directorio e Inmuebles (bloque FICHA). Es lo que
    # DESIGN.md §10 pide —el mundo visual se cambia en el sistema, no módulo
    # por módulo— y a cambio los tres módulos encogieron mucho más de lo que
    # creció el theme. Entra al inventario para que no siga creciendo sin
    # revisión.
    # Bumped 549 bytes: .tke-chips/.tke-chip — chips de categorías, usados
    # por Tareas y por el selector de categorías del composer de notas en
    # Contactos/Clientes/Inmuebles. Funcionalidad de producto real, no debt.
    "brokr-theme.css": 104_942,
}
MAX_LARGE_CODE_FILES = len(LARGE_FILE_MAX_BYTES)


def _excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def python_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.py")
        if path.is_file() and not _excluded(path)
    )


def findings() -> dict[str, list[str]]:
    result = {name: [] for name in PATTERNS}
    for path in python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(ROOT))
        for name, pattern in PATTERNS.items():
            if relative in PATTERN_EXEMPTIONS.get(name, set()):
                continue
            if pattern.search(text):
                result[name].append(relative)
    return result


def large_code_files() -> list[tuple[str, int]]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODE_SUFFIXES or _excluded(path):
            continue
        size = path.stat().st_size
        if size >= 100_000:
            result.append((str(path.relative_to(ROOT)), size))
    return sorted(result, key=lambda item: item[1], reverse=True)


def main() -> int:
    debt = findings()
    failures: list[str] = []

    print("Broquer architecture debt inventory")
    print("===================================")
    for name, paths in debt.items():
        count = len(paths)
        ceiling = BASELINE_MAX[name]
        print(f"{name}: {count} (ceiling {ceiling})")
        for path in paths:
            print(f"  - {path}")
        if count > ceiling:
            failures.append(f"{name} grew from ceiling {ceiling} to {count}")

    big = large_code_files()
    print(f"large_code_files_100kb_plus: {len(big)} (ceiling {MAX_LARGE_CODE_FILES})")
    for path, size in big:
        ceiling = LARGE_FILE_MAX_BYTES.get(path)
        ceiling_text = f"{ceiling:,}" if ceiling is not None else "new file"
        print(f"  - {path}: {size:,} bytes (ceiling {ceiling_text})")

        if ceiling is None:
            failures.append(f"new large code file appeared: {path} ({size:,} bytes)")
        elif size > ceiling:
            failures.append(
                f"{path} grew from ceiling {ceiling:,} to {size:,} bytes"
            )

    if len(big) > MAX_LARGE_CODE_FILES:
        failures.append(
            "large code files grew from ceiling "
            f"{MAX_LARGE_CODE_FILES} to {len(big)}"
        )

    if failures:
        print("\nArchitecture debt regression detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nArchitecture debt guard passed: debt did not grow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
