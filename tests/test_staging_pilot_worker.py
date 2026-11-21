"""Server pilot checks use injected providers; no production/network access."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class StagingPilotWorkerTests(unittest.TestCase):
    def test_authentication_revocation_and_error_receipt(self):
        self.assertIsNotNone(shutil.which('node'),'Node is required for worker contracts')
        subprocess.run(['node','tests/check_staging_pilot.cjs'],cwd=ROOT,check=True,capture_output=True)

    def test_staging_schema_has_no_client_flag_writes(self):
        sql=(ROOT/'docs/staging/pilot-schema-20261121.sql').read_text()
        self.assertIn('grant select on public.cecil_staging_pilot to authenticated',sql)
        self.assertNotIn('grant update',sql)
        self.assertIn('enable row level security',sql)
        self.assertIn("salvadorbolanosnavarro+cecila3@gmail.com",sql)

    def test_worker_origin_guard_precedes_auth_and_alt_html_is_gated(self):
        worker=(ROOT/'_worker.js').read_text()
        self.assertLess(worker.index("url.hostname.endsWith"),worker.index('await pilotRequest(request)'))
        self.assertIn("name.startsWith('cecil/')&&name.endsWith('.html')",worker)
        self.assertIn('private, no-store',worker)
        self.assertNotIn('urtgysmtnvoqaljuhntz',worker)

if __name__=='__main__':unittest.main()
