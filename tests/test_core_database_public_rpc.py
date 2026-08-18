"""Contract guards for public Supabase RPC access in core.database."""
from __future__ import annotations

import inspect
import unittest

from core.database import call_public_rpc, rpc_url


class CoreDatabasePublicRpcTests(unittest.TestCase):
    def test_public_rpc_uses_public_credentials_and_exact_status_gate(self):
        source = inspect.getsource(call_public_rpc)
        self.assertIn('rpc_url(function)', source)
        self.assertIn('headers=public_headers()', source)
        self.assertIn('json=dict(payload)', source)
        self.assertIn('_require_response_status(response, accepted_statuses)', source)
        self.assertIn('return response.json()', source)

    def test_public_rpc_exposes_timeout_and_exact_status_contract(self):
        signature = inspect.signature(call_public_rpc)
        self.assertIn('timeout', signature.parameters)
        self.assertIn('accepted_statuses', signature.parameters)
        self.assertIsNone(signature.parameters['accepted_statuses'].default)

    def test_rpc_url_is_namespaced_and_rejects_nested_paths(self):
        source = inspect.getsource(rpc_url)
        self.assertIn('/rest/v1/rpc/{normalized}', source)
        self.assertIn('if not normalized or "/" in normalized:', source)
        self.assertIn('require_supabase_public()', source)


if __name__ == '__main__':
    unittest.main()
