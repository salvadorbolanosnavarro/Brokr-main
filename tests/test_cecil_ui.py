import asyncio
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

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI();self.app.include_router(pilot.router)
        self.client=TestClient(self.app)

    def state(self,enabled=False,ids='',user='owner'):
        with patch.object(pilot,'settings',SimpleNamespace(cecil_ui_enabled=enabled,cecil_ui_user_ids=ids)),patch.object(pilot,'require_user_id',AsyncMock(return_value=user)):
            return self.client.get('/ui/cecil')

    def test_pilot_state_machine_preserves_session(self):
        subprocess.run(['node','tests/check_cecil_pilot_state.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)

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
