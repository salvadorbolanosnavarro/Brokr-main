from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "stripe.py"


class StripeConfigExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_shared_stripe_config_to_core(self):
        self.assertIn("from core.stripe import (", self.main)
        for name in (
            "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_PRO",
            "STRIPE_PRICE_AMPI", "STRIPE_PRICE_EMPRESA_MENSUAL",
            "STRIPE_PRICE_EMPRESA_ANUAL", "STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL",
            "STRIPE_PRICE_EMPRESA_EXTRA_ANUAL", "EMPRESA_ASIENTOS_BASE",
            "EMPRESA_ASIENTOS_MAX", "EMPRESA_TARIFAS", "PROMO_CODE_AMPI",
        ):
            tree = ast.parse(self.main)
            assigned = {
                target.id
                for node in tree.body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)
            }
            self.assertNotIn(name, assigned)
        self.assertNotIn("def _stripe_headers(", self.main)
        self.assertNotIn("def _precio_empresa(", self.main)

    def test_core_preserves_exact_pricing_and_header_contract(self):
        core = self.core
        self.assertIn("STRIPE_SECRET_KEY = settings.stripe_secret_key", core)
        self.assertIn("STRIPE_WEBHOOK_SECRET = legacy_main_settings.stripe_webhook_secret", core)
        self.assertIn('EMPRESA_ASIENTOS_BASE = 5', core)
        self.assertIn('EMPRESA_ASIENTOS_MAX = 500', core)
        self.assertIn('"mensual": {"base": 3499, "extra": 599, "etiqueta": "al mes"}', core)
        self.assertIn('"anual": {"base": 38489, "extra": 6589, "etiqueta": "al año"}', core)
        self.assertNotIn('TRIAL_MAX_DIAS', core)
        self.assertIn('PROMO_CODE_AMPI = "ampi2026"', core)
        self.assertIn('"Authorization": f"Bearer {STRIPE_SECRET_KEY}"', core)
        self.assertIn('"Content-Type": "application/x-www-form-urlencoded"', core)
        self.assertIn('if periodo == "anual":', core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/stripe.py", "exec")


if __name__ == "__main__":
    unittest.main()
