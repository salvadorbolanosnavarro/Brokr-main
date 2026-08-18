"""Permanent regression guard for main.py configuration centralization."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def imported_names(source: str, module: str) -> set[str]:
    tree = ast.parse(source)
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }


class MainConfigCoreRefactorTests(unittest.TestCase):
    def test_main_uses_core_configuration_only(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        easybroker = (ROOT / "core" / "easybroker.py").read_text(encoding="utf-8")
        revenuecat = (ROOT / "routers" / "revenuecat.py").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"\bos\.(?:getenv|environ)\b", source))
        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.legacy_main_config import legacy_main_settings", source)
        self.assertIn("SUPABASE_KEY      = settings.supabase_anon_key", source)
        self.assertIn("SUPABASE_SERVICE_KEY = settings.supabase_service_key", source)
        self.assertTrue({"EB_API_KEY", "EB_BASE", "eb_headers"} <= imported_names(source, "core.easybroker"))
        self.assertNotIn("EB_API_KEY       = settings.easybroker_api_key", source)
        self.assertIn('EB_API_KEY = settings.easybroker_api_key or _load_legacy_config().get("eb_api_key", "")', easybroker)
        self.assertIn('Path(__file__).resolve().parents[1] / "config.json"', easybroker)
        self.assertIn("FB_APP_ID     = settings.legacy_main_fb_app_id", source)
        self.assertIn("expected_auth = legacy_main_settings.revenuecat_webhook_auth", revenuecat)
        self.assertIn("settings.groq_api_key", source)
        compile(easybroker, "core/easybroker.py", "exec")
        compile(revenuecat, "routers/revenuecat.py", "exec")
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
