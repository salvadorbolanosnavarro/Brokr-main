"""Regression tests tying together two related access-state bugs.

1. ``usuarios.activo`` is ``NULL`` for accounts that were never explicitly
   disabled. ``core.user_access.get_user_access_state`` must treat that the
   same way ``routers/admin_read.py`` already does — as active — and only
   fail closed when the Supabase lookup itself is uncertain.
2. A user without an organization yet (``org_id`` is ``None``) must still be
   found by ``user_id`` when looking up their subscription. Filtering by
   ``org_id`` alone built an ``eq.None`` PostgREST filter that Supabase
   rejected with 400, which every caller silently turned into "no
   subscription" even for a paying user.
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from core.subscriptions import find_latest_subscription, has_paid_feature_access
from core.user_access import get_user_access_state
from routers.subscription_status import subscription_status


def _fake_settings():
    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_service_key="service",
    )


class UserAccessStateNullActivoTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_activo_is_treated_as_active(self):
        with (
            patch("core.user_access.settings", _fake_settings()),
            patch(
                "core.user_access.get_rows",
                new=AsyncMock(return_value=[{"rol": "agente", "activo": None}]),
            ),
        ):
            state = await get_user_access_state("user-1")
        self.assertEqual(state, {"rol": "agente", "activo": True})

    async def test_explicit_false_still_disables_the_account(self):
        with (
            patch("core.user_access.settings", _fake_settings()),
            patch(
                "core.user_access.get_rows",
                new=AsyncMock(return_value=[{"rol": "agente", "activo": False}]),
            ),
        ):
            state = await get_user_access_state("user-1")
        self.assertFalse(state["activo"])

    async def test_failed_lookup_still_fails_closed(self):
        with (
            patch("core.user_access.settings", _fake_settings()),
            patch(
                "core.user_access.get_rows",
                new=AsyncMock(side_effect=RuntimeError("supabase unavailable")),
            ),
        ):
            state = await get_user_access_state("user-1")
        self.assertFalse(state["activo"])


class FindLatestSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_org_id_searches_by_user_id_only(self):
        rows = AsyncMock(return_value=[{"status": "active", "user_id": "user-1"}])
        with patch("core.subscriptions.get_rows", new=rows):
            row = await find_latest_subscription("user-1", None)

        self.assertEqual(row["status"], "active")
        called_table, called_params = rows.await_args.args
        self.assertEqual(called_table, "suscripciones")
        self.assertEqual(called_params["user_id"], "eq.user-1")
        self.assertNotIn("org_id", called_params)
        self.assertNotIn("or", called_params)

    async def test_existing_org_id_searches_org_id_or_user_id(self):
        rows = AsyncMock(return_value=[{"status": "active"}])
        with patch("core.subscriptions.get_rows", new=rows):
            await find_latest_subscription("user-1", "org-9")

        _, called_params = rows.await_args.args
        self.assertEqual(called_params["or"], "(org_id.eq.org-9,user_id.eq.user-1)")
        self.assertNotIn("org_id", called_params)
        self.assertNotIn("user_id", called_params)


class PaidFeatureAccessWithoutOrgIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_subscription_without_org_id_grants_access(self):
        async def fake_get_rows(table, params, **kwargs):
            if table == "usuarios":
                return [{"rol": "agente", "activo": True}]
            if table == "suscripciones":
                self.assertEqual(params.get("user_id"), "eq.user-1")
                self.assertNotIn("org_id", params)
                return [{"status": "active"}]
            raise AssertionError(f"unexpected table {table}")

        with (
            patch("core.subscriptions.get_rows", new=AsyncMock(side_effect=fake_get_rows)),
            patch(
                "core.subscriptions.get_org_context",
                new=AsyncMock(return_value={"org_id": None, "org_tipo": "personal"}),
            ),
            patch("core.subscriptions.get_org_id_for_user", new=AsyncMock(return_value=None)),
        ):
            self.assertTrue(await has_paid_feature_access("user-1"))


class SubscriptionStatusEndpointTests(unittest.IsolatedAsyncioTestCase):
    """Covers both required scenarios end-to-end through /subscription/status."""

    async def test_null_activo_user_with_active_subscription_is_active(self):
        request = object()
        with (
            patch(
                "routers.subscription_status.get_user_id_from_token",
                new=AsyncMock(return_value="user-1"),
            ),
            patch("core.user_access.settings", _fake_settings()),
            patch(
                "core.user_access.get_rows",
                new=AsyncMock(return_value=[{"rol": "agente", "activo": None}]),
            ),
            patch(
                "routers.subscription_status.get_org_context",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "routers.subscription_status.get_org_id_for_user",
                new=AsyncMock(return_value="org-1"),
            ),
            patch(
                "core.subscriptions.get_rows",
                new=AsyncMock(return_value=[{"status": "active", "plan_nombre": "Broquer Max", "plan_id": "max"}]),
            ),
        ):
            result = await subscription_status(request)

        self.assertTrue(result["active"])
        self.assertEqual(result["status"], "active")

    async def test_user_without_org_id_with_active_subscription_is_active(self):
        request = object()

        async def fake_get_rows(table, params, **kwargs):
            self.assertEqual(table, "suscripciones")
            self.assertEqual(params.get("user_id"), "eq.user-1")
            self.assertNotIn("org_id", params)
            self.assertNotIn("or", params)
            return [{"status": "active", "plan_nombre": "Broquer Max", "plan_id": "max"}]

        with (
            patch(
                "routers.subscription_status.get_user_id_from_token",
                new=AsyncMock(return_value="user-1"),
            ),
            patch(
                "routers.subscription_status.get_user_access_state",
                new=AsyncMock(return_value={"rol": "agente", "activo": True}),
            ),
            patch(
                "routers.subscription_status.get_org_context",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "routers.subscription_status.get_org_id_for_user",
                new=AsyncMock(return_value=None),
            ),
            patch("core.subscriptions.get_rows", new=AsyncMock(side_effect=fake_get_rows)),
        ):
            result = await subscription_status(request)

        self.assertTrue(result["active"])
        self.assertEqual(result["status"], "active")


if __name__ == "__main__":
    unittest.main()
