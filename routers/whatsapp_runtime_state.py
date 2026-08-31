"""Process-local mutable state shared by WhatsApp runtime helpers."""
from __future__ import annotations


_LOCKS: dict = {}
_AUTO_ULTIMA: dict = {}
