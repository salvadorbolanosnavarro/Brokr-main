"""Lectura/escritura de las tablas avm_* en Supabase (siempre vía
core.database: nunca URLs REST a mano fuera de core/)."""
from __future__ import annotations

import json
from typing import Any, Iterable

import numpy as np
import pandas as pd

from core.database import get_rows, patch_rows, post_rows, upsert_rows

PAGINA = 1000
COLUMNAS_LISTING = [
    "id", "fuente", "url", "fecha_alta", "fecha_baja", "ultimo_visto", "tipo", "operacion", "precio", "moneda",
    "m2_construidos", "m2_terreno", "recamaras", "banos", "medios_banos", "estacionamientos", "edad_anios", "nivel",
    "amenidades", "descripcion", "fotos", "lat", "lon", "precision_ubicacion", "estado", "municipio", "colonia",
    "h3_7", "h3_8", "h3_9", "ageb_cvegeo", "cluster_id", "es_principal", "calidad", "motivo_descarte", "extra",
]


async def leer_todo(tabla: str, params: dict | None = None, orden: str = "id") -> list[dict]:
    filas: list[dict] = []
    offset = 0
    while True:
        lote = await get_rows(tabla, {**(params or {}), "order": orden, "limit": PAGINA, "offset": offset}, timeout=60)
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        offset += PAGINA


def _limpio(v: Any):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (pd.Timestamp,)):
        return None if pd.isna(v) else v.isoformat()
    if v is pd.NaT:
        return None
    return v


def registros(df: pd.DataFrame, columnas: Iterable[str]) -> list[dict]:
    cols = [c for c in columnas if c in df]
    return [{c: _limpio(v) for c, v in zip(cols, fila)} for fila in df[cols].itertuples(index=False, name=None)]


def listings_a_df(filas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    # Las variables extraídas del texto viven en 'extra' (jsonb): se aplanan.
    extra = pd.json_normalize(df["extra"].apply(lambda x: x if isinstance(x, dict) else (json.loads(x) if x else {})))
    amen = pd.json_normalize(df["amenidades"].apply(lambda x: x if isinstance(x, dict) else {}))
    for bloque in (extra, amen):
        for c in bloque.columns:
            if c not in df:
                df[c] = bloque[c].to_numpy()
    for c in ("precio", "m2_construidos", "m2_terreno", "lat", "lon"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("fecha_alta", "fecha_baja"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    if "ultimo_visto" in df:
        df["ultimo_visto"] = pd.to_datetime(df["ultimo_visto"], errors="coerce", utc=True).dt.tz_localize(None)
    df["ciudad"] = df.get("municipio")
    df["zona_indice"] = df.get("municipio")
    return df


async def cargar_todo() -> dict:
    listings = listings_a_df(await leer_todo("avm_listings", {"operacion": "eq.venta"}))
    closings = pd.DataFrame(await leer_todo("avm_closings"))
    if not closings.empty:
        for c in ("precio_oferta_inicial", "precio_cierre"):
            closings[c] = pd.to_numeric(closings[c], errors="coerce")
        closings["ciudad"] = closings["municipio"]
    indice = await leer_todo("avm_index", orden="trimestre")
    ageb = pd.DataFrame(await leer_todo("avm_context_ageb", orden="cvegeo"))
    poi = pd.DataFrame(await leer_todo("avm_poi_counts", orden="h3_9"))
    if not ageb.empty:
        ageb = ageb.rename(columns={})
        ageb["rezago_num"] = ageb["rezago_coneval"].astype(str).str.lower().map(
            {"muy bajo": 0, "bajo": 1, "medio": 2, "alto": 3, "muy alto": 4})
    return {"listings": listings, "closings": closings, "indice": indice,
            "contexto": {"ageb": ageb if not ageb.empty else None, "poi": poi if not poi.empty else None}}


async def upsert_listings(filas: list[dict]) -> list[dict]:
    out = []
    for i in range(0, len(filas), 200):
        out += await upsert_rows("avm_listings", filas[i:i + 200], conflict="url", timeout=60)
    return out


async def registrar_precios(cambios: list[dict]) -> None:
    if cambios:
        await post_rows("avm_price_history", cambios, prefer="return=minimal", timeout=60)


async def marcar(ids: list[int], cambios: dict) -> None:
    for i in range(0, len(ids), 300):
        lote = ",".join(str(int(x)) for x in ids[i:i + 300])
        await patch_rows("avm_listings", {"id": f"in.({lote})"}, cambios, timeout=60)


async def guardar_prediccion(fila: dict) -> None:
    await post_rows("avm_predictions", fila, prefer="return=minimal", timeout=15)


async def guardar_cierre(fila: dict) -> dict:
    filas = await post_rows("avm_closings", fila, timeout=15)
    return filas[0] if filas else {}
