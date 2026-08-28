"""Permanent guards for the EasyBroker bulk property upsert Core migration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_migration.py"


class MainPropertyBulkUpsertCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/easybroker/import-all")' in cls.source
        owner = cls.source if cls.legacy_owned else cls.router
        if cls.legacy_owned:
            start = owner.index("    # ─── Paso 4: UPSERT en lotes a Supabase (50 por POST) ───")
            end = owner.index("    nuevas      =", start)
        else:
            start = owner.index("        upserted = 0")
            end = owner.index("        nuevas =", start)
        cls.block = owner[start:end]

    def test_core_upsert_is_wired_and_direct_rest_post_stays_removed(self):
        tree = ast.parse(self.source)
        core_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "core.database"
            for alias in node.names
        }
        self.assertIn("upsert_rows", core_imports)
        if not self.legacy_owned:
            self.assertIn('"upsert_rows": upsert_rows', self.source)
            self.assertIn('upsert_rows_dep = deps["upsert_rows"]', self.router)
        self.assertNotIn("/rest/v1/propiedades", self.block)
        self.assertNotIn("ri = await client.post(", self.block)

    def test_retry_status_text_and_counters_remain_explicit(self):
        block = self.block
        self.assertIn("for intento in range(3):", block)
        if self.legacy_owned:
            self.assertIn('await upsert_rows(\n                        "propiedades",', block)
            self.assertIn("except httpx.HTTPStatusError as e:", block)
            self.assertIn("await asyncio.sleep(1.5 * (2 ** intento))", block)
        else:
            self.assertIn('await upsert_rows_dep(\n                            "propiedades",', block)
            self.assertIn("except httpx_dep.HTTPStatusError as e:", block)
            self.assertIn("await asyncio_dep.sleep(1.5 * (2 ** intento))", block)
        self.assertIn('conflict="org_id,eb_public_id"', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn("timeout=60", block)
        self.assertIn("accepted_statuses=(200, 201, 204)", block)
        self.assertIn("upserted += len(chunk)", block)
        self.assertIn("guardado = True", block)
        self.assertIn('ultimo_fallo = f"Supabase {e.response.status_code}: {e.response.text[:200]}"', block)
        self.assertIn("except Exception as e:", block)
        self.assertIn("ultimo_fallo = str(e)[:200]", block)
        self.assertIn("if not guardado:", block)
        self.assertIn('"id": f"lote_{i // ', block)


if __name__ == "__main__":
    unittest.main()
