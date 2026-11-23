"""Entrenamiento y estimación de punta a punta.

datos crudos → limpieza → duplicados → variables → 3 motores → validación
cruzada espacial (σ por motor, conformal) → ModeloAVM (lo que se guarda y se
carga en memoria al arrancar).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import VERSION_CODIGO
from . import settings as S
from .contexto import Contexto, ciudad_mas_cercana
from .engines.motor_a_comparables import MotorA
from .engines.motor_b_gbm import MotorB
from .engines.motor_c_fisico import MotorC
from .ensemble import (ConformalMondrian, TablaDelta, TablaSigma, delta_extra_por_dias, ensamblar)
from .etl import clean, dedupe
from .explain import frases
from .features import Featurizer, bloques_espaciales, preparar
from .indice import IndicePrecios

MOTORES = ("A", "B", "C")


def preparar_base(listings: pd.DataFrame, indice: IndicePrecios, fecha_valuacion,
                  contexto: Contexto | None = None) -> tuple[pd.DataFrame, dict]:
    """Limpia, agrupa duplicados y deja solo inmuebles principales en venta."""
    limpio = clean.limpiar(listings, S.ciudades())
    ok = limpio[limpio["calidad"] == "ok"]
    agrupado = dedupe.agrupar(ok)
    base = agrupado[agrupado["es_principal"]].copy()
    if contexto is not None:
        base = contexto.asignar(base)
    base = preparar(base, indice, fecha_valuacion)
    base = base[np.isfinite(base["y"])].reset_index(drop=True)
    info = {"limpieza": clean.resumen(limpio), "duplicados": dedupe.resumen(agrupado), "base": int(len(base))}
    return base, info


def _sujeto_df(sujeto: dict, fecha_valuacion, indice: IndicePrecios, contexto: Contexto) -> pd.DataFrame:
    s = dict(sujeto)
    s.setdefault("id", -1)
    s.setdefault("cluster_id", -1)
    s.setdefault("fecha_alta", pd.Timestamp(fecha_valuacion))
    s.setdefault("ultimo_visto", pd.Timestamp(fecha_valuacion))
    s["dias_publicado"] = 0.0   # se valúa como anuncio recién publicado
    if not s.get("ciudad"):
        s["ciudad"] = ciudad_mas_cercana(s["lat"], s["lon"])
    s.setdefault("municipio", s["ciudad"])
    s.setdefault("zona_indice", s["ciudad"])
    df = pd.DataFrame([s])
    df = contexto.asignar(df)
    return preparar(df, indice, fecha_valuacion)


@dataclass
class ModeloAVM:
    version: str
    fecha_valuacion: pd.Timestamp
    datos: str                        # "reales" | "sinteticos"
    featurizer: Featurizer
    motor_b: MotorB
    referencia: pd.DataFrame
    indice: IndicePrecios
    contexto: Contexto
    sigma: TablaSigma
    delta: TablaDelta
    conformal: ConformalMondrian
    ln_m2_tipico: dict
    info: dict = field(default_factory=dict)

    def __post_init__(self):
        self.motor_a = MotorA(self.referencia)
        self.motor_c = MotorC(self.referencia)

    # ── un inmueble ──
    def estimar(self, sujeto: dict) -> dict:
        df = _sujeto_df(sujeto, self.fecha_valuacion, self.indice, self.contexto)
        df = self.featurizer.transform(df)
        fila = df.iloc[0].to_dict()
        return self._combinar(fila, df)

    def estimar_filas(self, df_prep: pd.DataFrame) -> list[dict]:
        """Valúa en lote registros ya preparados (validación): cada uno como
        sujeto recién publicado, excluyendo su propio id y clúster."""
        df = df_prep.copy()
        df["dias_publicado"] = 0.0
        df = self.featurizer.transform(df).reset_index(drop=True)
        out = []
        for i in range(len(df)):
            fila = df.iloc[i].to_dict()
            out.append(self._combinar(fila, df.iloc[[i]], excluir_ids=(fila.get("id"),),
                                      excluir_clusters=(fila.get("cluster_id"),)))
        return out

    def _combinar(self, fila: dict, df_fila: pd.DataFrame, excluir_ids=(), excluir_clusters=()) -> dict:
        m2 = float(fila["m2_base"])
        tipo, ciudad = fila["tipo"], fila.get("ciudad")
        res_a = self.motor_a.estimar(fila, excluir_ids, excluir_clusters)
        res_b = self.motor_b.estimar(df_fila)
        res_c = self.motor_c.estimar(fila)
        valores = {"A": res_a.valor if res_a.ok else None, "B": res_b.valor if res_b.ok else None,
                   "C": res_c.valor if res_c.ok else None}
        ref_valor = next((v for v in (valores["B"], valores["A"], valores["C"]) if v), None)
        seg = S.segmento(ref_valor or 0)
        sigmas = {k: self.sigma.sigma(k, ciudad, tipo, seg) for k in MOTORES}
        d, n = self.delta.delta(fila.get("municipio") or ciudad, seg)
        d = min(S.DELTA_MAX, d + delta_extra_por_dias(res_a.comparables if res_a.ok else []))
        ens = ensamblar(valores, sigmas, res_b.q if res_b.ok else None, m2,
                        self.conformal.ajuste(ciudad, seg), d, n, valores["C"])
        explicacion = []
        if res_b.ok and res_b.contribuciones:
            explicacion = frases(res_b.contribuciones, float(fila["ln_m2"]),
                                 self.ln_m2_tipico.get(tipo, float(fila["ln_m2"])), fila.get("colonia"))
        motores = {
            "A": {"nombre": "Comparables homologados", "ok": res_a.ok, "valor": res_a.valor,
                  "motivo": res_a.motivo, "dispersion": res_a.dispersion, "radio_m": res_a.radio_m,
                  "sigma": sigmas["A"]},
            "B": {"nombre": "Modelo estadístico", "ok": res_b.ok, "valor": res_b.valor, "motivo": res_b.motivo,
                  "sigma": sigmas["B"]},
            "C": {"nombre": "Enfoque físico", "ok": res_c.ok, "valor": res_c.valor, "motivo": res_c.motivo,
                  "detalle": res_c.detalle, "sigma": sigmas["C"]},
        }
        for k, p in ens.pesos.items():
            motores[k]["peso"] = round(p, 4)
        return {
            "emitido": ens.emitido, "valor": ens.valor, "rango": ens.rango, "confianza": ens.confianza,
            "ancho_relativo": ens.ancho_relativo, "delta": ens.delta, "delta_n": ens.delta_n,
            "segmento": seg, "ciudad": ciudad, "motores": motores,
            "comparables": res_a.comparables if res_a.ok else [],
            "explicacion": explicacion, "advertencias": ens.advertencias,
            "version": self.version, "datos": self.datos,
            "_valor_calc": ens.valor_calculado, "_escala": ens.escala,
            "_q": res_b.q if res_b.ok else None, "_ln_valores": {k: (math.log(v) if v else None) for k, v in valores.items()},
        }


# ── entrenamiento ───────────────────────────────────────────────────────────
def _ajustar_motores(train: pd.DataFrame, rounds: int):
    fz = Featurizer()
    tr = fz.fit_transform(train)
    mb = MotorB(rounds=rounds).entrenar(tr)
    return fz, mb, tr


def predecir_oof(base: pd.DataFrame, rounds: int = S.B_ROUNDS, n_folds: int = S.B_FOLDS,
                 res_bloque: int = S.H3_BLOQUE_CALIBRACION, folds: np.ndarray | None = None) -> pd.DataFrame:
    """Validación cruzada por bloques espaciales H3: cada inmueble se estima con
    un modelo que nunca vio su bloque. Devuelve, por inmueble, ln precio/m2 de
    cada motor, cuantiles de B y lo necesario para ensamblar."""
    if folds is None:
        folds = bloques_espaciales(base, n_folds, res=res_bloque)
    n_folds = int(folds.max()) + 1
    filas = []
    for k in range(n_folds):
        tr_idx, va_idx = folds != k, folds == k
        if va_idx.sum() == 0 or tr_idx.sum() < 50:
            continue
        train = base[tr_idx].reset_index(drop=True)
        val = base[va_idx].reset_index(drop=True)
        fz, mb, _ = _ajustar_motores(train, rounds)
        va = val.copy()
        va["dias_publicado"] = 0.0
        va = fz.transform(va)
        ln_b = mb.predecir_ln_pm2(va)
        qs = mb.predecir_cuantiles(va)
        ma, mc = MotorA(train), MotorC(train)
        for i in range(len(va)):
            f = va.iloc[i].to_dict()
            ra = ma.estimar(f)
            rc = mc.estimar(f)
            filas.append({
                "id": f["id"], "fold": k, "ciudad": f.get("ciudad"), "municipio": f.get("municipio"),
                "tipo": f["tipo"], "m2_base": f["m2_base"], "y": f["y"], "precio_aj": f["precio_aj"],
                "ln_A": ra.ln_pm2 if ra.ok else np.nan,
                "ln_B": float(ln_b[i]),
                "ln_C": math.log(rc.valor / f["m2_base"]) if rc.ok else np.nan,
                "q10": float(qs[0.1][i]), "q50": float(qs[0.5][i]), "q90": float(qs[0.9][i]),
                "extra_dias": delta_extra_por_dias(ra.comparables if ra.ok else []),
            })
    oof = pd.DataFrame(filas)
    oof["segmento"] = np.exp(oof["y"] + np.log(oof["m2_base"])).map(S.segmento)
    return oof


def sigma_desde_oof(oof: pd.DataFrame) -> TablaSigma:
    partes = []
    for m in MOTORES:
        e = oof[["ciudad", "tipo", "segmento"]].copy()
        e["motor"] = m
        e["e"] = oof[f"ln_{m}"] - oof["y"]
        partes.append(e.dropna(subset=["e"]))
    return TablaSigma.desde_errores(pd.concat(partes, ignore_index=True))


def ensamblar_oof(oof: pd.DataFrame, sigma: TablaSigma, delta: TablaDelta,
                  conformal: ConformalMondrian | None, aplicar_delta: bool) -> pd.DataFrame:
    """Ensambla los OOF fila por fila con la misma función que producción."""
    out = []
    for _, r in oof.iterrows():
        m2 = r["m2_base"]
        valores = {m: (math.exp(r[f"ln_{m}"]) * m2 if np.isfinite(r[f"ln_{m}"]) else None) for m in MOTORES}
        ref = valores["B"] or valores["A"] or valores["C"]
        seg = S.segmento(ref or 0)
        sig = {m: sigma.sigma(m, r["ciudad"], r["tipo"], seg) for m in MOTORES}
        if aplicar_delta:
            d, n = delta.delta(r["municipio"], seg)
            d = min(S.DELTA_MAX, d + r["extra_dias"])
        else:
            d, n = 0.0, 0
        cq = conformal.ajuste(r["ciudad"], seg) if conformal else 0.0
        e = ensamblar(valores, sig, {0.1: r["q10"], 0.5: r["q50"], 0.9: r["q90"]}, m2, cq, d, n, valores["C"])
        out.append({"id": r["id"], "ens_valor": e.valor, "ens_valor_calc": e.valor_calculado, "ens_escala": e.escala,
                    "ens_bajo_calc": e.rango_calculado[0] if e.rango_calculado else np.nan,
                    "ens_alto_calc": e.rango_calculado[1] if e.rango_calculado else np.nan, "ens_bajo": e.rango[0] if e.rango else np.nan,
                    "ens_alto": e.rango[1] if e.rango else np.nan, "emitido": e.emitido,
                    "confianza": e.confianza, "valor_crudo": math.exp(sum(
                        e.pesos[k] * math.log(valores[k]) for k in e.pesos)) if e.pesos else np.nan,
                    "segmento_est": seg})
    return oof.merge(pd.DataFrame(out), on="id", how="left")


def calibrar_conformal(oof_ens: pd.DataFrame, cierres_eval: pd.DataFrame | None) -> ConformalMondrian:
    """Calibra el multiplicador del rango sobre el ensamble. Con ≥ 30 cierres
    se usa el precio de cierre (lo que importa); si no, el precio de oferta."""
    cm = ConformalMondrian()
    if cierres_eval is not None and len(cierres_eval) >= 30:
        d = cierres_eval[cierres_eval["ens_valor_calc"].notna()]
        ln_v, real = np.log(d["ens_valor_calc"]), np.log(d["real_aj"])
    else:
        d = oof_ens[oof_ens["valor_crudo"].notna()]
        ln_v, real = np.log(d["valor_crudo"]), np.log(d["precio_aj"])
    return cm.ajustar(real, ln_v, d["ens_escala"], d["ciudad"], d["segmento"])


def cierres_ajustados(cierres: pd.DataFrame, base: pd.DataFrame, indice: IndicePrecios, fecha_valuacion) -> pd.DataFrame:
    if cierres is None or cierres.empty:
        return pd.DataFrame()
    c = cierres.copy()
    zona = c["municipio"].fillna("")
    c["real_aj"] = c["precio_cierre"] * indice.factores(zona.tolist(), pd.to_datetime(c["fecha_cierre"]).tolist(),
                                                        fecha_valuacion)
    return c


def entrenar(listings: pd.DataFrame, cierres: pd.DataFrame | None, indice_rows: list[dict], fecha_valuacion,
             datos: str = "reales", contexto_tablas: dict | None = None, rounds: int = S.B_ROUNDS,
             con_validacion: bool = True) -> tuple[ModeloAVM, dict]:
    fv = pd.Timestamp(fecha_valuacion)
    indice = IndicePrecios(indice_rows)
    ctx_tablas = contexto_tablas or {}
    ctx0 = Contexto(ctx_tablas.get("ageb"), ctx_tablas.get("poi"))
    base, info = preparar_base(listings, indice, fv, ctx0)
    contexto = Contexto(ctx_tablas.get("ageb"), ctx_tablas.get("poi"), referencia=base)
    delta = TablaDelta.desde_cierres(cierres if cierres is not None else pd.DataFrame())
    sigma, conformal, oof = TablaSigma(), ConformalMondrian(), None
    if con_validacion:
        oof = predecir_oof(base, rounds)
        sigma = sigma_desde_oof(oof)
        oof_ens = ensamblar_oof(oof, sigma, delta, None, aplicar_delta=False)
        c_eval = evaluar_cierres_oof(oof, cierres, base, indice, fv, sigma)
        conformal = calibrar_conformal(oof_ens, c_eval)
    fz, mb, tr = _ajustar_motores(base, rounds)
    ln_m2_tipico = tr.groupby("tipo")["ln_m2"].mean().to_dict()
    version = f"v2-{datetime.now(timezone.utc):%Y%m%d-%H%M}-{datos[:4]}"
    modelo = ModeloAVM(version, fv, datos, fz, mb, tr, indice, contexto, sigma, delta, conformal, ln_m2_tipico,
                       info | {"codigo": VERSION_CODIGO, "entrenado_en": datetime.now(timezone.utc).isoformat()})
    return modelo, {"oof": oof, "info": info}


def evaluar_cierres_oof(oof: pd.DataFrame, cierres: pd.DataFrame | None, base: pd.DataFrame,
                        indice: IndicePrecios, fv, sigma: TablaSigma,
                        cross_conformal: bool = False) -> pd.DataFrame | None:
    """Une cierres con la estimación OOF de su anuncio. δ se calcula con los
    cierres de OTROS folds (el cierre evaluado nunca entra en su propio δ)."""
    if cierres is None or cierres.empty or oof is None or "listing_id" not in cierres:
        return None
    ligados = cierres.dropna(subset=["listing_id"])
    if ligados.empty:          # cierres capturados a mano: se miden aparte
        return None
    c = cierres_ajustados(ligados, base, indice, fv)
    c = c[["listing_id", "real_aj", "precio_oferta_inicial", "precio_cierre"]].copy()
    c["listing_id"] = c["listing_id"].astype(int)
    c = c.merge(oof, left_on="listing_id", right_on="id", how="inner")
    if c.empty:
        return None
    deltas = {k: TablaDelta.desde_cierres(c[c["fold"] != k]) for k in c["fold"].unique()}
    out = pd.concat([ensamblar_oof(g, sigma, deltas[k], None, aplicar_delta=True)
                     for k, g in c.groupby("fold")], ignore_index=True)
    if cross_conformal:
        # Segunda pasada: el rango (y por lo tanto la confianza y si se emite)
        # de cada fold se calibra solo con los cierres de los otros folds.
        partes = []
        for k, g in c.groupby("fold"):
            otros = out[out["fold"] != k]
            cm = calibrar_conformal(otros, otros) if len(otros) >= 30 else ConformalMondrian()
            partes.append(ensamblar_oof(g, sigma, deltas[k], cm, aplicar_delta=True))
        out = pd.concat(partes, ignore_index=True)
    return out
