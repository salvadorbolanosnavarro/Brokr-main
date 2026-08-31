"""Process-local PDF token store shared by legacy PDF producers and routers."""
from __future__ import annotations


# Historical contract: insertion-ordered dict, token -> (bytes, filename),
# with each producer enforcing the same maximum of 50 entries.
_pdf_store: dict[str, tuple[bytes, str]] = {}
