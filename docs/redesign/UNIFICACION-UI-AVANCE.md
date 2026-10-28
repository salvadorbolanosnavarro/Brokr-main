# Unificación UI — 28 de octubre de 2026

El sistema aprobado se aplica sobre el main actual `ee9c5579` (PR #209), integrado **dentro de la rama del PR #180**. No se ha actualizado main ni producción. Incluye países, validación de Broquer Max, supervisión y la calculadora de Impuestos por venta; el rediseño conserva el código funcional actual. El inventario no detecta IDs de controles retirados respecto a ese main. El backend coincide con él salvo el guard de staging y su instalación (81 líneas).

## Cambios

- Un solo contrato de acciones en `ui/actions.css`: cinco variantes y dos alturas. El adaptador conserva IDs, eventos, permisos, visibilidad y estados de los controles actuales. Se retiraron las declaraciones visuales que competían en los módulos; las filas de conversaciones, multimedia, pestañas y segmentados conservan su función específica.
- Campos y búsquedas compartidos, flecha de selects, radio 12 px, altura 48 px y suelo de 16 px. Se conserva explícitamente la protección global de inputs de iOS. Los filtros se apilan en móvil y las fechas mantienen ancho legible.
- Calendario español con teclado, límites mínimo/máximo, disabled/readonly, foco y Escape. Conserva los inputs originales `type=date`, valores ISO, validación y los eventos input/change que usa la aplicación.
- Marco común para los modales de contactos e inmuebles, de hasta 720 px, con cabecera y pie fijos y cuerpo desplazable. Guardar queda visible; campos repetibles y operaciones múltiples siguen funcionando. Escape conserva las confirmaciones de cambios sin guardar. También se incorpora manejo de foco para los modales compartidos existentes.
- Mi cuenta y Broq usan superficies claras y acciones compartidas. Se elimina la entrada flotante duplicada de Broq. Los formularios, voz, suscripción y manejadores existentes siguen presentes.
- Tarjetas blancas; selectores y estados compartidos. Finanzas evita montos cortados; la selección de inmueble ocupa su propia fila y no tapa la etiqueta de operación. No aparece la barra de acciones con cero seleccionados; los permisos originales limitan la selección destructiva.
- Se conserva el acceso a Contactos y Clientes que trae el main actual, con títulos coherentes. Títulos de navegador con formato `Módulo · Broquer`. Empresas y Soporte usan el logotipo oscuro sobre blanco.
- Demo después de la cabecera, datos ficticios, transporte local y aislamiento de red. No se representan envíos, cobros o conexiones externas como éxitos reales.

## Evidencia

- 55 páginas ejecutables, 110 vistas a 1440/390 px: cero errores JS, desbordamientos horizontales, filtros superpuestos, montos cortados o campos menores de 16 px. Incluye 48 páginas principales, dos callbacks y cinco referencias suplementarias; las plantillas no se cuentan como pantallas.
- Auditor estricto del render: cero infracciones, siete tamaños de texto y nueve combinaciones observadas de variante/tamaño de acción, dentro del máximo de diez. No mezcla filas de conversación o pestañas con botones de acción. Comprueba hashes para rechazar resultados anteriores a cambios en HTML/CSS/JS.
- 48 casos de CRM: datos/vacío/error/carga × agente/admin × dos anchos en Buzón, Alertas y Ajustes. Pruebas con fixtures, no RLS real.
- Flujos de demo: guardar y recargar clientes, contactos, tareas y movimientos; campos repetibles; operaciones múltiples; selección por permiso y cero selección; fechas ISO, límites y teclado; Escape y devolución del foco; cambio de rol, restablecimiento y envío externo bloqueado.
- Cinco países: navegación y render de las calculadoras originales. No es una auditoría de exactitud fiscal.
- 53 scripts inline pasan la verificación sintáctica. La muestra de componentes mantiene su auditor propio.

Repetir las pruebas de demo con `scripts/run_ui_quality.sh`, configurando `PLAYWRIGHT_MODULE` y `BROQUER_CHROMIUM_EXECUTABLE` en el entorno de QA. Los 48 casos con fixtures utilizan `scripts/check_crm_states.cjs` y `scripts/serve_staging.py` por separado. El auditor también rechaza mediciones manipuladas con tamaños no aprobados.

## Pendiente real

La tabla completa está en [COBERTURA-UI-Y-ENDPOINTS.md](COBERTURA-UI-Y-ENDPOINTS.md). Enumera cada pantalla y las 355 operaciones HTTP del main integrado, sin atribuir cobertura funcional completa a una prueba de superficie. Los contratos no invocados, los escenarios completos de otros módulos, RLS, persistencia en Supabase, storage, pagos y servicios externos quedan pendientes de pruebas reales. La base aislada requiere el esquema actual sin datos reales; los pasos están en `STAGING_SETUP.md`.

La emulación a 390 px no certifica WKWebView en un iPhone real. La suite histórica completa de backend/arquitectura no se presenta como aprobada por los resultados de UI. Nada se fusiona a main sin aprobación del usuario.
