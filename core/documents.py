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
    """Validate a DOCX container before handing it to an XML/Word parser.

    DOCX files are ZIP archives. Bounding the number and declared expanded size
    of their members prevents a small compressed upload from expanding without
    limit in ``python-docx`` or another downstream parser.
    """
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

            total = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise UnsafeDocument("Encrypted DOCX archives are not supported")
                if info.file_size < 0 or info.file_size > max_single_entry_bytes:
                    raise UnsafeDocument("DOCX archive entry is too large")
                total += info.file_size
                if total > max_uncompressed_bytes:
                    raise UnsafeDocument("DOCX archive expands beyond the allowed size")
    except zipfile.BadZipFile as exc:
        raise UnsafeDocument("File is not a valid DOCX archive") from exc
