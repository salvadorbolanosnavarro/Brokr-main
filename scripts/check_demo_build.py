"""Demo is explicit, isolated and injects its transport before application auth."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('build_demo',Path(__file__).with_name('build_staging.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
class DemoBuildTests(unittest.TestCase):
    def test_no_credentials_or_real_api_required(self):
        api,db,key=build.config({'BROQUER_STAGING_MODE':'demo'})
        self.assertEqual(api,'https://broquer-demo.invalid/api')
        self.assertTrue(db.startswith('https://broquer-demo.invalid/'))
        self.assertEqual(key,'DEMO_PUBLIC_NOT_A_KEY')
    def test_demo_cannot_build_main(self):
        with self.assertRaises(ValueError):build.config({'BROQUER_STAGING_MODE':'demo','CF_PAGES_BRANCH':'main'})
    def test_bootstrap_precedes_auth_and_csp_blocks_external_connections(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(build,'ROOT',Path(directory)):
            p=Path(directory)
            (p/'index.html').write_text('<head></head><script src="app-shell.js"></script>'+build.PROD_DB+' '+build.PROD_KEY)
            with patch.object(build.subprocess,'check_output',return_value='index.html\ndocs/private.json\n'):
                build.build({'BROQUER_STAGING_MODE':'demo'})
            html=(p/'dist/index.html').read_text()
            self.assertLess(html.index('demo-runtime.js'),html.index('app-shell.js'))
            self.assertIn('data-mode="demo"',html)
            self.assertNotIn(build.PROD_DB,html)
            self.assertNotIn(build.PROD_KEY,html)
            self.assertIn("connect-src 'self';",(p/'dist/_headers').read_text())
            self.assertFalse((p/'dist/docs').exists())
if __name__=='__main__':unittest.main()
