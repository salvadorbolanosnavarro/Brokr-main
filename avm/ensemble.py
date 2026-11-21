"""Ensamble, negociación y confianza.

- Pesos por inverso de varianza: α_j = (1/σ_j²) / Σ_k (1/σ_k²), con σ_j el error
  en log del motor j en validación para ciudad × tipo × segmento (con respaldo
  a ciudad × tipo, tipo y global). Motores que no calculan se excluyen.
- ln V = Σ α_j ln V_j + ln(1 − δ).
- δ (oferta → cierre) con encogimiento bayesiano por municipio × segmento:
  δ = (n·δ_obs + κ·δ0) / (n + κ), δ0 = 0.06, κ = 20. Más un extra si los
  comparables llevan mucho tiempo publicados (sobreprecio).
- Rango: q10/q90 del Motor B calibrados con conformal Mondrian por ciudad ×
  segmento para cobertura real del 80 %.
- Confianza por ancho relativo (q90 − q10)/q50.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import settings as S

NIVELES = ["Alta", "Media", "Baja", "Sin valor"]


# ── Pesos ───────────────────────────────────────────────────────────────────
class TablaSigma:
    """σ por motor y celda (ciudad, tipo, segmento) con respaldos."""

    def __init__(self, filas: list[dict] | None = None):
        self.filas = filas or []
        self._idx = {}
        for f in self.filas:
            self._idx[(f["motor"], f.get("ciudad"), f.get("tipo"), f.get("segmento"))] = (f["sigma"], f.get("n", 0))

    @classmethod
    def desde_errores(cls, err: pd.DataFrame, n_min: int = 15) -> "TablaSigma":
        """err: columnas motor, ciudad, tipo, segmento, e (= ln est − ln real)."""
        filas = []
        def robusta(e):
            e = np.asarray(e, float)
            e = e[np.isfinite(e)]
            # σ robusta (MAD·1.4826) para que un par de casos raros no la inflen.
            return float(np.median(np.abs(e - np.median(e))) * 1.4826) if len(e) else np.nan
        niveles = [["motor", "ciudad", "tipo", "segmento"], ["motor", "ciudad", "tipo"], ["motor", "tipo"], ["motor"]]
        for cols in niveles:
            for clave, g in err.groupby(cols):
                if len(g) < n_min:
                    continue
                clave = clave if isinstance(clave, tuple) else (clave,)
                d = dict(zip(cols, clave))
                filas.append({"motor": d["motor"], "ciudad": d.get("ciudad"), "tipo": d.get("tipo"),
                              "segmento": d.get("segmento"), "sigma": max(robusta(g["e"]), 0.02), "n": int(len(g))})
        return cls(filas)

    def sigma(self, motor: str, ciudad: str, tipo: str, segmento: str) -> float:
        for clave in ((motor, ciudad, tipo, segmento), (motor, ciudad, tipo, None),
                      (motor, None, tipo, None), (motor, None, None, None)):
            if clave in self._idx:
                return float(self._idx[clave][0])
        return S.SIGMA_DEFAULT[motor]


def pesos_inverso_varianza(sigmas: dict[str, float]) -> dict[str, float]:
    inv = {k: 1.0 / (s * s) for k, s in sigmas.items() if s and s > 0 and math.isfinite(s)}
    tot = sum(inv.values())
    return {k: v / tot for k, v in inv.items()} if tot else {}


# ── Negociación ─────────────────────────────────────────────────────────────
class TablaDelta:
    def __init__(self, filas: list[dict] | None = None):
        self.filas = filas or []
        self._idx = {(f["municipio"], f["segmento"]): f for f in self.filas}

    @classmethod
    def desde_cierres(cls, cierres: pd.DataFrame, delta0: float = S.DELTA0, kappa: float = S.KAPPA) -> "TablaDelta":
        filas = []
        if cierres is None or cierres.empty:
            return cls([])
        c = cierres.dropna(subset=["precio_oferta_inicial", "precio_cierre"]).copy()
        c = c[(c["precio_oferta_inicial"] > 0) & (c["precio_cierre"] > 0)]
        c["delta"] = (1 - c["precio_cierre"] / c["precio_oferta_inicial"]).clip(-0.2, 0.4)
        c["segmento"] = c["precio_cierre"].map(S.segmento)
        for (mun, seg), g in c.groupby(["municipio", "segmento"]):
            n = len(g)
            d_obs = float(g["delta"].mean())
            d = (n * d_obs + kappa * delta0) / (n + kappa)
            filas.append({"municipio": mun, "segmento": seg, "n": n, "delta_obs": round(d_obs, 4),
                          "delta": round(d, 4)})
        return cls(filas)

    def delta(self, municipio: str, segmento: str) -> tuple[float, int]:
        f = self._idx.get((municipio, segmento))
        if not f:
            return S.DELTA0, 0
        return float(f["delta"]), int(f["n"])


def delta_extra_por_dias(comparables: list[dict]) -> float:
    """Proporción (ponderada) de comparables publicados > 180 días × 3 pts."""
    if not comparables:
        return 0.0
    w = np.array([c.get("peso", 1.0) for c in comparables], float)
    viejo = np.array([1.0 if c.get("dias_publicado", 0) > S.A_DIAS_SOBREPRECIO else 0.0 for c in comparables])
    if w.sum() <= 0:
        return 0.0
    return float(S.DELTA_EXTRA_SOBREPRECIO * np.sum(w * viejo) / w.sum())


# ── Conformal Mondrian ──────────────────────────────────────────────────────
class ConformalMondrian:
    """Conformalized Quantile Regression (Romano et al. 2019) por grupos.
    Puntaje E_i = max(q10_i − y_i, y_i − q90_i); el ajuste Q es el cuantil
    ⌈(n+1)(1−α)⌉/n de E en el grupo. Intervalo = [q10 − Q, q90 + Q]."""

    def __init__(self, alpha: float = 1 - S.COBERTURA_OBJETIVO, n_min: int = S.CONFORMAL_MIN_GRUPO):
        self.alpha, self.n_min = alpha, n_min
        self.q: dict = {}

    def _cuantil(self, e: np.ndarray) -> float:
        n = len(e)
        nivel = min(1.0, math.ceil((n + 1) * (1 - self.alpha)) / n)
        return float(np.quantile(e, nivel, method="higher"))

    def ajustar(self, y, q10, q90, ciudad, segmento) -> "ConformalMondrian":
        df = pd.DataFrame({"e": np.maximum(np.asarray(q10) - np.asarray(y), np.asarray(y) - np.asarray(q90)),
                           "ciudad": list(ciudad), "segmento": list(segmento)})
        df = df[np.isfinite(df["e"])]
        self.q = {("_global", "_global"): self._cuantil(df["e"].to_numpy())} if len(df) else {}
        for c, g in df.groupby("ciudad"):
            if len(g) >= self.n_min:
                self.q[(c, "_global")] = self._cuantil(g["e"].to_numpy())
        for (c, s), g in df.groupby(["ciudad", "segmento"]):
            if len(g) >= self.n_min:
                self.q[(c, s)] = self._cuantil(g["e"].to_numpy())
        return self

    def ajuste(self, ciudad: str, segmento: str) -> float:
        for clave in ((ciudad, segmento), (ciudad, "_global"), ("_global", "_global")):
            if clave in self.q:
                return self.q[clave]
        return 0.0

    def to_dict(self) -> dict:
        return {"alpha": self.alpha, "q": {f"{a}|{b}": v for (a, b), v in self.q.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "ConformalMondrian":
        obj = cls(alpha=d.get("alpha", 0.2))
        obj.q = {tuple(k.split("|", 1)): v for k, v in d.get("q", {}).items()}
        return obj


# ── Confianza ───────────────────────────────────────────────────────────────
def nivel_confianza(ancho_relativo: float) -> str:
    for corte, nombre in S.CONFIANZA_CORTES:
        if ancho_relativo < corte:
            return nombre
    return "Sin valor"


def bajar_nivel(nivel: str) -> str:
    """Alta→Media, Media→Baja. Baja se queda en Baja (con advertencia):
    'bajar un nivel' no debe convertir una estimación emitible en no emitible."""
    if nivel in ("Alta", "Media"):
        return NIVELES[NIVELES.index(nivel) + 1]
    return nivel


@dataclass
class ResultadoEnsamble:
    emitido: bool
    valor: float | None
    rango: tuple[float, float] | None
    confianza: str
    ancho_relativo: float | None
    pesos: dict
    delta: float
    delta_n: int
    valores_motor: dict
    advertencias: list[str] = field(default_factory=list)
    valor_calculado: float | None = None     # aunque no se emita (para calibrar y auditar)
    rango_calculado: tuple[float, float] | None = None


def ensamblar(valores: dict[str, float | None], sigmas: dict[str, float], q_b: dict | None, m2: float,
              conformal_q: float, delta: float, delta_n: int, valor_c: float | None) -> ResultadoEnsamble:
    """valores: valor total por motor (oferta, a fecha de valuación) o None.
    q_b: cuantiles de ln(precio/m2) del Motor B {0.1, 0.5, 0.9}."""
    disponibles = {k: v for k, v in valores.items() if v and v > 0}
    adv: list[str] = []
    if not disponibles:
        return ResultadoEnsamble(False, None, None, "Sin valor", None, {}, delta, delta_n, valores,
                                 ["Ningún motor pudo calcular con los datos disponibles."])
    pesos = pesos_inverso_varianza({k: sigmas[k] for k in disponibles})
    ln_v = sum(pesos[k] * math.log(disponibles[k]) for k in pesos) + math.log(1 - delta)
    valor = math.exp(ln_v)

    rango, ancho = None, None
    if q_b and all(q in q_b for q in (0.1, 0.5, 0.9)):
        lo = q_b[0.1] - conformal_q
        hi = q_b[0.9] + conformal_q
        mid = q_b[0.5]
        ancho = (math.exp(hi) - math.exp(lo)) / math.exp(mid)
        # El rango se centra en el valor final conservando la forma calibrada.
        rango = (valor * math.exp(lo - mid), valor * math.exp(hi - mid))
    else:
        # Sin Motor B no hay rango calibrado: se usa la dispersión de σ.
        s = min(sigmas[k] for k in disponibles)
        z = 1.2816
        rango = (valor * math.exp(-z * s), valor * math.exp(z * s))
        ancho = math.exp(z * s) - math.exp(-z * s)
        adv.append("Rango aproximado: el modelo estadístico no pudo calcular para este inmueble.")

    nivel = nivel_confianza(ancho)
    if valor_c and valor_c > 0:
        v_sin_c = valor / (1 - delta)
        if abs(valor_c / v_sin_c - 1) > S.C_DIFERENCIA_MAX:
            nuevo = bajar_nivel(nivel)
            if nuevo != nivel or nivel == "Baja":
                adv.append("El enfoque físico (terreno + construcción) difiere más de 30 % del valor de mercado.")
            nivel = nuevo
    emitido = nivel != "Sin valor"
    if not emitido:
        adv.append("El rango es demasiado amplio para emitir un valor: se recomienda visita al inmueble.")
    return ResultadoEnsamble(emitido, valor if emitido else None, rango if emitido else None, nivel, ancho,
                             pesos, delta, delta_n, valores, adv, valor_calculado=valor,
                             rango_calculado=rango)
