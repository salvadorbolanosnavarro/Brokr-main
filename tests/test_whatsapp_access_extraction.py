from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from routers.whatsapp_access import _ids_visibles
from scripts.refactor_whatsapp_extract_access_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"


class WhatsAppAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_or_agent_account_sees_only_itself(self):
        with patch("routers.whatsapp_access.get_org_context", new=AsyncMock(return_value=None)):
            self.assertEqual(await _ids_visibles("u1"), ["u1"])
        with patch(
            "routers.whatsapp_access.get_org_context",
            new=AsyncMock(return_value={"org_id": "o1", "rol_org": "agent"}),
        ):
            self.assertEqual(await _ids_visibles("u1"), ["u1"])

    async def test_owner_and_admin_see_team_plus_themselves(self):
        for role in ("owner", "admin"):
            with self.subTest(role=role), (
                patch(
                    "routers.whatsapp_access.get_org_context",
                    new=AsyncMock(return_value={"org_id": "o1", "rol_org": role}),
                ),
                patch(
                    "routers.whatsapp_access.sb_get",
                    new=AsyncMock(return_value=[{"user_id": "u2"}, {"user_id": "u3"}, {"user_id": None}]),
                ) as get_rows,
            ):
                ids = await _ids_visibles("u1")
                self.assertEqual(set(ids), {"u1", "u2", "u3"})
                get_rows.assert_awaited_once_with(
                    "organizacion_miembros",
                    {"org_id": "eq.o1", "select": "user_id"},
                )


class WhatsAppAccessExtractionTests(unittest.TestCase):
    def test_transform_moves_only_access_helpers(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_access import _ids_visibles, _require_user", transformed)
        self.assertNotIn("async def _require_user", transformed)
        self.assertNotIn("async def _ids_visibles", transformed)
        self.assertIn('@router.post("/connect")', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
