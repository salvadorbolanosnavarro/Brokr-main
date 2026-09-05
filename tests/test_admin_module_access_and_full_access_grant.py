"""Tests for per-user module control and admin-granted full access.

Covers three pieces added together:
  1. ``core.subscriptions.full_access_grant_active`` — the expiry check for
     an admin-granted full-access window, independent from role/subscription.
  2. The new ``/admin/user/modulos`` and ``/admin/user/acceso-completo``
     endpoints in ``routers.admin_accounts``.
  3. ``full_access_grant_active`` folded into ``has_paid_feature_access`` and
     into ``/subscription/status``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from core.module_access import TOGGLEABLE_MODULES, normalize_disabled_modules
from core.subscriptions import full_access_grant_active, has_paid_feature_access
from routers.admin_accounts import (
    AdminAccesoCompletoReq,
    AdminModulosReq,
    admin_set_acceso_completo,
    admin_set_modulos,
)
from routers.subscription_status import subscription_status


FUTURE = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()


class FullAccessGrantActiveTests(unittest.TestCase):
    def test_future_date_is_active(self):
        self.assertTrue(full_access_grant_active(FUTURE))

    def test_past_date_is_not_active(self):
        self.assertFalse(full_access_grant_active(PAST))

    def test_missing_value_is_not_active(self):
        self.assertFalse(full_access_grant_active(None))
        self.assertFalse(full_access_grant_active(""))

    def test_malformed_value_fails_closed(self):
        self.assertFalse(full_access_grant_active("not-a-date"))


class NormalizeDisabledModulesTests(unittest.TestCase):
    def test_dedupes_and_sorts(self):
        self.assertEqual(
            normalize_disabled_modules(["isr", " avm ", "isr", ""]),
            ["avm", "isr"],
        )

    def test_empty_input_is_empty_list(self):
        self.assertEqual(normalize_disabled_modules(None), [])
        self.assertEqual(normalize_disabled_modules([]), [])


class HasPaidFeatureAccessWithFullAccessGrantTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_grant_overrides_missing_subscription(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(
                return_value=[{"rol": "agente", "activo": True, "acceso_completo_hasta": FUTURE}]
            ),
        ):
            self.assertTrue(await has_paid_feature_access("user-1"))

    async def test_expired_grant_falls_back_to_normal_checks(self):
        async def fake_get_rows(table, params, **kwargs):
            if table == "usuarios":
                return [{"rol": "agente", "activo": True, "acceso_completo_hasta": PAST}]
            if table == "suscripciones":
                return []
            raise AssertionError(f"unexpected table {table}")

        with (
            patch("core.subscriptions.get_rows", new=AsyncMock(side_effect=fake_get_rows)),
            patch("core.subscriptions.get_org_context", new=AsyncMock(return_value=None)),
        ):
            self.assertFalse(await has_paid_feature_access("user-1"))

    async def test_disabled_account_is_denied_even_with_active_grant(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(
                return_value=[{"rol": "agente", "activo": False, "acceso_completo_hasta": FUTURE}]
            ),
        ):
            self.assertFalse(await has_paid_feature_access("user-1"))


class SubscriptionStatusWithFullAccessGrantTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_grant_reports_active_before_role_or_org_checks(self):
        request = object()
        with (
            patch(
                "routers.subscription_status.get_user_id_from_token",
                new=AsyncMock(return_value="user-1"),
            ),
            patch(
                "routers.subscription_status.get_user_access_state",
                new=AsyncMock(
                    return_value={"rol": "agente", "activo": True, "acceso_completo_hasta": FUTURE}
                ),
            ),
        ):
            result = await subscription_status(request)
        self.assertTrue(result["active"])
        self.assertEqual(result["plan_id"], "acceso-completo")

    async def test_expired_grant_does_not_report_active(self):
        request = object()
        with (
            patch(
                "routers.subscription_status.get_user_id_from_token",
                new=AsyncMock(return_value="user-1"),
            ),
            patch(
                "routers.subscription_status.get_user_access_state",
                new=AsyncMock(
                    return_value={"rol": "agente", "activo": True, "acceso_completo_hasta": PAST}
                ),
            ),
            patch(
                "routers.subscription_status.get_org_context",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "routers.subscription_status.get_org_id_for_user",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "core.subscriptions.get_rows",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await subscription_status(request)
        self.assertFalse(result["active"])


class AdminSetModulosTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_unknown_module_key(self):
        req = AdminModulosReq(user_id="user-1", modulos_desactivados=["avm", "no-existe"])
        with patch(
            "routers.admin_accounts.require_legacy_admin",
            new=AsyncMock(return_value="admin-1"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await admin_set_modulos(req, request=object())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("no-existe", ctx.exception.detail)

    async def test_saves_normalized_module_list(self):
        req = AdminModulosReq(user_id="user-1", modulos_desactivados=["isr", "avm", "isr"])
        patch_mock = AsyncMock()
        with (
            patch(
                "routers.admin_accounts.require_legacy_admin",
                new=AsyncMock(return_value="admin-1"),
            ),
            patch("routers.admin_accounts.patch_rows_no_response", new=patch_mock),
        ):
            result = await admin_set_modulos(req, request=object())
        self.assertEqual(result["modulos_desactivados"], ["avm", "isr"])
        called_table, called_filters, called_body = patch_mock.await_args.args
        self.assertEqual(called_table, "usuarios")
        self.assertEqual(called_filters, {"id": "eq.user-1"})
        self.assertEqual(called_body, {"modulos_desactivados": ["avm", "isr"]})

    async def test_requires_user_id(self):
        req = AdminModulosReq(user_id="  ", modulos_desactivados=[])
        with patch(
            "routers.admin_accounts.require_legacy_admin",
            new=AsyncMock(return_value="admin-1"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await admin_set_modulos(req, request=object())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_toggleable_modules_never_includes_admin(self):
        self.assertNotIn("admin", TOGGLEABLE_MODULES)


class AdminSetAccesoCompletoTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_past_date(self):
        req = AdminAccesoCompletoReq(user_id="user-1", hasta=PAST)
        with patch(
            "routers.admin_accounts.require_legacy_admin",
            new=AsyncMock(return_value="admin-1"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await admin_set_acceso_completo(req, request=object())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_rejects_malformed_date(self):
        req = AdminAccesoCompletoReq(user_id="user-1", hasta="no-es-una-fecha")
        with patch(
            "routers.admin_accounts.require_legacy_admin",
            new=AsyncMock(return_value="admin-1"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await admin_set_acceso_completo(req, request=object())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_grants_future_date(self):
        req = AdminAccesoCompletoReq(user_id="user-1", hasta=FUTURE)
        patch_mock = AsyncMock()
        with (
            patch(
                "routers.admin_accounts.require_legacy_admin",
                new=AsyncMock(return_value="admin-1"),
            ),
            patch("routers.admin_accounts.patch_rows_no_response", new=patch_mock),
        ):
            result = await admin_set_acceso_completo(req, request=object())
        self.assertTrue(result["ok"])
        self.assertTrue(full_access_grant_active(result["acceso_completo_hasta"]))

    async def test_revokes_with_null_hasta(self):
        req = AdminAccesoCompletoReq(user_id="user-1", hasta=None)
        patch_mock = AsyncMock()
        with (
            patch(
                "routers.admin_accounts.require_legacy_admin",
                new=AsyncMock(return_value="admin-1"),
            ),
            patch("routers.admin_accounts.patch_rows_no_response", new=patch_mock),
        ):
            result = await admin_set_acceso_completo(req, request=object())
        self.assertIsNone(result["acceso_completo_hasta"])
        called_table, called_filters, called_body = patch_mock.await_args.args
        self.assertEqual(called_table, "usuarios")
        self.assertEqual(called_filters, {"id": "eq.user-1"})
        self.assertEqual(called_body, {"acceso_completo_hasta": None})


if __name__ == "__main__":
    unittest.main()
