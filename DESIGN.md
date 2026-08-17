# Broquer — Contrato de diseño

> **Edición vigente: “Canon” · revisión 2026-08-b.**
>
> La única fuente de verdad **ejecutable** de colores, tipografía, radios,
> sombras, espaciado, motion y componentes es **`brokr-theme.css`**. Este
> documento explica cómo consumirla; no mantiene una segunda copia de sus
> valores. Si este documento y el CSS discrepan, el CSS gana y este documento
> debe corregirse.

## Objetivo

Todo módulo de Broquer debe parecer hecho por el mismo equipo y en la misma
época. Un programador nuevo debe poder crear una pantalla sin inventar una
paleta, una tipografía, un sistema de botones o una geometría propios.

El chrome compartido —sidebar, topbar, navegación móvil, FAB de Broq, drawer de
perfil y encabezado de página— vive en **`app-shell.js`**. Un módulo aporta su
contenido y consume el sistema visual común.

---

## 1. Reglas de oro

1. **Cero colores de producto escritos a mano en un módulo.** Usa tokens
   `var(--…)` de `brokr-theme.css`. Solo se toleran blanco/negro puros cuando
   semánticamente corresponda y colores oficiales de marcas externas.
2. **Una sola familia tipográfica de producto.** La edición Canon usa **Inter**
   mediante `--font-sans`, `--font-display`, `--font-mono` y `--font-serif`.
   Los aliases históricos existen por compatibilidad; no son permiso para
   introducir otra familia.
3. **Tamaños tipográficos solo mediante la escala `--fs-*`.** No inventes
   tamaños en px dentro de un módulo nuevo.
4. **Radios, sombras, espaciado, alturas y motion salen de tokens.** No copies
   números de una pantalla a otra.
5. **Iconos = SVG con `currentColor`.** No uses emojis como iconografía de
   interfaz.
6. **Reutiliza componentes `bk-*` antes de crear una clase nueva.** Una clase
   específica del módulo debe cubrir una necesidad de dominio, no reinventar
   botones, inputs, cards o modales.
7. **Un módulo no elige theme.** No existen “skins” por módulo. Todos heredan
   Canon.
8. **No crees otra hoja de tokens.** Si falta un token verdaderamente global,
   se agrega a `brokr-theme.css`; si es específico de un dominio, usa una clase
   del módulo compuesta con tokens existentes.

---

## 2. Identidad Canon

La dirección actual está definida en `brokr-theme.css`: blanco dominante,
negro/tinta precisa, azul profundo para estructura y azul de acción para
interacción. Los estados semánticos usan los tokens `--success`, `--warn`,
`--danger` e `--info`.

Los colores exactos **no se duplican aquí** a propósito. Consulta los tokens
vigentes en `:root` de `brokr-theme.css`. Esto evita que una futura revisión del
theme deje este documento describiendo una edición muerta.

La paleta de datos (`--data-*`) se reserva para gráficas, etapas y casos donde
el color representa información. No la uses para decorar botones, bordes,
headings o cards.

---

## 3. Tipografía

Toda la interfaz Canon usa los aliases tipográficos del theme:

- `var(--font-sans)` para interfaz y cuerpo.
- `var(--font-display)` para headings.
- `var(--font-mono)` es un alias histórico y actualmente **no implica una
  fuente monoespaciada**.
- `var(--font-serif)` también apunta a la familia Canon vigente; no asumas que
  siempre será serif por el nombre heredado.

Usa `--fs-hero`, `--fs-display`, `--fs-h1`, `--fs-h2`, `--fs-h3`,
`--fs-body-lg`, `--fs-body`, `--fs-sm`, `--fs-xs`, `--fs-label-*` y
`--fs-caption`. Los valores concretos viven únicamente en el theme.

Los números de negocio deben usar cifras tabulares (`.bk-num` o
`font-variant-numeric: tabular-nums`).

---

## 4. Forma y espacio

La geometría Canon se expresa mediante:

- Radios: `--r-xs`, `--r-sm`, `--r`, `--r-lg`, `--r-xl`, `--r-modal`,
  `--r-pill`.
- Espaciado: `--sp-*`.
- Alturas: `--h-sm`, `--h`, `--h-lg`, `--touch-min`.
- Sombras: `--shadow-xs` a `--shadow-xl`.
- Foco: `--focus` y variantes semánticas.
- Motion: `--dur-fast`, `--dur`, `--dur-slow`, `--ease`, `--ease-out`.

