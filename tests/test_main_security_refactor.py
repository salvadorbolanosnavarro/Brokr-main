"""Permanent regression guard for the narrow main.py security cut."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainSecurityRegressionTests(unittest.TestCase):
    def test_main_keeps_privileged_fallbacks_closed(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn("from core.config import settings", source)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", source)
        self.assertNotIn(
            'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY',
            source,
        )
        self.assertIn("from routers.organizaciones import (", source)
        self.assertNotIn("No se pudo importar el contexto de organización", source)
        self.assertNotIn(
            "async def exigir_gestion_integraciones(request):\n        return await get_user_id_from_token(request)",
            source,
        )
        # Runtime environment access was centralized in Core after the original
        # security cut. main.py must never rebuild environment policy locally.
        self.assertIsNone(re.search(r"\bos\.(?:getenv|environ)\b", source))
        self.assertIn("EB_API_KEY       = settings.easybroker_api_key or _config.get", source)
        self.assertIn("from core.auth import get_user_id_from_token", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
