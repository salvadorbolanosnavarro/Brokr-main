# AVM Broquer v2 — Reporte de validación

Generado: 2026-11-23 22:25 UTC · fecha de valuación 2026-11-01 · datos: **sinteticos**

> ⚠️ **Estos resultados son con datos SINTÉTICOS.** Todavía no hay anuncios ni cierres reales en `avm_listings` / `avm_closings`. El mercado sintético (`avm/synthetic.py`) tiene una verdad conocida y sirve para comprobar que el pipeline completo funciona (la geografía sí es real: zonas y nivel socioeconómico del Censo 2020) y que la validación no hace trampa. **No dicen nada de la precisión real en Morelia o Guadalajara.** Cuando haya datos, este reporte se regenera solo cada mes con el reentrenamiento.

Reglas: nada de split aleatorio. Hold-out temporal (últimos 3 meses) + bloques espaciales H3. Cada cierre se estima con un modelo que no vio su zona (bloque H3-8) y cuyo δ (oferta→cierre) no incluye ese cierre; el rango de cada fold se calibra con los otros folds (conformal cruzado).

## 1. Contra cierres reales (lo que importa)

Cobertura del rango sobre **todas** las estimaciones calculadas (emitidas o no): **80.4 %**. La tabla mide solo las emitidas.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 9.6 | ≤ 12 | ✅ |
| PE10 % | 52.9 | ≥ 45 | ✅ |
| PE20 % | 85.2 | ≥ 75 | ✅ |
| Sesgo | 0.964 | 0.97–1.03 | ❌ |
| COD | 11.5 | ≤ 15 | ✅ |
| PRD | 1.036 | 0.98–1.03 | ❌ |
| Cobertura 80 % | 77.4 | 76–84 | ✅ |
| Hit rate % | 54.4 | — | — |

n = 285 · con valor emitido = 155

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 138 | 96 | 10.0 | 51.0 | 81.2 | 0.990 | 12.1 | 1.046 | 77.1 |
| Morelia | 147 | 59 | 8.9 | 55.9 | 91.5 | 0.948 | 9.6 | 1.018 | 78.0 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 194 | 112 | 8.8 | 57.1 | 89.3 | 0.960 | 10.8 | 1.028 | 81.2 |
| depto | 70 | 28 | 12.7 | 46.4 | 60.7 | 0.999 | 14.7 | 1.080 | 60.7 |
| local | 21 | 15 | 10.8 | 33.3 | 100.0 | 0.911 | 9.3 | 1.033 | 80.0 |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 117 | 57 | 8.9 | 52.6 | 89.5 | 0.948 | 10.6 | 1.004 | 78.9 |
| residencial_plus | 17 | 10 | 17.0 | 30.0 | 70.0 | 0.830 | 11.7 | 1.015 | 40.0 |
| social_medio | 151 | 88 | 9.3 | 55.7 | 84.1 | 0.996 | 11.1 | 1.012 | 80.7 |


**Niveles de confianza**

| Nivel | Casos | % |
|---|---|---|
| Baja | 154 | 54 |
| Sin valor | 130 | 46 |
| Media | 1 | 0 |


## 2. Hold-out temporal (últimos 3 meses) contra precio de oferta

Entrenado con 3940 inmuebles anteriores a 2026-08-01; valuados 522 publicados después. Se compara el valor **antes** del descuento de negociación contra el precio de oferta. La cobertura aquí es contra oferta (más ruidosa); la meta de cobertura aplica a cierres.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 10.5 | ≤ 12 | ✅ |
| PE10 % | 48.0 | ≥ 45 | ✅ |
| PE20 % | 79.7 | ≥ 75 | ✅ |
| Sesgo | 0.941 | 0.97–1.03 | ❌ |
| COD | 21.1 | ≤ 15 | ❌ |
| PRD | 1.126 | 0.98–1.03 | ❌ |
| Cobertura 80 % | 67.8 | 76–84 | ❌ |
| Hit rate % | 43.5 | — | — |

n = 522 · con valor emitido = 227

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 233 | 170 | 10.4 | 48.2 | 78.8 | 0.963 | 24.4 | 1.146 | 66.5 |
| Morelia | 289 | 57 | 10.7 | 47.4 | 82.5 | 0.898 | 8.7 | 1.020 | 71.9 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 311 | 137 | 10.7 | 46.7 | 80.3 | 0.932 | 12.3 | 1.047 | 68.6 |
| depto | 131 | 54 | 10.5 | 48.1 | 79.6 | 0.968 | 13.7 | 1.046 | 70.4 |
| local | 28 | 11 | 8.0 | 72.7 | 100.0 | 0.981 | 6.6 | 1.020 | 100.0 |
| terreno | 52 | 25 | 13.6 | 44.0 | 68.0 | 0.957 | 88.9 | 1.667 | 44.0 |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 221 | 113 | 9.8 | 50.4 | 85.0 | 0.910 | 9.2 | 1.009 | 75.2 |
| residencial_plus | 36 | 15 | 15.1 | 40.0 | 73.3 | 0.849 | 8.2 | 1.009 | 53.3 |
| social_medio | 265 | 99 | 10.8 | 46.5 | 74.7 | 1.042 | 30.7 | 1.155 | 61.6 |


**Por motor (hold-out temporal)**

