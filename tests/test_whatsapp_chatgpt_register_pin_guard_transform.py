from pathlib import Path
import ast
import unittest

from scripts.refactor_whatsapp_chatgpt_register_pin_guard_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "whatsapp_chatgpt.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class WhatsAppChatGPTRegisterPinGuardTests(unittest.TestCase):
    def test_registration_requires_configured_pin_only_when_requested(self):
        source = SOURCE.read_text(encoding="utf-8")
        transformed = transform_source(source)
        func = async_function_source(transformed, "complete_signup")
        self.assertIn("if req.register_number and not WA_REGISTER_PIN:", func)
        self.assertIn('detail="WA_REGISTER_PIN no configurado."', func)
        self.assertIn("if req.register_number:", func)
        self.assertIn('"pin": WA_REGISTER_PIN', func)

    def test_transform_is_idempotent(self):
        source = SOURCE.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
