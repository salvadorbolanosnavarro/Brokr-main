#!/usr/bin/env python3
"""Pass the owning user id into extracted WhatsApp media-AI helpers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

OLD_AUDIO = "await _transcribir_audio(media_bytes, media_mime) if media_bytes else \"\""
NEW_AUDIO = "await _transcribir_audio(media_bytes, media_mime, numero[\"user_id\"]) if media_bytes else \"\""
OLD_IMAGE = "await _describir_imagen(media_bytes, media_mime) if media_bytes else \"\""
NEW_IMAGE = "await _describir_imagen(media_bytes, media_mime, numero[\"user_id\"]) if media_bytes else \"\""


def _replace_or_require(source: str, old: str, new: str, label: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new not in source:
        raise RuntimeError(f"{label} call anchor not found")
    return source


def transform_source(source: str) -> str:
    transformed = _replace_or_require(source, OLD_AUDIO, NEW_AUDIO, "voice transcription")
    transformed = _replace_or_require(transformed, OLD_IMAGE, NEW_IMAGE, "image description")
    if OLD_AUDIO in transformed or OLD_IMAGE in transformed:
        raise RuntimeError("unattributed WhatsApp media AI call remains")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
