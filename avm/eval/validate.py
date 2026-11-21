"""Validación del AVM v2. Prohibido el split aleatorio.

1. Hold-out temporal: se entrena con todo lo anterior a los últimos 3 meses y
   se valúa lo publicado en esos 3 meses (escenario de producción).
2. Validación cruzada por bloques H3-6 (prueba de estrés: zona sin datos).
3. Contra cierres reales (avm_closings): cada cierre se estima con un modelo
   que no vio su bloque H3-8 ni su propio cierre en δ; el rango se evalúa con
   conformal cruzado (calibrado en los otros folds).
4. Golden set (avalúos reales capturados a mano), si tiene filas.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .. import settings as S
from ..contexto import Contexto
from ..indice import IndicePrecios
from .. import pipeline as P
from .metrics import cumple, metricas, por_grupo

GOLDEN = Path(__file__).resolve().parent / "golden_set.csv"
COLUMNAS_GOLDEN = ["id", "fecha_avaluo", "tipo", "ciudad", "colonia", "lat", "lon", "m2_construidos", "m2_terreno",
                   "recamaras", "banos", "edad_anios", "conservacion", "valor_avaluo", "valor_motor_actual", "notas"]


def _tabla_res(resultados: list[dict], df: pd.DataFrame, real_col: str, con_delta: bool) -> pd.DataFrame:
    filas = []
    for r, (_, d) in zip(resultados, df.iterrows()):
        v = r["valor"] if con_delta else (r["valor"] / (1 - r["delta"]) if r["valor"] else None)
        lo = hi = None
        if r["rango"]:
            f = 1.0 if con_delta else 1 / (1 - r["delta"])
            lo, hi = r["rango"][0] * f, r["rango"][1] * f
        filas.append({"id": d["id"], "ciudad": d.get("ciudad"), "tipo": d["tipo"], "segmento": S.segmento(d[real_col]),
                      "real": d[real_col], "estimado": v, "bajo": lo, "alto": hi, "emitido": r["emitido"],
                      "confianza": r["confianza"],
                      **{f"valor_{k}": r["motores"][k]["valor"] for k in "ABC"}})
    return pd.DataFrame(filas)


def holdout_temporal(listings, cierres, indice_rows, fv, ctx_tablas=None, rounds=S.B_ROUNDS) -> dict:
    fv = pd.Timestamp(fv)
    corte = fv - pd.DateOffset(months=S.HOLDOUT_MESES)
    indice = IndicePrecios(indice_rows)
    base, _ = P.preparar_base(listings, indice, fv, Contexto(**_ctx(ctx_tablas)))
    test = base[pd.to_datetime(base["fecha_alta"]) >= corte]
    c_test = cierres[pd.to_datetime(cierres["fecha_cierre"]) >= corte] if cierres is not None and len(cierres) else None
    excluir = set(c_test["listing_id"]) if c_test is not None else set()
    ids_train = base[(pd.to_datetime(base["fecha_alta"]) < corte) & ~base["id"].isin(excluir)]["id"]
    l_train = listings[listings["id"].isin(ids_train)]
    c_train = cierres[pd.to_datetime(cierres["fecha_cierre"]) < corte] if cierres is not None and len(cierres) else None
    modelo, _ = P.entrenar(l_train, c_train, indice_rows, fv, datos="validacion", contexto_tablas=ctx_tablas,
                           rounds=rounds)
    res = modelo.estimar_filas(test)
    t_oferta = _tabla_res(res, test, "precio_aj", con_delta=False)
    out = {"corte": str(corte.date()), "n_train": int(len(ids_train)), "n_test": int(len(test)),
           "oferta": t_oferta}
    if c_test is not None and len(c_test) and c_test["listing_id"].isin(base["id"]).any():
        c = P.cierres_ajustados(c_test, base, indice, fv)
        c = c[c["listing_id"].isin(base["id"])]
        sujetos = base.set_index("id").loc[c["listing_id"]].reset_index()
        sujetos = sujetos.rename(columns={"index": "id"})
        res_c = modelo.estimar_filas(sujetos)
        sujetos["real_aj"] = c["real_aj"].to_numpy()
        out["cierres"] = _tabla_res(res_c, sujetos, "real_aj", con_delta=True)
    return out


def cv_espacial(listings, indice_rows, fv, ctx_tablas=None, rounds=S.B_ROUNDS, res=S.H3_BLOQUE_CV) -> pd.DataFrame:
    indice = IndicePrecios(indice_rows)
    base, _ = P.preparar_base(listings, indice, pd.Timestamp(fv), Contexto(**_ctx(ctx_tablas)))
    oof = P.predecir_oof(base, rounds, res_bloque=res)
    sigma = P.sigma_desde_oof(oof)
    ens = P.ensamblar_oof(oof, sigma, None, None, aplicar_delta=False)
    return pd.DataFrame({"id": ens["id"], "ciudad": ens["ciudad"], "tipo": ens["tipo"], "segmento": ens["segmento"],
                         "real": ens["precio_aj"], "estimado": ens["valor_crudo"], "emitido": True,
                         **{f"valor_{k}": np.exp(ens[f"ln_{k}"]) * ens["m2_base"] for k in "ABC"}})


def contra_cierres(listings, cierres, indice_rows, fv, ctx_tablas=None, rounds=S.B_ROUNDS) -> pd.DataFrame | None:
    if cierres is None or cierres.empty:
        return None
    fv = pd.Timestamp(fv)
    indice = IndicePrecios(indice_rows)
    base, _ = P.preparar_base(listings, indice, fv, Contexto(**_ctx(ctx_tablas)))
    oof = P.predecir_oof(base, rounds, res_bloque=S.H3_BLOQUE_CALIBRACION)
    sigma = P.sigma_desde_oof(oof)
    c = P.evaluar_cierres_oof(oof, cierres, base, indice, fv, sigma, cross_conformal=True)
    if c is None or c.empty:
        return None
    return pd.DataFrame({"id": c["listing_id"], "ciudad": c["ciudad"], "tipo": c["tipo"],
                         "segmento": c["real_aj"].map(S.segmento), "real": c["real_aj"], "estimado": c["ens_valor"],
                         "bajo": c["ens_bajo"], "alto": c["ens_alto"], "emitido": c["emitido"],
                         "confianza": c["confianza"], "estimado_calc": c["ens_valor_calc"],
                         "bajo_calc": c["ens_bajo_calc"], "alto_calc": c["ens_alto_calc"]})


def golden(modelo: "P.ModeloAVM") -> pd.DataFrame | None:
    if not GOLDEN.exists():
        return None
    g = pd.read_csv(GOLDEN)
    g = g.dropna(subset=["valor_avaluo", "lat", "lon"])
    if g.empty:
        return None
    filas = []
    for _, r in g.iterrows():
        sujeto = {k: (None if pd.isna(r.get(k)) else r.get(k)) for k in COLUMNAS_GOLDEN if k in r}
        res = modelo.estimar(sujeto)
        filas.append({"id": r["id"], "ciudad": r.get("ciudad"), "tipo": r["tipo"], "segmento": S.segmento(r["valor_avaluo"]),
                      "real": r["valor_avaluo"], "estimado": res["valor"],
                      "bajo": res["rango"][0] if res["rango"] else None,
                      "alto": res["rango"][1] if res["rango"] else None, "emitido": res["emitido"],
                      "motor_actual": r.get("valor_motor_actual")})
    return pd.DataFrame(filas)


def resumen(tabla: pd.DataFrame | None) -> dict | None:
    if tabla is None or tabla.empty:
        return None
    m = metricas(tabla["estimado"], tabla["real"], tabla.get("bajo"), tabla.get("alto"), tabla.get("emitido"))
    return {"global": m, "cumple": cumple(m),
            "ciudad": por_grupo(tabla, ["ciudad"]), "tipo": por_grupo(tabla, ["tipo"]),
            "segmento": por_grupo(tabla, ["segmento"])}


def por_motor(tabla: pd.DataFrame) -> dict:
    out = {}
    for k in "ABC":
        col = f"valor_{k}"
        if col in tabla:
            out[k] = metricas(tabla[col], tabla["real"])
    return out


def _ctx(ctx_tablas):
    ctx_tablas = ctx_tablas or {}
    return {"ageb": ctx_tablas.get("ageb"), "poi": ctx_tablas.get("poi")}
