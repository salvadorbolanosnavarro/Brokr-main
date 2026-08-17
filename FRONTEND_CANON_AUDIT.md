# Broquer — Auditoría de unificación visual

## Estado actual

La unificación visual de las superficies activas de Broquer ya alcanzó su objetivo estructural:

- **`index.html`** es la referencia de identidad general;
- **`whatsapp.html`** es la referencia de interacción densa/productiva;
- **`brokr-theme.css`** es la única implementación ejecutable del sistema visual;
- **`app-shell.js`** es el único propietario del chrome compartido de la aplicación;
- los módulos conservan únicamente layout y comportamiento específicos de su dominio.

La migración se hizo preservando rutas, IDs, contratos de API y lógica de negocio. Los archivos grandes se modificaron mediante transformaciones determinísticas con dry-run, pruebas dirigidas y comprobación exacta de archivos cambiados.

## Referencias maestras

### `index.html` — identidad

Index define el lenguaje visual global:

- blanco dominante y respiración;
- navy como estructura;
- azul como acción;
- Inter como familia tipográfica única;
- jerarquía compacta y clara;
- tarjetas, hairlines, radios y sombras Canon;
- KPIs, estados semánticos y visualización de información;
- comportamiento responsive del producto.

### `whatsapp.html` — interacción densa

WhatsApp define patrones útiles para interfaces de trabajo intensivo:

- paneles y listas densas;
- búsqueda, filtros y tabs compactos;
- estados activo/no leído/pendiente;
- avatares y metadatos;
- composer y acciones contextuales;
- adaptación móvil de flujos complejos.

Su antigua piel independiente no forma parte de la referencia. La UX se conserva; la identidad es Canon.

## Hallazgo original — doble sistema visual — RESUELTO

Al iniciar la auditoría, WhatsApp cargaba `brokr-theme.css` y después `broquer-ui.css`. Esta última era una segunda piel derivada de Zillow con tokens `--bq-*`, paleta, tipografía, radios y sombras propios.

Ese conflicto fue eliminado en dos pasos:

1. `broquer-ui.css` se redujo primero a un adaptador de dominio que consumía exclusivamente tokens Canon.
2. Sus pocas reglas `w2-*` necesarias se absorbieron finalmente en `brokr-theme.css` y **`broquer-ui.css` fue eliminado del repositorio**.

El ratchet permanente falla si `broquer-ui.css` reaparece o si algún HTML intenta volver a cargarlo.

## Contrato visual vigente

Toda nueva superficie o migración debe cumplir:

1. Cargar `brokr-theme.css`; no crear otra hoja de tokens o skin.
2. No definir un `:root` visual propio salvo artefactos autocontenidos explícitamente exentos, como documentos generados.
3. Usar tokens Canon para color, tipografía, radios, sombras, espaciado, alturas y motion.
4. Mantener Inter como familia del producto.
5. Reutilizar componentes `bk-*` cuando exista un equivalente real.
6. Conservar CSS de módulo solo para necesidades legítimas del dominio.
7. No copiar sidebar, topbar, navegación móvil, FAB, drawer ni encabezados globales: pertenecen a `app-shell.js`.
8. Mantener SVG/iconografía con `currentColor` cuando corresponda.
9. Preservar estados hover/focus/disabled/loading/error/empty y funcionamiento móvil.
10. Pasar los guards de `tests/test_frontend_canon_contract.py` y `audit.py` antes de considerar una superficie migrada.

## Trabajo completado

### Base y protección

- [x] `brokr-theme.css` establecido como única fuente ejecutable de verdad.
- [x] `_TEMPLATE-modulo.html` alineado con Canon y shell compartido.
- [x] `tests/test_frontend_canon_contract.py` creado como ratchet permanente.
- [x] Quality ampliado para auditar **26 superficies Canon**.
- [x] `broquer-ui.css` eliminado por completo.
- [x] Cero HTML debe definir `.app-sidebar`.

### Autenticación y superficies públicas

- [x] `login.html`
- [x] `registro.html`
- [x] `reset-password.html`
- [x] `unirse.html`
- [x] `aviso-privacidad.html`
- [x] `facebook-callback.html`
- [x] `whatsapp-callback.html`
- [x] `landing.html`

Landing ya no tiene el namespace `--b2-*` ni carga tipografía independiente; conserva contenido, SEO, video, navegación y CTAs sobre Canon.

### Núcleo y shell compartido

