from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_concurrency_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_concurrency.py"


class WhatsAppConcurrencyExtractionTests(unittest.TestCase):
    def test_lock_registry_keeps_bounds_and_skips_locked_entries(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            "if len(_LOCKS) > 5000:",
            "list(_LOCKS.keys())[:1000]",
            "if not _LOCKS[key].locked():",
            "_LOCKS.pop(key, None)",
        ):
            self.assertIn(required, source)

    def test_transform_reuses_lock_caller(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("def _lock_conv(", transformed)
        self.assertNotIn("_LOCKS: dict", transformed)
        self.assertIn('async with _lock_conv(item["conversacion_id"]):', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