No escribas una cifra “porque se parece” a otro componente. Usa el token que
representa la función del elemento.

---

## 5. Anatomía de un módulo

```html
<body data-app="mi-modulo">
  <!-- contenido específico del módulo -->
  <script src="app-shell.js" defer></script>
</body>
```

El shell compartido debe encargarse del chrome y del encabezado de página. Un
módulo no debe dibujar una segunda navegación ni un hero propio para sustituir
el encabezado común.

Mientras `app-shell.js` siga usando metadatos manuales, cualquier módulo nuevo
necesita una entrada coherente en sus registros de navegación. La arquitectura
objetivo es que esos metadatos provengan del contrato declarativo de módulos y
no de listas paralelas; hasta completar esa migración, no crees una tercera
lista.

Anchos de página, gutters, sidebar y topbar se consumen desde los tokens de
layout del theme (`--page-max`, `--form-max`, `--pad-x`, `--sidebar-w`,
`--topbar-h`).

---

## 6. Componentes compartidos

Antes de escribir CSS nuevo revisa los componentes `bk-*` del theme. Entre los
principales están:

- botones e icon buttons;
- fields, labels, inputs, textarea, select, checks y switches;
- chips, badges, eyebrows, alerts y toasts;
- headers, tabs, segmented controls y menus;
- tablas;
- overlays, modales y sheets;
- empty states, skeletons, spinners y loaders;
- métricas y grids;
- cards de propiedades/leads;
- stacks, clusters y divisores.

El principio es más importante que la lista: **si el sistema ya tiene el
componente, úsalo**. Una variante global se arregla en el componente global,
no con veinte overrides de página.

---

## 7. CSS específico de un dominio

Solo crea CSS específico cuando el dominio realmente lo necesite.

1. Prefija la clase con el módulo (`.avm-*`, `.fin-*`, `.wa-*`, etc.).
2. Compón la apariencia usando tokens Canon.
3. No redefinas `:root` desde un módulo.
4. No sobrescribas globalmente un `bk-*` para arreglar una sola pantalla.
5. No introduzcas un segundo archivo “theme-v3”, “nuevo-theme”, “final” o
   equivalente. Git es el historial; producción tiene un solo sistema vivo.

---

## 8. PDFs y contenido generado por backend

Los PDFs también son producto Broquer y deben seguir Canon.

- No mantengas diccionarios de hex y fuentes copiados dentro de routers.
- Los tokens necesarios para impresión deben derivarse del theme canónico a
  través de una capa compartida de backend.
- Un router de dominio define contenido y estructura del documento, no una
  identidad visual alternativa.
- Si el theme no puede cargarse, la infraestructura debe reportar el problema
  explícitamente en lugar de caer silenciosamente a una edición antigua.

Esta regla aplica a reportes de Finanzas, contratos, constancias de Firmas y
cualquier PDF futuro.

---

## 9. Checklist para un módulo nuevo

- [ ] Tiene `data-app` y carga `app-shell.js`.
- [ ] No crea navegación/chrome propios.
- [ ] Consume `brokr-theme.css`; no elige otra piel.
- [ ] Cero colores de producto hardcodeados.
- [ ] Cero familias tipográficas propias.
- [ ] Tamaños, radios, sombras, espacio y motion salen de tokens.
- [ ] Reutiliza `bk-*` antes de inventar componentes.
- [ ] Iconografía SVG con `currentColor`.
- [ ] Estados hover/focus/disabled/loading/error/empty cubiertos cuando aplican.
- [ ] `python3 audit.py <archivo>` termina sin violaciones relevantes.
- [ ] No agrega otra lista manual de metadatos si existe una fuente compartida.
- [ ] Si genera PDF, consume la infraestructura visual compartida del backend.

---

## 10. Regla para futuras revisiones visuales

Una nueva dirección visual no se implementa editando módulos uno por uno. Se
cambian **los valores del sistema canónico** y, solo cuando sea inevitable, los
componentes compartidos. Los nombres de token se mantienen estables siempre que
sea razonable para que el producto pueda cambiar de piel sin reescribir cada
pantalla.

**`brokr-theme.css` es la implementación visual canónica. `DESIGN.md` es su
contrato de uso. No debe existir una tercera fuente de verdad.**
