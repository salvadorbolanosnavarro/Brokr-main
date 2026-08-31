"""Permanent guards for connected Facebook property publishing extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_publish_property.py"


class FacebookPublishPropertyExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_publish_property_to_router(self):
        self.assertNotIn('@app.post("/facebook/publish-property")', self.main)
        self.assertIn(
            "from routers.facebook_publish_property import router as facebook_publish_property_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_publish_property_router)", self.main)

    def test_router_preserves_auth_connection_and_message_mapping(self):
        router = self.router
        self.assertIn('@router.post("/facebook/publish-property")', router)
        self.assertIn('user_id = await get_user_id_from_token(request)', router)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado")', router)
        self.assertIn('body = await request.json()', router)
        self.assertIn('body.get("titulo", "Nueva propiedad")', router)
        self.assertIn('body.get("tipo", "Inmueble")', router)
        self.assertIn('body.get("operacion", "venta")', router)
        self.assertIn('row = await get_facebook_meta_row(user_id)', router)
        self.assertIn('page_id = meta.get("page_id", "")', router)
        self.assertIn('page_token = row.get("page_token", "")', router)
        self.assertIn('"Facebook no conectado. Ve a tu perfil para conectar tu página."', router)
        self.assertIn('precio_fmt = f"${int(precio):,}" if precio else ""', router)
        self.assertIn('descripcion[:200]', router)
        self.assertIn('"✅ Publicado con Broquer"', router)

    def test_router_preserves_photo_fail_soft_and_final_publish(self):
        router = self.router
        self.assertIn('httpx.AsyncClient(timeout=30)', router)
        self.assertIn('for url in (fotos or [])[:5]:', router)
        self.assertIn('f"{page_id}/photos"', router)
        self.assertIn('token=page_token', router)
        self.assertIn('json_body={"url": url, "published": False}', router)
        self.assertIn('except Exception:', router)
        self.assertIn('payload: dict = {"message": mensaje}', router)
        self.assertIn('payload["attached_media"] = photo_ids', router)
        self.assertIn('f"{page_id}/feed"', router)
        self.assertIn('_fb_exigir_ok(post_response, "Error publicando en Facebook")', router)
        self.assertIn('"page_name": facebook.get("page_name", "")', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_publish_property.py", "exec")


if __name__ == "__main__":
    unittest.main()
