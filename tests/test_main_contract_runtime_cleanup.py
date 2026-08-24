"""Permanent guard for dead contract-runtime imports removed from main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainContractRuntimeCleanupTests(unittest.TestCase):
    def test_dead_contract_runtime_imports_stay_out_of_main(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("from core.executors import _thread_pool", main)
        self.assertNotIn("from fastapi.responses import FileResponse", main)
        self.assertNotIn("tempfile", main)
        self.assertNotIn("subprocess", main)
        self.assertNotIn("json as _json", main)
        self.assertNotIn("_json.loads(", main)
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
