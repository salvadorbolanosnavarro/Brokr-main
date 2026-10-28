# Sistema visual propuesto para aprobación

Esta propuesta no cambia todavía las pantallas actuales.

- Manrope. Escala: 12, 14, 16, 20, 24, 32 y 48 px. Título de módulo: 48/600 escritorio y 32/600 móvil; sección: 24/600; cuerpo: 16; etiqueta: 14; ayuda: 12.
- Colores: tinta #191C1F, secundario #59636C, blanco #FFFFFF, superficie #F5F7F8, celeste #E8F4FA, borde #D5D9DD, acción naranja #FF9257 y destructivo #B42318.
- Espacios: 4, 8, 12, 16, 24, 32 y 48 px. Controles con radio 12 px; tarjetas y ventanas con radio 20 px.
- Botones: principal, secundario, texto, destructivo y deshabilitado. Dos alturas: 44 y 48 px; texto 14/600. Sin píldoras como excepción de módulo.
- Campos de una línea: 48 px, texto mínimo 16 px, borde y padding comunes. Etiqueta y ayuda compartidas; textarea con altura adaptable. Selects con una flecha; calendario español accesible que conserve valores ISO.
- Contenedor de módulo: máximo 1256 px; margen de 32 px en escritorio y 20 px en móvil. Encabezado con título, descripción y acciones; filtros en cuadrícula sin superposición.
- Pestañas subrayadas; segmentados con selección celeste. Tarjetas blancas, incluidas las herramientas de Inicio.
- Modal de máximo 720 px, cabecera y pie dentro de la ventana, cuerpo desplazable, cierre de 44 px, Escape y devolución del foco. Panel lateral con los mismos componentes y sin degradado.
- Broq: una sola entrada en la cabecera; ventana blanca, cabecera clara y envío naranja. Conservar su lógica y retirar la entrada flotante duplicada al migrar.
- Avisos, toast y estados vacíos compartidos; texto claro y acción opcional. Añadir otro usa el secundario compacto.

Página de revisión: `ui-components.html`. Implementa el calendario en español con valor ISO, navegación por teclado, modales y paneles con Escape/devolución del foco, campos repetibles y conversación Broq explícitamente simulada. El CSS compartido está en `ui/tokens.css` y `ui/components.css`; no se carga en los módulos existentes. Auditor: `python scripts/audit_ui_kit.py`; alcance inicial: la muestra. Prueba de navegador: `scripts/check_ui_kit.cjs` a 1440/390 px. Tras aprobación, migrar módulos, retirar estilos contradictorios, añadir auditor estricto y entregar la medición completa. Esta propuesta por sí sola no acredita la implementación ni la publicación.
