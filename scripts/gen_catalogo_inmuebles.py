"""Genera inmuebles-catalogo.js desde core/catalogo_inmuebles.py.

Uso: python scripts/gen_catalogo_inmuebles.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.catalogo_inmuebles import catalogo_dict  # noqa: E402

MARCA_INI = "/*__CATALOGO_INICIO__*/"
MARCA_FIN = "/*__CATALOGO_FIN__*/"


def render() -> str:
    data = json.dumps(catalogo_dict(), ensure_ascii=False, indent=1)
    plantilla = (ROOT / "scripts" / "inmuebles-catalogo.plantilla.js").read_text(encoding="utf-8")
    return plantilla.replace("__DATA__", f"{MARCA_INI}{data}{MARCA_FIN}")


if __name__ == "__main__":
    (ROOT / "inmuebles-catalogo.js").write_text(render(), encoding="utf-8")
    print("inmuebles-catalogo.js actualizado")
