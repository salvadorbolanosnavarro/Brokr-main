"""Dry-run guards for Lead Ads anti-replay Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_lead_replay_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_lead_replay_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFbLeadReplayLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_replay_get_only(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertEqual(block.count("/rest/v1/fb_leads_recibidos"), 1)  # _anota POST remains
        compile(transformed, "main.py", "exec")

    def test_lookup_uses_core_and_preserves_fail_soft_and_write(self):
        block = self._block(_load_transform()(self.source))
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
