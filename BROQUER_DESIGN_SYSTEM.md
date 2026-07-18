# Broquer — Design System Editorial Estate

## Índice
1. ADN visual de referencia
2. Tokens listos para código
3. Especificación de componentes
4. Mapa de aplicación referencia → Broquer
5. Implementación aplicada
6. QA visual

## 1. ADN visual de referencia

### Principios de diseño
1. **Navy estructural, azul de acción.** Usar `--sky-navy-deep`, `--sky-navy` y `--sky-navy-mid` para navegación, footer, paneles oscuros y glass cards; usar `--sky-blue` solo para CTA, foco y estado activo.
2. **Fondos alternados, nunca plantilla plana.** Alternar `--surface-white`, `--surface-off` y `--surface-cold` por sección; una pantalla no debe tener más de dos secciones consecutivas con el mismo fondo.
3. **Titulares editoriales.** H1/H2 usan `--font-display` (Instrument Serif), `line-height` entre `.91` y `1.02`, tracking de `-0.045em` a `-0.04em`; una palabra clave puede ir en cursiva con `--forest`.
4. **UI geométrica y legible.** Navegación, inputs, botones, tablas y microcopy usan `--font-sans` (Manrope), peso 400/600/700, body `1.7` de interlineado.
5. **Elevación suave con tinte navy.** Cards base no llevan sombra por defecto; hover usa `--shadow`; overlay premium usa `.bk-card--glass-navy` con `--glass-navy`, `--glass-line` y `--glass-blur`.
6. **Fotografía inmobiliaria premium.** Imágenes de propiedades usan `--photo-filter`: saturación contenida, contraste leve y luz natural; encuadres amplios sin filtros de color agresivos.
7. **Iconografía fina.** Íconos existentes mantienen SVG lineal con `currentColor`; no se agregan emojis ni ilustraciones nuevas.

## 2. Tokens listos para código

La hoja canónica es `brokr-theme.css`; `globals.css` importa esa fuente para builds modernos.

```css
@import './brokr-theme.css';
```

Tailwind queda configurado en `tailwind.config.js` con colores `navy`, `blue`, `surface`, tipografías `sans/display/serif`, radios, sombras y breakpoints derivados de CSS variables.

## 3. Especificación de componentes

| Componente | Existe en Broquer | Regla visual | Estados |
|---|---:|---|---|
| Botón `.bk-btn` | Sí | Primario navy, CTA azul solo con `.bk-btn--forest`, radio `--r-sm`, altura `--h` | default/hover/active/focus/disabled ya cubiertos por tokens |
| Input/select/textarea | Sí | Fondo `--paper`, borde `--line-2`, foco `--forest` + `--focus`, radio `--r` | default/hover/focus/error/disabled |
| Badge/chip | Sí | Píldora `--r-pill`, microcopy `--fs-caption`/`--fs-sm`, estados semánticos suaves | default/hover en chip, estados semánticos en badge |
| Card | Sí | Base blanca con borde frío; elevada solo con `--raise` o hover | default/hover/navy/glass |
| Navbar/sidebar | Sí | Navy profundo, enlaces blancos al 68%, activo con superficie translúcida | default/hover/active |
| Stat cards | Sí | Número serif/display, etiqueta sans pequeña | default/delta up/down |
| Tablas | Sí | Encabezado discreto, filas aireadas, hover frío | default/hover/sticky |
| Property/lead cards | Sí | Imagen con filtro premium, tarjeta blanca, radio amplio | default/hover |
| Hero con foto + glass card de referencia | Parcial | Aplicable como lenguaje a landing/marketing, no como estructura nueva | no aplica a módulos densos si no hay hero real |
| Métricas/textos específicos de la referencia | No | No se incorporan | no aplica |

## 4. Mapa de aplicación referencia → Broquer

| Pantalla | Antes | Regla de cambio visual |
|---|---|---|
| Landing | Hero navy más rígido, display sans | Mantener estructura y copy; cambiar a display serif, azul claro para énfasis, fondos alternados y cards más amplias |
| App shell | Navegación funcional existente | Mantener rutas y auth; actualizar navy profundo, hover sutil y topbar glass blanco |
| Dashboard/módulos CRM | Cards densas sin lenguaje editorial | Mantener datos y layout; aplicar tokens de surface, radio amplio, sombras suaves y jerarquía tipográfica |
| Propiedades/leads | Cards existentes | Mantener interacción; aplicar filtro fotográfico, borde frío y hover elevado |
| Tablas/charts | UI densa existente | Mantener columnas y cálculos; solo reducir ruido visual con headers discretos y superficies frías |

### Antipatrones
- No copiar secciones, métricas, textos ni módulos de la referencia.
- No introducir nuevas rutas, estados, hooks, endpoints ni props.
- No usar hex o tamaños sueltos en componentes; declarar token primero.
- No usar serif en tablas, filtros o formularios densos salvo títulos.

## 5. Implementación aplicada

1. **Base:** `brokr-theme.css` ahora define la piel Editorial Estate con navy profundo, azul claro de acción, superficies frías, radios amplios, sombras navy, helper glass y filtro fotográfico.
2. **Tailwind:** `tailwind.config.js` expone los mismos tokens para componentes futuros.
3. **Globals:** `globals.css` sirve como entrypoint pegable y mantiene `brokr-theme.css` como única fuente visual.

## 6. QA visual

- Contraste objetivo: texto principal sobre blanco/off-white ≥ AA; CTA navy/azul con texto blanco ≥ AA.
- Grid: usar `--pad-x`, `--page-max`, `--form-max` y escala `--sp-*`.
- Estados: validar focus visible en `.bk-btn`, `.bk-input`, `.bk-tab`, `.bk-seg__btn`, `.bk-menu__item`.
- Responsive: breakpoints 640/768/1024/1280/1440.
- No aplica documentado: módulos, copies y métricas de referencia que no existen en Broquer.
