import asyncio
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

    def test_production_builder_refuses_staging_preview_branch(self):
        # This branch intentionally adds staging-only code/assets beyond the
        # original #217 pilot. The production constructor must fail closed.
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'cecil'
            with self.assertRaises(ValueError): build(output)
            self.assertFalse(output.exists())