| Motor | n con valor | MdAPE | PE10 | PE20 | Sesgo | COD |
|---|---|---|---|---|---|---|
| A · Comparables | 466 | 17.3 | 28.8 | 57.3 | 0.977 | 21.5 |
| B · Modelo estadístico | 522 | 11.6 | 45.4 | 75.1 | 0.965 | 17.2 |
| C · Físico | 376 | 12.8 | 41.0 | 69.9 | 0.944 | 20.3 |


## 3. Hold-out temporal contra cierres de esos 3 meses



| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 9.6 | ≤ 12 | ✅ |
| PE10 % | 51.4 | ≥ 45 | ✅ |
| PE20 % | 91.4 | ≥ 75 | ✅ |
| Sesgo | 0.963 | 0.97–1.03 | ❌ |
| COD | 11.4 | ≤ 15 | ✅ |
| PRD | 1.040 | 0.98–1.03 | ❌ |
| Cobertura 80 % | 85.7 | 76–84 | ❌ |
| Hit rate % | 39.8 | — | — |

n = 88 · con valor emitido = 35

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 42 | 27 | 10.4 | 48.1 | 88.9 | 1.023 | 12.0 | 1.048 | 85.2 |
| Morelia | 46 | 8 | 4.4 | 62.5 | 100.0 | 0.960 | 6.4 | 1.004 | 87.5 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 61 | 26 | 9.6 | 53.8 | 96.2 | 0.956 | 10.1 | 1.027 | 88.5 |
| depto | 21 | 8 | 13.2 | 37.5 | 75.0 | 1.055 | 13.1 | 1.075 | 75.0 |
| local | 6 | 1 | 2.1 | 100.0 | 100.0 | 1.021 | 0.0 | 1.000 | 100.0 |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 34 | 16 | 10.0 | 50.0 | 100.0 | 0.907 | 6.6 | 1.001 | 93.8 |
| residencial_plus | 6 | 1 | 9.0 | 100.0 | 100.0 | 0.910 | 0.0 | 1.000 | 100.0 |
| social_medio | 48 | 18 | 10.2 | 50.0 | 83.3 | 1.083 | 9.5 | 1.006 | 77.8 |


## 4. Prueba de estrés: bloques H3-6 (valuar una zona sin ningún dato)

Cada bloque de ~36 km² se valúa sin haber visto nada de él. Es el peor caso; sirve para saber cuánto empeora el modelo en una colonia nueva.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 12.1 | ≤ 12 | ❌ |
| PE10 % | 42.5 | ≥ 45 | ❌ |
| PE20 % | 74.8 | ≥ 75 | ❌ |
| Sesgo | 0.990 | 0.97–1.03 | ✅ |
| COD | 15.3 | ≤ 15 | ❌ |
| PRD | 1.058 | 0.98–1.03 | ❌ |
| Cobertura 80 % | — | 76–84 | — |
| Hit rate % | 100.0 | — | — |

n = 4505 · con valor emitido = 4505

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 2182 | 2182 | 12.6 | 41.2 | 74.2 | 0.965 | 16.2 | 1.060 | — |
| Morelia | 2323 | 2323 | 11.4 | 43.8 | 75.4 | 1.012 | 14.3 | 1.053 | — |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 2629 | 2629 | 12.1 | 42.1 | 75.4 | 0.991 | 14.4 | 1.045 | — |
| depto | 1079 | 1079 | 12.7 | 41.4 | 72.3 | 0.978 | 16.0 | 1.064 | — |
| local | 259 | 259 | 11.1 | 46.7 | 76.4 | 0.969 | 17.9 | 1.127 | — |
| terreno | 538 | 538 | 11.4 | 45.0 | 76.6 | 1.013 | 17.2 | 1.091 | — |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 1735 | 1735 | 10.9 | 46.6 | 80.5 | 0.957 | 12.6 | 1.007 | — |
| residencial_plus | 265 | 265 | 17.3 | 25.3 | 59.6 | 0.839 | 13.3 | 1.026 | — |
| social_medio | 2505 | 2505 | 12.3 | 41.5 | 72.5 | 1.036 | 15.9 | 1.029 | — |


**Por motor (bloques H3-6)**

| Motor | n con valor | MdAPE | PE10 | PE20 | Sesgo | COD |
|---|---|---|---|---|---|---|
| A · Comparables | 1816 | 18.9 | 26.8 | 51.9 | 0.984 | 24.4 |
| B · Modelo estadístico | 4505 | 12.2 | 42.1 | 74.3 | 0.991 | 15.4 |
| C · Físico | 1255 | 13.0 | 38.4 | 69.4 | 1.022 | 21.2 |


## 5. Golden set (avalúos reales de Morelia)


_`avm/eval/golden_set.csv` está vacío: los 7 avalúos de Morelia no están en el repositorio. En cuanto se capturen (una fila por avalúo), esta sección compara v2 contra el AVM actual._


## 6. Comparación contra el AVM actual (`/api/avm-websearch`)

El AVM actual calcula el valor con el LLM a partir de 8 páginas leídas en el momento: no es repetible (la misma consulta puede dar otro número) ni guarda sus estimaciones, así que no se puede validar en lote. La única comparación justa es el golden set (sección 5): capturar ahí el valor que dio el AVM actual para cada avalúo (`valor_motor_actual`).
