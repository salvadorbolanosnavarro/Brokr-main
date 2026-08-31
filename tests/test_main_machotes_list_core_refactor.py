"""Keep GET /contrato/machotes behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "machotes.py"


class MainMachotesListCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROUTER.read_text(encoding="utf-8")
        start = source.index('@router.get("/contrato/machotes")')
        end = source.index('@router.get("/contrato/machote/{machote_id}")', start)
        cls.block = source[start:end]

    def test_list_uses_core_and_preserves_http_500_contract(self):
        block = self.block
        self.assertIn('rows = await get_rows(', block)
        self.assertIn('"machotes_contrato"', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": "id,titulo,tipo,campos,motor,created_at"', block)
        self.assertIn('"order": "created_at.desc"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")', block)
        self.assertIn('return {"machotes": rows}', block)
        self.assertNotIn("/rest/v1/machotes_contrato", block)
        self.assertNotIn("Authorization", block)
        self.assertNotIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
