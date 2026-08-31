"""Keep main.py user_integrations access behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainUserIntegrationsCoreBoundaryTests(unittest.TestCase):
    def test_main_has_no_direct_user_integrations_rest_url(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertNotIn("/rest/v1/user_integrations", source)
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
