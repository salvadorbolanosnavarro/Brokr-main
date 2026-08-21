from pathlib import Path
import unittest

from routers.whatsapp_property_view import (
    _fotos_a_imagenes,
    _propiedad_para_ficha,
    _texto_inmueble,
)
from scripts.refactor_whatsapp_extract_property_view_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppPropertyViewTests(unittest.TestCase):
    def test_text_preserves_rental_and_fallback_contract(self):
        p = {
            "titulo": "Casa Olivar",
            "calle": "Paseo Uno",
            "colonia": "El Olivar",
            "ciudad": "Morelia",
            "recamaras": 3,
            "banos": 2,
            "m2_construccion": 180,
            "precio": 25000,
            "moneda": "MXN",
            "operacion": "renta",
        }
        self.assertEqual(
            _texto_inmueble(p),
            "*Casa Olivar*\nPaseo Uno, El Olivar, Morelia\n3 rec · 2 baños · 180 m2\n$25,000 MXN / mes",
        )
        self.assertIn("Ubicación a consultar", _texto_inmueble({"tipo": "Terreno"}))

    def test_photo_normalization_preserves_string_and_legacy_dict_shapes(self):
        self.assertEqual(
            _fotos_a_imagenes([" https://a.test/x.jpg ", {"original": "https://b.test/y.jpg"}, {}, None]),
            [{"url": "https://a.test/x.jpg"}, {"url": "https://b.test/y.jpg"}],
        )

    def test_technical_sheet_mapping_preserves_operation_and_address(self):
        p = {
            "id": "p1",
            "titulo": "Casa",
            "tipo": "Casa",
            "operacion": "renta",
            "precio": 20000,
            "moneda": "MXN",
            "calle": "Av. Uno",
            "num_exterior": "14",
            "colonia": "Centro",
            "ciudad": "Morelia",
            "recamaras": 2,
            "banos": 1,
            "estacionamientos": 1,
            "m2_construccion": 120,
            "m2_terreno": 100,
            "descripcion": "D",
            "fotos": ["https://a.test/1.jpg"],
        }
        out = _propiedad_para_ficha(p)
        self.assertEqual(out["public_id"], "p1")
        self.assertEqual(out["address"], "Av. Uno 14")
        self.assertEqual(out["operations"], [{"type": "rental", "amount": 20000, "currency": "MXN"}])
        self.assertEqual(out["property_images"], [{"url": "https://a.test/1.jpg"}])


class WhatsAppPropertyViewExtractionTests(unittest.TestCase):
    def test_transform_moves_only_presentation_helpers(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_property_view import (", transformed)
        self.assertNotIn("def _texto_inmueble", transformed)
        self.assertNotIn("def _fotos_a_imagenes", transformed)
        self.assertNotIn("def _propiedad_para_ficha", transformed)
        self.assertIn("async def _buscar_inmuebles", transformed)
        self.assertIn("async def _generar_ficha_pdf", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
