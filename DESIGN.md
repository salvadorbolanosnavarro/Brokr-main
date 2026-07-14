# Broquer — Reglas de diseño (sistema "Sky")

> **Nota (2026-07):** los tokens de la capa "Upgrade Premium" se consolidaron
> como valores canónicos del `:root` principal. Ya no existe redefinición
> tardía de tokens dentro del theme: una sola fuente, un solo valor.
> Azul de acción canónico: `#0055CC` (press `#003D99`). Radios: `--r` 14,
> `--r-lg` 28. La verificación automática vive en `audit.py` (raíz del repo).

> **Objetivo:** que todo módulo parezca **hermano** de los demás y de `index.html`.
> Un módulo nuevo debe verse como si lo hubiera hecho la misma mano que hizo el
> resto. Este documento es la ley; `brokr-theme.css` es la implementación.

La única fuente de verdad visual es **`brokr-theme.css`**. El chrome (sidebar,
topbar, bottom-nav, FAB de Broq, drawer de perfil y el **encabezado de página**)
lo inyecta **`app-shell.js`**. Un módulo solo aporta *su contenido*.

---

## 0. Las 7 reglas de oro (si no lees más, lee esto)

1. **Cero hex a mano.** Ningún color literal (`#00AA6C`, `rgba(0,0,0,.1)`…). Todo
   color sale de un token `var(--…)`. Única excepción: `#fff`/`#000` puros y los
   tokens de **marca externa** (`--brand-whatsapp`, `--brand-facebook`).
2. **Paleta restringida:** navy `--sky-navy` = estructura, azul `--sky-blue`/
   `--forest` = acción. Texto `--ink`, secundario `--mute`, líneas `--line`.
   Estados solo con `--success / --warn / --danger / --info`. **Nada de verdes
   `#00AA6C`, ámbar `#E8910C`, morados, teal decorativo, ni azules distintos.**
3. **Una sola tipografía:** DM Sans vía `--font-sans` / `--font-display`. Nunca
   `Inter`, `Segoe UI`, `Georgia`, `ui-monospace`, ni `-apple-system` suelto.
   Pesos **400 y 700** únicamente (700 en headings/labels).
4. **Tamaños solo desde la escala** `--fs-*` (ver §3). Prohibido `font-size` en px
   crudo. **Los labels/eyebrows/subtítulos son microcopy → 12-13px**, nunca 18-26px.
5. **Radios y sombras solo desde tokens:** cards `var(--r-lg)`, controles
   `var(--r)`, píldoras `var(--r-pill)`; sombras `var(--shadow-*)`. Nada de
   `border-radius:16px` ni `box-shadow:0 4px 20px rgba(0,0,0,.1)` a mano.
6. **Iconos = SVG stroke** (`stroke-width="1.6"`, `stroke="currentColor"`),
   normalmente dentro de un *tile* navy. **Nunca emojis** (`✅ 🏠 ⚠️`) como icono.
7. **Reutiliza los componentes `bk-*`** del theme antes de inventar una clase.
   Si el sistema ya tiene botón/input/card/modal/tabla/badge/empty, úsalo.

---

## 1. Anatomía de un módulo

```
<body data-app="mi-modulo">      ← clave del módulo (obligatoria)
  … tu contenido …               ← el shell lo envuelve en .bk-page
<script src="app-shell.js" defer></script>
```

- El **encabezado de página** (título + subtítulo grande) lo pinta el shell desde
  `PAGE_META['mi-modulo']` en `app-shell.js`. **No hagas tu propio hero/título de
  página**: regístralo ahí y el shell inyecta `.bk-ph` idéntico al de sus hermanos.
- El `data-app` también activa la capa de normalización `body[data-app]` del shell
  y marca el ítem activo en la navegación.
- Para que aparezca en el menú lateral, añade una entrada a `MODS` en `app-shell.js`
  (`{ key, href, label, group, icon }`).

## 2. Color — tokens (nunca hex)

| Uso | Token |
|-----|-------|
| Estructura (nav, footer, tiles de icono, cards oscuras) | `--sky-navy` |
| Acción (CTA, botón primario, foco, links activos) | `--sky-blue` / `--forest` |
| Texto principal / secundario / tenue | `--ink` / `--ink-2` / `--mute` |
| Superficie card / canvas / hover | `--bone` / `--paper-2` / `--shell` |
| Líneas y bordes | `--line` / `--line-2` |
| Éxito / advertencia / error / info | `--success` / `--warn` / `--danger` / `--info` (+ `-soft` para fondos) |
| **Marca externa (solo su superficie)** | `--brand-whatsapp` · `--brand-facebook` |

