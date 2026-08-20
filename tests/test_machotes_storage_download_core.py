from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "machotes.py"
TRANSFORM = ROOT / "scripts" / "refactor_machotes_download_storage_core.py"


class MachotesStorageDownloadCoreTests(unittest.TestCase):
    def test_download_is_valid_before_or_after_core_cut(self):
        source = ROUTER.read_text(encoding="utf-8")
        direct = 'f"{settings.supabase_url}/storage/v1/object/{MACHOTES_BUCKET}/{storage_path}"' in source
        delegated = "return await download_object(MACHOTES_BUCKET, storage_path, timeout=30)" in source
        self.assertNotEqual(direct, delegated)

        # Upload is intentionally out of scope for this bounded cut.
        self.assertIn("async def _subir_a_storage(", source)
        self.assertIn('"x-upsert": "true"', source)
        compile(source, "routers/machotes.py", "exec")
        compile(TRANSFORM.read_text(encoding="utf-8"), str(TRANSFORM), "exec")

    def test_post_cut_contract_is_encoded_in_transform(self):
        transform = TRANSFORM.read_text(encoding="utf-8")
        self.assertIn("from core.storage import download_object", transform)
        self.assertIn("timeout=30", transform)
        self.assertIn('except httpx.HTTPStatusError:', transform)
        self.assertIn('detail=\"No se pudo leer el archivo de tu machote.\"', transform)
        self.assertIn("Machotes upload behavior moved unexpectedly", transform)


if __name__ == "__main__":
    unittest.main()
