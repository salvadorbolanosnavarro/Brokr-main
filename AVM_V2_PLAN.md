# AVM Broquer v2: plan de construcción

Escrito antes del código, después de leer el repo. Resume qué se reutiliza, qué
cambia respecto al encargo y qué queda nuevo.

## 1. Lo que hay hoy en el repo

| Pieza | Archivo | Qué hace |
|---|---|---|
| AVM principal | `routers/avm_websearch.py` (`POST /api/avm-websearch`) | Busca anuncios (Google CSE / SerpAPI / Brave / Tavily / Firecrawl), lee hasta ~8 páginas con fetch directo o Firecrawl (con extracción estructurada de anuncios), y **Claude extrae y calcula el valor**. |
| Caché de páginas | `migracion-avm-cache.sql` → `avm_scrape_cache` | Texto de cada página leída, con colonia/ciudad y fecha. Ya es un histórico, pero en texto crudo. |
| Comparables PostGIS | `routers/avm_nearby.py` (`buscar_cercanos`) | RPC sobre propiedades de Supabase. |
| Colonias | `routers/avm_places.py`, `core/easybroker.py` | Autocompletado y geocodificación con Google Places. |
| PDF | `routers/avm_pdf.py` | "Opinión de valor" en PDF. |
| Frontend | `avm.html` | Formulario y resultado del módulo. |
| Auth | `core/auth.require_user_id` | Token de sesión de Supabase. |
| BD | `core/database.py` | `get_rows`, `upsert_rows`, `post_rows`, `call_service_rpc` con service key. |
| Storage | `core/storage.py` | `upload_object` / `download_object`. |
| Config | `core/config.py` (`settings`) | Única puerta para variables de entorno (`scripts/architecture_debt.py` prohíbe `os.getenv` y `/rest/v1/` fuera de `core/`). |

## 2. Diferencias con el encargo (y cómo se resuelven)

1. **No existe `motor_pericial.py`** (ni en esta rama ni en `main`). Tampoco hay
   Playwright para scraping de portales: Playwright se usa solo para generar
   PDFs. El scraping real es Firecrawl + fetch directo en `routers/avm_websearch.py`,
   y ahí **el valor lo calcula Claude**, lo que choca con la regla de oro.
   → El **Motor A** es un motor nuevo de comparables 100 % determinista
   (`avm/engines/motor_a_comparables.py`) que reutiliza la homologación y la
   depuración de outliers del flujo actual, pero sobre `avm_listings`. El
   endpoint `/api/avm-websearch` **no se toca**: sigue funcionando igual.
2. **Ingesta**: `avm/etl/ingest_listings.py` reutiliza `_firecrawl_scrape` y
   el bloque `ANUNCIOS ESTRUCTURADOS` que ya produce, y primero convierte lo que
   ya está en `avm_scrape_cache` (mismo formato) en filas de `avm_listings`.
3. **LLM**: el encargo dice Groq. El repo tiene Groq (`settings.groq_api_key`)
   y Anthropic. `extract_text.py` usa Groq si hay llave; si no, Anthropic; si no
   hay ninguno, deja los campos vacíos. Solo extrae JSON con esquema fijo.
4. **Golden set de 7 avalúos de Morelia**: no están en el repo.
   → Se deja `avm/eval/golden_set.csv` como plantilla con las columnas exactas;
   la evaluación lo usa en cuanto tenga filas.
5. **Migraciones**: el repo no corre migraciones automáticas. La convención
   es un `.sql` para pegar en el SQL Editor de Supabase. Se entrega
   `migracion-avm-v2.sql` (idempotente) con PostGIS.
6. **Staging**: staging es la rama `work/redesign-preview-20261003`, que se
   alimenta sola desde `main` (`.github/workflows/sync-main-a-staging.yml`).
   No hay credenciales de Railway ni de Supabase en este entorno.
7. **mapie / shap**: conformal propio (Mondrian, ~40 líneas) y SHAP con
   `pred_contrib=True` de LightGBM (el SHAP exacto de árboles, sin dependencia extra).

## 3. Estructura nueva

```
avm/
  config/            tablas editables (vida útil, costos de reposición, Heidecke, ciudades)
  settings.py        constantes del modelo (k, radios, topes de homologación, delta0, kappa…)
  geo.py             haversine, H3, bloques espaciales
  indice.py          llevar precios a la fecha de valuación con avm_index
  features.py        matriz de variables, target encoding OOF espacial, mediana kNN sin fuga
  engines/
    motor_a_comparables.py
    motor_b_gbm.py
    motor_c_fisico.py
  ensemble.py        pesos 1/σ², delta bayesiano, conformal Mondrian, confianza
  explain.py         SHAP → frases en español
  registry.py        guardar/cargar artefactos (joblib, local + Supabase Storage), promoción
  service.py         carga en memoria al arrancar y estimar()
  jobs.py            ingesta diaria, limpieza diaria, recalibración semanal, reentreno mensual
  synthetic.py       mercado sintético con verdad conocida (pruebas y demo sin datos)
  etl/               ingest_listings, dedupe, clean, extract_text, load_context, repo
  eval/              metrics, validate, run_report, golden_set.csv, REPORTE.md
  tests/             pytest
routers/avm_v2.py    POST /avm/v2/estimar, POST /avm/v2/cierre, GET /avm/v2/estado
migracion-avm-v2.sql
```

## 4. Integración sin romper nada

- `main.py`: el router v2 se monta con import defensivo (si faltan lightgbm u
  otra dependencia, el resto del backend sigue vivo).
- Los jobs solo arrancan si `AVM_V2_JOBS=true`. El front nuevo solo aparece si
  el backend responde `AVM_V2=true` en `/avm/v2/estado`, así producción no cambia
  aunque llegue el código.
- Las pruebas de `avm/tests` no viven en `tests/`, para que el `unittest`
  de Quality (que solo instala `requirements-ci.txt`) no intente importar
  lightgbm; corren en un job propio de CI.
