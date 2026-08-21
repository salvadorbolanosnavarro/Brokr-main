from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_appointments_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_appointments.py"


class WhatsAppAppointmentsExtractionTests(unittest.TestCase):
    def test_appointment_contract_preserves_task_links_and_ics(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/agendar")',
            '"user_id": _in_filter(ids)',
            '{"etapa": "Cita"}',
            '"fecha_entrega": _fecha_hora_utc_iso',
            '"tareas_contactos"',
            '"tareas_propiedades"',
            "_construir_ics(",
            "await _wa_send_document(",
            '"cita.ics"',
        ):
            self.assertIn(required, source)

    def test_transform_moves_only_appointment_endpoint(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class AgendarReq", transformed)
        self.assertNotIn("async def wa2_agendar", transformed)
        self.assertIn("async def recepcion2_responde", transformed)
        self.assertIn("async def _buscar_inmuebles", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
