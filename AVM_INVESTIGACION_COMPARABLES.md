# AVM con investigación controlada de comparables

Esta versión reemplaza el flujo anterior de `/api/avm-websearch` por una arquitectura más defendible y controlable:

1. El usuario pide una opinión de valor.
2. El backend consulta una API de búsqueda configurada.
3. El backend toma pocas URLs candidatas.
4. El backend lee contenido público visible de forma limitada.
5. Claude limpia, clasifica, descarta duplicados/sospechosos y calcula la opinión.
6. El resultado incluye comparables, descartes, fuentes, queries, advertencias y metodología.

## Archivos modificados

- `main.py`
  - Reescrito el endpoint `POST /api/avm-websearch`.
  - Agregadas funciones de búsqueda con Google CSE, SerpAPI, Brave Search y Tavily.
  - Agregada lectura limitada de URLs públicas con `httpx` + `BeautifulSoup`.
  - Agregado prompt de Claude para extraer solo datos visibles y no inventar comparables.

- `valor.html`
  - Cambiado el endpoint backend de búsqueda web a `/api/avm-websearch`.
  - Adaptado el botón de búsqueda para enviar el formato nuevo del endpoint.

## Variables de entorno necesarias

Obligatoria para el cálculo final por IA:

```bash
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
```

Configura al menos una de estas APIs de búsqueda:

```bash
# Google Programmable Search / Custom Search JSON API
GOOGLE_CSE_API_KEY=tu_google_cse_key
GOOGLE_CSE_ID=tu_search_engine_id

# o SerpAPI
SERPAPI_API_KEY=tu_serpapi_key

# o Brave Search API
BRAVE_SEARCH_API_KEY=tu_brave_key

# o Tavily
TAVILY_API_KEY=tu_tavily_key
```

Opcionales:

```bash
ANTHROPIC_AVM_MODEL=claude-sonnet-4-6
AVM_MAX_SEARCH_RESULTS=16
AVM_MAX_URLS_TO_FETCH=8
AVM_SEARCH_TIMEOUT=18
AVM_FETCH_TIMEOUT=10
AVM_MAX_TEXT_CHARS_PER_URL=6500
```

## Prueba rápida

```bash
curl -X POST https://TU-DOMINIO/api/avm-websearch \
  -H "Content-Type: application/json" \
  -d '{
    "colonia":"Chapultepec Oriente",
    "tipo_inmueble":"casa",
    "operacion":"venta",
    "m2_terreno":87.5,
    "m2_construccion":126,
    "recamaras":3,
    "banos":2,
    "ciudad":"Morelia",
    "estado":"Michoacán",
    "comentarios":"Casa chica en zona con escasez de producto comparable."
  }'
```

## Advertencia operativa

Esto no convierte la herramienta en un avalúo certificado. Está diseñada como opinión de valor comercial asistida por comparables públicos, con fuente y fecha. Para producción seria, conviene agregar revisión humana antes de entregar documentos a clientes.
