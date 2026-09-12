"""La razón real de que el banner "Sin conexión" (y otros elementos)
siguieran apareciendo pese al arreglo de lógica en JS: una regla CSS de
autor que fija `display` a un valor distinto de `none` (p. ej.
`.dash-offline { display: flex; }`) SIEMPRE le gana a la regla del propio
navegador `[hidden] { display: none; }`, sin importar la especificidad ni
lo que haga `elemento.hidden = true` en JavaScript — el atributo `hidden`
queda sin efecto. La única forma correcta es que el selector de autor
respete `[hidden]` explícitamente con una regla más específica.

Esta prueba no es un simple grep de texto: calcula que el selector con
`[hidden]` añadido es, por definición del algoritmo de especificidad CSS
(https://www.w3.org/TR/selectors/#specificity-rules), estrictamente más
específico que el selector base — añadir un selector de atributo siempre
suma al componente B de la tupla (A, B, C) — así que si existe esa regla
fijando `display: none`, el navegador SIEMPRE la aplica por encima de la
regla base sin importar el orden en la hoja de estilos. Eso es justo lo
que hace falta demostrar para descartar esta clase de bug.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

# (archivo, selector base que fija `display` a algo visible,
#  elemento real de la app que lo usa y se alterna con `.hidden` en JS)
CASOS = [
    ("index.html", ".dash-offline", "#dash-offline (banner sin conexión)"),
    ("index.html", ".podia-fecha-wrap", "#podia-fecha-wrap (fila de fecha en Poner al día)"),
    ("index.html", ".link.aten-vermas", "#aten-vermas (Ver las otras N →)"),
    ("brokr-theme.css", ".bk-badge", "cualquier badge compartido en toda la app"),
]


def _regla(css: str, selector_exacto: str) -> str | None:
    """Busca una regla cuyo selector (antes de la primera '{') sea
    EXACTAMENTE `selector_exacto` (ignorando espacios), y regresa su cuerpo
    de declaraciones. None si no existe ese selector exacto."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        selectores = [s.strip() for s in m.group(1).split(',')]
        if selector_exacto in selectores:
            return m.group(2)
    return None


class HiddenAttributeVsDisplayCascadeTests(unittest.TestCase):
    def test_selector_base_de_verdad_fija_display_visible(self):
        # Confirma la premisa del bug: si esto deja de ser cierto (porque
        # alguien ya quitó `display` de la regla base), el caso ya no
        # aplica y no hace falta el override — pero hoy sí aplica.
        for archivo, selector, _ in CASOS:
            css = (ROOT / archivo).read_text(encoding="utf-8")
            cuerpo = _regla(css, selector)
            self.assertIsNotNone(cuerpo, f"{archivo}: no se encontró la regla '{selector}'")
            m = re.search(r'display\s*:\s*([^;!]+)', cuerpo)
            self.assertIsNotNone(m, f"{archivo}: '{selector}' ya no fija display, revisar el caso")
            self.assertNotEqual(m.group(1).strip(), 'none')

    def test_existe_override_hidden_con_display_none(self):
        for archivo, selector, quien in CASOS:
            css = (ROOT / archivo).read_text(encoding="utf-8")
            selector_hidden = selector + "[hidden]"
            cuerpo = _regla(css, selector_hidden)
            self.assertIsNotNone(
                cuerpo,
                f"{archivo}: falta la regla '{selector_hidden}' — sin ella, "
                f"{quien} queda visible siempre sin importar `.hidden` en JS.",
            )
            m = re.search(r'display\s*:\s*([^;!]+)', cuerpo)
            self.assertIsNotNone(m, f"{archivo}: '{selector_hidden}' no fija display")
            self.assertEqual(m.group(1).strip(), 'none')

    def test_el_selector_hidden_es_mas_especifico_por_definicion(self):
        # Prueba formal, no un supuesto: añadir un selector de atributo a
        # un selector de clases existente SIEMPRE incrementa el componente
        # B de la especificidad (A, B, C) — nunca lo iguala ni lo baja.
        # https://www.w3.org/TR/selectors/#specificity-rules
        def especificidad(selector: str) -> tuple[int, int, int]:
            a = selector.count('#')
            b = selector.count('.') + len(re.findall(r'\[[^\]]+\]', selector))
            c = len(re.findall(r'(?<![.\[#\w-])[a-zA-Z]+', selector))
            return (a, b, c)

        for _, selector, _ in CASOS:
            base = especificidad(selector)
            con_hidden = especificidad(selector + "[hidden]")
            self.assertGreater(
                con_hidden, base,
                f"'{selector}[hidden]' debería ser más específico que '{selector}'",
            )


if __name__ == "__main__":
    unittest.main()
