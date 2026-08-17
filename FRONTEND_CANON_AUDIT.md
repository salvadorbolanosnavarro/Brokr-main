# Broquer — Auditoría de unificación visual

## Estado actual

La unificación visual del frontend activo de Broquer alcanzó su objetivo estructural:

- **`index.html`** es la referencia de identidad general.
- **`whatsapp.html`** es la referencia de interacción densa/productiva.
- **`brokr-theme.css`** es la única implementación ejecutable del sistema visual.
- **`app-shell.js`** es el propietario del chrome compartido de la aplicación.
- Los módulos conservan únicamente layout y comportamiento específicos de su dominio.
- **42 superficies activas** se auditan automáticamente en Quality.

La migración preservó rutas, IDs, contratos de API y lógica de negocio. Los archivos grandes se modificaron mediante transformaciones determinísticas, auditorías dirigidas y comprobación exacta de archivos cambiados.

## Referencias maestras

### `index.html` — identidad

Index define el lenguaje visual global: blanco dominante, navy como estructura, azul como acción, Inter como familia tipográfica, tarjetas y hairlines Canon, radios/sombras por tokens, jerarquía compacta y comportamiento responsive.

### `whatsapp.html` — interacción densa

WhatsApp define patrones de trabajo intensivo: paneles y listas densas, búsqueda/filtros/tabs compactos, estados activo/no leído/pendiente, avatares/metadatos, composer y adaptación móvil. Su antigua piel independiente no forma parte de la referencia: la UX se conserva y la identidad es Canon.

## Doble sistema visual — RESUELTO

Al iniciar la auditoría, WhatsApp cargaba `brokr-theme.css` y después `broquer-ui.css`. La segunda hoja era una skin derivada de Zillow con tokens `--bq-*`, paleta, tipografía, radios y sombras propios.

Se eliminó en dos pasos:

1. `broquer-ui.css` se redujo a un adaptador que consumía tokens Canon.
2. Sus reglas `w2-*` necesarias se absorbieron en `brokr-theme.css` y **`broquer-ui.css` fue eliminado del repositorio**.

El ratchet permanente falla si reaparece la segunda hoja o si algún HTML intenta volver a cargarla.

## Contrato visual vigente

Toda nueva superficie o migración debe:

1. Cargar `brokr-theme.css` y no crear otra hoja de tokens/skin.
2. No definir un `:root` visual propio salvo artefactos autocontenidos explícitamente exentos.
3. Usar tokens Canon para color, tipografía, radios, sombras, espaciado, alturas y motion.
4. Mantener Inter como familia del producto.
5. Reutilizar componentes `bk-*` cuando exista un equivalente real.
6. Conservar CSS local solo para necesidades legítimas del dominio.
7. No copiar sidebar, topbar, navegación móvil, FAB, drawer ni encabezados globales: pertenecen a `app-shell.js`.
8. Usar iconografía SVG/currentColor y no emojis como iconos de UI.
9. Preservar hover/focus/disabled/loading/error/empty y funcionamiento móvil.
10. Pasar `tests/test_frontend_canon_contract.py`, `tests/test_frontend_canon_inventory.py` y `audit.py`.

## Cobertura activa

Quality audita automáticamente estas **42 superficies**:

`index`, `whatsapp`, `contactos`, `leads`, `propiedades`, `isr`, `estadisticas`, `bandeja`, `bolsa`, `expediente`, `ficha-manual`, `firmar`, `firmas`, `verificar-firma`, `verificador`, `guia-agente`, `legal`, `blog`, `login`, `registro`, `reset-password`, `unirse`, `correo`, `aviso-privacidad`, `facebook-callback`, `whatsapp-callback`, `whatsapp-chatgpt`, `avm`, `contratos`, `image-cleaner`, `robin`, `landing`, `tareas`, `finanzas`, `cumplimiento`, `video`, `facebook-ads`, `mi-sitio`, `equipo`, `empresas`, `admin` y `soporte`.

`audit.py` se ejecuta sin lista manual. `tests/test_frontend_canon_inventory.py` protege ese comportamiento: un HTML raíz activo nuevo entra al auditor por defecto y no puede escapar porque alguien olvidó añadirlo a CI.

## Migraciones estructurales principales

