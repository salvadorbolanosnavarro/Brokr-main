"""Documentos del servidor con la marca de quien los pide (Broquer por defecto)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.marca_documentos import logo_data_uri, marca  # noqa: E402
from routers.ficha_pdf_renderer import build_ficha_html  # noqa: E402

FICHA = {"title": "Casa", "property_type": "Casa", "location": {"name": "Altozano", "city": "Morelia"},
         "operations": [{"type": "sale", "amount": 2950000, "currency": "MXN"}], "property_images": []}


class MarcaDocumentosTests(unittest.TestCase):
    def test_marca_desconocida_es_broquer(self):
        self.assertEqual(marca(None)["clave"], "broquer")
        self.assertEqual(marca("otra")["clave"], "broquer")
        self.assertEqual(marca(" Cecil ")["clave"], "cecil")
        self.assertTrue(logo_data_uri(marca("cecil")).startswith("data:image/png;base64,"))

    def test_ficha_broquer_sin_cambios(self):
        html = build_ficha_html(dict(FICHA), {})
        self.assertIn("Powered by Broquer", html)
        self.assertNotIn("Cecil", html)

    def test_ficha_cecil_con_su_marca_y_sin_azul(self):
        html = build_ficha_html(dict(FICHA, brand="cecil"), {})
        self.assertIn("Powered by Cecil", html)
        self.assertNotIn("Broquer", html)
        self.assertIn("--sky-blue:#F26A1B", html)
        self.assertIn("Manrope", html)
        self.assertNotIn("0,20,59", html)
        self.assertTrue(html.index("@import") < html.index(":root"))

    def test_informe_finanzas(self):
        from routers.finanzas import _html_reporte
        agg = {"ingresos": 1, "gastos": 0, "utilidad": 1, "por_categoria": [], "por_mes": [], "por_propiedad": []}
        self.assertIn(">Broquer<", _html_reporte("p", agg))
        cecil = _html_reporte("p", agg, "cecil")
        self.assertIn("Generado con Cecil · cecilapp.co", cecil)
        self.assertNotIn("Broquer", cecil)


if __name__ == "__main__":
    unittest.main()
