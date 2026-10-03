"""Regression guards for extracted EasyBroker property normalization."""
from __future__ import annotations

from pathlib import Path
import unittest

from core.easybroker_mapping import (
    _EB_LIMITE_PROPIEDADES,
    _EB_STATUS_DEFAULT,
    _EB_STATUS_MAP,
    _eb_to_brokr,
    _split_location_name,
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

    def test_location_name_from_api_is_split_without_morelia_default(self):
        # Forma real de la API v1: todo viene en "name", sin city/region.
        row = _eb_to_brokr(
            {
                "public_id": "EB-2",
                "location": {
                    "name": "Ciudad Granja, Zapopan, Jalisco",
                    "postal_code": "45010",
                    "street": "Av. Vallarta 5000",
                },
            },
            "user-1",
        )
        self.assertEqual(row["colonia"], "Ciudad Granja")
        self.assertEqual(row["ciudad"], "Zapopan")
        self.assertEqual(row["estado"], "Jalisco")

    def test_location_name_splitter_shapes(self):
        self.assertEqual(_split_location_name("A, B, C"), ("A", "B", "C"))
        self.assertEqual(_split_location_name("Fracc. X, Sección 2, Morelia, Michoacán"),
                         ("Fracc. X, Sección 2", "Morelia", "Michoacán"))
        self.assertEqual(_split_location_name("A, B"), ("A", "B", None))
        self.assertEqual(_split_location_name("A"), ("A", None, None))
        self.assertEqual(_split_location_name(""), (None, None, None))
        self.assertEqual(_split_location_name(None), (None, None, None))

    def test_paridad_operaciones_tipos_caracteristicas_coordenadas(self):
        row = _eb_to_brokr(
            {
                "public_id": "EB-3",
                "property_type": "Nave industrial",
                "operations": [
                    {"type": "rental", "amount": 90000, "currency": "mxn", "unit": "total"},
                    {"type": "sale", "amount": 25, "currency": "usd", "unit": "square_meter"},
                    {"type": "temporary_rental", "amount": 1500, "currency": "MXN", "period": "daily"},
                ],
                "features": [{"name": "Alberca", "category": "Recreación"}, "Seguridad 24h", "Vista a la presa"],
                "location": {"name": "Col. X, Morelia, Michoacán", "latitude": 19.7, "longitude": -101.18},
                "age": 12,
            },
            "user-1",
        )
        self.assertEqual(row["tipo"], "bodega")
        self.assertEqual(row["subtipo"], "nave_industrial")
        self.assertEqual(row["operacion"], "venta")
        self.assertEqual(row["precio"], 25.0)
        self.assertEqual(row["moneda"], "USD")
        self.assertEqual(row["precio_unidad"], "m2")
        self.assertEqual([o["tipo"] for o in row["operaciones"]], ["venta", "renta", "renta_temporal"])
        self.assertEqual(row["operaciones"][2]["periodo"], "noche")
        self.assertEqual(row["caracteristicas"], ["alberca", "seguridad_24h"])
        self.assertEqual(row["otras_caracteristicas"], "Vista a la presa")
        self.assertEqual((row["lat"], row["lng"]), (19.7, -101.18))
        self.assertEqual(row["antiguedad"], 12)
        self.assertIsNone(row["anio_construccion"])

    def test_videos_y_tour_virtual(self):
        row = _eb_to_brokr({
            "public_id": "EB-5",
            "videos": ["https://youtu.be/dQw4w9WgXcQ", {"url": "https://vimeo.com/1"}, "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "virtual_tour": "https://my.matterport.com/show/?m=abc",
        }, "u")
        self.assertEqual(row["videos"], ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
        self.assertEqual(row["tours"], ["https://my.matterport.com/show/?m=abc"])

    def test_columnas_extendidas_se_pueden_quitar(self):
        from core.easybroker_mapping import quitar_columnas_extendidas
        row = _eb_to_brokr({"public_id": "EB-4"}, "u")
        base = quitar_columnas_extendidas(row)
        self.assertNotIn("operaciones", base)
        self.assertIn("titulo", base)

    def test_main_delegates_mapping_after_transform(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        # This assertion becomes true when the deterministic transform is applied
        # by the Quality workflow; the source module itself remains independently tested.
        if "from core.easybroker_mapping import" in source:
            self.assertNotIn("def _eb_to_brokr(", source)
            self.assertNotIn("def _split_street(", source)


if __name__ == "__main__":
    unittest.main()
