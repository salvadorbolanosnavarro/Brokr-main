"""Pure formatting/parsing helpers for WhatsApp.

This module intentionally contains no network, database, FastAPI, or global
runtime configuration access so its historical behavior can be characterized
and moved out of the root monolith independently.
"""
from __future__ import annotations

import re


def normaliza_mx(num: str) -> str:
    n = "".join(ch for ch in str(num) if ch.isdigit())
    if n.startswith("521") and len(n) == 13:
        n = "52" + n[3:]
    return n


def money(n) -> str:
    try:
        return "$" + f"{int(round(float(n))):,}"
    except Exception:
        return str(n) if n else ""


def parsear_presupuesto(texto: str) -> int | None:
    if not texto:
        return None
    t = texto.lower().replace(",", "").replace("$", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(millones|mill?on|mdp|m\b)", t)
    if m:
        return int(float(m.group(1)) * 1_000_000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mil|k\b)", t)
    if m:
        return int(float(m.group(1)) * 1_000)
    m = re.search(r"(\d{5,})", t)
    if m:
        return int(m.group(1))
    return None


def in_filter(ids: list[str]) -> str:
    return "in.(" + ",".join(ids) + ")"
