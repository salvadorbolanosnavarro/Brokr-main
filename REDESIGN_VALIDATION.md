# Verificación de cobertura ampliada

## Alcance conservado

52 HTML inventariados, incluidos páginas públicas, callbacks, prototipos y plantilla.
268 declaraciones de endpoints inventariadas (sin expandir prefijos de routers).
Ningún ID de control original eliminado. Backend y tests originales sin cambios.
Esto es evidencia estática, no una certificación funcional completa.

## Navegador

El recorrido completo más reciente visitó 102 vistas (51 HTML a 1440/390 px).
100 terminaron sin fallos de comprobación. AVM quedó bloqueado por su dependencia
externa de React/Babel; se sustituyó la carga externa por las mismas versiones de
React locales y una compilación reproducible del JSX existente. La comprobación
posterior de AVM, inicio y cumplimiento pasó en los dos tamaños: 6 vistas, cero
fallos, cero errores JavaScript y cero desbordamientos horizontales.

Comprobaciones específicas: apertura de Broq, acceso a Chats, perfil de cuenta,
acceso a firmas y cumplimiento, administración no visible para agente,
selección de contrato de promesa y apertura de nuevo expediente. Se conserva
además la revisión anterior de favoritos y formularios de CRM/agenda/finanzas.

Las respuestas son fixtures exclusivas de las pruebas. No se ha validado guardado
real, autenticación real, entregas de mensajes, pagos, OAuth ni integraciones.

## Controles del repositorio

- Suite original: 886 tests; cuatro subcasos del contrato de fuente siguen exigiendo Inter.
- Gateway: siete pruebas aprobadas.
- Auditoría visual de código anterior a la preparación local de AVM: cero violaciones en 44 HTML.
- Arquitectura: aprobada antes de incluir ReactDOM local. Ahora detecta el archivo
  de terceros `vendor/react-18.2.0/react-dom.production.min.js` de 131,882 bytes,
  superior al umbral de 100 KB. El control no fue modificado para ocultarlo.

## Pendiente

Revisión visual detallada de cada módulo y sus estados con datos, páginas con
interfaz propia, permisos completos, persistencia, archivos e integraciones en
servicios de staging. Resolver el contrato de fuente y revisar explícitamente la
distribución de terceros señalada por el control de arquitectura antes de fusionar.
No se ha modificado producción ni publicado una URL de pruebas.
