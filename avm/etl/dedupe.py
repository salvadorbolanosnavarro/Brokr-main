"""Agrupa anuncios duplicados (el mismo inmueble publicado varias veces).

Dos anuncios son el mismo inmueble si son del mismo tipo y:
  (a) están a menos de 30 m, sus m2 difieren ±3 % y su precio ±5 %; o
  (b) el hash perceptual de la primera foto es igual.
Los pares se unen con union-find (si A≈B y B≈C, los tres son un clúster).
El principal es el más completo; en empate, el de fecha de alta más antigua.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from ..geo import R_TIERRA_M

DIST_M = 30.0
TOL_M2 = 0.03
TOL_PRECIO = 0.05
CAMPOS_COMPLETITUD = ["m2_construidos", "m2_terreno", "recamaras", "banos", "estacionamientos", "edad_anios",
                      "descripcion", "lat", "lon"]


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def phash_bytes(contenido: bytes) -> str | None:
    """Hash perceptual de una imagen (para el criterio b)."""
    try:
        import imagehash
        from PIL import Image
        return str(imagehash.phash(Image.open(io.BytesIO(contenido))))
    except Exception:
        return None


def _cerca(a: float, b: float, tol: float) -> bool:
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0 or b <= 0:
        return False
    return abs(a - b) / max(a, b) <= tol


def agrupar(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index(drop=True).copy()
    n = len(out)
    uf = _UF(n)
    base = np.where(out["tipo"] == "terreno", out.get("m2_terreno"), out.get("m2_construidos")).astype(float)
    precio = out["precio"].astype(float).to_numpy()
    tipos = out["tipo"].to_numpy()

    con_coord = out[["lat", "lon"]].notna().all(axis=1).to_numpy()
    idx = np.flatnonzero(con_coord)
    if len(idx):
        arbol = BallTree(np.radians(out.loc[idx, ["lat", "lon"]].to_numpy(float)), metric="haversine")
        vecinos = arbol.query_radius(np.radians(out.loc[idx, ["lat", "lon"]].to_numpy(float)), r=DIST_M / R_TIERRA_M)
        for i_local, vs in enumerate(vecinos):
            i = idx[i_local]
            for j_local in vs:
                j = idx[j_local]
                if j <= i or tipos[i] != tipos[j]:
                    continue
                if _cerca(base[i], base[j], TOL_M2) and _cerca(precio[i], precio[j], TOL_PRECIO):
                    uf.union(i, j)

    if "foto_phash" in out:
        for _, g in out[out["foto_phash"].notna()].groupby(["tipo", "foto_phash"]):
            ids = g.index.to_list()
            for j in ids[1:]:
                uf.union(ids[0], j)

    raiz = np.array([uf.find(i) for i in range(n)])
    completitud = out.reindex(columns=CAMPOS_COMPLETITUD).notna().sum(axis=1).to_numpy()
    alta = pd.to_datetime(out["fecha_alta"]).to_numpy()
    ids = out["id"].to_numpy() if "id" in out else np.arange(n)
    cluster = np.empty(n, dtype=np.int64)
    principal = np.zeros(n, dtype=bool)
    for r in np.unique(raiz):
        miembros = np.flatnonzero(raiz == r)
        # Más completo primero; luego el más antiguo; luego el id menor.
        orden = sorted(miembros, key=lambda m: (-completitud[m], alta[m], ids[m]))
        cluster[miembros] = ids[orden[0]]
        principal[orden[0]] = True
    out["cluster_id"] = cluster
    out["es_principal"] = principal
    return out


def resumen(df: pd.DataFrame) -> dict:
    tam = df.groupby("cluster_id").size()
    return {"anuncios": int(len(df)), "inmuebles_unicos": int(len(tam)), "clusters_con_duplicados": int((tam > 1).sum())}
