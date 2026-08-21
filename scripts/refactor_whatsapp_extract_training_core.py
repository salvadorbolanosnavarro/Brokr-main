#!/usr/bin/env python3
"""Extract pure WhatsApp training policy from the root monolith."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_training import (\n"
    "    TRAINING_DEFAULTS, _calificacion_para_prompt, _conocimiento_para_prompt,\n"
    "    _en_horario, _reglas_para_prompt,\n"
    ")\n"
)
DEFAULTS_START = "TRAINING_DEFAULTS = {\n"
DEFAULTS_END = "\n\n\ndef _now() -> str:\n"
HELPERS_START = "def _reglas_para_prompt(e: dict) -> str:\n"
HELPERS_END = (
    "\n\n# =============================================================================\n"
    "# 3) EL CEREBRO — Anthropic, con JSON estructurado + acciones\n"
    "# =============================================================================\n"
)


def _remove_between(source: str, start: str, end: str, *, keep_end: bool = True) -> str:
    i = source.find(start)
    if i < 0:
        raise RuntimeError(f"start anchor not found: {start[:60]!r}")
    j = source.find(end, i)
    if j < 0:
        raise RuntimeError(f"end anchor not found: {end[:60]!r}")
    return source[:i] + (source[j:] if keep_end else source[j + len(end):])


def transform_source(source: str) -> str:
    transformed = source

    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if DEFAULTS_START in transformed:
        transformed = _remove_between(transformed, DEFAULTS_START, DEFAULTS_END)
    elif "TRAINING_DEFAULTS = {" in transformed:
        raise RuntimeError("Unexpected TRAINING_DEFAULTS shape")

    if HELPERS_START in transformed:
        transformed = _remove_between(transformed, HELPERS_START, HELPERS_END)
    elif "def _reglas_para_prompt" in transformed:
        raise RuntimeError("Unexpected training helper shape")

    for forbidden in (
        "TRAINING_DEFAULTS = {",
        "def _reglas_para_prompt",
        "def _conocimiento_para_prompt",
        "def _calificacion_para_prompt",
        "def _en_horario",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"training policy remains in whatsapp.py: {forbidden}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
