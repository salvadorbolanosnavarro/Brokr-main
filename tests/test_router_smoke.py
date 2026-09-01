"""Router smoke test.

Detecta en CI, antes del merge, cualquier router declarado en main.py cuyo
archivo .py no exista en routers/. Evita exactamente el bug que causó el
outage del 2026-09-01: demo_live.py subido a la raíz via GitHub UI en lugar
de routers/, haciendo que Railway no arrancara con ModuleNotFoundError.

Corre dentro de scripts/run_quality.sh via:
    python -m unittest discover -s tests -p 'test_*.py'
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / "main.py"
ROUTERS_DIR = ROOT / "routers"

# Extrae todos los módulos de routers referenciados en main.py,
# tanto en imports duros como dentro de bloques try/except.
_IMPORT_RE = re.compile(
    r"from\s+routers\.(\w+)\s+import",
)


def _declared_router_modules() -> list[str]:
    src = MAIN_PY.read_text(encoding="utf-8")
    return _IMPORT_RE.findall(src)


class RouterSmokeTests(unittest.TestCase):
    """Cada módulo de router declarado en main.py debe existir en routers/."""

    def test_all_declared_routers_exist_on_disk(self):
        missing = []
        for mod in _declared_router_modules():
            path = ROUTERS_DIR / f"{mod}.py"
            if not path.exists():
                missing.append(f"routers/{mod}.py (referenciado en main.py)")
        if missing:
            self.fail(
                "Los siguientes routers están declarados en main.py pero su "
                "archivo no existe en routers/:\n"
                + "\n".join(f"  • {m}" for m in missing)
                + "\n\nPosible causa: archivo subido a la raíz via GitHub UI "
                "en vez de la carpeta routers/."
            )

    def test_no_router_module_lives_at_repo_root_without_routers_copy(self):
        """Si un archivo .py está en la raíz con el mismo nombre que un router declarado
        pero NO existe en routers/, es señal de que fue subido al lugar equivocado.
        Un duplicado en raíz junto al archivo correcto en routers/ es inofensivo
        (aunque desordenado); este test solo captura el caso peligroso."""
        declared = set(_declared_router_modules())
        bad = []
        for py in ROOT.glob("*.py"):
            if py.stem in declared:
                correct_path = ROUTERS_DIR / py.name
                if not correct_path.exists():
                    bad.append(str(py.relative_to(ROOT)))
        if bad:
            self.fail(
                "Los siguientes archivos están en la RAÍZ del repo, son "
                "routers declarados en main.py, y NO existe su copia en "
                "routers/ (archivo subido al lugar equivocado via GitHub UI):\n"
                + "\n".join(f"  • {f}" for f in bad)
            )

    def test_main_imports_cleanly(self):
        """import main no debe lanzar ninguna excepción."""
        try:
            import main  # noqa: F401
        except Exception as exc:
            self.fail(f"'import main' falló: {exc}")


if __name__ == "__main__":
    unittest.main()
