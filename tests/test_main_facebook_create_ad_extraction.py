"""Permanent guards for static extraction of POST /facebook/create-ad."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_create_ad.py"


class FacebookCreateAdExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_model_and_route_move_out_of_main(self):
        self.assertNotIn("class FbCreateAdRequest(", self.main)
        self.assertNotIn('@app.post("/facebook/create-ad")', self.main)
        self.assertNotIn("async def facebook_create_ad(", self.main)
        self.assertIn("from routers.facebook_create_ad import router as facebook_create_ad_router", self.main)
        self.assertIn("app.include_router(facebook_create_ad_router)", self.main)
        self.assertIn('@router.post("/facebook/create-ad")', self.router)

    def test_server_side_account_page_and_idempotency_are_preserved(self):
        router = self.router
        self.assertIn('user_id = await get_user_id_from_token(request)', router)
        self.assertIn('detail="No autenticado"', router)
        self.assertIn('row = await get_facebook_meta_row(user_id)', router)
        self.assertIn('detail="Facebook no conectado"', router)
        self.assertIn('page_id = meta.get("page_id", "")', router)
        self.assertIn('server_account_id = meta.get("ad_account_id", "")', router)
        self.assertIn('req.account_id = (', router)
        self.assertIn('req.page_id = page_id', router)
        self.assertIn('f"{req.account_id}/promote_pages"', router)
        self.assertIn('except HTTPException:\n        raise\n    except Exception:\n        pass', router)
        self.assertIn('idem = (req.idempotency_key or "").strip()[:120]', router)
        self.assertIn('reserva = await reserve_facebook_creation(', router)
        self.assertIn('if estado_previo == "CREANDO":', router)
        self.assertIn('if estado_previo == "FALLIDO":', router)
        self.assertIn('"duplicado": True', router)
        self.assertIn('"Este anuncio ya se había creado. No se cobró dos veces."', router)

    def test_validation_targeting_and_cleanup_are_preserved(self):
        router = self.router
        self.assertIn('if not req.post_id and not images_b64:', router)
        self.assertIn('if len(images_b64) > 10:', router)
        self.assertIn('images_mime.append("image/jpeg")', router)
        self.assertIn('detail="Debes seleccionar una ciudad para el anuncio."', router)
        self.assertIn('f"{account_id}/adimages"', router)
        self.assertIn('ad_text = (req.ad_text or "")[:2200]', router)
        self.assertIn('headline = (req.headline or "")[:40]', router)
        self.assertIn('"is_adset_budget_sharing_enabled": False', router)
        self.assertIn('"targeting_automation": {"advantage_audience": 0}', router)
        self.assertIn('targeting["custom_audiences"]', router)
        self.assertIn('targeting["excluded_custom_audiences"]', router)
        self.assertIn('"destination_type": "MESSENGER"', router)
        self.assertIn('"DELETE",', router)
        self.assertIn('"No se pudieron borrar recursos de Meta: %s"', router)
        self.assertIn('"Revísalos en Ads Manager."', router)

    def test_creation_activation_rollback_and_bookkeeping_are_preserved(self):
        router = self.router
        self.assertIn('_fb_exigir_ok(campaign_response, "Error creando campaña")', router)
        self.assertIn('"object_story_id": req.post_id', router)
        self.assertIn('"type": "MESSAGE_PAGE"', router)
        self.assertIn('f"https://www.facebook.com/{page_id}"', router)
        self.assertIn('for nivel, resource_id in (', router)
        self.assertIn('(\"anuncio\", ad_id)', router)
        self.assertIn('json_body={"status": "ACTIVE"}', router)
        self.assertIn('for resource_id in reversed(activados):', router)
        self.assertIn('json_body={"status": "PAUSED"}', router)
        self.assertIn('target_status = "PAUSED"', router)
        self.assertIn('await update_facebook_entity(', router)
        self.assertIn('"error_detail": aviso_activacion or None', router)
        self.assertIn('"ads_manager_url": ads_manager_url', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_create_ad.py", "exec")


if __name__ == "__main__":
    unittest.main()
