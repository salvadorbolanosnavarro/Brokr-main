"""Regression tests for paid-feature entitlement checks."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from core.subscriptions import has_paid_feature_access, require_paid_feature_access


class SubscriptionAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_admin_has_access(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(return_value=[{"rol": "admin", "activo": True}]),
        ):
            self.assertTrue(await has_paid_feature_access("user-1"))

    async def test_disabled_account_is_denied(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(return_value=[{"rol": "agente", "activo": False}]),
        ):
            self.assertFalse(await has_paid_feature_access("user-1"))

    async def test_verification_error_fails_closed(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            self.assertFalse(await has_paid_feature_access("user-1"))

    async def test_missing_user_is_denied(self):
        with patch(
            "core.subscriptions.get_rows",
            new=AsyncMock(return_value=[]),
        ):
            self.assertFalse(await has_paid_feature_access("user-1"))

    async def test_request_guard_returns_trusted_user_for_paid_access(self):
        request = object()
        with (
            patch(
                "core.subscriptions.require_user_id",
                new=AsyncMock(return_value="user-1"),
            ),
            patch(
                "core.subscriptions.has_paid_feature_access",
                new=AsyncMock(return_value=True),
            ),
        ):
            self.assertEqual(await require_paid_feature_access(request), "user-1")

    async def test_request_guard_returns_402_without_paid_access(self):
        request = object()
        with (
            patch(
                "core.subscriptions.require_user_id",
                new=AsyncMock(return_value="user-1"),
            ),
            patch(
                "core.subscriptions.has_paid_feature_access",
                new=AsyncMock(return_value=False),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await require_paid_feature_access(
                    request,
                    detail="La firma electrónica es parte de Broquer Max.",
                )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(
            ctx.exception.detail,
            "La firma electrónica es parte de Broquer Max.",
        )


if __name__ == "__main__":
    unittest.main()
