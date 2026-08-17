# Broquer — Auditoría de unificación visual

## Estado actual

La unificación visual de las superficies activas de Broquer alcanzó su objetivo estructural y el inventario activo ya está cubierto de extremo a extremo:

- **`index.html`** es la referencia de identidad general;
- **`whatsapp.html`** es la referencia de interacción densa/productiva;
- **`brokr-theme.css`** es la única implementación ejecutable del sistema visual;
- **`app-shell.js`** es el único propietario del chrome compartido de la aplicación;
- los módulos conservan únicamente layout y comportamiento específicos de su dominio;
- **42 superficies activas de Broquer** se auditan automáticamente en Quality.

La migración preservó rutas, IDs, contratos de API y lógica de negocio. Los archivos grandes se modificaron mediante transformaciones determinísticas, auditorías dirigidas y comprobación exacta de archivos cambiados.

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
8. Mantener SVG/iconografía con `currentColor` cuando corresponda y no introducir emojis como iconos de UI.
9. Preservar estados hover/focus/disabled/loading/error/empty y funcionamiento móvil.
10. Pasar los guards de `tests/test_frontend_canon_contract.py` y `audit.py` antes de considerar una superficie migrada.

## Trabajo completado

### Base y protección

- [x] `brokr-theme.css` establecido como única fuente ejecutable de verdad.
- [x] `_TEMPLATE-modulo.html` alineado con Canon y shell compartido.
- [x] `tests/test_frontend_canon_contract.py` creado como ratchet permanente.
- [x] Quality ampliado hasta cubrir **42 superficies activas Canon**.
- [x] El modo sin argumentos de `audit.py` refleja el inventario activo y excluye solamente el motor de sitios públicos, la plantilla de desarrollo y artefactos históricos.
- [x] `broquer-ui.css` eliminado por completo.
- [x] Cero HTML de producto debe definir `.app-sidebar`.

### Autenticación y superficies públicas Broquer

- [x] `login.html`
- [x] `registro.html`
- [x] `reset-password.html`
- [x] `unirse.html`
- [x] `aviso-privacidad.html`
- [x] `facebook-callback.html`
- [x] `whatsapp-callback.html`
- [x] `landing.html`
- [x] `blog.html`

Landing ya no tiene el namespace `--b2-*` ni carga tipografía independiente; conserva contenido, SEO, video, navegación y CTAs sobre Canon.

### Núcleo y shell compartido

- [x] `index.html`
- [x] `whatsapp.html`
- [x] `contactos.html`
- [x] `leads.html`
- [x] `propiedades.html`
- [x] `isr.html`
- [x] `estadisticas.html`
- [x] `bandeja.html`

En Contactos, Leads, Propiedades e ISR se retiraron copias de chrome/sidebar que competían con `app-shell.js`. Estas migraciones no implican que toda regla de dominio haya sido reescrita; sí garantizan que identidad y chrome compartidos no vuelvan a bifurcarse.

### Herramientas, operación y canales

- [x] `bolsa.html`
- [x] `expediente.html`
- [x] `ficha-manual.html`
- [x] `firmar.html`
- [x] `firmas.html`
- [x] `verificar-firma.html`
- [x] `verificador.html`
- [x] `guia-agente.html`
- [x] `legal.html`
- [x] `avm.html`
- [x] `contratos.html`
- [x] `image-cleaner.html`
- [x] `correo.html`
- [x] `whatsapp-chatgpt.html`
- [x] `robin.html`
- [x] `tareas.html`
- [x] `finanzas.html`
- [x] `cumplimiento.html`
- [x] `video.html`
- [x] `facebook-ads.html`
- [x] `mi-sitio.html`
- [x] `equipo.html`
- [x] `empresas.html`
- [x] `admin.html`
- [x] `soporte.html`

Estas superficies conservan su densidad y layout de dominio, pero comparten paleta, tipografía, geometría, estados y reglas estructurales desde Canon.

## Últimos cuatro outliers — RESUELTOS

El barrido completo de 41 superficies previo a incluir Blog encontró solo cuatro incumplimientos reales:

### `isr.html`

- Dos reglas de CTA usaban tinta negra como superficie de acción.
- Se movieron a los tokens azules de acción Canon sin alterar cálculo, formulario ni PDF.

### `bandeja.html`