- [x] `contactos.html` — eliminado chrome/sidebar duplicado.
- [x] `leads.html` — eliminado chrome/sidebar duplicado.
- [x] `propiedades.html` — eliminado shell histórico duplicado.
- [x] `isr.html` — eliminado root de aliases de la aplicación y shell duplicado.

Estas migraciones no implican que toda regla de dominio de esos archivos haya sido reescrita; sí garantizan que la identidad y el chrome compartidos no vuelvan a bifurcarse.

### Herramientas y canales migrados directamente a Canon

- [x] `avm.html`
- [x] `contratos.html`
- [x] `image-cleaner.html`
- [x] `correo.html`
- [x] `whatsapp-chatgpt.html`
- [x] `robin.html`
- [x] `whatsapp.html` — sin segunda hoja visual.

Image Cleaner conserva carga, limpieza IA, descarga, guardado nativo y handoff a Ficha/Facebook Ads/Video. Robin conserva ruta diaria, prospectos prioritarios, copiloto Broq y marcador de cierres, pero ya comparte la identidad de Broquer.

### Superficies adicionales protegidas por auditoría Canon

Además de las migraciones explícitas anteriores, Quality ya vigila permanentemente:

- [x] `tareas.html`
- [x] `firmas.html`
- [x] `finanzas.html`
- [x] `cumplimiento.html`
- [x] `video.html`
- [x] `facebook-ads.html`
- [x] `mi-sitio.html`
- [x] `equipo.html`
- [x] `empresas.html`
- [x] `admin.html`
- [x] `soporte.html`

Estas pantallas pasaron el auditor sin necesidad de reescrituras cosméticas innecesarias. Los bloques que representan contenido externo o miniaturas de otros productos permanecen exentos solo cuando están marcados de forma estrecha y explícita.

## Validación automática

Último estado limpio validado de esta rama:

- **232 tests:** pasan.
- **26 superficies en `audit.py`: 0 violaciones.**
- **`scripts/architecture_debt.py`: pasa.**
- `whatsapp.html` permanece dentro de su ceiling de tamaño; no se relajó el guard para acomodar la migración.

Quality protege específicamente contra:

- reaparición de una segunda hoja visual;
- nuevos `:root` de producto en superficies migradas;
- regreso de Bricolage/Figtree o `--b2-*` en autenticación/Landing;
- HTML que vuelva a apropiarse del sidebar;
- aliases visuales históricos en ISR/AVM/Contratos/Image Cleaner;
- regresiones auditables de color, contraste, tipografía, geometría y hardcodes en las superficies incluidas.

## Deuda visual restante

La deuda de **sistema visual activo** está esencialmente cerrada. Lo que queda se divide en dos categorías:

### Artefactos históricos / de referencia

- `Copia de index.html`
- `preview-redesign.html`
- `mock-editorial.html`
- `mock-ejecutiva.html`

Estos archivos pueden conservarse, archivarse o eliminarse según su utilidad histórica; no deben convertirse en fuentes de diseño del producto.

### Afinado por módulo

Todavía puede existir CSS específico antiguo, geometría local o patrones mejorables en superficies no cubiertas por las 26 auditorías. Ese trabajo es **refinamiento**, no coexistencia de dos sistemas de diseño. Debe atacarse módulo por módulo sin reintroducir tokens o chrome paralelos.

`index.html` conserva únicamente bloques auxiliares estrechos y explícitamente exentos necesarios para su dashboard; no constituyen un segundo theme.

## Criterio de terminado

Una pantalla se considera alineada cuando:

- se reconoce como parte del mismo producto que Index y WhatsApp;
- consume la identidad desde Canon;
- no introduce paleta, fuente o geometría global propia;
- usa `app-shell.js` para chrome compartido cuando corresponde;
- mantiene estados y responsive coherentes;
- no altera lógica de negocio para lograr el rediseño;
- pasa los guards aplicables.

## Trabajo paralelo y seguridad

La unificación visual vive en **`agent/frontend-canon-unification`** y su PR apunta a **`agent/architecture-cleanup`**. La auditoría técnica puede seguir avanzando en paralelo; antes de cerrar el PR visual se sincroniza explícitamente con el head técnico vigente y se vuelve a ejecutar Quality.

No se realizan cambios visuales directamente sobre la rama técnica y este PR permanece Draft. No hay merge a `main` ni despliegue de producción implícito en este trabajo.
