import tempfile
import unittest
from pathlib import Path
from scripts.package_cecil_preview import audit

class PublishedArtifactTests(unittest.TestCase):
    def test_every_published_file_including_binary_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for payload in (b'https://api.broquer.app/instagram/feed',b'urtgysmtnvoqaljuhntz',b'prefix\x00API.BROQUER.APP'):
                (root/'arbitrary.bin').write_bytes(payload)
                with self.assertRaises(ValueError): audit(root)
            (root/'arbitrary.bin').write_bytes(b'staging')
            self.assertIn('arbitrary.bin',audit(root))

    def test_checked_in_published_files_match_manifest(self):
        import json
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(audit(root/'preview-public'),json.loads((root/'preview-public-manifest.json').read_text()))

if __name__=='__main__': unittest.main()
