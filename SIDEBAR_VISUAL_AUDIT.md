# Sidebar visual audit — active product only

Scope is intentionally limited to pages reachable from the `app-shell.js` sidebar.

## Confirmed structural outliers

- `estadisticas.html`: historical standalone hero / floating module navigation.
- `avm.html`: standalone navy header + dark tab strip.
- `contactos.html`: own sticky page header and page-specific width rhythm.
- `leads.html`: own sticky page header and page-specific width rhythm.
- `propiedades.html`: own header metrics separate from the shell rhythm.
- `tareas.html`: own header metrics separate from the shell rhythm.
- `isr.html`: legacy local skin still overrides broad element families; requires a separate bounded pass after the first composition cut.

## Screens reviewed that already compose acceptably with the shell

- `bolsa.html`
- `correo.html`
- `firmas.html`
- `cumplimiento.html`

These may still receive detail polish later, but they do not currently show the same level of structural divergence as the outliers above.

## Current cut

1. Flatten Estadísticas into a white operational surface.
2. Normalize header width/rhythm for Propiedades, Contactos, Tareas and Leads.
3. Flatten AVM's standalone navy chrome into the common white product skeleton.
4. Preserve all IDs, event handlers, data loading and backend behavior.
5. Keep non-sidebar pages out of scope.
