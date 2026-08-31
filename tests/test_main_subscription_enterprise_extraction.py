from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_enterprise.py"
WEBHOOK = ROOT / "routers" / "stripe_webhook.py"
CORE = ROOT / "core" / "stripe.py"


class SubscriptionEnterpriseExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.webhook = WEBHOOK.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_enterprise_routes_live_only_in_router(self):
        for route in (
            '@router.get("/subscription/empresa/plan")',
            '@router.post("/subscription/empresa/checkout")',
            '@router.post("/subscription/empresa/asientos")',
        ):
            self.assertIn(route, self.router)
        for route in (
            '@app.get("/subscription/empresa/plan")',
            '@app.post("/subscription/empresa/checkout")',
            '@app.post("/subscription/empresa/asientos")',
        ):
            self.assertNotIn(route, self.main)
        self.assertIn('app.include_router(subscription_enterprise_router)', self.main)

    def test_enterprise_legacy_permission_contract_is_preserved(self):
        r = self.router
        self.assertIn('from routers.organizaciones import get_org_context', r)
        self.assertIn('raise HTTPException(status_code=401, detail="Inicia sesión.")', r)
        self.assertIn('raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")', r)
        self.assertIn('ctx.get("rol_org") not in ("owner", "admin")', r)
        self.assertIn('Solo el dueño de la cuenta puede contratar o cambiar el plan de la empresa.', r)

    def test_checkout_and_seat_contracts_are_preserved(self):
        r = self.router
        self.assertIn('if n < EMPRESA_ASIENTOS_BASE:', r)
        self.assertIn('if n > EMPRESA_ASIENTOS_MAX:', r)
        self.assertIn('f"{SUPABASE_URL}/auth/v1/user"', r)
        self.assertIn('await get_or_create_stripe_customer(user_id, email, nombre)', r)
        self.assertIn('"metadata[plan_id]": "empresas"', r)
        self.assertIn('"proration_behavior": "create_prorations"', r)
        self.assertIn('await patch_rows_ignoring_http_status(', r)
        self.assertIn('"asientos_max": asientos', r)

    def test_webhook_uses_shared_enterprise_activation(self):
        self.assertNotIn('async def _activar_empresa(', self.main)
        self.assertNotIn('activate_enterprise_subscription as _activar_empresa', self.main)
        self.assertNotIn('@app.post("/subscription/webhook")', self.main)
        self.assertIn('app.include_router(stripe_webhook_router)', self.main)
        self.assertIn('activate_enterprise_subscription,', self.webhook)
        self.assertIn('await activate_enterprise_subscription(', self.webhook)
        c = self.core
        self.assertIn('async def activate_enterprise_subscription(', c)
        self.assertIn('"tipo": "empresa"', c)
        self.assertIn('"rol_org": "owner"', c)
        self.assertGreaterEqual(c.count('await patch_rows_ignoring_http_status('), 2)

    def test_local_enterprise_helpers_are_removed(self):
        for helper in (
            'async def _exigir_admin_de_org(',
            'def _valida_asientos(',
            'async def _ocupacion_org(',
            'async def _activar_empresa(',
        ):
            self.assertNotIn(helper, self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/subscription_enterprise.py", "exec")
        compile(self.webhook, "routers/stripe_webhook.py", "exec")
        compile(self.core, "core/stripe.py", "exec")


if __name__ == "__main__":
    unittest.main()
