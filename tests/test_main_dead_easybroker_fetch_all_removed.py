"""Guard removal of the unused legacy EasyBroker all-properties loader."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeadEasyBrokerFetchAllRemovalTests(unittest.TestCase):
    def test_dead_loader_does_not_return_to_main(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("async def fetch_all_properties()", source)
        self.assertNotIn('cache_get("all_properties")', source)
        self.assertNotIn('cache_set("all_properties"', source)
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
