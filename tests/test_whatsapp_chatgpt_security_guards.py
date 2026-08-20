from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "whatsapp_chatgpt.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.get_source_segment(source, node) or ""


class WhatsAppChatGPTSecurityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_public_number_strips_meta_access_token(self):
        func = function_source(self.source, "_public_number")
        self.assertIn('safe.pop("access_token", None)', func)
        signup = function_source(self.source, "complete_signup")
        self.assertIn('"number": _public_number(stored)', signup)

    def test_numbers_list_never_selects_access_token(self):
        func = function_source(self.source, "numbers")
        self.assertNotIn("access_token", func)
        self.assertIn('"user_id": f"eq.{uid}"', func)

    def test_send_test_requires_number_owned_by_current_user(self):
        func = function_source(self.source, "send_test")
        self.assertIn('"user_id": f"eq.{uid}"', func)
        self.assertIn('"phone_number_id": f"eq.{req.phone_number_id}"', func)
        self.assertIn('detail="Ese número no está conectado a tu cuenta."', func)


if __name__ == "__main__":
    unittest.main()
