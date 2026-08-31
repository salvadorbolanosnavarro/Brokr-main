"""Permanent guards for GET /facebook/page-posts extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_page_posts.py"


class FacebookPagePostsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_route_to_router(self):
        self.assertIn(
            "from routers.facebook_page_posts import router as facebook_page_posts_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_page_posts_router)", self.main)
        self.assertNotIn('@app.get("/facebook/page-posts")', self.main)

    def test_router_preserves_auth_page_resolution_and_errors(self):
        r = self.router
        self.assertIn("user_id = await get_user_id_from_token(request)", r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn("row = await get_facebook_meta_row(user_id)", r)
        self.assertIn('status_code=400, detail="Facebook no conectado"', r)
        self.assertIn('(page_id or meta.get("page_id", "")).strip()', r)
        self.assertIn('status_code=400, detail="No hay página seleccionada."', r)
        self.assertIn('page_token = row.get("page_token", "")', r)
        self.assertIn('status_code=400, detail="Reconecta tu Facebook."', r)
        self.assertIn('"me/accounts"', r)
        self.assertIn('params={"fields": "id,access_token", "limit": "100"}', r)
        self.assertIn('prefix="No se pudieron resolver las páginas"', r)
        self.assertIn('status_code=400, detail="No administras esa página."', r)

    def test_router_preserves_post_shape_and_bounds(self):
        r = self.router
        self.assertIn("httpx.AsyncClient(timeout=15)", r)
        self.assertIn('f"{page_id}/posts"', r)
        self.assertIn('"limit": "25"', r)
        self.assertIn("max_paginas=1", r)
        self.assertIn("max_items=25", r)
        self.assertIn('prefix="Error obteniendo publicaciones"', r)
        self.assertIn('if p.get("is_published") is False:', r)
        self.assertIn('msg = (p.get("message") or "").strip()', r)
        self.assertIn('"message": msg[:280]', r)
        self.assertIn('"has_image": bool(p.get("full_picture"))', r)
        self.assertIn('return {"posts": items, "page_id": page_id}', r)
        self.assertNotIn("from main import", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_page_posts.py", "exec")


if __name__ == "__main__":
    unittest.main()
