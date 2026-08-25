"""Permanent guards for Facebook custom/lookalike audience extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_audiences.py"


class FacebookAudiencesExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_audience_routes_and_helpers_move_out_of_main(self):
        for fragment in (
            "def _hash_meta(",
            "def _normaliza_email(",
            "def _normaliza_telefono(",
            "class FbAudienceRequest(",
            "async def facebook_audience_from_contacts(",
            "class FbLookalikeRequest(",
            "async def facebook_audience_lookalike(",
            "async def _fb_guardar_audiencia(",
        ):
            self.assertNotIn(fragment, self.main)
        self.assertIn("from routers.facebook_audiences import router as facebook_audiences_router", self.main)
        self.assertIn("app.include_router(facebook_audiences_router)", self.main)
        self.assertIn('@router.post("/facebook/audiences/from-contacts")', self.router)
        self.assertIn('@router.post("/facebook/audiences/lookalike")', self.router)

    def test_hashing_normalization_and_tenant_filters_are_preserved(self):
        router = self.router
        self.assertIn('hashlib.sha256(valor.strip().lower().encode("utf-8")).hexdigest()', router)
        self.assertIn('email.count("@") != 1', router)
        self.assertIn('re.sub(r"\\D", "", tel or "")', router)
        self.assertIn('len(digitos) == 13 and digitos.startswith(lada_pais + "1")', router)
        self.assertIn('org_id = await get_org_id_for_user(user_id)', router)
        self.assertIn('filtros["org_id"] = f"eq.{org_id}"', router)
        self.assertIn('filtros["user_id"] = f"eq.{user_id}"', router)
        self.assertIn('filtros["es_potencial"] = "eq.true"', router)
        self.assertIn('"limit": "5000"', router)

    def test_custom_audience_upload_cleanup_and_warnings_are_preserved(self):
        router = self.router
        self.assertIn('"customer_file_source": "USER_PROVIDED_ONLY"', router)
        self.assertIn('"2654" in texto', router)
        self.assertIn('for i in range(0, len(datos), 5000):', router)
        self.assertIn('"schema": ["EMAIL", "PHONE"]', router)
        self.assertIn('timeout=90', router)
        self.assertIn('if not subidos:', router)
        self.assertIn('"DELETE",', router)
        self.assertIn('reintentos=2', router)
        self.assertIn('if subidos < 100:', router)
        self.assertIn('Meta tarda entre 30 minutos y varias horas', router)

    def test_lookalike_and_best_effort_persistence_are_preserved(self):
        router = self.router
        self.assertIn('ratio = req.ratio if 0.01 <= req.ratio <= 0.20 else 0.01', router)
        self.assertIn('pais = (req.pais or "MX").upper()[:2]', router)
        self.assertIn('"subtype": "LOOKALIKE"', router)
        self.assertIn('"type": "similarity"', router)
        self.assertIn('await post_rows(', router)
        self.assertIn('"fb_audiences"', router)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', router)
        self.assertIn('accepted_statuses=(200, 201, 204)', router)
        self.assertIn('warn_facebook_migration("guardar público", exc.response)', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_audiences.py", "exec")


if __name__ == "__main__":
    unittest.main()