- Un tamaño tipográfico fijo y un glifo `✕` quedaban fuera del contrato.
- Se sustituyeron por escala tipográfica Canon y texto accesible `Cerrar`.

### `legal.html`

- Conservaba una skin histórica con colores y geometría hardcodeados.
- Se reemplazó únicamente la capa visual; contenido jurídico y navegación por pestañas permanecen intactos.

### `verificador.html`

Era el último outlier grande: usaba aliases visuales históricos no definidos por Canon, numerosos hardcodes, emoji como iconografía y una copia oculta del shell.

Se migró manteniendo intactos checklist, IDs, handlers y flujo de análisis IA:

- CSS reconstruido sobre tokens Canon;
- aliases históricos eliminados;
- copia oculta de sidebar eliminada;
- estados y acciones expresados con texto/SVG-neutral en lugar de emoji;
- auditor dirigido ejecutado antes de permitir el commit.

El transformador y workflow temporales usados para esta migración fueron eliminados después de validar el resultado; no quedó andamiaje de una sola vez en el repositorio.

## Validación automática

Último estado global limpio validado antes de la siguiente sincronización con la rama técnica:

- **238 tests: pasan.**
- **42 superficies en `audit.py`: 0 violaciones.**
- **`scripts/architecture_debt.py`: pasa; la deuda no creció.**
- `direct_env_reads`: 0.
- `duplicated_auth_helpers`: 0.
- `service_key_fallbacks`: 0.
- `embedded_jwt_secrets`: 0.
- `fail_open_webhook_secrets`: 0.
- `fail_open_entitlements`: 0.
- `direct_supabase_rest`: 1, todavía contenido en `main.py` y dentro de su ceiling.
- Los 10 archivos de código mayores a 100 KB permanecen dentro de sus ceilings; `whatsapp.html` sigue por debajo de su límite estricto.

Quality protege específicamente contra:

- reaparición de una segunda hoja visual;
- nuevos `:root` de producto en superficies migradas;
- regreso de Bricolage/Figtree o `--b2-*` en autenticación/Landing;
- HTML que vuelva a apropiarse del sidebar;
- aliases visuales históricos en módulos migrados;
- emojis usados como iconografía de interfaz;
- regresiones auditables de color, contraste, tipografía, geometría y hardcodes en las superficies activas.

## Superficies deliberadamente fuera del Canon de la app

### Motor de sitios públicos de agentes

- `sitio.html`
- `404.html`

Estas páginas cargan `sitio.css` / `sitio-engine.js` y representan los sitios públicos generados para agentes/clientes. **No son UI de la aplicación Broquer** y no deben heredar `app-shell.js` ni ser forzadas a parecerse al dashboard. Su exclusión es arquitectónica y deliberada, no deuda pendiente.

### Artefactos históricos / de referencia

- `Copia de index.html`
- `preview-redesign.html`
- `mock-editorial.html`
- `mock-ejecutiva.html`
- `videos/landing.html` cuando se use como referencia/demo aislada.

Estos archivos no son fuentes de diseño del producto. Pueden conservarse, archivarse o eliminarse según su utilidad histórica, pero no deben influir en nuevas superficies.

## Deuda visual restante

La deuda de **sistema visual activo** queda cerrada por contrato: el inventario activo conocido está cubierto por Canon y por auditoría automática.

Puede seguir existiendo refinamiento de UX o CSS específico de dominio —densidad, microinteracciones, jerarquías locales, simplificación de markup—, pero ya no existe una segunda identidad visual ejecutable que compita con Canon. Cualquier refinamiento futuro debe reducir complejidad sin reintroducir tokens, chrome o skins paralelos.

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

La unificación visual vive en **`agent/frontend-canon-unification`** y su PR apunta a **`agent/architecture-cleanup`**. La auditoría técnica sigue avanzando en paralelo mediante ciclos de migración protegidos. La rama visual solo se sincroniza con estados técnicos terminados y limpios; no incorpora workflows/scripts temporales a mitad de un ciclo.

Antes de considerar listo el PR visual se sincroniza explícitamente con el último head técnico terminado y se vuelve a ejecutar Quality completo.

No se realizan cambios visuales directamente sobre la rama técnica y este PR permanece Draft. No hay merge a `main` ni despliegue de producción implícito en este trabajo.
