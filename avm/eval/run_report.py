"""Genera avm/eval/REPORTE.md.

    python -m avm.eval.run_report --sintetico      # sin datos reales (prueba del pipeline)
    python -m avm.eval.run_report --supabase       # con avm_listings / avm_closings reales
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .. import settings as S
from .metrics import cumple, metricas
from . import validate as V

REPORTE = Path(__file__).resolve().parent / "REPORTE.md"
ETIQUETAS = {"mdape": "MdAPE %", "pe10": "PE10 %", "pe20": "PE20 %", "sesgo": "Sesgo", "cod": "COD",
             "prd": "PRD", "cobertura": "Cobertura 80 %", "hit_rate": "Hit rate %"}
META_TXT = {"mdape": "≤ 12", "pe10": "≥ 45", "pe20": "≥ 75", "sesgo": "0.97–1.03", "cod": "≤ 15",
            "prd": "0.98–1.03", "cobertura": "76–84", "hit_rate": "—"}


def _fmt(v, clave: str = "") -> str:
    if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
        return "—"
    if isinstance(v, (float, np.floating)):
        return f"{v:.3f}" if clave in ("sesgo", "prd") else f"{v:.1f}"
    return str(v)


def _tabla_metas(m: dict) -> str:
    ok = cumple(m)
    filas = ["| Métrica | Resultado | Meta | ¿Cumple? |", "|---|---|---|---|"]
    for k in ("mdape", "pe10", "pe20", "sesgo", "cod", "prd", "cobertura", "hit_rate"):
        c = ok.get(k)
        filas.append(f"| {ETIQUETAS[k]} | {_fmt(m.get(k), k)} | {META_TXT[k]} | "
                     f"{'—' if c is None else ('✅' if c else '❌')} |")
    return "\n".join(filas) + f"\n\nn = {m.get('n')} · con valor emitido = {m.get('n_emitidos')}\n"


def _tabla_grupos(df: pd.DataFrame, col: str) -> str:
    if df is None or df.empty:
        return "_Sin datos._\n"
    cols = [col, "n", "n_emitidos", "mdape", "pe10", "pe20", "sesgo", "cod", "prd", "cobertura"]
    out = ["| " + " | ".join(["Grupo", "n", "emitidos", "MdAPE", "PE10", "PE20", "Sesgo", "COD", "PRD", "Cobertura"]) + " |",
           "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(_fmt(r.get(c), c) for c in cols) + " |")
    return "\n".join(out) + "\n"


def _seccion(titulo: str, tabla: pd.DataFrame | None, nota: str = "") -> str:
    r = V.resumen(tabla)
    if r is None:
        return f"## {titulo}\n\n_Sin datos para esta sección._\n\n"
    txt = f"## {titulo}\n\n{nota}\n\n{_tabla_metas(r['global'])}\n"
    for g, nombre in (("ciudad", "Por ciudad"), ("tipo", "Por tipo"), ("segmento", "Por rango de precio")):
        txt += f"**{nombre}**\n\n{_tabla_grupos(r[g], g)}\n"
    return txt


def _motores(tabla: pd.DataFrame) -> str:
    pm = V.por_motor(tabla)
    filas = ["| Motor | n con valor | MdAPE | PE10 | PE20 | Sesgo | COD |", "|---|---|---|---|---|---|---|"]
    nombres = {"A": "A · Comparables", "B": "B · Modelo estadístico", "C": "C · Físico"}
    for k, m in pm.items():
        filas.append(f"| {nombres[k]} | {m['n_emitidos']} | {_fmt(m['mdape'])} | {_fmt(m['pe10'])} | "
                     f"{_fmt(m['pe20'])} | {_fmt(m['sesgo'], 'sesgo')} | {_fmt(m['cod'])} |")
    return "\n".join(filas) + "\n"


def escribir(listings, cierres, indice_rows, fv, datos: str, ctx_tablas=None, rounds=S.B_ROUNDS,
             modelo_final=None) -> str:
    h = V.holdout_temporal(listings, cierres, indice_rows, fv, ctx_tablas, rounds)
    cv = V.cv_espacial(listings, indice_rows, fv, ctx_tablas, rounds)
    cc = V.contra_cierres(listings, cierres, indice_rows, fv, ctx_tablas, rounds)
    g = V.golden(modelo_final) if modelo_final is not None else None

    aviso = ""
    if datos == "sinteticos":
        aviso = ("> ⚠️ **Estos resultados son con datos SINTÉTICOS.** Todavía no hay anuncios ni cierres reales en "
                 "`avm_listings` / `avm_closings`. El mercado sintético (`avm/synthetic.py`) tiene una verdad conocida "
                 "y sirve para comprobar que el pipeline completo funciona y que la validación no hace trampa. "
                 "**No dicen nada de la precisión real en Morelia o Guadalajara.** Cuando haya datos, este reporte se "
                 "regenera solo cada mes con el reentrenamiento.\n")
    md = [f"# AVM Broquer v2 — Reporte de validación\n",
          f"Generado: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · fecha de valuación {pd.Timestamp(fv).date()} · "
          f"datos: **{datos}**\n", aviso,
          "Reglas: nada de split aleatorio. Hold-out temporal (últimos 3 meses) + bloques espaciales H3. "
          "Cada cierre se estima con un modelo que no vio su zona (bloque H3-8) y cuyo δ (oferta→cierre) no incluye "
          "ese cierre; el rango de cada fold se calibra con los otros folds (conformal cruzado).\n"]

    if cc is not None:
        cobertura_total = metricas(cc["estimado_calc"], cc["real"], cc["bajo_calc"], cc["alto_calc"])["cobertura"]
        md.append(_seccion("1. Contra cierres reales (lo que importa)", cc,
                           f"Cobertura del rango sobre **todas** las estimaciones calculadas (emitidas o no): "
                           f"**{_fmt(cobertura_total)} %**. La tabla mide solo las emitidas."))
        md.append("**Niveles de confianza**\n\n" + _conf(cc) + "\n")
    else:
        md.append("## 1. Contra cierres reales\n\n_Sin cierres capturados todavía (`POST /avm/v2/cierre`)._\n\n")

    md.append(_seccion("2. Hold-out temporal (últimos 3 meses) contra precio de oferta", h["oferta"],
                       f"Entrenado con {h['n_train']} inmuebles anteriores a {h['corte']}; valuados {h['n_test']} "
                       "publicados después. Se compara el valor **antes** del descuento de negociación contra el precio "
                       "de oferta. La cobertura aquí es contra oferta (más ruidosa); la meta de cobertura aplica a cierres."))
    md.append("**Por motor (hold-out temporal)**\n\n" + _motores(h["oferta"]) + "\n")
    if "cierres" in h:
        md.append(_seccion("3. Hold-out temporal contra cierres de esos 3 meses", h["cierres"]))
    md.append(_seccion("4. Prueba de estrés: bloques H3-6 (valuar una zona sin ningún dato)", cv,
                       "Cada bloque de ~36 km² se valúa sin haber visto nada de él. Es el peor caso; sirve para saber "
                       "cuánto empeora el modelo en una colonia nueva."))
    md.append("**Por motor (bloques H3-6)**\n\n" + _motores(cv) + "\n")

    md.append("## 5. Golden set (avalúos reales de Morelia)\n\n")
    if g is None:
        md.append("_`avm/eval/golden_set.csv` está vacío: los 7 avalúos de Morelia no están en el repositorio. "
                  "En cuanto se capturen (una fila por avalúo), esta sección compara v2 contra el AVM actual._\n\n")
    else:
        m2 = metricas(g["estimado"], g["real"], g["bajo"], g["alto"], g["emitido"])
        txt = _tabla_metas(m2)
        if g["motor_actual"].notna().any():
            ma = metricas(g["motor_actual"], g["real"])
            txt += (f"\nAVM actual en el mismo golden set: MdAPE {_fmt(ma['mdape'])} %, PE10 {_fmt(ma['pe10'])} %, "
                    f"sesgo {_fmt(ma['sesgo'], 'sesgo')}.\n")
        md.append(txt + "\n")
    md.append("## 6. Comparación contra el AVM actual (`/api/avm-websearch`)\n\n"
              "El AVM actual calcula el valor con el LLM a partir de 8 páginas leídas en el momento: no es repetible "
              "(la misma consulta puede dar otro número) ni guarda sus estimaciones, así que no se puede validar "
              "en lote. La única comparación justa es el golden set (sección 5): capturar ahí el valor que dio el AVM "
              "actual para cada avalúo (`valor_motor_actual`).\n")
    texto = "\n".join(md)
    REPORTE.write_text(texto, encoding="utf-8")
    return texto


def _conf(t: pd.DataFrame) -> str:
    if "confianza" not in t:
        return "_—_\n"
    vc = t["confianza"].value_counts()
    return "| Nivel | Casos | % |\n|---|---|---|\n" + "\n".join(
        f"| {k} | {v} | {100 * v / len(t):.0f} |" for k, v in vc.items()) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--supabase", action="store_true")
    ap.add_argument("--rounds", type=int, default=S.B_ROUNDS)
    ap.add_argument("--n", type=int, default=2500)
    a = ap.parse_args()
    if a.supabase:
        from ..etl import repo
        datos = asyncio.run(repo.cargar_todo())
        from .. import pipeline as P
        fv = pd.Timestamp.today().normalize()
        modelo, _ = P.entrenar(datos["listings"], datos["closings"], datos["indice"], fv, "reales",
                               datos["contexto"], a.rounds)
        escribir(datos["listings"], datos["closings"], datos["indice"], fv, "reales", datos["contexto"], a.rounds, modelo)
    else:
        from .. import synthetic, pipeline as P
        m = synthetic.generar(a.n)
        modelo, _ = P.entrenar(m.listings, m.closings, m.indice, synthetic.FECHA_FIN, "sinteticos", rounds=a.rounds)
        escribir(m.listings, m.closings, m.indice, synthetic.FECHA_FIN, "sinteticos", rounds=a.rounds, modelo_final=modelo)
    print(f"Escrito {REPORTE}")


if __name__ == "__main__":
    main()
