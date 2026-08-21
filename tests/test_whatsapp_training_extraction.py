from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from routers.whatsapp_training import (
    TRAINING_DEFAULTS,
    _calificacion_para_prompt,
    _conocimiento_para_prompt,
    _en_horario,
    _reglas_para_prompt,
)
from scripts.refactor_whatsapp_extract_training_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppTrainingPolicyTests(unittest.TestCase):
    def test_defaults_preserve_legacy_business_policy(self):
        self.assertEqual(TRAINING_DEFAULTS["tono"], "cálido y profesional")
        self.assertEqual(TRAINING_DEFAULTS["modo_ia"], "siempre_encendida")
        self.assertEqual(TRAINING_DEFAULTS["pausa_duracion_min"], 0)
        self.assertEqual(TRAINING_DEFAULTS["nuevos_meses"], 3)
        self.assertEqual(
            TRAINING_DEFAULTS["datos_calificar"],
            ["presupuesto", "forma de pago", "para cuándo busca", "zona de interés"],
        )

    def test_prompt_rules_keep_order_and_only_list_questions(self):
        e = {
            "puede": "A",
            "debe": "B",
            "no_debe": "C",
            "preguntas_extra": ["D", "E"],
        }
        self.assertEqual(
            _reglas_para_prompt(e),
            "Puedes: A. Debes: B. Nunca: C. Además pregunta cuando venga al caso: D; E.",
        )
        self.assertEqual(_reglas_para_prompt({"preguntas_extra": "D"}), "")

    def test_business_knowledge_is_trimmed_and_capped(self):
        self.assertEqual(_conocimiento_para_prompt({"conocimiento": "  "}), "")
        out = _conocimiento_para_prompt({"conocimiento": " x " * 4000})
        prefix = "INFORMACIÓN DEL NEGOCIO (fuente de verdad, úsala tal cual y NUNCA la contradigas):\n"
        self.assertTrue(out.startswith(prefix))
        self.assertLessEqual(len(out) - len(prefix) - 1, 6000)
        self.assertTrue(out.endswith("\n"))

    def test_qualification_accepts_list_string_and_default(self):
        self.assertEqual(_calificacion_para_prompt({"datos_calificar": ["a", "b"]}), "a, b")
        self.assertEqual(_calificacion_para_prompt({"datos_calificar": "a, b , c"}), "a, b, c")
        self.assertEqual(
            _calificacion_para_prompt({}),
            "presupuesto, forma de pago, para cuándo busca, zona de interés",
        )

    def test_schedule_is_fail_open_exactly_like_legacy_policy(self):
        self.assertTrue(_en_horario({"horario_activo": False}))
        fake_now = datetime(2026, 8, 20, 12, 0)
        with patch("routers.whatsapp_training._hora_local", return_value=fake_now):
            self.assertTrue(_en_horario({"horario_activo": True, "hora_inicio": "08:00", "hora_fin": "21:00"}))
            self.assertFalse(_en_horario({"horario_activo": True, "hora_inicio": "13:00", "hora_fin": "21:00"}))
        with patch("routers.whatsapp_training._hora_local", side_effect=RuntimeError("bad tz")):
            self.assertTrue(_en_horario({"horario_activo": True}))


class WhatsAppTrainingExtractionTests(unittest.TestCase):
    def test_transform_imports_policy_and_removes_duplicate_implementation(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_training import (", transformed)
        self.assertNotIn("TRAINING_DEFAULTS = {", transformed)
        self.assertNotIn("def _reglas_para_prompt", transformed)
        self.assertNotIn("def _conocimiento_para_prompt", transformed)
        self.assertNotIn("def _calificacion_para_prompt", transformed)
        self.assertNotIn("def _en_horario", transformed)
        self.assertIn("async def _entrenamiento_de", transformed)
        self.assertIn("async def recepcion2_responde", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
