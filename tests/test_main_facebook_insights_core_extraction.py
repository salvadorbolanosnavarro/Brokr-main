"""Permanent guards for shared Facebook insights logic living in Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_insights.py"


class FacebookInsightsCoreExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_insights_vocabulary_and_normalizer(self):
        self.assertIn("from core.facebook_insights import (", self.main)
        for name in ("_FB_DATE_PRESETS", "_FB_BREAKDOWNS", "_FB_ACCIONES_CLAVE", "_FB_INSIGHTS_FIELDS"):
            self.assertNotIn(f"{name} =", self.main)
        self.assertNotIn("def _fb_normaliza_insights(", self.main)
        self.assertIn("_FB_DATE_PRESETS", self.main)
        self.assertIn("_FB_INSIGHTS_FIELDS", self.main)
        self.assertIn("_fb_normaliza_insights", self.main)

    def test_core_preserves_fields_actions_and_defensive_normalization(self):
        c = self.core
        self.assertIn('"last_7d"', c)
        self.assertIn('"publisher_platform"', c)
        self.assertIn('"onsite_conversion.messaging_conversation_started_7d": "conversaciones"', c)
        self.assertIn('"leadgen_grouped": "leads_formulario"', c)
        self.assertIn("actions,cost_per_action_type,objective,date_start,date_stop", c)
        self.assertIn("def normalize_facebook_insights(ins: dict) -> dict:", c)
        self.assertIn("if not isinstance(item, dict):", c)
        self.assertIn("except (TypeError, ValueError):", c)
        self.assertIn('"actions": ins.get("actions") or []', c)
        self.assertIn('out["engagement"] = out.get("engagement", 0) or acciones.get("post_engagement", 0)', c)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_insights.py", "exec")


if __name__ == "__main__":
    unittest.main()
