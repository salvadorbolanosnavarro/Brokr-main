import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import build_staging as preview

ENV = {'CF_PAGES_BRANCH':preview.BRANCH, 'BROQUER_STAGING_API_URL':'https://brokr-main-staging.up.railway.app', 'BROQUER_STAGING_SUPABASE_URL':'https://tymhlvawnqadqgwnpruk.supabase.co', 'BROQUER_STAGING_SUPABASE_KEY':'sb_publishable_TEST_NOT_A_REAL_KEY'}

class StagingPreviewTests(unittest.TestCase):
    def test_rejects_wrong_branch_api_database_and_secret(self):
        for key,value in [('CF_PAGES_BRANCH','main'),('CF_PAGES_BRANCH',''),('BROQUER_STAGING_API_URL','https://api.broquer.app'),('BROQUER_STAGING_SUPABASE_URL',preview.PROD_DB),('BROQUER_STAGING_SUPABASE_KEY','sb_secret_fake'),('BROQUER_STAGING_SUPABASE_KEY',''),('BROQUER_STAGING_MODE','demo')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                preview.config({**ENV,key:value})

    def test_complete_release_has_no_production_or_demo_and_has_csp(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(preview,'ROOT',Path(tmp)), patch.dict(os.environ,ENV,clear=True):
            preview.build(ENV)
            output=Path(tmp)/'dist'
            self.assertGreaterEqual(len(list((output/'cecil').glob('*.html'))),52)
            for page in output.rglob('*.html'):
                html=page.read_text()
                self.assertIn('href="/staging-mobile-fields.css"',html,str(page))
                self.assertNotRegex(html,r'(?i)user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(?:\s*[,;"\'])')
            self.assertIn('max(16px, 1rem)',(output/'staging-mobile-fields.css').read_text())
            for shell_path in (output/'app-shell.js',output/'cecil/app-shell.js'):
                self.assertNotIn("['gesturestart', 'gesturechange', 'gestureend']",shell_path.read_text())
                self.assertNotIn('user-scalable=no',shell_path.read_text())
            for path in output.rglob('*'):
                if path.is_file() and path.suffix in {'.html','.js','.css','.json','.svg'}:
                    text=path.read_text()
                    for forbidden in ('api.broquer.app','urtgysmtnvoqaljuhntz.supabase.co',preview.PROD_KEY,'demo-runtime.js'):
                        self.assertNotIn(forbidden,text,str(path))
            for property_page in (output/'cecil/propiedades.html',):
                property_html=property_page.read_text()
                self.assertIn('const btn = e.submitter ||',property_html)
                self.assertNotIn("const btn = form.querySelector('.pf-save-btn');",property_html)
            self.assertIn('staging-pilot.js',(output/'app-shell.js').read_text())
            self.assertIn('staging-pilot.js',(output/'cecil/app-shell.js').read_text())
            self.assertNotIn('Sentry.onLoad',(output/'cecil/app-shell.js').read_text())
            shell=(output/'cecil/app-shell.js').read_text()
            self.assertIn(ENV['BROQUER_STAGING_API_URL'],shell)
            self.assertNotIn("rollout.src='/ui/cecil-rollout.js'",shell)
            headers=(output/'_headers').read_text()
            self.assertIn('connect-src',headers)
            self.assertIn(ENV['BROQUER_STAGING_API_URL'],headers)
            self.assertNotIn('api.broquer.app',headers)

if __name__=='__main__': unittest.main()
