from pathlib import Path
import unittest

from routers.whatsapp_utils import in_filter, money, normaliza_mx, parsear_presupuesto

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppPureUtilityTests(unittest.TestCase):
    def test_mexico_phone_normalization_contract(self):
        self.assertEqual(normaliza_mx("+52 443 123 4567"), "524431234567")
        self.assertEqual(normaliza_mx("+52 1 443 123 4567"), "524431234567")
        self.assertEqual(normaliza_mx("443-123-4567"), "4431234567")
        self.assertEqual(normaliza_mx(""), "")

    def test_money_contract(self):
        self.assertEqual(money(1200000), "$1,200,000")
        self.assertEqual(money("1999.6"), "$2,000")
        self.assertEqual(money("texto"), "texto")
        self.assertEqual(money(None), "")

    def test_budget_parser_contract(self):
        self.assertEqual(parsear_presupuesto("2 millones"), 2_000_000)
        self.assertEqual(parsear_presupuesto("1.5 mdp"), 1_500_000)
        self.assertEqual(parsear_presupuesto("800 mil"), 800_000)
        self.assertEqual(parsear_presupuesto("$1,200,000"), 1_200_000)
        self.assertIsNone(parsear_presupuesto("unos cuantos"))
        self.assertIsNone(parsear_presupuesto(""))

    def test_postgrest_in_filter_contract(self):
        self.assertEqual(in_filter(["a", "b", "c"]), "in.(a,b,c)")
        self.assertEqual(in_filter([]), "in.()")

    def test_root_has_exactly_one_utility_implementation_state(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        canonical = (
            "from routers.whatsapp_utils import "
            "in_filter as _in_filter, money as _money, normaliza_mx as _normaliza_mx, "
            "parsear_presupuesto as _parsear_presupuesto"
        )
        local_names = ("_normaliza_mx", "_money", "_parsear_presupuesto", "_in_filter")
        local_present = [f"def {name}(" in source for name in local_names]
        imported = canonical in source
        self.assertTrue(imported or all(local_present))
        self.assertFalse(imported and any(local_present))


if __name__ == "__main__":
    unittest.main()
