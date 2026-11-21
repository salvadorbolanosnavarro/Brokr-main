"""Variables del modelo.

- Variable objetivo: y = ln(P_aj / m2_base), con P_aj llevado a la fecha de
  valuación por el índice de la zona; m2_base = construidos (terrenos: terreno).
- Bloques espaciales H3 para todo lo que es "fuera de muestra": target encoding
  de H3-7/8/9 y validación. Nunca split aleatorio.
- Mediana kNN de vecinos excluyendo el propio registro y su clúster de
  duplicados (si no, el modelo se ve a sí mismo).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from . import geo
from . import settings as S
from .indice import IndicePrecios

TIPO_CODE = {"casa": 0, "depto": 1, "terreno": 2, "local": 3}
REGIMEN_CODE = {"independiente": 0, "privada": 1, "condominio": 2, "ejidal": 3}
REZAGO_CODE = {"muy bajo": 0, "bajo": 1, "medio": 2, "alto": 3, "muy alto": 4}

ESTRUCTURALES = ["ln_m2", "ln_m2_terreno", "recamaras", "banos", "medios_banos", "estacionamientos",
                 "edad_anios", "nivel", "tipo_code"]
TEXTO = ["conservacion", "remodelada", "jardin", "roof_garden", "seguridad_24h", "alberca", "cajones",
         "esquina", "regimen_code"]
CONTEXTO = ["nse_score", "escolaridad_prom", "pct_auto", "pct_internet", "pct_computadora",
            "densidad_hab_km2", "rezago_num", "escuelas", "hospitales", "supermercados", "bancos",
            "restaurantes", "dist_avenida_m", "dist_parque_m", "dist_centro_m"]
ESPACIALES = ["lat", "lon", "te_h3_7", "te_h3_8", "te_h3_9", "knn_med"]
TIEMPO = ["dias_publicado", "t_meses", "mes_sin", "mes_cos"]
FEATURES = ESTRUCTURALES + TEXTO + CONTEXTO + ESPACIALES + TIEMPO

GRUPOS_EXPLICACION = {
    "ubicacion": ["lat", "lon", "te_h3_7", "te_h3_8", "te_h3_9", "knn_med", "nse_score", "escolaridad_prom",
                  "pct_auto", "pct_internet", "pct_computadora", "densidad_hab_km2", "rezago_num",
                  "escuelas", "hospitales", "supermercados", "bancos", "restaurantes",
                  "dist_avenida_m", "dist_parque_m", "dist_centro_m"],
    "superficie": ["ln_m2", "ln_m2_terreno"],
    "antiguedad": ["edad_anios", "conservacion", "remodelada"],
    "distribucion": ["recamaras", "banos", "medios_banos", "estacionamientos", "cajones", "nivel"],
    "amenidades": ["jardin", "roof_garden", "seguridad_24h", "alberca", "esquina", "regimen_code"],
    "mercado": ["dias_publicado", "t_meses", "mes_sin", "mes_cos", "tipo_code"],
}

EPOCA = pd.Timestamp("2020-01-01")


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def m2_base(df: pd.DataFrame) -> pd.Series:
    return np.where(df["tipo"] == "terreno", _num(df, "m2_terreno"), _num(df, "m2_construidos"))


def preparar(df: pd.DataFrame, indice: IndicePrecios, fecha_valuacion) -> pd.DataFrame:
    """Columnas derivadas comunes (no dependen de otros registros)."""
    out = df.copy()
    fv = pd.Timestamp(fecha_valuacion)
    out["m2_base"] = m2_base(out)
    zona = out["zona_indice"] if "zona_indice" in out else out.get("municipio", pd.Series("", index=out.index))
    fecha_obs = pd.to_datetime(out["ultimo_visto"] if "ultimo_visto" in out else out["fecha_alta"], utc=False)
    fecha_obs = fecha_obs.dt.tz_localize(None) if getattr(fecha_obs.dt, "tz", None) is not None else fecha_obs
    out["_fecha_obs"] = fecha_obs.fillna(fv)
    if "precio" in out:
        out["precio_aj"] = out["precio"].astype(float) * indice.factores(zona.fillna("").tolist(), out["_fecha_obs"].tolist(), fv)
        with np.errstate(divide="ignore", invalid="ignore"):
            out["y"] = np.log(out["precio_aj"] / out["m2_base"])
    out["ln_m2"] = np.log(out["m2_base"].astype(float))
    out["ln_m2_terreno"] = np.log(_num(out, "m2_terreno").where(lambda s: s > 0))
    out["tipo_code"] = out["tipo"].map(TIPO_CODE).astype(float)
    out["regimen_code"] = out["regimen"].map(REGIMEN_CODE) if "regimen" in out else np.nan
    out["rezago_num"] = (out["rezago_coneval"].astype(str).str.lower().map(REZAGO_CODE)
                         if "rezago_coneval" in out else _num(out, "rezago_num"))
    if "cajones" not in out:
        out["cajones"] = _num(out, "estacionamientos")
    alta = pd.to_datetime(out["fecha_alta"]) if "fecha_alta" in out else pd.Series(fv, index=out.index)
    if "dias_publicado" not in out or out["dias_publicado"].isna().all():
        out["dias_publicado"] = (out["_fecha_obs"] - alta).dt.days.clip(lower=0)
    out["t_meses"] = (alta - EPOCA).dt.days / 30.44
    mes = alta.dt.month
    out["mes_sin"] = np.sin(2 * np.pi * mes / 12)
    out["mes_cos"] = np.cos(2 * np.pi * mes / 12)
    for res in (7, 8, 9):
        col = f"h3_{res}"
        if col not in out or out[col].isna().all():
            out[col] = geo.celdas(out["lat"], out["lon"], res)
    for col in FEATURES:
        if col not in out:
            out[col] = np.nan
    return out


def bloques_espaciales(df: pd.DataFrame, n_folds: int = S.B_FOLDS, res: int = S.H3_BLOQUE_CV,
                       semilla: int = 7) -> np.ndarray:
    """Asigna cada registro a un fold por su hexágono H3 padre: todo un bloque
    cae en el mismo fold. Reparto voraz por tamaño para que queden parejos."""
    bloque = [geo.celda(la, lo, res) if np.isfinite(la) and np.isfinite(lo) else f"_sin_{i}"
              for i, (la, lo) in enumerate(zip(df["lat"].astype(float), df["lon"].astype(float)))]
    bloque = pd.Series(bloque, index=df.index)
    tam = bloque.value_counts()
    rng = np.random.default_rng(semilla)
    orden = tam.sample(frac=1.0, random_state=int(rng.integers(1e9))).sort_values(ascending=False, kind="stable")
    carga = np.zeros(n_folds)
    asignacion = {}
    for b, n in orden.items():
        k = int(np.argmin(carga))
        asignacion[b] = k
        carga[k] += n
    return bloque.map(asignacion).to_numpy()


class Featurizer:
    """Ajusta lo que depende del conjunto de entrenamiento (target encoding,
    referencia kNN) y transforma sin fuga de información."""

    def __init__(self, n_folds: int = S.B_FOLDS, m: float = S.B_TE_SUAVIZADO, k: int = S.B_KNN_VECINOS,
                 res_bloque: int = S.H3_BLOQUE_TE):
        self.n_folds, self.m, self.k, self.res_bloque = n_folds, m, k, res_bloque

    # ── residual por tipo ──
    def _r(self, df: pd.DataFrame) -> pd.Series:
        return df["y"] - df["tipo"].map(self.med_tipo).fillna(self.med_global)

    @staticmethod
    def _te_maps(df: pd.DataFrame, r: pd.Series, m: float) -> dict:
        maps = {}
        for res in (7, 8, 9):
            g = pd.DataFrame({"c": df[f"h3_{res}"], "r": r}).groupby("c")["r"].agg(["sum", "count"])
            maps[res] = (g["sum"] / (g["count"] + m)).to_dict()     # prior 0 en el residual
        return maps

    def fit(self, train: pd.DataFrame) -> "Featurizer":
        train = train[np.isfinite(train["y"])]
        self.med_tipo = train.groupby("tipo")["y"].median().to_dict()
        self.med_global = float(train["y"].median())
        r = self._r(train)
        self.te = self._te_maps(train, r, self.m)
        self.ref = pd.DataFrame({
            "lat": train["lat"].to_numpy(), "lon": train["lon"].to_numpy(), "r": r.to_numpy(),
            "tipo": train["tipo"].to_numpy(),
            "cluster": (train["cluster_id"] if "cluster_id" in train else train["id"]).fillna(-1).to_numpy(),
            "id": train["id"].to_numpy(),
        })
        self._arboles = {}
        for tipo, sub in self.ref.groupby("tipo"):
            self._arboles[tipo] = (BallTree(np.radians(sub[["lat", "lon"]].to_numpy()), metric="haversine"),
                                   sub.reset_index(drop=True))
        return self

    def _knn(self, df: pd.DataFrame) -> np.ndarray:
        out = np.full(len(df), np.nan)
        clusters = (df["cluster_id"] if "cluster_id" in df else df.get("id", pd.Series(-2, index=df.index)))
        clusters = clusters.fillna(-2).to_numpy()
        ids = df["id"].to_numpy() if "id" in df else np.full(len(df), -2)
        for tipo, idx in df.groupby("tipo").indices.items():
            if tipo not in self._arboles:
                continue
            arbol, sub = self._arboles[tipo]
            kq = min(len(sub), self.k + 25)
            if kq == 0:
                continue
            pts = np.radians(df.iloc[idx][["lat", "lon"]].to_numpy(dtype=float))
            ok = np.isfinite(pts).all(axis=1)
            if not ok.any():
                continue
            _, vecinos = arbol.query(pts[ok], k=kq)
            for fila, vs in zip(np.asarray(idx)[ok], vecinos):
                cand = sub.iloc[vs]
                cand = cand[(cand["id"] != ids[fila]) & (cand["cluster"] != clusters[fila])]
                if len(cand):
                    out[fila] = float(np.median(cand["r"].to_numpy()[: self.k]))
        return out

    def _aplicar_te(self, df: pd.DataFrame, maps: dict) -> pd.DataFrame:
        for res in (7, 8, 9):
            df[f"te_h3_{res}"] = df[f"h3_{res}"].map(maps[res]).astype(float).fillna(0.0)
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Para registros que NO están en el entrenamiento (validación, sujeto)."""
        out = self._aplicar_te(df.copy(), self.te)
        out["knn_med"] = self._knn(out)
        return out

    def fit_transform(self, train: pd.DataFrame) -> pd.DataFrame:
        """Para el propio entrenamiento: target encoding fuera de fold (folds
        espaciales) y kNN excluyendo el propio registro y sus duplicados."""
        self.fit(train)
        out = train.copy()
        folds = bloques_espaciales(out, self.n_folds, res=self.res_bloque)
        r = self._r(out)
        for res in (7, 8, 9):
            out[f"te_h3_{res}"] = 0.0
        for k in range(self.n_folds):
            dentro = folds != k
            maps = self._te_maps(out[dentro], r[dentro], self.m)
            fuera = ~dentro
            for res in (7, 8, 9):
                out.loc[fuera, f"te_h3_{res}"] = out.loc[fuera, f"h3_{res}"].map(maps[res]).astype(float).fillna(0.0)
        out["knn_med"] = self._knn(out)
        return out


def matriz(df: pd.DataFrame) -> pd.DataFrame:
    return df[FEATURES].apply(pd.to_numeric, errors="coerce").astype(float)
