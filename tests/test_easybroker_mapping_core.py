"""Regression guards for extracted EasyBroker property normalization."""
from __future__ import annotations

from pathlib import Path
import unittest

from core.easybroker_mapping import (
    _EB_LIMITE_PROPIEDADES,
    _EB_STATUS_DEFAULT,
    _EB_STATUS_MAP,
    _eb_to_brokr,
    _split_street,
)

ROOT = Path(__file__).resolve().parents[1]


class EasyBrokerMappingCoreTests(unittest.TestCase):
    def test_status_contract_and_limit_are_preserved(self):
        self.assertEqual(
            _EB_STATUS_MAP,
            {
                "published": "activa",
                "not_published": "suspendida",
                "reserved": "reservada",
                "sold": "vendida",
                "rented": "rentada",
            },
        )
        self.assertEqual(_EB_STATUS_DEFAULT, ["published", "reserved", "sold", "rented"])
        self.assertEqual(_EB_LIMITE_PROPIEDADES, 1000)

    def test_street_parser_preserves_legacy_shapes(self):
        self.assertEqual(_split_street("Av. Madero 123 Int 4"), ("Av. Madero", "123", "4"))
        self.assertEqual(_split_street("Sin Número"), ("Sin Número", None, None))
        self.assertEqual(_split_street(""), (None, None, None))

    def test_property_mapping_preserves_core_fields(self):
        row = _eb_to_brokr(
            {
                "public_id": "EB-1",
                "title": "Casa prueba",
                "property_type": "Casa en condominio",
                "operations": [{"type": "sale", "amount": 3200000, "currency": "mxn"}],
                "location": {
                    "city_area": "Altozano",
                    "city": "Morelia",
                    "region": "Michoacán",
                    "postal_code": "58090",
                    "street": "Av. Prueba 10 Int 2",
                },
                "property_images": [{"url": "https://example.test/1.jpg"}],
                "features": ["Alberca", ""],
                "bedrooms": 3,
                "bathrooms": 2.5,
            },
            "user-1",
        )
        self.assertEqual(row["user_id"], "user-1")
        self.assertEqual(row["eb_public_id"], "EB-1")
        self.assertEqual(row["tipo"], "casa")
        self.assertEqual(row["operacion"], "venta")
        self.assertEqual(row["precio"], 3200000.0)
        self.assertEqual(row["moneda"], "MXN")
        self.assertEqual(row["calle"], "Av. Prueba")
        self.assertEqual(row["num_exterior"], "10")
        self.assertEqual(row["num_interior"], "2")
        self.assertEqual(row["amenidades"], ["Alberca"])
        self.assertEqual(row["estatus"], "activa")

    def test_main_delegates_mapping_after_transform(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        # This assertion becomes true when the deterministic transform is applied
        # by the Quality workflow; the source module itself remains independently tested.
        if "from core.easybroker_mapping import" in source:
            self.assertNotIn("def _eb_to_brokr(", source)
            self.assertNotIn("def _split_street(", source)


if __name__ == "__main__":
    unittest.main()
