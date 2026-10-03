"""El editor de páginas del sitio nunca deja pasar código."""
from __future__ import annotations

import unittest

from core.html_limpio import limpiar_html


class HtmlLimpioTests(unittest.TestCase):
    def test_quita_scripts_eventos_y_javascript(self):
        sucio = '<p onclick="x()">Hola <script>alert(1)</script><a href="javascript:alert(1)">liga</a></p><iframe src="https://x"></iframe>'
        limpio = limpiar_html(sucio)
        self.assertEqual(limpio, '<p>Hola <a rel="noopener nofollow">liga</a></p>')

    def test_conserva_formato_basico(self):
        html = '<h2>Aviso</h2><ul><li><strong>Uno</strong></li></ul><a href="https://x.mx" target="_blank">x</a><img src="https://a/b.jpg" alt="b">'
        self.assertEqual(limpiar_html(html), '<h2>Aviso</h2><ul><li><strong>Uno</strong></li></ul>'
                                             '<a href="https://x.mx" target="_blank" rel="noopener nofollow">x</a><img src="https://a/b.jpg" alt="b">')

    def test_cierra_etiquetas_abiertas_y_escapa_texto(self):
        self.assertEqual(limpiar_html('<p><em>1 < 2 & 3'), '<p><em>1 &lt; 2 &amp; 3</em></p>')

    def test_img_solo_https(self):
        self.assertEqual(limpiar_html('<img src="http://x/a.jpg" onerror="x">'), '<img>')


if __name__ == "__main__":
    unittest.main()
