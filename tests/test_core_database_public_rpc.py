"""Contract guards for public/service Supabase RPC access in core.database."""
from __future__ import annotations

import inspect
import unittest

from core.database import call_public_rpc, call_service_rpc, rpc_url


class CoreDatabaseRpcTests(unittest.TestCase):
    def test_public_rpc_uses_public_credentials_and_exact_status_gate(self):
        source = inspect.getsource(call_public_rpc)
        self.assertIn('rpc_url(function)', source)
        self.assertIn('headers=public_headers()', source)
        self.assertIn('json=dict(payload)', source)
        self.assertIn('_require_response_status(response, accepted_statuses)', source)
        self.assertIn('return response.json()', source)

    def test_service_rpc_uses_service_credentials_and_raw_json(self):
        source = inspect.getsource(call_service_rpc)
        self.assertIn('rpc_url(function)', source)
        self.assertIn('headers=service_headers()', source)
        self.assertIn('json=dict(payload)', source)
        self.assertIn('_require_response_status(response, accepted_statuses)', source)
        self.assertIn('return response.json()', source)
        self.assertNotIn('isinstance', source)

    def test_rpc_helpers_expose_timeout_and_exact_status_contract(self):
        for helper in (call_public_rpc, call_service_rpc):
            signature = inspect.signature(helper)
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
