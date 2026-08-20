from pathlib import Path
import ast
import unittest

from scripts.refactor_whatsapp_connect_secret_guards_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class WhatsAppConnectSecretGuardTransformTests(unittest.TestCase):
    def test_connect_fails_closed_without_verify_token_and_registration_pin(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        func = async_function_source(transformed, "wa2_connect")
        self.assertIn("if not WA2_VERIFY_TOKEN:", func)
        self.assertIn('raise HTTPException(status_code=500, detail="WA2_VERIFY_TOKEN no configurado")', func)
        self.assertIn("if not req.coexistence and not WA2_REGISTER_PIN:", func)
        self.assertIn('raise HTTPException(status_code=500, detail="WA_REGISTER_PIN no configurado")', func)

    def test_coexistence_keeps_pin_optional_because_register_is_skipped(self):
        transformed = transform_source(WHATSAPP.read_text(encoding="utf-8"))
        func = async_function_source(transformed, "wa2_connect")
        self.assertIn("if req.coexistence:", func)
        self.assertIn("se omite /register", func)
        self.assertIn('json={"messaging_product": "whatsapp", "pin": WA2_REGISTER_PIN}', func)

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
