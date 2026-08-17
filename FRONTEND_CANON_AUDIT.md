# Broquer — Auditoría de unificación visual

## Objetivo

Unificar la interfaz de producto usando **`index.html`** y **`whatsapp.html`** como referencias de experiencia, sin alterar lógica de negocio, rutas, APIs ni comportamiento funcional.

La implementación visual compartida debe tener una sola fuente de verdad: **`brokr-theme.css`**. El chrome común permanece en **`app-shell.js`**.

## Referencias maestras

### `index.html` — referencia de identidad general

Conservar como patrón para:

- jerarquía tipográfica;
- blanco dominante y respiración;
- navy como estructura;
- azul como acción;
- tarjetas, hairlines y profundidad;
- KPIs y visualización de información;
- estados de atención y semánticos;
- densidad general del dashboard;
- responsive de la pantalla principal.

`index.html` ya consume `brokr-theme.css` y sus tokens Canon.

### `whatsapp.html` — referencia de interfaces densas

Conservar como patrón para:

- paneles de dos columnas;
- búsquedas y filtros compactos;
- navegación por tabs;
- listas densas;
- estados activo/no leído/pendiente;
- avatares y metadatos;
- composer y acciones contextuales;
- adaptación móvil de interfaces de trabajo intensivo.

La estructura y UX de WhatsApp son referencia. **Su segunda piel visual no lo es.**

## Hallazgo crítico 01 — doble sistema visual

`whatsapp.html` carga:

1. `brokr-theme.css` — sistema Canon actual;
2. `broquer-ui.css` — capa histórica “Zillow/BROQUER UI v2” que gana la cascada.

`broquer-ui.css` define un segundo conjunto de tokens (`--bq-*`) con colores, radios, sombras, tipografía y geometría propios. Esto contradice directamente `DESIGN.md`, que establece:

- una sola fuente ejecutable de verdad (`brokr-theme.css`);
- cero skins por módulo;
- cero segunda hoja de tokens;
- reutilización de componentes `bk-*`.

### Decisión

No copiar `broquer-ui.css` al resto del producto.

La migración correcta es la inversa: conservar las mejores decisiones de interacción de WhatsApp, pero llevar su apariencia al sistema Canon compartido.

## Hallazgo crítico 02 — referencias no significan duplicación

`index` y `whatsapp` cumplen papeles distintos:

- `index`: lenguaje visual global y dashboard;
- `whatsapp`: patrón de aplicación densa/productiva.

La unificación no consiste en hacer que todas las pantallas sean visualmente idénticas. Consiste en que todas compartan la misma tipografía, geometría, componentes, color, profundidad, estados y comportamiento responsive, permitiendo layouts específicos por dominio.

## Contrato de migración

Para cada módulo de producto:

1. Mantener HTML/JS funcional salvo que una corrección de accesibilidad o responsive lo exija.
2. Cargar `brokr-theme.css` como sistema de diseño.
3. Eliminar skins visuales alternativas y tokens locales de producto.
4. Sustituir componentes reinventados por `bk-*` cuando exista equivalente.
5. Conservar CSS específico solo para layout o necesidades reales del dominio.
6. Sustituir colores, radios, sombras, tamaños y espaciados hardcodeados por tokens Canon.
7. Mantener SVG con `currentColor` para iconografía de producto.
8. Verificar desktop y móvil.
9. Ejecutar los guards de diseño y la auditoría del archivo antes de dar el módulo por migrado.

## Orden de migración

### Fase 0 — referencias y sistema

- [x] Identificar `index.html` como referencia global.
- [x] Identificar `whatsapp.html` como referencia de interfaz densa.
- [x] Confirmar `brokr-theme.css` como fuente Canon.
- [x] Detectar la segunda piel `broquer-ui.css`.
- [ ] Migrar `whatsapp.html` para depender solo de Canon sin perder su UX.
- [ ] Revisar componentes `bk-*` faltantes que WhatsApp realmente necesite y, solo si son globales, agregarlos al theme.

### Fase 1 — núcleo operativo

- [ ] `contactos.html`
- [ ] `leads.html`
- [ ] `propiedades.html`
- [ ] `tareas.html`
- [ ] `estadisticas.html`

### Fase 2 — herramientas de operación

- [ ] `avm.html`
- [ ] `isr.html`
- [ ] `contratos.html`
- [ ] `firmas.html`
- [ ] `finanzas.html`
- [ ] `cumplimiento.html`

### Fase 3 — crecimiento y canales

- [ ] `facebook-ads.html`
- [ ] `correo.html`
- [ ] `video.html`
- [ ] `image-cleaner.html`
- [ ] `mi-sitio.html`

### Fase 4 — administración y secundarios

- [ ] `equipo.html`
- [ ] `empresas.html`
- [ ] `admin.html`
- [ ] `soporte.html`
- [ ] restantes pantallas de producto y flujos auxiliares.

## Criterios de terminado por pantalla

Una pantalla se considera unificada cuando:

- parece parte del mismo producto que `index` y `whatsapp`;
- no introduce una paleta propia;
- no introduce una familia tipográfica propia;
- no introduce una segunda geometría de botones/cards/inputs;
- usa el shell común cuando corresponde;
- sus estados hover/focus/disabled/loading/error/empty son coherentes;
- funciona correctamente en móvil;
- no modifica lógica de negocio para conseguir el rediseño;
- pasa los guards de diseño aplicables.

## Regla de seguridad del trabajo paralelo

Esta rama visual parte del estado de `agent/architecture-cleanup`, pero los cambios visuales se mantienen en **`agent/frontend-canon-unification`**. No se escriben cambios de unificación visual directamente sobre la rama de auditoría técnica. Los puntos de integración se resolverán explícitamente al sincronizar ramas.
