"""Keep _machote_o_404's read behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainMachoteLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = MAIN.read_text(encoding="utf-8")
        start = source.index("async def _machote_o_404(")
        end = source.index("\n\nasync def _descargar_plantilla", start)
        cls.block = source[start:end]

    def test_lookup_uses_core_and_preserves_404_contract(self):
        block = self.block
        self.assertIn('rows = await get_rows(\n            "machotes_contrato",', block)
        self.assertIn('"id": f"eq.{machote_id}"', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": select', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertEqual(block.count('raise HTTPException(status_code=404, detail="No encontramos ese machote.")'), 2)
        self.assertIn("if not rows:", block)
        self.assertIn("return rows[0]", block)
        self.assertNotIn("/rest/v1/machotes_contrato", block)
        self.assertNotIn("Authorization", block)
        self.assertNotIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
