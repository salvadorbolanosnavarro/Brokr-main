from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_tokens.py"
PROFILE = ROOT / "routers" / "profile_status.py"


class FacebookTokenStateExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.profile = PROFILE.read_text(encoding="utf-8")

    def test_callers_delegate_token_state_to_core(self):
        self.assertIn('from core.facebook_tokens import facebook_token_state as _fb_estado_token', self.main)
        self.assertIn('facebook_token_state(meta)', self.profile)
        self.assertNotIn('def _fb_estado_token(', self.main)
        self.assertNotIn('_FB_AVISO_DIAS = 14', self.main)

    def test_core_preserves_warning_and_messages(self):
        self.assertIn('FACEBOOK_TOKEN_WARNING_DAYS = 14', self.core)
        self.assertIn('datetime.fromisoformat(str(raw).replace("Z", "+00:00"))', self.core)
        self.assertIn('Tu conexión con Facebook expiró.', self.core)
        self.assertIn('Reconéctala desde tu perfil para no perder tus campañas de vista.', self.core)
        self.assertIn('"por_expirar": 0 < dias <= FACEBOOK_TOKEN_WARNING_DAYS', self.core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_tokens.py", "exec")
        compile(self.profile, "routers/profile_status.py", "exec")


if __name__ == "__main__":
    unittest.main()
