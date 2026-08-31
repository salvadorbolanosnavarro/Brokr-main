"""Guards that prevent migrated modules from regressing into legacy patterns."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]

MIGRATED_MODULES = (
    "admin_consola.py",
    "limites.py",
    "push.py",
    "routers/bolsa.py",
    "routers/staging.py",
    "routers/correo.py",
    "routers/video.py",
    "routers/whatsapp_chatgpt.py",
)

# These patterns are intentionally narrow: the goal is to stop migrated files
# from rebuilding infrastructure that already has one canonical home in Core.
FORBIDDEN_PATTERNS = {
    "direct environment reads": re.compile(r"\bos\.(?:getenv|environ)\b"),
    "service-key fallback to anon": re.compile(
        r"SUPABASE_SERVICE_KEY\s*=.*\bor\b.*(?:SUPABASE_KEY|SUPABASE_ANON_KEY)"
    ),
    "duplicated auth helper": re.compile(r"async\s+def\s+get_user_id_from_token\s*\("),
    "duplicated service headers": re.compile(r"def\s+_(?:sb_)?headers\s*\("),
    "direct Supabase REST I/O": re.compile(r"/rest/v1/"),
}


class MigratedModuleGuards(unittest.TestCase):
    def test_migrated_modules_do_not_rebuild_core_infrastructure(self):
        for relative_path in MIGRATED_MODULES:
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            for label, pattern in FORBIDDEN_PATTERNS.items():
                with self.subTest(file=relative_path, rule=label):
                    self.assertIsNone(
                        pattern.search(text),
                        f"{relative_path} regressed: {label} belongs in core/",
                    )

    def test_migrated_modules_import_shared_core(self):
        for relative_path in MIGRATED_MODULES:
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(file=relative_path):
                self.assertRegex(
                    text,
                    r"(?:from|import)\s+core(?:\.|\s)",
                    f"{relative_path} must depend on shared Core infrastructure",
                )

    def test_whatsapp_signup_never_returns_meta_token(self):
        text = (ROOT / "routers/whatsapp_chatgpt.py").read_text(encoding="utf-8")
        self.assertIn("_public_number", text)
        self.assertIn('safe.pop("access_token", None)', text)


if __name__ == "__main__":
    unittest.main()
