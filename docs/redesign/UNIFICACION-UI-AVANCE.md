# Unificación aprobada — avance del 28 de octubre de 2026

La aprobación autoriza aplicar el sistema de `ui-components.html`. Se conserva el funcionamiento de Broquer; solo rama del PR #180. No se ha fusionado main ni publicado producción.

## Implementado en esta entrega

- El tema de la aplicación importa `ui/tokens.css`: los alias existentes de tipografía, geometría, superficies, bordes y alturas consumen el mismo contrato aprobado de la muestra. No se copia un segundo juego de valores.
- Títulos de módulo 48 px en escritorio y 32 px en móvil. Corrección en origen de alturas de botones, sin añadir otra capa de overrides.
- Mi cuenta: cabecera blanca, avatar celeste, cierre 44 px, panel 420 px, campos de 48 px/16 px y acción naranja. Conserva edición, contraseña, suscripción, equipo y demás manejadores.
- Broq: cabecera blanca, texto oscuro, envío naranja, sin botón flotante duplicado. Conserva las entradas de cabecera y navegación móvil, conversación y voz existentes.
- Inicio: tarjetas blancas y texto oscuro; se retiran las variantes oscuras y azules desde las reglas originales.
- Contactos e Inmuebles: alturas y tipografía de controles ajustadas en sus reglas existentes.
- Barra de demo: colocación explícita después de la cabecera al terminar de cargar el shell; botones de 48 px/radio 12 px.

## Verificación y límites

`check_ui_migration.cjs` mide Inicio, Contactos, Inmuebles, Agenda y Finanzas a 1440/390 px: errores JavaScript, desbordamiento horizontal, campos visibles de 16 px mínimo, ausencia de FAB duplicado y cabeceras de Mi cuenta/Broq. Resultado detallado: `ui-migration-20261028.json`. La prueba abre ambos paneles reales de la aplicación; no utiliza los paneles simulados de la muestra.

Son comprobaciones con datos ficticios de navegador. No acreditan guardado en Supabase, RLS, pagos ni integraciones reales. El auditor estricto de la muestra sigue limitado a la muestra; no se presenta como auditor de toda la aplicación.

## Pendiente de completar

Migrar y auditar las reglas locales restantes de cada pantalla: calendarios españoles, filtros, modales completos y campos repetibles, bandejas, avisos y estados vacíos. Completar las mediciones de todas las pantallas y estados por rol. La tabla final de pantallas/endpoints debe distinguir mock, real y pendiente. La base Supabase aislada y las pruebas reales permanecen sujetas a disponer del esquema actual sin datos de clientes. Esta entrega no declara terminada la unificación global.
