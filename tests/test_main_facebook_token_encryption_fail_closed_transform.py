from pathlib import Path
import ast
import unittest

from scripts.refactor_main_facebook_token_encryption_fail_closed_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


class FacebookTokenEncryptionFailClosedTransformTests(unittest.TestCase):
    def test_new_token_writes_cannot_fall_back_to_cleartext(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        func = function_source(transformed, "cifrar_secreto")
        self.assertIn("if not _FERNET:", func)
        self.assertIn("no se guardará el token en texto plano", func)
        self.assertIn("raise RuntimeError", func)
        self.assertNotIn("_fermet_aviso_dado", func)

    def test_legacy_cleartext_reads_remain_compatible(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        decrypt = function_source(transformed, "descifrar_secreto")
        self.assertIn('if not valor.startswith(_PREFIJO_CIFRADO):\n        return valor', decrypt)

    def test_user_and_page_tokens_still_pass_through_encryptor_before_persistence(self):
        transformed = transform_source(MAIN.read_text(encoding="utf-8"))
        self.assertIn('"user_token": cifrar_secreto(req.user_token)', transformed)
        self.assertIn('"api_key": cifrar_secreto(req.page_token)', transformed)
        self.assertIn('meta["user_token"] = cifrar_secreto(meta["user_token"])', transformed)
        self.assertIn('"api_key": cifrar_secreto(page_token)', transformed)

    def test_transform_is_idempotent_and_compiles(self):
        source = MAIN.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))
        compile(once, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
