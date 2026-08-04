# Broquer — Reglas de diseño (edición "Navarro")

> **Este documento describe la piel VIGENTE** (revisión 2026-07-b, "Lienzo
> blanco"). La edición anterior "Sky" (DM Sans, azul #0055CC, radios 14/28)
> quedó obsoleta: cualquier referencia a ella en chats o notas viejas ya no
> aplica. La única fuente de verdad ejecutable es **`brokr-theme.css`**; la
> verificación automática vive en `audit.py` (raíz del repo).

> **Objetivo:** que todo módulo parezca **hermano** de los demás y de
> `index.html`. Un módulo nuevo debe verse como si lo hubiera hecho la misma
> mano que hizo el resto. Este documento es la ley; `brokr-theme.css` es la
> implementación.

El chrome (sidebar azul, topbar, bottom-nav líquida, FAB de Broq, drawer de
perfil y el **encabezado de página** `.bk-ph`) lo inyecta **`app-shell.js`**,
que además re-ancla su `<style>` al final del `<head>` para ganar la cascada.
Un módulo solo aporta *su contenido*.

---

## 0. Las 7 reglas de oro (si no lees más, lee esto)

1. **Cero hex a mano.** Todo color sale de un token `var(--…)`. Únicas
   excepciones: `#fff`/`#000` puros y los tokens de **marca externa**
   (`--brand-whatsapp` #25D366, `--brand-facebook` #1877F2).
2. **Dos paletas, no una.**
   · **INTERFAZ (restringida):** navy `--sky-navy` #00143B = estructura y
     texto (la tinta es navy, no negro); azul royal `--sky-blue` #1240A0 =
     acción (links, foco, CTA, activos). Secundario `--mute`, líneas
     `--line/-2/-3`. Estados solo con `--success #0C7A5E / --warn #B45309 /
     --danger #C62839 / --info`. **Nada de verdes #00AA6C, magentas #E70866,
     azul viejo #0062E3 ni el navy viejo #05203C**: son de ediciones muertas.
   · **DATOS (`--data-1…8`):** prohibida en botones, links, foco, bordes,
     fondos de card y headings. Permitida **solo donde el color ES el dato**
     (ver §2.1).
3. **Una sola tipografía de interfaz: Manrope** vía `--font-sans` /
   `--font-display` (pesos 400–800). `--font-serif` (Instrument Serif) es
   **exclusiva de landing/marketing**: nunca en tablas, filtros, formularios,
   menús ni módulos densos. Nunca monoespaciadas.
4. **Tamaños solo desde la escala `--fs-*`** (§3). Prohibido `font-size` en px
   crudo dentro de módulos. Microcopy (labels, eyebrows, `th`, badges) =
   12–13px, nunca tamaño de heading.
5. **Radios y sombras solo desde tokens:** botón `--r-sm` 8 · input/contenedor
   `--r` 10 · card `--r-lg` 16 · card grande `--r-xl` 22 · modal `--r-modal`
   24 · píldora `--r-pill`. Sombras `--shadow-xs…xl` (tinte navy
   rgba(0,20,59,…) — una sombra negra a mano se ve "de otra app").
6. **Iconos = SVG stroke** (`stroke="currentColor"`), **nunca emojis**.
7. **Reutiliza los componentes `bk-*`** del theme antes de inventar una clase.

---

## 1. Anatomía de un módulo

```
<body data-app="mi-modulo">      ← clave del módulo (obligatoria)
  … tu contenido …               ← el shell lo envuelve en .bk-page
<script src="app-shell.js" defer></script>
```

- El **encabezado de página** (título 30px + subtítulo) lo pinta el shell desde
  `PAGE_META['mi-modulo']`. **No hagas tu propio hero/título de página.**
- Para aparecer en el menú lateral, agrega la entrada a `MODS` en `app-shell.js`.
- El `data-app` activa además la capa de normalización legacy del shell
  (unifica cards, inputs, botones primarios en azul, títulos a 30px).
- Anchos canónicos: `--page-max` 1280 (datos) · `--form-max` 920 (formularios).
  El shell ya estrecha isr/ficha-manual/avm/contratos/mi-sitio/image-cleaner.

## 2. Color

- El **canvas de la app es `--canvas`** (#F4F7FD, teñido). `--paper` es blanco
  y lo consumen superficies flotantes (topbar, dropdowns, popovers): si se
  tiñe, se tiñen ellas. `.bk-card` es `--bone` (blanco) y se lee como card
  gracias al canvas teñido.
- **Sidebar/drawer:** azul `--sb-bg` (= `--sky-blue`) con destello blanco
  arriba y aurora abajo; módulos en blanco y negritas dentro de bloques
  translúcidos `--sb-panel`. La separación se hace con aire y paneles, nunca
  con líneas.
- **Botones:** primario por default = **navy sólido** (`.bk-btn`); el azul de
  acción (`.bk-btn--forest`, `--forest` = #1240A0) es para el CTA de
  conversión, no el default. Máximo un primario dominante por zona. En módulos
  legacy el shell fuerza el botón principal a azul.
- Texto sobre navy: usar `--sky-blue-on-dark` #7FA8F0 (7.5:1); el azul de
  acción no contrasta sobre navy.

### 2.1 Paleta de datos — `--data-1 … --data-8`

| Uso | Token |
|-----|-------|
| Series categóricas de gráficas | `--data-1…8` (+ `-soft` al 12%) |
| Etapas de pipeline / kanban | `--etapa-{nuevo,activo,contactado,cerrado,descartado}` |
| Módulo WhatsApp | `--wa-{canvas,out,ia,out-meta}` |

- La rampa está **ordenada por distinguibilidad**: empieza en `--data-1` y
  avanza; nunca elijas por gusto.
- **Nunca uses `--success/--warn/--danger` como color categórico** (rojo se
  lee "error").
- Las etapas son **ordinales** (frío → comprometido → verde ganado → gris
  muerto). A una escala ordinal le corresponde degradado de un tono o
  progresión verde→ámbar→rojo, no colores categóricos.
- WhatsApp es el único módulo donde el verde deja de ser solo el botón de
  conectar. Las burbujas son CLARAS con texto oscuro (nunca color sólido +
  blanco): verde claro `--wa-out`/`--wa-out-ink` = mensaje del agente,
  violeta claro `--wa-ia-soft` con tinta y meta `--wa-ia` = Broq, blanco con
  hairline = el cliente. El lienzo del hilo es `--wa-canvas` (frío, hermano
  de `--canvas`), sin patrones de puntos.

## 3. Tipografía — escala `--fs-*`

`--fs-hero` 64 (solo landing) · `--fs-display` 42 · `--fs-h1` 36 ·
`--fs-h2` 24 · `--fs-h3` 20 · `--fs-h5` 17 · `--fs-body-lg` 18 ·
`--fs-body` 16 · `--fs-sm` 14 · `--fs-xs` 13 · `--fs-label-1/2/3` 15/13/12 ·
`--fs-caption` 11.

- Headings: `--font-display`, peso 700, tracking negativo (ya lo trae el theme).
- El título de página que pinta el shell (`.bk-ph__title`) es 30px: entre
  `--fs-h2` y `--fs-h1`, uniforme en toda la app.
- **Microcopy** (eyebrow, label, badge, `th`, status): `--fs-label-3` (12) o
  `--fs-caption` (11). *Nunca* a tamaño de heading.
- Números siempre tabulares (`.bk-num` o `font-variant-numeric: tabular-nums`).

## 4. Forma — radios, sombras, espaciado, foco

- Geometría: botón 8 · input 10 · card 16 · card grande 22 · modal 24 ·
  chips/tabs/píldoras `--r-pill`. Altura de control `--h` 48 (`--h-sm` 40,
  `--h-lg` 56); mínimo táctil `--touch-min` 44.
- Sombras `--shadow-xs → --shadow-xl` (tinte navy). La card NO lleva sombra
  por default (`.bk-card--raise` solo donde agregue jerarquía).
- Espaciado: escala `--sp-1…24` (base 4px). Gutter lateral `--pad-x` 40
  (24 tablet, 16 móvil).
- Foco: `box-shadow: var(--focus)` (nunca un anillo propio). Sobre el sidebar
  azul el shell usa anillo blanco interior.
- Motion: `--dur-fast` .12s · `--dur` .18s · `--dur-slow` .28s con `--ease` /
  `--ease-out`. `prefers-reduced-motion` ya está cubierto por el theme.

## 5. Componentes `bk-*` disponibles (no reinventar)

Botón `.bk-btn` (+`--forest/--ghost/--quiet/--danger/--sm/--lg/--block`,
`.is-loading`) · icono `.bk-icon-btn` · campo `.bk-field` `.bk-label`
`.bk-input` `.bk-textarea` `.bk-select` `.bk-input-affix` `.bk-check`
`.bk-switch` · `.bk-chip` · `.bk-badge` (+ estados) · `.bk-eyebrow` ·
`.bk-page-header` / `.bk-section-header` · `.bk-tabs`/`.bk-tab` · `.bk-seg` ·
`.bk-menu` · `.bk-tooltip` · `.bk-table` · `.bk-overlay`+`.bk-modal`
(+`--sheet/--full` móvil) · `.bk-empty` · `.bk-alert` · `.bk-toast` ·
`.bk-skeleton`/`.bk-spinner`/`.bk-shark-loader` · `.bk-metric`+
`.bk-metric-grid` · `.bk-prop-card` · `.bk-lead-card` · `.bk-stack` ·
`.bk-cluster` · `.bk-divider`.

**El modelo a imitar es `estadisticas.html`**: usa `bk-card`, `bk-seg`,
`bk-tabs` y solo añade una capa `es-*` mínima para lo específico.

> **Reservado:** `.bk-badge` es el badge de estado del theme. El globito rojo
> de no-leídos del shell vive acotado en `.bk-bnav__ico .bk-badge` /
> `.bk-sheet__ico .bk-badge` — no reutilices ese patrón fuera de ahí.

## 6. Si necesitas CSS propio

1. ¿Existe un componente `bk-*`? → úsalo.
2. ¿Es una variante puntual? → clase con prefijo del módulo (`.avm-…`,
   `.tk-…`) que **compone tokens**.
3. Nunca redefinas `:root` ni tokens del sistema dentro de un módulo.
4. Si te falta un nombre de token, **agrégalo como alias** en la capa de
   compatibilidad al final de `brokr-theme.css` — no hardcodees un hex.

## 7. Checklist para un módulo nuevo (o auditar uno existente)

- [ ] `<body data-app="…">` y `app-shell.js` cargado con `defer`.
- [ ] Registrado en `PAGE_META` (título/subtítulo) y en `MODS` (nav) del shell.
- [ ] No define su propio hero/título de página (lo pinta el shell).
- [ ] `python3 audit.py mi-modulo.html` → **0 violaciones**.
- [ ] **0** `#hex` fuera de blanco/negro/marca · **0** `font-family` fuera de
  `var(--font-*)` · **0** `font-size` en px crudo · **0** radios/sombras a
  mano · **0** emojis como icono.
- [ ] Botón primario navy (o azul si es el CTA del módulo), secundario ghost,
  danger solo contorno.
- [ ] Estados cubiertos: hover, focus-visible, disabled, loading, error, empty.
- [ ] Reutiliza `bk-*` donde el sistema ya lo ofrece.