Los colores de marca externa **solo** van en el botón/icono de esa integración
(“Conectar WhatsApp”, “Conectar Facebook”). Prohibido usarlos como acento general.

## 3. Tipografía — escala `--fs-*`

`--fs-display` 40 · `--fs-h1` 36 · `--fs-h2` 28 · `--fs-h3` 22 · `--fs-h5` 18 ·
`--fs-body-lg` 20 · `--fs-body` 17 · `--fs-sm` 15 · `--fs-xs` 13 ·
`--fs-label-1/2/3` 16/14/12 · `--fs-caption` 11.

- Headings: `--font-display`, peso **700**.
- Cuerpo: `--font-sans`, peso 400.
- **Microcopy** (eyebrow, label, badge, `th`, subtítulo mono, status): `--fs-label-3`
  (12) o `--fs-caption` (11). *Nunca* a tamaño de heading — es el bug histórico
  que ya se corrigió en los componentes `bk-*` y no debe reintroducirse.

## 4. Forma — radios, sombras, espaciado

- Cards / modales: `--r-lg`. Inputs / botones / contenedores: `--r`.
  Botones-icono: `--r-sm`. Chips / tabs / píldoras: `--r-pill`.
- Sombras: `--shadow-xs → --shadow-xl` (llevan tinte azul del sistema; una sombra
  negra a mano se ve “de otra app”).
- Espaciado: escala `--sp-1…16` (base 4px).
- Foco: `box-shadow: var(--focus)` (nunca un anillo propio).

## 5. Componentes `bk-*` disponibles (no reinventar)

Botón `.bk-btn` (+`--forest/--ghost/--quiet/--danger/--sm/--lg/--block`) ·
icono `.bk-icon-btn` · campo `.bk-field` `.bk-label` `.bk-input` `.bk-textarea`
`.bk-select` `.bk-check` `.bk-switch` · `.bk-chip` · `.bk-badge` (+ estados) ·
`.bk-eyebrow` · `.bk-page-header` / `.bk-section-header` · `.bk-tabs`/`.bk-tab` ·
`.bk-seg` (segmented) · `.bk-menu` (dropdown) · `.bk-table` · `.bk-overlay`+
`.bk-modal` · `.bk-empty` · `.bk-alert` · `.bk-toast` · `.bk-skeleton`/`.bk-spinner`/
`.bk-shark-loader` · `.bk-prop-card` · `.bk-lead-card`.

**El módelo a imitar es `estadisticas.html`**: usa `bk-card`, `bk-seg`, `bk-tabs`
y solo añade una capa `es-*` mínima para lo específico (gráficas).

## 6. Si necesitas CSS propio

1. ¿Existe un componente `bk-*`? → úsalo.
2. ¿Es una variante puntual? → clase con prefijo del módulo (`.avm-…`, `.tk-…`) que
   **compone tokens** (`background:var(--bone);border-radius:var(--r-lg)`).
3. Nunca redefinas `:root` ni tokens del sistema dentro de un módulo.
4. Si te falta un nombre de token, **agrégalo como alias** en la capa de
   compatibilidad al final de `brokr-theme.css` — no hardcodees un valor.

## 7. Checklist para un módulo nuevo (o auditar uno existente)

- [ ] `<body data-app="…">` y `app-shell.js` cargado con `defer`.
- [ ] Registrado en `PAGE_META` (título/subtítulo) y en `MODS` (nav) del shell.
- [ ] No define su propio hero/título de página (lo pinta el shell).
- [ ] `grep` del archivo → **0** `#hex` fuera de blanco/negro/marca.
- [ ] **0** `font-family` que no sea `var(--font-*)`.
- [ ] **0** `font-size` en px crudo; todo `var(--fs-*)`. Microcopy ≤ 13px.
- [ ] **0** `border-radius`/`box-shadow` en px/rgba a mano.
- [ ] Iconos SVG stroke 1.6; **0 emojis** como icono.
- [ ] Botón primario azul, secundario navy/ghost, todos píldora.
- [ ] Reutiliza `bk-*` donde el sistema ya lo ofrece.

> Comprobación rápida:
> `grep -oE '#[0-9a-fA-F]{3,6}' mi-modulo.html | sort -u`
> — cualquier hex que no sea `#fff/#000/#25D366/#1877F2` es una violación.
