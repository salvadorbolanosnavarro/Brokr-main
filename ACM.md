# Análisis comparativo de mercado (ACM)

Herramienta del **asesor**: arma el análisis de una propiedad en su mesa de trabajo y se lo presenta al **propietario** como PDF con su marca o como liga para WhatsApp. No es un AVM: el centro es la evidencia (comparables), y el rango de precio sale de esa evidencia con matemática fija y visible.

## Puesta en marcha

1. **Base de datos:** correr `migracion-acm.sql` y después `migracion-acm-ubicacion.sql` en Supabase → SQL Editor, antes de desplegar. Son idempotentes.
2. **Desplegar** el backend y el frontend. El módulo aparece en el menú como **Análisis comparativo** (grupo Números) y vive en `acm.html`. Reemplaza por completo a la antigua «Estimación de valor» (AVM), que se retiró: el asistente del chat también arma un ACM cuando le piden un análisis o una estimación de valor.
3. **Opcional: recolección nocturna.** Viene apagada porque gasta crédito de búsqueda, Firecrawl e IA. Para encenderla, en **una sola** instancia (igual que el Buscador):

   ```bash
   ACM_RECOLECCION_ACTIVA=1
   ACM_RECOLECCION_HORA=3   # hora local (0-23), por defecto 3 a. m.
   ```

   Un administrador de Broquer puede correrla al momento con `POST /acm/admin/recolectar`.

Usa las llaves de búsqueda web que ya tiene el servidor (búsqueda web, `FIRECRAWL_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_PLACES_KEY`). No requiere variables nuevas para funcionar.

## Cómo funciona

| Capa | Archivo | Qué hace |
|---|---|---|
| Normalización | `core/acm_mercado.py` | Convierte anuncios a una forma única, lee el bloque estructurado de los portales sin IA y calcula la "huella" que deduplica un mismo inmueble publicado en varios portales |
| Motor | `core/acm_calculo.py` | Similitud, ajustes, atípicos, rango (percentiles 25/50/75 ponderados), confianza, estrategia y datos de mercado. Determinista: la misma entrada da el mismo resultado |
| Datos | `routers/acm_datos.py` | Base propia `mercado_comparables`, geocodificación de colonias con caché, búsqueda en vivo (usa la búsqueda y lectura de portales de `routers/avm_websearch.py` y **guarda todo lo que encuentra**), inventario, Bolsa, cierres y recolección nocturna |
| API | `routers/acm.py` | Mesa de trabajo, versiones, liga pública, PDF |
| Reporte | `core/acm_reporte.py` | Un solo HTML para la liga y el PDF, con la marca del asesor |
| Interfaz | `acm.html` + `acm.js` | Captura, mesa de trabajo y presentación |

**La IA nunca calcula valores.** Sólo transcribe anuncios cuando un portal no trae datos estructurados.

### Fuentes de comparables

- **Portales** (base propia, alimentada por la búsqueda en vivo y la recolección nocturna).
- **Inventario activo de la cuenta** y **Bolsa Broquer** en la misma ciudad.
- **Cierres reales de la cuenta**, con su precio de cierre. Sólo para quien tiene el permiso «Ver comisiones» (dueño y administradores lo tienen).
- **Comparables a mano** que agrega el asesor.

### Grupos que ve el propietario

- **Tu competencia:** en venta ahora.
- **Lo que el mercado sí pagó:** cierres reales y anuncios que se retiraron.
- **Lo que pasa cuando se sale caro:** bajaron de precio o llevan más de 180 días publicados.

### Ajustes automáticos (el asesor puede cambiarlos)

| Concepto | Regla | Tope |
|---|---|---|
| Superficie | elasticidad 0.20 del precio/m² a la superficie | ±10% |
| Recámaras | 2.5% por recámara de diferencia (casa y departamento) | ±7.5% |
| Baños | 2% por baño | ±6% |
| Estacionamientos | 3% por cajón | ±9% |
| Antigüedad | 0.5% por año | ±10% |
| Negociación | −5% en venta, −3% en renta, a precios de oferta (no a cierres). Con 5 o más cierres de la cuenta se calibra solo con la diferencia real entre precio publicado y precio de cierre | — |

Conservación de la propiedad: excelente +5%, bueno 0, regular −7%, para remodelar −15%. El asesor también puede poner un ajuste general.

### Zona: qué comparables entran solos al cálculo

- **Sólo con ubicación confirmada:** la colonia tiene que venir en el propio anuncio (o en el registro de la cuenta). Un anuncio que no dice dónde está nunca se supone en la colonia buscada; se muestra con «Ubicación no confirmada en el anuncio», sin incluir.
- **Radio que crece sólo si hace falta:** 1 km; si no hay al menos 5 comparables, 2 km; luego 3 km. Nada a más de 3 km entra solo; se muestra con «Fuera de la zona (X km)».
- **Colonias hermanas:** Chapultepec Sur, Oriente y Norte son de la misma familia y cuentan como cercanas (≈ 900 m) aunque no haya coordenadas.
- **Cierres reales de la cuenta:** radio mínimo de 2 km, porque su precio es el que realmente se pagó.
- **Sin búsqueda «en toda la ciudad»:** la búsqueda en portales se limita a la colonia y sus colindantes.
- **Candidatos sólo de la zona:** la base, el inventario, la Bolsa y los cierres sólo aportan comparables con ubicación confirmada a 3 km o menos (antes la base llegaba a 6 km y el inventario/Bolsa a toda la ciudad).
- **La lista muestra la zona:** lo de fuera queda tras «Ver descartados». Un ACM guardado antes de esta regla se recalcula una vez al abrirlo.
- **Búsqueda automática:** al abrir un análisis con menos de 8 comparables en la zona se busca en portales solo, una vez por análisis en cada sesión.
- El asesor siempre puede incluir a mano cualquier comparable de la lista.

## Limitaciones honestas

- **Ubicación aproximada:** casi ningún anuncio trae coordenadas, así que se ubica en el centro de la colonia que declara. La distancia se muestra como «≈». Si Google no encuentra la colonia (o sólo encuentra la ciudad), el anuncio queda sin ubicación en vez de ponerse en el centro de la ciudad.
- **"Retirado" no siempre es "vendido":** un anuncio pasa a retirado si no aparece en las búsquedas de su zona durante 30 días, con al menos 3 recolecciones. Puede haberse vendido, rentado o simplemente dejado de anunciar. Por eso el grupo se llama «vendidos o retirados» y sólo los cierres de la cuenta se etiquetan como «Vendida».
- **Arranque en frío:** la base empieza vacía. Las primeras semanas casi todo sale de la búsqueda en vivo (tarda hasta un minuto). Cada búsqueda deja la base más completa.
- **Una moneda por análisis:** los comparables publicados en otra moneda se muestran pero no se incluyen en el cálculo.

## Pruebas

```bash
python -m unittest tests.test_acm_calculo tests.test_acm_datos tests.test_acm_router
```
