# Sidebar visual audit — active product only

Scope is intentionally limited to pages reachable from the `app-shell.js` sidebar.

## Structural outliers fixed in this cut

- `estadisticas.html`: historical standalone hero / floating module navigation.
- `avm.html`: standalone navy header + dark tab strip.
- `contactos.html`: own sticky page header and page-specific width rhythm.
- `leads.html`: own sticky page header and page-specific width rhythm.
- `propiedades.html`: own header metrics separate from the shell rhythm.
- `tareas.html`: own header metrics separate from the shell rhythm.

## Screens reviewed that already compose acceptably with the shell

- `bolsa.html`
- `whatsapp.html` — intentionally denser/wider because the primary content is a conversation console; it still uses Canon surfaces and tokens.
- `correo.html`
- `contratos.html`
- `firmas.html`
- `cumplimiento.html`
- `isr.html` — contains legacy CSS debt, but the rendered page content already sits under the shell header on a centered form canvas; refactoring that stylesheet is not required for this visual cut.
- `finanzas.html`
- `image-cleaner.html`
- `ficha-manual.html`
- `facebook-ads.html` — branded preview/content is functional content, not alternate application chrome.
- `video.html`
- `mi-sitio.html`
- `blog.html`
- `guia-agente.html`

These pages can still receive detail polish later, but their functional content is not the same class of structural divergence as the six corrected outliers.

## Explicit exception

- `admin.html` is reachable from the sidebar for admins but `app-shell.js` deliberately excludes it from the shared shell. It therefore remains a standalone console with its own top bar. Removing that exception is not a safe CSS-only change: it requires a bounded shell/layout compatibility pass and is intentionally not mixed into this visual-only cut.

## Current cut

1. Flatten Estadísticas into a white operational surface.
2. Normalize header width/rhythm for Propiedades, Contactos, Tareas and Leads.
3. Flatten AVM's standalone navy chrome into the common white product skeleton.
4. Preserve all IDs, event handlers, data loading and backend behavior.
5. Keep non-sidebar pages out of scope.
6. Record Admin separately instead of disguising a functional shell exception as cosmetic work.
