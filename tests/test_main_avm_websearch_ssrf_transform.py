from pathlib import Path
import ast
import unittest

from scripts.refactor_main_avm_websearch_ssrf_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def nested_async_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise AssertionError(f"expected one {name}, got {len(nodes)}")
    return ast.get_source_segment(source, nodes[0]) or ""


class AVMWebsearchSSRFTransformTests(unittest.TestCase):
    def test_transform_routes_page_fetch_through_safe_core_transport(self):
        source = MAIN.read_text(encoding="utf-8")
        transformed = transform_source(source)
        helper = nested_async_source(transformed, "_try_httpx")
        self.assertIn("await fetch_public_http_result(", helper)
        self.assertIn("timeout=FETCH_TIMEOUT", helper)
        self.assertIn("headers=headers", helper)
        self.assertNotIn("httpx.AsyncClient", helper)
        self.assertNotIn("follow_redirects=True", helper)

    def test_status_content_type_and_text_contract_are_preserved(self):
        helper = nested_async_source(transform_source(MAIN.read_text(encoding="utf-8")), "_try_httpx")
        self.assertIn('(r.headers.get("content-type") or "").lower()', helper)
        self.assertIn('if r.status_code >= 400 or "text/html" not in ctype:', helper)
        self.assertIn('return {"ok": False, "status": r.status_code, "text": ""}', helper)
        self.assertIn('return {"ok": True, "status": r.status_code, "text": _extract_visible_text(r.text)}', helper)

    def test_transform_is_idempotent_and_compiles(self):
        source = MAIN.read_text(encoding="utf-8")
        once = transform_source(source)
        twice = transform_source(once)
        self.assertEqual(once, twice)
        compile(once, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
