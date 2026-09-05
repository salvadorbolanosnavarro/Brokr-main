from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_checkout.py"
CORE = ROOT / "core" / "stripe.py"


class SubscriptionCheckoutExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/subscription/checkout")', self.router)
        self.assertNotIn('@app.post("/subscription/checkout")', self.main)
        self.assertIn('app.include_router(subscription_checkout_router)', self.main)
        self.assertNotIn('async def _get_or_create_stripe_customer', self.main)
        self.assertIn('get_or_create_stripe_customer as _get_or_create_stripe_customer', self.main)

    def test_checkout_contract_is_preserved(self):
        r = self.router
        self.assertIn('plan_map = {"max": STRIPE_PRICE_PRO, "ampi": STRIPE_PRICE_AMPI}', r)
        self.assertIn('Código promocional inválido para el plan AMPI.', r)
        self.assertIn('f"{SUPABASE_URL}/auth/v1/user"', r)
        self.assertIn('headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth_tok}"}', r)
        self.assertNotIn('trial', r.lower())
        self.assertIn('await get_or_create_stripe_customer(user_id, email, nombre)', r)
        self.assertIn('https://api.stripe.com/v1/checkout/sessions', r)
        self.assertIn('if r_cs.status_code not in (200, 201):', r)
        self.assertIn('Stripe checkout session:', r)

    def test_customer_creation_is_shared_and_preserves_fail_soft_local_patch(self):
        c = self.core
        self.assertIn('async def get_or_create_stripe_customer(', c)
        self.assertIn('https://api.stripe.com/v1/customers', c)
        self.assertIn('{"stripe_customer_id": customer_id}', c)
        self.assertIn('prefer="return=minimal"', c)
        self.assertIn('except httpx.HTTPStatusError:', c)
        self.assertIn('pass', c)
        self.assertNotIn('/rest/v1/', c)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/subscription_checkout.py", "exec")
        compile(self.core, "core/stripe.py", "exec")


if __name__ == "__main__":
    unittest.main()
