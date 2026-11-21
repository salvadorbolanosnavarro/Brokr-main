"""Mercado sintético con verdad conocida.

Sirve para dos cosas y para nada más:
1. Pruebas automáticas (cada motor debe recuperar valores que sabemos).
2. Ejercitar el pipeline completo (limpieza → dedupe → entrenamiento →
   validación → reporte) mientras no haya datos reales en avm_listings.

El valor "real" de cada inmueble se genera con el enfoque físico más una prima
de ubicación, así que los tres motores tienen algo que aprender. Los precios de
oferta llevan sobreprecio y ruido; los cierres, solo ruido pequeño. NUNCA se usa
para valuar a un cliente: cualquier modelo entrenado aquí se marca
datos="sinteticos" y la API lo muestra.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import geo
from .engines.motor_c_fisico import depreciacion_ross_heidecke, coef_heidecke
from .settings import tabla

CIUDADES_SINT = {
    # nombre: (lat, lon, precio_terreno_m2, precio_depto_m2, zona_indice)
    "Morelia": (19.7027, -101.1923, 5200.0, 24000.0, "Morelia"),
    "Guadalajara": (20.6767, -103.3475, 8200.0, 34000.0, "Guadalajara"),
}
FECHA_FIN = pd.Timestamp("2026-11-01")
MESES = 24
CRECIMIENTO_TRIMESTRAL = 0.018


@dataclass
class MercadoSintetico:
    listings: pd.DataFrame
    closings: pd.DataFrame
    indice: list[dict]
    verdad: pd.Series          # valor de mercado real a FECHA_FIN, por id


def _campo(rng, lat0, lon0, n_bumps=9):
    """Campo espacial suave (suma de gaussianas) en log, rango aprox ±0.6."""
    centros = np.column_stack([lat0 + rng.normal(0, 0.035, n_bumps), lon0 + rng.normal(0, 0.035, n_bumps)])
    amp = rng.normal(0, 0.35, n_bumps)
    esc = rng.uniform(0.008, 0.025, n_bumps)

    def f(lat, lon):
        lat = np.asarray(lat, float)
        lon = np.asarray(lon, float)
        out = np.zeros_like(lat)
        for (cl, cn), a, s in zip(centros, amp, esc):
            out += a * np.exp(-(((lat - cl) ** 2 + (lon - cn) ** 2) / (2 * s * s)))
        return np.clip(out, -0.7, 0.7)

    return f


def _indice_rows(rng) -> list[dict]:
    rows = []
    for nombre, (_, _, _, _, zona) in CIUDADES_SINT.items():
        valor = 100.0
        trimestres = pd.period_range(FECHA_FIN - pd.DateOffset(months=MESES + 3), FECHA_FIN, freq="Q")
        for t in trimestres:
            rows.append({"zona": zona, "trimestre": f"{t.year}T{t.quarter}", "valor": round(valor, 4), "fuente": "sintetico"})
            valor *= 1 + CRECIMIENTO_TRIMESTRAL + rng.normal(0, 0.002)
    return rows


def generar(n_por_ciudad: int = 2500, semilla: int = 11, duplicados: float = 0.06,
            outliers: float = 0.015, n_cierres_por_ciudad: int = 160) -> MercadoSintetico:
    rng = np.random.default_rng(semilla)
    indice = _indice_rows(rng)
    from .indice import IndicePrecios
    idx = IndicePrecios(indice)
    vida = tabla("vida_util")
    vrn = tabla("costos_reposicion")

    frames = []
    for nombre, (lat0, lon0, p_terr, p_depto, zona) in CIUDADES_SINT.items():
        f = _campo(rng, lat0, lon0)
        n = n_por_ciudad
        lat = lat0 + rng.normal(0, 0.03, n)
        lon = lon0 + rng.normal(0, 0.035, n)
        campo = f(lat, lon)
        tipo = rng.choice(["casa", "depto", "terreno", "local"], n, p=[0.58, 0.25, 0.12, 0.05])
        nse = np.clip(4 + 3.2 * campo + rng.normal(0, 0.5, n), 1, 7)
        calidad_idx = np.clip(np.round((nse - 1) / 6 * 3 + rng.normal(0, 0.4, n)), 0, 3).astype(int)
        calidad = np.array(["economica", "media", "residencial", "residencial_plus"])[calidad_idx]

        m2c = np.where(tipo == "depto", rng.lognormal(np.log(85), 0.3, n), rng.lognormal(np.log(150), 0.4, n))
        m2c = np.where(tipo == "local", rng.lognormal(np.log(90), 0.5, n), m2c)
        m2t = np.where(tipo == "terreno", rng.lognormal(np.log(220), 0.5, n), m2c * rng.uniform(0.6, 1.4, n))
        m2t = np.where(tipo == "depto", np.nan, m2t)
        m2c = np.where(tipo == "terreno", np.nan, np.round(m2c, 1))
        m2t = np.round(m2t, 1)
        edad = np.where(tipo == "terreno", np.nan, np.round(rng.gamma(2.0, 8.0, n)).clip(0, 60))
        conservacion = np.where(tipo == "terreno", np.nan,
                                np.clip(np.round(5 - edad / 15 + rng.normal(0, 0.8, n)), 1, 5))
        recamaras = np.where(np.isin(tipo, ["casa", "depto"]), np.clip(np.round(np.nan_to_num(m2c) / 45 + rng.normal(0, 0.6, n)), 1, 6), np.nan)
        banos = np.where(np.isin(tipo, ["casa", "depto"]), np.clip(np.round(recamaras * 0.7 + rng.normal(0, 0.4, n)), 1, 5), np.nan)
        alberca = (rng.random(n) < 0.03 + 0.04 * (nse > 5.5)).astype(float)
        seguridad = (rng.random(n) < 0.25 + 0.3 * (nse > 4.5)).astype(float)
        jardin = ((tipo == "casa") & (rng.random(n) < 0.55)).astype(float)
        esquina = (rng.random(n) < 0.12).astype(float)

        # ── valor de mercado real a FECHA_FIN ──
        precio_terr = p_terr * np.exp(1.0 * campo)
        valor = np.zeros(n)
        for i in range(n):
            t = tipo[i]
            if t == "terreno":
                valor[i] = m2t[i] * precio_terr[i]
                continue
            q = calidad[i]
            if t == "depto":
                vu = vida["depto"][q]
                dep = depreciacion_ross_heidecke(edad[i], vu, coef_heidecke(conservacion[i]))
                calidad_mult = {"economica": 0.8, "media": 1.0, "residencial": 1.25, "residencial_plus": 1.5}[q]
                valor[i] = m2c[i] * p_depto * calidad_mult * np.exp(0.8 * campo[i]) * (1 - 0.7 * dep)
            else:
                tt = "local" if t == "local" else "casa"
                vu = vida[tt][q]
                dep = depreciacion_ross_heidecke(edad[i], vu, coef_heidecke(conservacion[i]))
                construccion = m2c[i] * vrn[tt][q] * (1 - dep)
                valor[i] = (m2t[i] * precio_terr[i] + construccion) * np.exp(0.15 * campo[i])
        valor *= np.exp(0.06 * alberca + 0.04 * seguridad + 0.02 * jardin + 0.04 * esquina)
        valor *= np.exp(rng.normal(0, 0.06, n))        # idiosincrasia no observable

        # ── anuncio: fecha, sobreprecio, ruido ──
        dias_atras = rng.integers(0, MESES * 30, n)
        fecha_alta = FECHA_FIN - pd.to_timedelta(dias_atras, unit="D")
        sobreprecio = np.clip(rng.normal(0.07, 0.05, n), -0.05, 0.30)
        f_tiempo = np.array([idx.factor(zona, FECHA_FIN, fa) for fa in fecha_alta])
        precio = valor * f_tiempo * (1 + sobreprecio) * np.exp(rng.normal(0, 0.05, n))
        dias_mercado = np.clip(rng.gamma(2.0, 40.0, n) + 500 * np.clip(sobreprecio - 0.08, 0, None), 5, 700).round()
        fecha_baja = fecha_alta + pd.to_timedelta(dias_mercado, unit="D")
        fecha_baja = pd.Series(fecha_baja).where(fecha_baja < FECHA_FIN, pd.NaT)

        frames.append(pd.DataFrame({
            "ciudad": nombre, "municipio": nombre, "estado": "Michoacán" if nombre == "Morelia" else "Jalisco",
            "zona_indice": zona, "fuente": rng.choice(["inmuebles24", "vivanuncios"], n),
            "tipo": tipo, "operacion": "venta", "precio": np.round(precio, -3), "moneda": "MXN",
            "m2_construidos": m2c, "m2_terreno": m2t, "recamaras": recamaras, "banos": banos,
            "medios_banos": np.where(tipo == "casa", rng.integers(0, 2, n), 0).astype(float),
            "estacionamientos": np.where(tipo == "terreno", np.nan, rng.integers(0, 3, n)).astype(float),
            "edad_anios": edad, "conservacion": conservacion, "calidad_construccion": calidad,
            "alberca": alberca, "seguridad_24h": seguridad, "jardin": jardin, "esquina": esquina,
            "roof_garden": ((tipo == "depto") & (rng.random(n) < 0.2)).astype(float),
            "remodelada": (rng.random(n) < 0.08).astype(float),
            "lat": lat, "lon": lon, "precision_ubicacion": "exacta",
            "fecha_alta": fecha_alta.normalize(), "fecha_baja": fecha_baja,
            "ultimo_visto": [min(fb, FECHA_FIN) if pd.notna(fb) else FECHA_FIN for fb in fecha_baja],
            "nse_score": np.round(nse, 2), "escolaridad_prom": np.round(7 + 1.2 * nse + rng.normal(0, 0.5, n), 2),
            "pct_auto": np.clip(20 + 10 * nse + rng.normal(0, 5, n), 0, 100),
            "pct_internet": np.clip(25 + 10 * nse + rng.normal(0, 5, n), 0, 100),
            "pct_computadora": np.clip(10 + 9 * nse + rng.normal(0, 5, n), 0, 100),
            "densidad_hab_km2": np.clip(rng.lognormal(np.log(7000), 0.5, n), 200, 40000),
            "escuelas": rng.poisson(3 + nse, n), "hospitales": rng.poisson(1, n),
            "supermercados": rng.poisson(0.5 + 0.3 * nse, n), "bancos": rng.poisson(0.3 * nse, n),
            "restaurantes": rng.poisson(2 + 2 * nse, n),
            "dist_avenida_m": rng.gamma(2, 250, n), "dist_parque_m": rng.gamma(2, 400, n),
            "dist_centro_m": geo.haversine_m(lat, lon, lat0, lon0),
            "_valor_real": valor, "_sobreprecio": sobreprecio,
        }))

    df = pd.concat(frames, ignore_index=True)
    df["url"] = [f"https://sintetico.broquer.app/anuncio/{i}" for i in range(len(df))]

    # ── duplicados: el mismo inmueble anunciado por otro asesor ──
    n_dup = int(len(df) * duplicados)
    base = df.sample(n_dup, random_state=semilla)
    dups = base.copy()
    jitter = rng.normal(0, 0.00008, (n_dup, 2))       # ~10 m
    dups["lat"] += jitter[:, 0]
    dups["lon"] += jitter[:, 1]
    dups["precio"] = np.round(dups["precio"] * rng.uniform(0.97, 1.03, n_dup), -3)
    dups["fuente"] = np.where(dups["fuente"] == "inmuebles24", "vivanuncios", "inmuebles24")
    dups["fecha_alta"] = dups["fecha_alta"] + pd.to_timedelta(rng.integers(1, 30, n_dup), unit="D")
    dups["url"] = [f"https://sintetico.broquer.app/anuncio/dup{i}" for i in range(n_dup)]
    dups["_dup_de"] = base["url"].values
    df["_dup_de"] = None
    df = pd.concat([df, dups], ignore_index=True)

    # ── errores de captura: precio con ceros de más/menos, rentas como venta ──
    n_out = int(len(df) * outliers)
    pos = rng.choice(len(df), n_out, replace=False)
    df["_outlier"] = False
    df.loc[pos, "precio"] = df.loc[pos, "precio"] * rng.choice([10.0, 0.1, 0.01], n_out)
    df.loc[pos, "_outlier"] = True

    df.insert(0, "id", np.arange(1, len(df) + 1))
    for res in (7, 8, 9):
        df[f"h3_{res}"] = geo.celdas(df["lat"], df["lon"], res)

    # ── cierres reales: precio de cierre ≈ valor de mercado a su fecha ──
    cierres = []
    vivos = df[(df["_dup_de"].isna()) & (~df["_outlier"]) & (df["tipo"] != "terreno")]
    for nombre in CIUDADES_SINT:
        sub = vivos[vivos["ciudad"] == nombre].sample(n_cierres_por_ciudad, random_state=semilla + len(nombre))
        for _, r in sub.iterrows():
            fecha_cierre = min(r["fecha_alta"] + pd.Timedelta(days=int(rng.integers(30, 200))), FECHA_FIN)
            f_t = idx.factor(r["zona_indice"], FECHA_FIN, fecha_cierre)
            cierres.append({
                "listing_id": int(r["id"]), "tipo": r["tipo"], "ciudad": nombre, "municipio": nombre,
                "precio_oferta_inicial": float(r["precio"]),
                "precio_cierre": float(round(r["_valor_real"] * f_t * np.exp(rng.normal(0, 0.03)), -3)),
                "fecha_cierre": fecha_cierre, "dias_en_mercado": int((fecha_cierre - r["fecha_alta"]).days),
                "fuente": "cierres",
            })
    closings = pd.DataFrame(cierres)
    verdad = df.set_index("id")["_valor_real"]
    return MercadoSintetico(listings=df, closings=closings, indice=indice, verdad=verdad)
