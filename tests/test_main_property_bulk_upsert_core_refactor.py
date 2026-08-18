"""Permanent guards for the EasyBroker bulk property upsert Core migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainPropertyBulkUpsertCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("    # ─── Paso 4: UPSERT en lotes a Supabase (50 por POST) ───")
        end = cls.source.index("    nuevas      =", start)
        cls.block = cls.source[start:end]

    def test_core_upsert_is_imported_and_direct_rest_post_stays_removed(self):
        tree = ast.parse(self.source)
        core_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "core.database"
            for alias in node.names
        }
        self.assertIn("upsert_rows", core_imports)
        self.assertNotIn("/rest/v1/propiedades", self.block)
        self.assertNotIn("ri = await client.post(", self.block)

    def test_retry_status_text_and_counters_remain_explicit(self):
        block = self.block
        self.assertIn("for intento in range(3):", block)
        self.assertIn('await upsert_rows(\n                        "propiedades",', block)
        self.assertIn('conflict="org_id,eb_public_id"', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn("timeout=60", block)
        self.assertIn("accepted_statuses=(200, 201, 204)", block)
        self.assertIn("upserted += len(chunk)", block)
        self.assertIn("guardado = True", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn('ultimo_fallo = f"Supabase {e.response.status_code}: {e.response.text[:200]}"', block)
        self.assertIn("except Exception as e:", block)
        self.assertIn("ultimo_fallo = str(e)[:200]", block)
        self.assertIn("await asyncio.sleep(1.5 * (2 ** intento))", block)
        self.assertIn("if not guardado:", block)
        self.assertIn('"id": f"lote_{i // UPSERT_BATCH}"', block)


if __name__ == "__main__":
    unittest.main()
