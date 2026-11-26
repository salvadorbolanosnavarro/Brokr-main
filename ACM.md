# Análisis comparativo de mercado (ACM)

Herramienta del **asesor**: arma el análisis de una propiedad en su mesa de trabajo y se lo presenta al **propietario** como PDF con su marca o como liga para WhatsApp. No es un AVM: el centro es la evidencia (comparables), y el rango de precio sale de esa evidencia con matemática fija y visible.

## Puesta en marcha

1. **Base de datos:** correr `migracion-acm.sql` en Supabase → SQL Editor. Es idempotente y sólo crea tablas nuevas.
2. **Desplegar** el backend y el frontend. El módulo aparece en el menú como **Análisis comparativo** (grupo Números) y vive en `acm.html`. Reemplaza en el menú a la antigua «Estimación de valor» (AVM), que queda oculta pero sigue funcionando en `avm.html` y desde el chat.
3. **Opcional: recolección nocturna.** Viene apagada porque gasta crédito de búsqueda, Firecrawl e IA. Para encenderla, en **una sola** instancia (igual que el Buscador):

   ```bash
   ACM_RECOLECCION_ACTIVA=1
   ACM_RECOLECCION_HORA=3   # hora local (0-23), por defecto 3 a. m.
   ```

   Un administrador de Broquer puede correrla al momento con `POST /acm/admin/recolectar`.

Usa las mismas llaves que ya usa el AVM (búsqueda web, `FIRECRAWL_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_PLACES_KEY`). No requiere variables nuevas para funcionar.

## Cómo funciona

| Capa | Archivo | Qué hace |
|---|---|---|
| Normalización | `core/acm_mercado.py` | Convierte anuncios a una forma única, lee el bloque estructurado de los portales sin IA y calcula la "huella" que deduplica un mismo inmueble publicado en varios portales |
| Motor | `core/acm_calculo.py` | Similitud, ajustes, atípicos, rango (percentiles 25/50/75 ponderados), confianza, estrategia y datos de mercado. Determinista: la misma entrada da el mismo resultado |
| Datos | `routers/acm_datos.py` | Base propia `mercado_comparables`, geocodificación de colonias con caché, búsqueda en vivo (reutiliza la del AVM y **guarda todo lo que encuentra**), inventario, Bolsa, cierres y recolección nocturna |
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

## Limitaciones honestas

- **Ubicación aproximada:** casi ningún anuncio trae coordenadas, así que se ubica en el centro de su colonia. La distancia se muestra como «≈».
- **"Retirado" no siempre es "vendido":** un anuncio pasa a retirado si no aparece en las búsquedas de su zona durante 30 días, con al menos 3 recolecciones. Puede haberse vendido, rentado o simplemente dejado de anunciar. Por eso el grupo se llama «vendidos o retirados» y sólo los cierres de la cuenta se etiquetan como «Vendida».
- **Arranque en frío:** la base empieza vacía. Las primeras semanas casi todo sale de la búsqueda en vivo (tarda hasta un minuto). Cada búsqueda deja la base más completa.
- **Una moneda por análisis:** los comparables publicados en otra moneda se muestran pero no se incluyen en el cálculo.

## Pruebas

```bash
python -m unittest tests.test_acm_calculo tests.test_acm_datos tests.test_acm_router
```
