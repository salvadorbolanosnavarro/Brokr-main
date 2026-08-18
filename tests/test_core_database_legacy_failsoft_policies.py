"""Contracts for explicitly named legacy-compatible database policies."""
from __future__ import annotations

import inspect
import unittest

from core.database import get_service_json_or_empty, patch_rows_ignoring_http_status


class CoreDatabaseLegacyFailsoftPolicyTests(unittest.TestCase):
    def test_service_get_policy_only_swallows_http_and_json_decode(self):
        source = inspect.getsource(get_service_json_or_empty)
        self.assertIn('accepted_statuses=(200,)', source)
        self.assertIn('except httpx.HTTPStatusError:', source)
        self.assertIn('except json.JSONDecodeError:', source)
        self.assertNotIn('except Exception:', source)
        self.assertIn('return []', source)

    def test_patch_policy_ignores_http_status_but_not_transport(self):
        source = inspect.getsource(patch_rows_ignoring_http_status)
        self.assertIn('await patch_rows_no_response(', source)
        self.assertIn('prefer="return=minimal"', source)
        self.assertIn('except httpx.HTTPStatusError:', source)
        self.assertNotIn('except Exception:', source)
        self.assertIn('pass', source)


if __name__ == '__main__':
    unittest.main()
