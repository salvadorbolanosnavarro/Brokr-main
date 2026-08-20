from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from routers.whatsapp_time import construir_ics, fecha_hora_utc_iso, fmt_fecha_larga, hora_local

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppTimeExtractionTests(unittest.TestCase):
    def test_mexico_city_conversion_contract(self):
        self.assertEqual(
            fecha_hora_utc_iso("2026-08-20", "10:30", "America/Mexico_City"),
            "2026-08-20T16:30:00Z",
        )
        self.assertIsNone(fecha_hora_utc_iso("mal", "10:30", "America/Mexico_City"))

    def test_timezone_is_not_hardcoded_to_mexico_city(self):
        tijuana = fecha_hora_utc_iso("2026-08-20", "10:30", "America/Tijuana")
        cancun = fecha_hora_utc_iso("2026-08-20", "10:30", "America/Cancun")
        self.assertNotEqual(tijuana, cancun)
        self.assertTrue(tijuana.endswith("Z"))
        self.assertTrue(cancun.endswith("Z"))

    def test_long_spanish_date_contract(self):
        dt = datetime(2026, 8, 20, 10, 30, tzinfo=ZoneInfo("America/Mexico_City"))
        self.assertEqual(fmt_fecha_larga(dt), "jueves 20 de agosto de 2026, 10:30")

    def test_ics_keeps_one_hour_and_utc_shape(self):
        ics = construir_ics("2026-08-20", "10:30", "Visita", "Casa", "America/Mexico_City")
        self.assertIn("BEGIN:VCALENDAR\r\n", ics)
        self.assertIn("DTSTART:20260820T163000Z", ics)
        self.assertIn("DTEND:20260820T173000Z", ics)
        self.assertIn("SUMMARY:Visita", ics)
        self.assertIn("DESCRIPTION:Casa", ics)
        self.assertIn("@broquer.app", ics)

    def test_local_time_returns_aware_datetime_for_valid_zone(self):
        self.assertIsNotNone(hora_local("America/Mexico_City").tzinfo)

    def test_preparation_does_not_change_root_runtime_yet(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        for name in ("_now", "_hora_local", "_fmt_fecha_larga", "_fecha_hora_utc_iso", "_construir_ics"):
            self.assertIn(f"def {name}(", source)


if __name__ == "__main__":
    unittest.main()
