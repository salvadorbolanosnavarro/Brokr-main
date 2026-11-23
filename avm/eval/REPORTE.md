# AVM Broquer v2 — Reporte de validación

Generado: 2026-11-21 08:11 UTC · fecha de valuación 2026-11-01 · datos: **sinteticos**

> ⚠️ **Estos resultados son con datos SINTÉTICOS.** Todavía no hay anuncios ni cierres reales en `avm_listings` / `avm_closings`. El mercado sintético (`avm/synthetic.py`) tiene una verdad conocida y sirve para comprobar que el pipeline completo funciona y que la validación no hace trampa. **No dicen nada de la precisión real en Morelia o Guadalajara.** Cuando haya datos, este reporte se regenera solo cada mes con el reentrenamiento.

Reglas: nada de split aleatorio. Hold-out temporal (últimos 3 meses) + bloques espaciales H3. Cada cierre se estima con un modelo que no vio su zona (bloque H3-8) y cuyo δ (oferta→cierre) no incluye ese cierre; el rango de cada fold se calibra con los otros folds (conformal cruzado).

## 1. Contra cierres reales (lo que importa)

Cobertura del rango sobre **todas** las estimaciones calculadas (emitidas o no): **80.8 %**. La tabla mide solo las emitidas.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 7.2 | ≤ 12 | ✅ |
| PE10 % | 60.7 | ≥ 45 | ✅ |
| PE20 % | 90.0 | ≥ 75 | ✅ |
| Sesgo | 0.988 | 0.97–1.03 | ✅ |
| COD | 9.2 | ≤ 15 | ✅ |
| PRD | 1.021 | 0.98–1.03 | ✅ |
| Cobertura 80 % | 76.0 | 76–84 | ✅ |
| Hit rate % | 49.7 | — | — |

n = 302 · con valor emitido = 150

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 153 | 59 | 8.7 | 59.3 | 89.8 | 0.977 | 9.3 | 1.025 | 67.8 |
| Morelia | 149 | 91 | 6.5 | 61.5 | 90.1 | 0.995 | 9.1 | 1.016 | 81.3 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 195 | 101 | 6.2 | 65.3 | 92.1 | 0.979 | 8.3 | 1.018 | 79.2 |
| depto | 87 | 46 | 9.2 | 52.2 | 87.0 | 0.997 | 10.8 | 1.028 | 69.6 |
| local | 20 | 3 | 15.4 | 33.3 | 66.7 | 1.072 | 12.3 | 1.024 | 66.7 |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 90 | 55 | 6.2 | 63.6 | 94.5 | 0.946 | 7.1 | 1.005 | 74.5 |
| residencial_plus | 6 | 2 | 20.3 | 0.0 | 50.0 | 0.797 | 5.3 | 0.997 | 0.0 |
| social_medio | 206 | 93 | 7.3 | 60.2 | 88.2 | 1.027 | 9.0 | 1.004 | 78.5 |


**Niveles de confianza**

| Nivel | Casos | % |
|---|---|---|
| Sin valor | 152 | 50 |
| Baja | 141 | 47 |
| Media | 9 | 3 |


## 2. Hold-out temporal (últimos 3 meses) contra precio de oferta

Entrenado con 4137 inmuebles anteriores a 2026-08-01; valuados 558 publicados después. Se compara el valor **antes** del descuento de negociación contra el precio de oferta. La cobertura aquí es contra oferta (más ruidosa); la meta de cobertura aplica a cierres.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 8.8 | ≤ 12 | ✅ |
| PE10 % | 57.5 | ≥ 45 | ✅ |
| PE20 % | 84.6 | ≥ 75 | ✅ |
| Sesgo | 0.991 | 0.97–1.03 | ✅ |
| COD | 11.3 | ≤ 15 | ✅ |
| PRD | 1.049 | 0.98–1.03 | ❌ |
| Cobertura 80 % | 70.5 | 76–84 | ❌ |
| Hit rate % | 52.3 | — | — |

n = 558 · con valor emitido = 292

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 305 | 139 | 9.3 | 54.0 | 84.2 | 0.991 | 11.4 | 1.020 | 73.4 |
| Morelia | 253 | 153 | 8.6 | 60.8 | 85.0 | 0.992 | 11.3 | 1.077 | 68.0 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 328 | 175 | 7.5 | 64.6 | 90.3 | 0.992 | 9.4 | 1.021 | 80.0 |
| depto | 139 | 75 | 13.1 | 44.0 | 72.0 | 0.959 | 14.8 | 1.038 | 50.7 |
| local | 31 | 5 | 15.8 | 40.0 | 100.0 | 1.097 | 10.2 | 1.037 | 60.0 |
| terreno | 60 | 37 | 8.9 | 54.1 | 81.1 | 0.996 | 13.7 | 1.331 | 67.6 |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 196 | 126 | 8.3 | 59.5 | 87.3 | 0.949 | 9.8 | 1.002 | 71.4 |
| residencial_plus | 10 | 5 | 22.5 | 20.0 | 40.0 | 0.775 | 23.8 | 1.332 | 20.0 |
| social_medio | 352 | 161 | 9.0 | 57.1 | 83.9 | 1.036 | 10.7 | 1.013 | 71.4 |


**Por motor (hold-out temporal)**

