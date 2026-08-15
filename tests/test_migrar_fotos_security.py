"""Regression guards for the one-shot photo migration script."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MigrarFotosSecurityTests(unittest.TestCase):
    def test_script_has_no_embedded_jwt_or_direct_supabase_rest(self):
        source = (ROOT / "migrar_fotos.py").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"eyJ[A-Za-z0-9_-]{20,}", source))
        self.assertNotIn("/rest/v1/", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", source)

    def test_script_uses_canonical_core_access(self):
        source = (ROOT / "migrar_fotos.py").read_text(encoding="utf-8")

        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.database import get_rows, patch_rows", source)
        self.assertIn("from core.storage import upload_object", source)
        self.assertIn("settings.require_supabase_service()", source)
        compile(source, "migrar_fotos.py", "exec")


if __name__ == "__main__":
    unittest.main()
