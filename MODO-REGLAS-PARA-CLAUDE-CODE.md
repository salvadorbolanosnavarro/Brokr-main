# "modo" — sistema de diseño propuesto en el prototipo de ChatGPT

> **Estado: NO integrado en este repositorio.** Este documento existe solo como
> registro de lo que se diseñó en los prototipos de ChatGPT Work
> (`modo-espacio-modular.salvadorbolanosnavar.chatgpt.site` y
> `broquer-workspace.salvadorbolanosnavar.chatgpt.site`). Ese código vive
> únicamente en esos sitios; nunca se subió a este repo.
>
> **Conflicto detectado con el canon vigente del repo real** (ver
> `DESIGN.md` y `FRONTEND_CANON_AUDIT.md`): Broquer ya tiene un sistema de
> diseño único y obligatorio ("Canon"), implementado en `brokr-theme.css`,
> con **Inter** como única tipografía de producto y una auditoría automática
> (`audit.py`, `tests/test_frontend_canon_contract.py`,
> `tests/test_frontend_canon_inventory.py`) que **falla la build** si una
> superficie define su propio `:root`, otra hoja de tokens, u otra familia
> tipográfica. El sistema "modo" descrito abajo usa Manrope y una paleta
> `--sky/--orange/...` distinta — aplicarlo tal cual rompería ese contrato y
> reintroduciría el "doble sistema visual" que el equipo ya resolvió una vez
> (ver sección "Doble sistema visual — RESUELTO" en `FRONTEND_CANON_AUDIT.md`).
>
> Antes de portar cualquier pieza de "modo" a producción hay que decidir,
> con el usuario, una de estas rutas — no asumir ninguna:
> 1. Adaptar la *intención* de "modo" (jerarquía, tamaños táctiles,
>    composición de pantallas) usando los tokens y componentes `bk-*` de
>    Canon que ya existen — sin nueva tipografía ni nueva paleta.
> 2. Actualizar el propio Canon (`brokr-theme.css`) si el usuario decide que
>    Manrope/la paleta nueva reemplazan a Inter/la paleta actual en *todo*
>    el producto (impacto en 42+ superficies auditadas).
> 3. Dejarlo como referencia de diseño, sin portarlo.

## Contenido original del prototipo (para referencia, no para copiar literal)

Sistema de diseño mobile-first, luego escritorio, para agentes inmobiliarios
mexicanos de todas las edades y niveles tecnológicos, con 3 pantallas:
Inicio, Campañas y Agenda. Referencia visual: precisión tecnológica tipo
Apple, sin plantilla genérica de IA (barra lateral + tarjetas redondeadas +
colores pastel).

### Paleta de color (tokens del prototipo, no del repo real)

```
--sky: #9FD8F5            (contexto/resultados)
--sky-soft: #E7F4FC        (agenda, selección suave)
--sky-ink: #165474          (texto sobre azul)
--orange: #FF9257           (acción principal, acento de marca)
--orange-ink: #813B12       (etiqueta temporal)
--ink: #191C1F              (texto principal)
--white: #FFFFFF            (fondo)
--surface: #F5F6F7          (agrupaciones secundarias)
--muted-ink: #61666C        (texto secundario)
--line: #E4E6E8             (divisiones)
--control-border: #7C858D
--ring: #2675A3             (foco de teclado)
--green: #246B48             (estado activo)
--destructive: #B42318       (error)
Facebook oficial: #0866FF (logo oficial, nunca recolorear a marca propia)
```

Reglas de aplicación de color: blanco domina, negro da precisión, azul y
naranja orientan. Botón naranja siempre con texto negro (nunca texto blanco
chico sobre naranja o azul cielo). Sin degradados, glassmorphism ni halos
decorativos. Tema claro únicamente.

### Tipografía

Manrope autoalojada (pesos 400/500/600/700/800, licencia SIL OFL). Usar rem.
Interlineado 1.5–1.7 en texto, 1.15–1.4 en títulos. No reducir el texto para
usuarios de mayor edad — dos tamaños de fuente están permitidos si hace
falta.

Escala: título de pantalla 32px móvil / 42–48px escritorio · título de
sección 18/20px · nombre de herramienta 16/18–19px · texto principal 16px ·
botón 15–16px · descripción 14–15px · metadato 12–13px.

### Breakpoints (por ancho de contenedor, no por detección de dispositivo)

- 320–479px: cabecera 74px, nav inferior, 1 columna (herramientas en 2
  columnas), margen 24px (16px bajo 360px)
- 480–767px: igual estructura, margen 32px
- 768–1023px: cabecera 88px, nav horizontal, columnas para
  herramientas/visita, margen 40px
