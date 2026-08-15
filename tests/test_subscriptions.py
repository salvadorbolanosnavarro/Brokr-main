"""Regression tests for paid-feature entitlement checks."""
import unittest
from unittest.mock import AsyncMock, patch

from core.subscriptions import has_paid_feature_access


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


if __name__ == "__main__":
    unittest.main()
