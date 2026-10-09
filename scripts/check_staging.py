"""Offline checks for the isolated staging gateway; never contacts production."""
import base64
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serve_staging as staging


class ConfigurationChecks(unittest.TestCase):
    def test_missing_config_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(staging.settings(), ('', '', ''))

    def test_production_api_and_database_are_rejected(self):
        for name, value in [('BROQUER_STAGING_API_URL', staging.PRODUCTION_API),
                            ('BROQUER_STAGING_SUPABASE_URL', staging.PRODUCTION_DB)]:
            with self.subTest(name=name), patch.dict(os.environ, {name: value}, clear=True):
                with self.assertRaises(ValueError):
                    staging.settings()

    def test_privileged_keys_are_rejected(self):
        claims = base64.urlsafe_b64encode(json.dumps({'role': 'service_role'}).encode()).decode().rstrip('=')
        for key in ['sb_secret_not_public', 'header.' + claims + '.signature', staging.PRODUCTION_KEY]:
            with self.subTest(key_type=key.split('_')[0]), patch.dict(os.environ, {'BROQUER_STAGING_SUPABASE_KEY': key}, clear=True):
                with self.assertRaises(ValueError):
                    staging.settings()

    def test_remote_services_require_https_and_no_embedded_credentials(self):
        for value in ['http://staging.example.test', 'https://user:pass@staging.example.test', 'https://staging.example.test?token=secret']:
            with patch.dict(os.environ, {'BROQUER_STAGING_API_URL': value}, clear=True):
                with self.assertRaises(ValueError):
                    staging.settings()


class GatewayChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = staging.ThreadingHTTPServer(('127.0.0.1', 0), staging.Handler)
        cls.server.staging_settings = ('', '', '')
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.server.public_origin = cls.base
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_frontend_sources_are_rewritten_and_connections_restricted(self):
        with urlopen(self.base + '/app-shell.js') as response:
            source = response.read().decode()
            self.assertNotIn(staging.PRODUCTION_API, source)
            self.assertNotIn(staging.PRODUCTION_DB, source)
            self.assertNotIn(staging.PRODUCTION_KEY, source)
            self.assertIn(self.base + '/__stage/supabase', source)
            self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
            self.assertIn("worker-src 'none'", response.headers['Content-Security-Policy'])

    def test_unconfigured_requests_do_not_reach_any_upstream(self):
        with patch.object(staging, 'build_opener', side_effect=AssertionError('Unexpected upstream request')):
            for route in ['/__stage/api/config/public', '/__stage/supabase/rest/v1/contactos']:
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.base + route)
                self.assertEqual(error.exception.code, 503)

    def test_server_sources_secrets_and_git_are_not_public(self):
        for route in ['/.git/config', '/.env', '/core/config.py', '/scripts/serve_staging.py', '/sw.js', '/%2e%2e/%2e%2e/etc/passwd']:
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                urlopen(self.base + route)
            self.assertEqual(error.exception.code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
