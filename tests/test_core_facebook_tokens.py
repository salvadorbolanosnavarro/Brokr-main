from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from core.facebook_tokens import FACEBOOK_TOKEN_WARNING_DAYS, facebook_token_state

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_tokens.py"


class FacebookTokenStateTests(unittest.TestCase):
    def test_missing_or_invalid_expiry_stays_unknown(self):
        expected = {"conocido": False, "dias_restantes": None, "expirado": False,
                    "por_expirar": False, "mensaje": ""}
        self.assertEqual(facebook_token_state({}), expected)
        self.assertEqual(facebook_token_state({"token_expires_at": "basura"}), expected)

    def test_warning_window_remains_fourteen_days(self):
        self.assertEqual(FACEBOOK_TOKEN_WARNING_DAYS, 14)
        future = datetime.now(timezone.utc) + timedelta(days=5)
        state = facebook_token_state({"token_expires_at": future.isoformat()})
        self.assertTrue(state["conocido"])
        self.assertTrue(state["por_expirar"])
        self.assertFalse(state["expirado"])
        self.assertIn("Reconéctala desde tu perfil", state["mensaje"])

    def test_expired_message_is_preserved(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        state = facebook_token_state({"token_expires_at": past.isoformat()})
        self.assertTrue(state["expirado"])
        self.assertIn("Tu conexión con Facebook expiró.", state["mensaje"])

    def test_core_compiles(self):
        source = CORE.read_text(encoding="utf-8")
        compile(source, "core/facebook_tokens.py", "exec")


if __name__ == "__main__":
    unittest.main()
