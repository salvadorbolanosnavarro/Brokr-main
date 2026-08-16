"""Permanent guards for Lead Ads anti-replay Core delegation."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbLeadReplayLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = cls.source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
        cls.block = cls.source[start:end]

    def test_only_ledger_write_remains_direct(self):
        self.assertEqual(self.block.count("/rest/v1/fb_leads_recibidos"), 1)

    def test_lookup_uses_core_and_preserves_fail_soft_and_write(self):
        block = self.block
        self.assertIn('filas_previas = await get_rows(\n                "fb_leads_recibidos",', block)
        self.assertIn('"leadgen_id": f"eq.{leadgen_id}"', block)
        self.assertIn('"select": "id,procesado"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn("if _fb_tabla_falta(e.response):", block)
        self.assertIn('_fb_avisa_migracion("procesar lead", e.response)', block)
        self.assertIn("filas_previas = []", block)
        self.assertIn('if filas_previas and (filas_previas[0] or {}).get("procesado"):', block)
        self.assertIn('except Exception:\n        pass', block)
        self.assertIn('r = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/fb_leads_recibidos"', block)


if __name__ == "__main__":
    unittest.main()
