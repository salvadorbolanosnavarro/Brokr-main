"""Permanent guards for extracting POST /facebook/encrypt-tokens from main.py."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_encrypt_tokens.py"


class MainFacebookEncryptTokensExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_leaves_main_and_router_is_mounted(self):
        self.assertNotIn('@app.post("/facebook/encrypt-tokens")', self.main)
        self.assertIn(
            "from routers.facebook_encrypt_tokens import router as facebook_encrypt_tokens_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_encrypt_tokens_router)", self.main)
        self.assertIn('@router.post("/facebook/encrypt-tokens")', self.router)

    def test_fail_closed_authorization_and_idempotent_rewrite_stay_intact(self):
        source = self.router
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", source)
        self.assertIn("if not facebook_secret_encryption_available():", source)
        self.assertIn("status_code=503", source)
        self.assertIn("Falta configurar TOKEN_ENC_KEY en el servidor.", source)
        self.assertIn("fila = await get_facebook_meta_row(user_id)", source)
        self.assertIn('status_code=400, detail="No hay conexión de Facebook."', source)
        self.assertIn("await patch_facebook_meta(", source)
        self.assertIn('"tokens_cifrados_at": datetime.now(timezone.utc).isoformat()', source)
        self.assertIn('"mensaje": "Tus tokens de Facebook quedaron cifrados en reposo."', source)

    def test_router_has_no_main_dependency_and_compiles(self):
        self.assertNotIn("from main import", self.router)
        self.assertIn(
            "from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta",
            self.router,
        )
        self.assertIn(
            "from core.facebook_secrets import facebook_secret_encryption_available",
            self.router,
        )
        self.assertIn(
            "from routers.organizaciones import exigir_gestion_integraciones",
            self.router,
        )
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_encrypt_tokens.py", "exec")


if __name__ == "__main__":
    unittest.main()
