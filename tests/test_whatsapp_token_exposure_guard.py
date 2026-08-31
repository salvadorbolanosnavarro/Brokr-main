from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )
    return ast.get_source_segment(source, node) or ""


class WhatsAppTokenExposureGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WHATSAPP.read_text(encoding="utf-8")

    def test_number_list_never_returns_stored_access_token(self):
        func = async_function_source(self.source, "wa2_numeros_list")
        self.assertIn('r.pop("access_token", None)', func)
        self.assertIn('return {"numeros": rows}', func)

    def test_connect_response_does_not_echo_business_token(self):
        func = async_function_source(self.source, "wa2_connect")
        return_tail = func.rsplit("return resultado", 1)[0]
        self.assertIn('resultado = {"ok": True', return_tail)
        self.assertNotIn('"access_token": business_token', return_tail.split('resultado = ', 1)[1])
        self.assertNotIn('"token": business_token', return_tail.split('resultado = ', 1)[1])

    def test_number_patch_cannot_replace_access_token_from_browser(self):
        tree = ast.parse(self.source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NumeroPatchReq")
        fields = {
            target.id
            for node in cls.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            for target in [node.target]
        }
        self.assertEqual(fields, {"alias", "ia_enabled", "numero_personal"})
        self.assertNotIn("access_token", fields)


if __name__ == "__main__":
    unittest.main()
