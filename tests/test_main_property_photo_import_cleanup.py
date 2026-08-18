from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class PropertyPhotoImportCleanupTests(unittest.TestCase):
    def test_dead_bucket_alias_is_absent_from_main(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertNotIn('from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET', source)
        self.assertNotIn('_FOTOS_BUCKET', source)
        compile(source, 'main.py', 'exec')


if __name__ == '__main__':
    unittest.main()
