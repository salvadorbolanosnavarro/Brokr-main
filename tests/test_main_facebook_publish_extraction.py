"""Permanent guards for legacy Facebook Page publish extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_publish.py"


class FacebookPublishExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_publish_to_router(self):
        self.assertNotIn('class FbPublishRequest(BaseModel):', self.main)
        self.assertNotIn('@app.post("/facebook/publish")', self.main)
        self.assertIn(
            "from routers.facebook_publish import router as facebook_publish_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_publish_router)", self.main)

    def test_router_preserves_legacy_request_and_publish_flow(self):
        router = self.router
        self.assertIn('class FbPublishRequest(BaseModel):', router)
        self.assertIn('page_id: str', router)
        self.assertIn('page_token: str', router)
        self.assertIn('message: str', router)
        self.assertIn('photo_urls: list[str] = []', router)
        self.assertIn('@router.post("/facebook/publish")', router)
        self.assertIn('async def facebook_publish(req: FbPublishRequest):', router)
        self.assertIn('httpx.AsyncClient(timeout=30)', router)
        self.assertIn('for url in req.photo_urls[:10]:', router)
        self.assertIn('f"{req.page_id}/photos"', router)
        self.assertIn('token=req.page_token', router)
        self.assertIn('json_body={"url": url, "published": False}', router)
        self.assertIn('response.status_code in (200, 201)', router)
        self.assertIn('photo_ids.append({"media_fbid": photo_id})', router)
        self.assertIn('payload: dict = {"message": req.message}', router)
        self.assertIn('payload["attached_media"] = photo_ids', router)
        self.assertIn('f"{req.page_id}/feed"', router)
        self.assertIn('_fb_exigir_ok(post_response, "Error publicando en Facebook")', router)
        self.assertIn('return {"ok": True, "post_id": data.get("id")}', router)
        self.assertNotIn("from main import", router)

    def test_legacy_route_remains_unauthenticated_until_separate_hardening(self):
        self.assertNotIn("get_user_id_from_token", self.router)
        self.assertNotIn("exigir_gestion_integraciones", self.router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_publish.py", "exec")


if __name__ == "__main__":
    unittest.main()