| Motor | n con valor | MdAPE | PE10 | PE20 | Sesgo | COD |
|---|---|---|---|---|---|---|
| A · Comparables | 513 | 15.1 | 34.5 | 61.4 | 0.997 | 18.4 |
| B · Modelo estadístico | 558 | 13.5 | 39.1 | 70.1 | 1.011 | 15.4 |
| C · Físico | 395 | 8.8 | 56.7 | 86.1 | 0.977 | 11.8 |


## 3. Hold-out temporal contra cierres de esos 3 meses



| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 7.6 | ≤ 12 | ✅ |
| PE10 % | 67.7 | ≥ 45 | ✅ |
| PE20 % | 87.1 | ≥ 75 | ✅ |
| Sesgo | 0.999 | 0.97–1.03 | ✅ |
| COD | 9.7 | ≤ 15 | ✅ |
| PRD | 1.025 | 0.98–1.03 | ✅ |
| Cobertura 80 % | 71.0 | 76–84 | ❌ |
| Hit rate % | 43.1 | — | — |

n = 72 · con valor emitido = 31

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 40 | 13 | 8.6 | 61.5 | 92.3 | 0.942 | 10.8 | 1.032 | 69.2 |
| Morelia | 32 | 18 | 5.6 | 72.2 | 83.3 | 1.015 | 8.7 | 1.013 | 72.2 |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 45 | 23 | 5.8 | 73.9 | 87.0 | 0.990 | 8.8 | 1.022 | 69.6 |
| depto | 24 | 8 | 9.8 | 50.0 | 87.5 | 1.058 | 10.4 | 1.033 | 75.0 |
| local | 3 | 0 | — | — | — | — | — | — | — |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 18 | 10 | 6.7 | 70.0 | 100.0 | 0.933 | 6.5 | 1.004 | 60.0 |
| residencial_plus | 1 | 0 | — | — | — | — | — | — | — |
| social_medio | 53 | 21 | 8.0 | 66.7 | 81.0 | 1.054 | 8.7 | 1.009 | 76.2 |


## 4. Prueba de estrés: bloques H3-6 (valuar una zona sin ningún dato)

Cada bloque de ~36 km² se valúa sin haber visto nada de él. Es el peor caso; sirve para saber cuánto empeora el modelo en una colonia nueva.

| Métrica | Resultado | Meta | ¿Cumple? |
|---|---|---|---|
| MdAPE % | 11.9 | ≤ 12 | ✅ |
| PE10 % | 42.9 | ≥ 45 | ❌ |
| PE20 % | 74.2 | ≥ 75 | ❌ |
| Sesgo | 1.021 | 0.97–1.03 | ✅ |
| COD | 14.6 | ≤ 15 | ✅ |
| PRD | 1.046 | 0.98–1.03 | ❌ |
| Cobertura 80 % | — | 76–84 | — |
| Hit rate % | 100.0 | — | — |

n = 4744 · con valor emitido = 4744

**Por ciudad**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| Guadalajara | 2357 | 2357 | 11.8 | 43.4 | 74.6 | 1.018 | 14.7 | 1.043 | — |
| Morelia | 2387 | 2387 | 12.0 | 42.5 | 73.7 | 1.026 | 14.4 | 1.049 | — |

**Por tipo**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| casa | 2766 | 2766 | 11.3 | 44.3 | 76.8 | 1.022 | 13.4 | 1.037 | — |
| depto | 1168 | 1168 | 13.5 | 36.9 | 69.5 | 1.006 | 17.0 | 1.058 | — |
| local | 227 | 227 | 12.0 | 44.9 | 68.3 | 1.020 | 19.0 | 1.087 | — |
| terreno | 583 | 583 | 11.1 | 47.7 | 73.2 | 1.042 | 13.7 | 1.044 | — |

**Por rango de precio**

| Grupo | n | emitidos | MdAPE | PE10 | PE20 | Sesgo | COD | PRD | Cobertura |
|---|---|---|---|---|---|---|---|---|---|
| residencial | 1556 | 1556 | 10.6 | 48.1 | 80.4 | 0.964 | 12.3 | 1.006 | — |
| residencial_plus | 100 | 100 | 14.7 | 26.0 | 72.0 | 0.857 | 12.7 | 1.038 | — |
| social_medio | 3088 | 3088 | 12.3 | 40.9 | 71.1 | 1.063 | 14.5 | 1.022 | — |


**Por motor (bloques H3-6)**

| Motor | n con valor | MdAPE | PE10 | PE20 | Sesgo | COD |
|---|---|---|---|---|---|---|
| A · Comparables | 2406 | 15.9 | 32.4 | 60.6 | 0.984 | 19.2 |
| B · Modelo estadístico | 4744 | 12.7 | 40.7 | 70.4 | 1.020 | 15.6 |
| C · Físico | 2003 | 11.8 | 43.6 | 71.2 | 1.069 | 15.4 |


## 5. Golden set (avalúos reales de Morelia)


_`avm/eval/golden_set.csv` está vacío: los 7 avalúos de Morelia no están en el repositorio. En cuanto se capturen (una fila por avalúo), esta sección compara v2 contra el AVM actual._


## 6. Comparación contra el AVM actual (`/api/avm-websearch`)

El AVM actual calcula el valor con el LLM a partir de 8 páginas leídas en el momento: no es repetible (la misma consulta puede dar otro número) ni guarda sus estimaciones, así que no se puede validar en lote. La única comparación justa es el golden set (sección 5): capturar ahí el valor que dio el AVM actual para cada avalúo (`valor_motor_actual`).
