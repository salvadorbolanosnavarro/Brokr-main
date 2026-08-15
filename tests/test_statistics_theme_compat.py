"""Prove that Statistics can run on the canonical Broquer theme."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VAR_USE = re.compile(r"var\(\s*--([A-Za-z0-9_-]+)")
VAR_DEF = re.compile(r"--([A-Za-z0-9_-]+)\s*:")


class StatisticsThemeCompatibilityTests(unittest.TestCase):
    def test_every_statistics_token_exists_in_canon_or_locally(self):
        statistics = (ROOT / "estadisticas.html").read_text(encoding="utf-8")
        canonical = (ROOT / "brokr-theme.css").read_text(encoding="utf-8")

        used = set(VAR_USE.findall(statistics))
        available = set(VAR_DEF.findall(canonical)) | set(VAR_DEF.findall(statistics))
        missing = sorted(used - available)

        self.assertEqual(
            missing,
            [],
            "estadisticas.html still depends on tokens absent from brokr-theme.css: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
