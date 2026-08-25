"""Permanent guards for static extraction of POST /facebook/reconcile."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_reconcile.py"


class FacebookReconcileExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_moves_out_of_main(self):
        self.assertNotIn('@app.post("/facebook/reconcile")', self.main)
        self.assertNotIn("async def facebook_reconcile(", self.main)
        self.assertIn("from routers.facebook_reconcile import router as facebook_reconcile_router", self.main)
        self.assertIn("app.include_router(facebook_reconcile_router)", self.main)
        self.assertIn('@router.post("/facebook/reconcile")', self.router)

    def test_auth_storage_and_migration_errors_are_preserved(self):
        router = self.router
        self.assertIn("user_id = await exigir_gestion_integraciones(request)", router)
        self.assertIn('limpiar = bool(body.get("limpiar"))', router)
        self.assertIn('raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")', router)
        self.assertIn('raise HTTPException(status_code=500, detail="Supabase no configurado")', router)
        self.assertIn('"order": "created_at.desc"', router)
        self.assertIn('"limit": "200"', router)
        self.assertIn("timeout=15", router)
        self.assertIn('warn_facebook_migration("reconciliar", exc.response)', router)
        self.assertIn("Falta correr migracion-facebook-ads.sql en Supabase", router)
        self.assertIn("No se pudo leer el registro de campañas.", router)

    def test_cleanup_remains_guarded_and_never_deletes_delivering_campaigns(self):
        router = self.router
        self.assertIn('entrega = eff in ("ACTIVE", "PENDING_REVIEW", "IN_PROCESS")', router)
        self.assertIn("if entrega:", router)
        self.assertIn("elif limpiar:", router)
        self.assertIn('"DELETE",', router)
        self.assertIn('reintentos=2', router)
        self.assertIn('"Revísala a mano antes de borrar."', router)
        self.assertIn('"borrada": True', router)
        self.assertIn('"borrada": False', router)
        self.assertIn('"No se pudo borrar"', router)
        self.assertIn("'Manda {\"limpiar\": true} para borrarla.'", router)

    def test_bookkeeping_and_response_shape_are_preserved(self):
        router = self.router
        self.assertIn('"status": "FALLIDO"', router)
        self.assertIn('"Creación interrumpida antes de crear la campaña."', router)
        self.assertIn('"status": "ELIMINADO"', router)
        self.assertIn('datetime.now(timezone.utc).isoformat()', router)
        for key in (
            '"ok": True',
            '"revisadas": len(filas)',
            '"sanas": len(sanas)',
            '"huerfanas": huerfanas',
            '"requieren_revision_manual": revisar',
            '"corregidas": corregidas',
            '"limpieza_aplicada": limpiar',
        ):
            self.assertIn(key, router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_reconcile.py", "exec")


if __name__ == "__main__":
    unittest.main()