- ≥1024px: nav horizontal, margen 48px, separación entre columnas 60–72px
- ≥1400px: contenido centrado, máx 1256px, panel de visita 360px

### Componentes clave y estados

- Navegación: 3 rutas + acceso móvil a Herramientas, etiqueta bajo el icono,
  `aria-current` en la ruta activa.
- Tarjeta de herramienta: icono + nombre + función + acción; el botón de
  favorito es un elemento hermano, nunca anidado dentro de un link.
- Favorito: área táctil 44×44px, `aria-pressed`.
- Botón principal: mínimo 50px alto, naranja, texto negro, radio 12px.
- Campo de formulario: etiqueta permanente, altura mínima 52px, fuente 16px
  (evita el zoom automático de iOS).
- Diálogo: radio 24px, foco contenido, cierre con Escape, retorno de foco al
  disparador.
- Checkbox: toda la fila es objetivo de interacción.
- Fotografía: dimensiones reservadas, alt text cuando aporte información.
- Estado vacío: explicación breve + salida útil, nunca una pantalla muerta.
- Movimiento: feedback de 160–200ms, respetar `prefers-reduced-motion`.

### Composición de pantallas

- **Inicio** (móvil): marca+avatar → saludo+fecha → próxima visita compacta
  (hora, propiedad, cliente, foto, acceso a Agenda) → herramientas con
  filtro Todas/Favoritas → 6 herramientas en 2 columnas → nav inferior.
  Escritorio: herramientas en columna principal, visita a la derecha en
  panel fijo.
- **Campañas**: acción principal "Nueva campaña"; resultados como personas
  interesadas, inversión, costo por contacto; gráfico semanal con cifras
  visibles (no depender de hover); estado Activar/Pausar explícito;
  exportar es secundario.
- **Agenda**: semana visible con día seleccionado inequívoco; hora separada
  del contenido de la cita; tocar la cita abre detalles (lugar,
  participantes, duración, zona horaria); "Nueva cita" es la acción
  principal.

### Nota de alcance real del prototipo (no romper esto al integrar)

En el prototipo de ChatGPT, campañas/citas/pendientes eran demos en memoria
sin backend real, y Fotografía/Documentos/Clientes/Automatizar eran solo
conceptos. **El proyecto real (Broquer) ya tiene equivalentes con datos y
contratos reales** — ver la sección "Verificación" abajo. No reemplazar esas
capacidades reales por las demos del prototipo.

### Fuentes de referencia usadas en el diseño original

<https://www.insaim.design/blog/10-best-app-ui-ux-designs> (Airbnb, Spotify,
Dropbox, Slack, Headspace, Google Maps, Medium, Pinterest, Calm, Notion — se
tomó un principio de cada uno, no su identidad visual completa). Manrope
(fonts.google.com/specimen/Manrope), Lucide (lucide.dev), Simple Icons
(github.com/simple-icons/simple-icons).

---

## Verificación hecha en el repo real (2026-09-19)

1. **Logotipos**: SÍ existen en el repo real (`logotipo-black.png`,
   `logotipo-white.png`, `logo-broquer.png`, `logo-broquer-blanco.png`,
   `logo-inmobiliaria-navarro.png`, `isotipo-broquer.png`, etc.) y ya se usan
   en superficies reales, p. ej. `landing.html` (nav y footer cargan
   `logotipo-black.png`). No se ven en el prototipo de ChatGPT porque ese
   sitio es un entorno aislado sin acceso a los assets de este repositorio,
   no porque falten en Broquer.
2. **Agenda**: **No existe** un módulo "Agenda" (calendario semanal de
   citas) en el backend/frontend real. Lo más cercano es:
   - `tareas.html` + tabla `tareas` (CRM de pendientes, con menciones a
     "cita agendada" cuando WhatsApp agenda una visita).
   - `wa2_agenda` (`migracion-coexistencia-agenda.sql`): es la **libreta de
     contactos del celular** sincronizada para WhatsApp 2.0, no un
     calendario de citas.
   Es decir: la Agenda del prototipo de ChatGPT fue una demo inventada, tal
   como advierte la nota de alcance real de arriba. Si se quiere una Agenda
   de verdad, es una funcionalidad nueva por construir sobre `tareas`
   (o una tabla de citas dedicada), no algo que ya exista.
3. **landing.html**: Sí existe, y ya tiene su propio sistema de diseño
   ejecutable, "Blanca" (ver comentario en el `<style>` del archivo): fondo
   papel, azul como única acción, Inter, tarjetas con sombra suave. Es
   distinto tanto del Canon (`brokr-theme.css`) que usan las demás 42
   superficies como del "modo" del prototipo. Aplicar "modo" a landing
   crearía un tercer sistema visual — se necesita decisión del usuario (ver
   arriba).
