import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class SecurityHardeningTests(unittest.TestCase):
    def test_whatsapp_secrets_have_no_public_defaults_and_webhook_fails_closed(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        self.assertIn('WA2_VERIFY_TOKEN = os.environ.get("WA2_VERIFY_TOKEN", "").strip()', source)
        self.assertIn('WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "").strip()', source)
        self.assertNotIn('broquer2_verify', source)
        self.assertIn('if WA2_VERIFY_TOKEN and p.get("hub.mode") == "subscribe"', source)

    def test_chatgpt_registration_pin_fails_closed(self):
        source = (ROOT / "routers" / "whatsapp_chatgpt.py").read_text(encoding="utf-8")
        self.assertIn('WA_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "").strip()', source)
        self.assertIn('if req.register_number and not WA_REGISTER_PIN:', source)

    def test_meta_token_writes_fail_closed(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('TOKEN_ENC_KEY no configurada o inválida; no se guardará el token en texto plano.', source)
        self.assertIn('No se pudo cifrar el token de Meta; no se guardará en texto plano.', source)

    def test_avm_fetch_uses_ssrf_safe_transport(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_try_httpx"]
        self.assertEqual(len(nodes), 1)
        block = ast.get_source_segment(source, nodes[0]) or ""
        self.assertIn('fetch_public_http_result', block)
        self.assertNotIn('follow_redirects=True', block)

    def test_docx_parsers_validate_before_expansion(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        machotes = (ROOT / "machotes.py").read_text(encoding="utf-8")
        self.assertIn('validate_docx_archive(raw)', main)
        self.assertIn('validate_docx_archive(content)', main)
        self.assertIn('validate_docx_archive(content)', machotes)

if __name__ == '__main__':
    unittest.main()
