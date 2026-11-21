"""Utilidades geográficas: distancias, celdas H3 y bloques espaciales."""
from __future__ import annotations

import h3
import numpy as np

R_TIERRA_M = 6_371_008.8


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros; acepta escalares o arreglos (se difunde)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_TIERRA_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def celda(lat: float, lon: float, res: int) -> str | None:
    if lat is None or lon is None or not np.isfinite(lat) or not np.isfinite(lon):
        return None
    return h3.latlng_to_cell(float(lat), float(lon), res)


def celdas(lat, lon, res: int) -> list[str | None]:
    return [celda(a, b, res) for a, b in zip(lat, lon)]


def padre(cell: str | None, res: int) -> str | None:
    if not cell:
        return None
    return h3.cell_to_parent(cell, res)


def dentro_bbox(lat: float, lon: float, bbox) -> bool:
    s, w, n, e = bbox
    return s <= lat <= n and w <= lon <= e
