from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_training_api_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
TRAINING_API = ROOT / "routers" / "whatsapp_training_api.py"


class WhatsAppTrainingAPIStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRAINING_API.read_text(encoding="utf-8")

    def test_request_defaults_and_bounds_are_preserved(self):
        for snippet in (
            'hora_inicio: str = "08:00"',
            'hora_fin: str = "21:00"',
            'modo_ia: str = "siempre_encendida"',
            'pausa_duracion_min: int = 0',
            'nuevos_meses: int = 3',
            '60 * 24 * 30',
            'min(int(fila.get("nuevos_meses") or 3), 24)',
        ):
            self.assertIn(snippet, self.source)

    def test_team_scope_and_persisted_owner_contract_are_preserved(self):
        self.assertIn('"user_id": _in_filter(ids)', self.source)
        self.assertIn('fila["user_id"] = numero_rows[0]["user_id"]', self.source)
        self.assertIn('detail="Número no encontrado o no tienes permiso sobre él"', self.source)

    def test_failed_persistence_is_not_reported_as_success(self):
        self.assertIn("if not guardado:", self.source)
        self.assertIn("status_code=500", self.source)
        self.assertIn("No se pudo guardar el entrenamiento", self.source)


class WhatsAppTrainingAPIExtractionTests(unittest.TestCase):
    def test_transform_moves_get_put_but_leaves_ai_sandbox(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_training_api import router as whatsapp_training_api_router", transformed)
        self.assertIn("router.include_router(whatsapp_training_api_router)", transformed)
        self.assertNotIn("class TrainingReq", transformed)
        self.assertNotIn("async def wa2_training_get", transformed)
        self.assertNotIn("async def wa2_training_put", transformed)
        self.assertIn("class ProbarReq", transformed)
        self.assertIn("async def wa2_probar", transformed)
        self.assertIn("async def recepcion2_responde", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
