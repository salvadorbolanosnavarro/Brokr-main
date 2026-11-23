import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import cecil_ui as pilot
from scripts.build_cecil_canary import build
from scripts.build_pages_pilot import package

# The production builder refuses to run when the checkout differs from its pinned
# base (protection against shipping an outdated design). The staging sync tests
# a main+staging merge, which always differs; it sets this variable and runs
# these two tests separately on the untouched main tree. Quality never sets it.
COMBINED_STAGING_TREE = os.environ.get('CECIL_BUILD_TREE') == 'staging-combined'
SKIP_COMBINED = unittest.skipIf(COMBINED_STAGING_TREE, 'production build guard runs on the main tree, not main+staging')

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI();self.app.include_router(pilot.router)
        self.client=TestClient(self.app)

    def state(self,enabled=False,ids='',user='owner'):
        with patch.object(pilot,'settings',SimpleNamespace(cecil_ui_enabled=enabled,cecil_ui_user_ids=ids)),patch.object(pilot,'require_user_id',AsyncMock(return_value=user)):
            return self.client.get('/ui/cecil')

    def test_pilot_state_machine_preserves_session(self):
        subprocess.run(['node','tests/check_cecil_pilot_state.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)

    def test_error_probe_requires_transport_acceptance_and_strips_private_data(self):
        subprocess.run(['node','tests/check_cecil_error_probe.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)

    def test_default_off_and_empty_list_fail_closed(self):
        self.assertFalse(self.state().json()['enabled'])
        self.assertFalse(self.state(True).json()['enabled'])
        self.assertFalse(self.state(False,'owner').json()['enabled'])

    def test_exact_verified_id_only_and_no_cache(self):
        r=self.state(True,' owner , other ')
        self.assertTrue(r.json()['enabled']);self.assertIn('no-store',r.headers['cache-control'])
        self.assertEqual(r.headers['vary'],'Authorization')
        self.assertFalse(self.state(True,'owner-extra').json()['enabled'])
        self.assertFalse(self.state(True,'owner',user='another-account').json()['enabled'])

    def test_no_session_rejected(self):
        r=self.client.get('/ui/cecil');self.assertEqual(r.status_code,401)

    @SKIP_COMBINED
    def test_pages_artifact_keeps_original_and_excludes_backend(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'pages';package(output)
            for page in root.glob('*.html'):
                if not page.name.startswith('_'):
                    self.assertEqual((output/page.name).read_bytes(),page.read_bytes())
            self.assertTrue((output/'cecil/index.html').exists())
            self.assertTrue((output/'ui/cecil-rollout.js').exists())
            self.assertTrue((output/'intro.mp4').exists())
            self.assertFalse((output/'main.py').exists())
            self.assertFalse((output/'core').exists())
            self.assertFalse((output/'tests').exists())
            self.assertFalse(list(output.rglob('*.sql')))
            self.assertFalse((output/'production-pilot-private').exists())

    @SKIP_COMBINED
    def test_build_preserves_real_endpoints_and_excludes_demo(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'cecil';build(output)
            self.assertFalse((output/'demo-runtime.js').exists())
            self.assertFalse(list(output.rglob('*.py')))
            self.assertFalse(list(output.rglob('*.sql')))
            shell=(output/'app-shell.js').read_text()
            self.assertIn("rollout.src='/ui/cecil-rollout.js'",shell)
            self.assertIn('https://api.broquer.app',shell)
            self.assertNotIn('broquer-demo.invalid',shell)
            self.assertNotIn('user-scalable=no', shell)
            self.assertNotIn('Guarda de escala en iOS', shell)
            css = (output/'mobile-fields.css').read_text()
            self.assertIn('font-size: max(16px, 1rem) !important', css)
            self.assertIn('touch-action: pan-y pinch-zoom !important', css)
            for page in output.glob('*.html'):
                self.assertNotIn('src="demo-runtime.js"',page.read_text())
                self.assertIn('href="/cecil/mobile-fields.css"', page.read_text())
                self.assertNotIn('user-scalable=no', page.read_text())
            self.assertIn('Cecil', (output/'index.html').read_text())
            with self.assertRaises(ValueError):build(output)
