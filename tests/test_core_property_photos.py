from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "property_photos.py"


class CorePropertyPhotosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_shared_bucket_and_worker_state_are_canonical(self):
        self.assertIn('FOTOS_BUCKET = "fotos-propiedades"', self.source)
        self.assertIn('fotos_en_proceso: set[str] = set()', self.source)

    def test_migration_predicate_preserves_external_http_contract(self):
        self.assertIn('url.startswith("http")', self.source)
        self.assertIn('not foto_ya_es_de_broquer(url)', self.source)
        self.assertIn('settings.supabase_url in url', self.source)

    def test_module_compiles(self):
        compile(self.source, "core/property_photos.py", "exec")


if __name__ == "__main__":
    unittest.main()
