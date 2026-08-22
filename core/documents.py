"""Safety helpers for untrusted office-document uploads."""
from __future__ import annotations

import io
import zipfile


class UnsafeDocument(ValueError):
    """Raised when an uploaded document is malformed or unsafe to expand."""


def validate_docx_archive(
    content: bytes,
    *,
    max_entries: int = 2000,
    max_uncompressed_bytes: int = 64 * 1024 * 1024,
    max_single_entry_bytes: int = 32 * 1024 * 1024,
) -> None:
    """Validate and bounded-read a DOCX container before XML/Word expansion."""
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise UnsafeDocument("DOCX content is empty")
    if max_entries <= 0 or max_uncompressed_bytes <= 0 or max_single_entry_bytes <= 0:
        raise ValueError("DOCX safety limits must be positive")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > max_entries:
                raise UnsafeDocument("DOCX archive contains too many entries")

            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UnsafeDocument("File is not a valid DOCX document")

            total_actual = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise UnsafeDocument("Encrypted DOCX archives are not supported")
                # Metadata is only an early rejection. The security boundary is the
                # bounded decompression below because ZIP file_size is attacker-controlled.
                if info.file_size < 0 or info.file_size > max_single_entry_bytes:
                    raise UnsafeDocument("DOCX archive entry is too large")

                entry_actual = 0
                with archive.open(info, "r") as member:
                    while True:
                        remaining_entry = max_single_entry_bytes - entry_actual
                        remaining_total = max_uncompressed_bytes - total_actual
                        allowed = min(remaining_entry, remaining_total)
                        if allowed < 0:
                            raise UnsafeDocument("DOCX archive expands beyond the allowed size")
                        chunk = member.read(min(64 * 1024, allowed + 1))
                        if not chunk:
                            break
                        entry_actual += len(chunk)
                        total_actual += len(chunk)
                        if entry_actual > max_single_entry_bytes:
                            raise UnsafeDocument("DOCX archive entry is too large")
                        if total_actual > max_uncompressed_bytes:
                            raise UnsafeDocument("DOCX archive expands beyond the allowed size")
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise UnsafeDocument("File is not a valid DOCX archive") from exc
