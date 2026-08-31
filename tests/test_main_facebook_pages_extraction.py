"""Permanent guards for GET /facebook/pages living outside main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_pages.py"


class FacebookPagesExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_mounts_read_only_pages_router(self):
        self.assertIn(
            "from routers.facebook_pages import router as facebook_pages_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_pages_router)", self.main)
        self.assertNotIn('@app.get("/facebook/pages")', self.main)
        self.assertNotIn("async def facebook_list_pages(", self.main)

    def test_router_preserves_auth_token_and_response_contract(self):
        router = self.router
        self.assertIn('@router.get("/facebook/pages")', router)
        self.assertIn("user_id = await get_user_id_from_token(request)", router)
        self.assertIn('status_code=401, detail="No autenticado"', router)
        self.assertIn("row = await get_facebook_meta_row(user_id)", router)
        self.assertIn('detail="Reconecta tu Facebook para habilitar el cambio de página."', router)
        self.assertIn('"me/accounts"', router)
        self.assertIn('"fields": "id,name,access_token,picture.type(square)"', router)
        self.assertIn('return {"pages": pages, "active_page_id": active_id}', router)

    def test_router_does_not_return_page_access_tokens(self):
        router = self.router
        return_block = router[router.index("pages = ["):]
        self.assertNotIn('"access_token":', return_block)
        self.assertIn('"picture":', return_block)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_pages.py", "exec")


if __name__ == "__main__":
    unittest.main()