- Autenticación/public: `login`, `registro`, `reset-password`, `unirse`, `aviso-privacidad`, callbacks, `landing` y `blog`.
- Shell compartido: se retiraron copias de sidebar/chrome en Contactos, Leads, Propiedades, ISR, Contratos e Image Cleaner.
- Herramientas/canales: AVM, Contratos, Image Cleaner, Correo, WhatsApp ChatGPT, Robin y WhatsApp consumen Canon directamente.
- Landing dejó de usar `--b2-*`, Bricolage/Figtree y su sistema visual independiente.

## Últimos cuatro outliers — RESUELTOS

El barrido amplio final encontró cuatro incumplimientos reales:

### `isr.html`
Dos reglas de CTA usaban tinta negra como superficie de acción. Se movieron a tokens azules Canon sin alterar cálculo, formulario ni PDF.

### `bandeja.html`
Un tamaño tipográfico fijo y un glifo `✕` quedaron fuera del contrato. Se sustituyeron por escala Canon y texto accesible `Cerrar`.

### `legal.html`
Conservaba una skin histórica con colores/geometría hardcodeados. Se reemplazó la capa visual manteniendo contenido jurídico y navegación por pestañas. Después se compactó únicamente formato fuente no renderizado para respetar el ceiling arquitectónico existente **sin aumentarlo**.

### `verificador.html`
Era el último outlier grande: aliases históricos no definidos por Canon, hardcodes, emojis de UI y una copia oculta del shell. Se reconstruyó la capa visual sobre Canon conservando checklist, IDs, handlers y flujo de análisis IA.

Todos los workflows/scripts de transformación de una sola vez fueron eliminados después de validar sus resultados.

## Validación final

Último Quality limpio sobre `agent/frontend-canon-unification`, sincronizado con el head técnico terminado vigente de `agent/architecture-cleanup`:

- **237 tests: pasan.**
- **42 superficies: 0 violaciones.**
- **`scripts/architecture_debt.py`: pasa; la deuda no creció.**
- `direct_env_reads`: 0.
- `duplicated_auth_helpers`: 0.
- `service_key_fallbacks`: 0.
- `embedded_jwt_secrets`: 0.
- `fail_open_webhook_secrets`: 0.
- `fail_open_entitlements`: 0.
- `direct_supabase_rest`: 1 (`main.py`), dentro de ceiling.
- Archivos de código >100 KB: 10, dentro del ceiling existente.
- `whatsapp.html`: **127,064 / 127,110 bytes**.
- `legal.html`: **109,055 / 109,324 bytes**.

Quality protege contra reaparición de una segunda skin, nuevos roots visuales, regreso de Bricolage/Figtree/`--b2-*`, HTML apropiándose del sidebar, aliases históricos, emojis como iconografía, regresiones de contraste/color/tipografía/geometría y superficies activas omitidas del auditor.

## Exclusiones deliberadas

### Motor de sitios públicos de agentes

- `sitio.html`
- `404.html`

Estas páginas cargan `sitio.css` / `sitio-engine.js`; no son UI de la aplicación Broquer y no deben heredar `app-shell.js` ni ser forzadas a parecerse al dashboard.

### Artefactos históricos / referencia

- `Copia de index.html`
- `preview-redesign.html`
- `mock-editorial.html`
- `mock-ejecutiva.html`
- `videos/landing.html` cuando se use como demo/referencia aislada.

No son fuentes de diseño del producto.

## Deuda visual restante

La deuda de **sistema visual activo** queda cerrada por contrato. Puede seguir existiendo refinamiento UX o CSS específico de dominio —densidad, microinteracciones, jerarquías locales, simplificación de markup—, pero ya no existe una segunda identidad visual ejecutable que compita con Canon.

## Seguridad de integración

La unificación visual vive en **`agent/frontend-canon-unification`** y PR #45 apunta a **`agent/architecture-cleanup`**, no a `main`. La rama visual se sincroniza únicamente con ciclos técnicos terminados y limpios. Si la rama técnica avanza antes de una futura revisión/merge, debe sincronizarse otra vez y volver a ejecutar Quality completo.

El PR permanece Draft. No hay merge a `main` ni despliegue de producción implícito en este trabajo.
