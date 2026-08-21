from datetime import datetime, timezone
from pathlib import Path
import unittest

from routers.whatsapp_stats import _agrega_ventana, _dt, _mediana
from scripts.refactor_whatsapp_extract_stats_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppStatsTests(unittest.TestCase):
    def test_timestamp_and_median_contract(self):
        self.assertIsNone(_dt(None))
        self.assertIsNone(_dt("bad"))
        self.assertEqual(_dt("2026-08-20T12:00:00Z").tzinfo, timezone.utc)
        self.assertIsNone(_mediana([]))
        self.assertEqual(_mediana([3]), 3.0)
        self.assertEqual(_mediana([1, 3]), 2.0)

    def test_window_aggregates_messages_response_and_handoff(self):
        now = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
        contactos = [{
            "created_at": "2026-08-20T15:00:00Z",
            "temperatura": "Caliente", "etapa": "Cita",
            "forma_pago": "contado", "score": 80,
        }]
        conversaciones = [{
            "id": "c1", "numero_id": "n1",
            "created_at": "2026-08-20T14:00:00Z",
            "last_message_at": "2026-08-20T17:00:00Z",
            "ia_enabled": False,
            "ultimas_propiedades": [{"id": "p1", "titulo": "Casa"}],
        }]
        mensajes = [
            {"conversacion_id": "c1", "created_at": "2026-08-20T16:00:00Z", "direction": "in", "sender": "prospecto"},
            {"conversacion_id": "c1", "created_at": "2026-08-20T16:05:00Z", "direction": "out", "sender": "ia"},
        ]
        numeros = [{"id": "n1", "alias": "Ventas", "display_number": "521", "ia_enabled": True}]
        out = _agrega_ventana(7, now, "America/Mexico_City", contactos, conversaciones, mensajes, numeros)
        self.assertEqual(out["totales"]["mensajes"], 2)
        self.assertEqual(out["totales"]["entrantes"], 1)
        self.assertEqual(out["totales"]["ia"], 1)
        self.assertEqual(out["totales"]["handoffs"], 1)
        self.assertEqual(out["respuesta_min"]["mediana"], 5.0)
        self.assertEqual(out["score"]["promedio"], 80)
        self.assertEqual(out["propiedades"]["p1"]["conversaciones"], 1)
        self.assertEqual(out["numeros"][0]["pct_ia"], 100)

    def test_invalid_timezone_falls_back_without_crashing(self):
        out = _agrega_ventana(0, datetime.now(timezone.utc), "Not/AZone", [], [], [], [])
        self.assertEqual(out["totales"]["mensajes"], 0)
        self.assertEqual(out["numeros"], [])


class WhatsAppStatsExtractionTests(unittest.TestCase):
    def test_transform_moves_only_pure_aggregation(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_stats import _agrega_ventana, _dt, _mediana", transformed)
        self.assertNotIn("def _agrega_ventana(", transformed)
        self.assertNotIn("def _mediana(nums", transformed)
        self.assertIn("async def _sb_diag", transformed)
        self.assertIn("async def _sb_get_paginado", transformed)
        self.assertIn('@router.get("/estadisticas")', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
