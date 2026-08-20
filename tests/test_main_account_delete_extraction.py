"""Static preservation guards for self-service account deletion extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "account_delete.py"
SCRIPT = ROOT / "scripts" / "refactor_main_extract_account_delete_core.py"


class AccountDeleteExtractionPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_irreversible_sequence_contract_is_preserved(self):
        r = self.router
        self.assertIn('@router.delete("/usuario/eliminar-cuenta")', r)
        self.assertIn('user_id = await get_user_id_from_token(request)', r)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado.")', r)
        self.assertIn('raise HTTPException(status_code=500, detail="Supabase no está configurado.")', r)
        self.assertIn('"suscripciones"', r)
        self.assertIn('"select": "stripe_subscription_id"', r)
        self.assertIn('accepted_statuses=(200,)', r)
        self.assertIn('f"https://api.stripe.com/v1/subscriptions/{sub_id}"', r)
        self.assertIn('marcador = "/fotos-propiedades/"', r)
        self.assertIn('f"{SUPABASE_URL}/storage/v1/object/fotos-propiedades/{nombre}"', r)
        self.assertIn('tablas = ["propiedades", "contactos", "contratos", "user_integrations",', r)
        self.assertIn('accepted_statuses=(200, 204)', r)
        self.assertIn('f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"', r)
        self.assertIn('return {"ok": True, "user_id": user_id, "borrados": borrados, "errores": errores}', r)

    def test_fail_soft_ledger_contract_is_preserved(self):
        r = self.router
        self.assertIn('borrados["stripe"] = "sin_suscripcion"', r)
        self.assertIn('errores.append(f"stripe: {e}")', r)
        self.assertIn('except Exception:\n                    pass', r)
        self.assertIn('errores.append(f"{tabla}: {e}")', r)
        self.assertIn('except httpx.HTTPStatusError:\n            borrados["usuarios"] = False', r)

    def test_transform_only_removes_endpoint_and_mounts_router(self):
        s = self.script
        self.assertIn("_remove_function(transformed, 'eliminar_cuenta_y_datos')", s)
        self.assertIn('from routers.account_delete import router as account_delete_router', s)
        self.assertIn("compile(transformed, str(MAIN), 'exec')", s)

    def test_prepared_files_compile(self):
        compile(self.router, "routers/account_delete.py", "exec")
        compile(self.script, "scripts/refactor_main_extract_account_delete_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
