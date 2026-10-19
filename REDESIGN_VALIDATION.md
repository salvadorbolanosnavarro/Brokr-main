# Verificación de cobertura ampliada

## Alcance conservado

52 HTML inventariados, incluidos páginas públicas, callbacks, prototipos y plantilla.
268 declaraciones de endpoints inventariadas, con prefijos locales expandidos; falta comparar montajes dinámicos.
Ningún ID de control original eliminado. Los handlers originales y tests existentes se conservan. main.py instala una protección de staging antes de importar servicios; solo se activa con BROQUER_ENV=staging.
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

## Flujos públicos y de cuenta

Adaptados registro/completar perfil, recuperación, invitaciones, firma pública,
verificación de firma y expediente público. Se conservan todos sus controles,
validaciones y contratos de URL. La revisión visual de las seis páginas a dos
tamaños pasó (12 vistas). Las capturas esperan ahora la retirada del splash.

`check_public_flows.cjs` comprueba: registro sin sesión redirige a acceso,
aceptación de términos habilita continuar, nombre requerido, recuperación sin
token bloqueada, longitud/coincidencia de contraseña, actualización y cierre
global de sesiones interceptados en el navegador, y estados de ligas incompletas.
Resultado: aprobado, cero peticiones a producción. El éxito de las peticiones
interceptadas no certifica autenticación o guardado reales.

La configuración concreta que falta para avanzar a servicios reales está descrita
en `STAGING_SETUP.md`.

## Aislamiento de staging añadido

Compilación estática configurable para el proyecto Pages existente, con URLs de
Railway staging y Supabase independiente, rechazo de main/producción/secret keys,
y connect-src restringido. Backend con protección HTTPX/SMTP, Stripe solo test,
recordatorios y buscador automático obligatoriamente apagados. Cuatro pruebas
específicas de aislamiento pasaron, incluida la denegación de Meta, Resend, APNs,
API productiva, Stripe sin credencial test y SMTP. No hicieron llamadas reales.

Todos los 52 HTML cargan el mínimo de 16px para inputs; un guardia del navegador
lo aplica también a controles dinámicos y reglas antiguas con !important. No se
ha probado todavía la escala del WebView real de iOS.

Preparados exportadores SQL de metadatos/buckets y seed transaccional. El esquema
completo actual no está en el repo: falta la exportación de producción (solo
definiciones) para generar y validar la migración exacta. No hay base de pruebas
conectada y no se han certificado escrituras reales ni matriz completa de roles.
Cloudflare mostró login; este avance no equivale a un despliegue publicado.

## Actualización al Broquer actual

Se incorporó en la rama del PR el main 1f5fc8d5a5a7650bd315bfead3515d708f828bae,
sin modificar main ni producción. El alcance actual creció a **55 HTML y 348
operaciones HTTP**: se conserva también la lista de declaraciones y handlers.
Incluye Buzón, alertas, ajustes CRM, cierres, catálogo de inmuebles, mejoras del
sitio público y AVM/Firecrawl. Regenerado avm-runtime.js desde el JSX actualizado.
El contador de Buzón también se conserva en la cabecera nueva.

Se ejecutaron 61 pruebas existentes de las funciones incorporadas: 59 aprobaron
inicialmente y dos de AVM fallaron por faltar socksio en el entorno de ejecución.
Después de instalar esa dependencia local se repitieron únicamente esas dos.
No se modificaron las pruebas ni sus contratos. La nueva compilación estática
incluye los 55 HTML. Los mocks de navegador anteriores se identifican como
evidencia de la versión previa; no certifican estas funciones incorporadas.
No se pudo renovar el recorrido visual: la descarga del navegador devolvió un
archivo inválido. No se considera aprobado el recorrido de esta versión.

La protección de correo también bloquea IMAP: no conecta cuentas de correo
reales. Las integraciones nuevas externas siguen bloqueadas por HTTPX en staging.

Supabase Auth: envíos de registro/recuperación/OTP/invitación bloqueados en frontend compilado y HTTPX de staging; login con contraseña QA permitido. Pendiente auditar webhooks, cron y funciones de envío dentro de PostgreSQL con el esquema real.

## Verificación del 19 de octubre de 2026

Se recuperó un navegador Chromium 133 para pruebas locales; se supera el bloqueo
anterior de instalación. Recorrido de las 54 páginas ejecutables a 390/1440px:
108 vistas verificadas sin desbordamientos, errores JavaScript ni inputs visibles
por debajo de 16px. La plantilla de desarrollo sigue inventariada como HTML 55.

El primer recorrido detectó errores de sintaxis en Estadísticas e ISR: la
inserción anterior del guardia de inputs también había entrado en plantillas HTML
de impresión dentro de cadenas JavaScript. Se retiraron esas dos inserciones
duplicadas, conservando el guardia en la cabecera real. Se revalidaron las dos
páginas y Buzón en seis vistas. Además, los 48 scripts ejecutables incrustados
en el HTML pasaron análisis de sintaxis. No se cambió la lógica de cálculo de ISR.

Buzón, Alertas y Ajustes de CRM: 48 casos aprobados (3 módulos × 2 tamaños ×
2 roles × datos/vacío/error/carga), con fixtures exclusivos de las pruebas.
Se comprobaron errores escapados como texto, reintento, controles de edición
para administrador y bloqueados para agente, apertura/retorno del detalle móvil,
guardado de nota, sustitución de respuestas guardadas, alta manual de lead,
pausa/reanudación de alerta y cambio de nombre de etapa. Los cambios persisten
solo en la memoria del mock: no certifican guardado real, permisos del servidor
ni aislamiento RLS. Los teléfonos, nombres, correos y mensajes son ficticios.

Mejoras de producto: estados accesibles con reintento; se ignoran respuestas
antiguas de filtros de Alertas/Buzón; panel inicial de conversaciones, filtros
con etiquetas legibles y distribución móvil. Estados visuales alineados al
lenguaje blanco/celeste/naranja. Backend y reglas de autorización conservados.

Validaciones adicionales: 14 tests existentes de Buzón/Alertas/CRM aprobados,
4 pruebas de aislamiento aprobadas y auditor de diseño con 0 violaciones en
47 HTML. El gate de arquitectura sigue sin aprobar: además del vendor ReactDOM,
existen archivos por encima de los límites de bytes anteriores (entre ellos
app-shell, contratos, propiedades, WhatsApp, legal y admin). El escaneo local
también alcanzó artefactos generados de dist. No se modificaron los límites ni
los tests existentes para ocultar estos fallos. Las expectativas de Inter siguen
pendientes de resolución frente a la tipografía Manrope del rediseño.

Evidencia resumida versionada: `docs/redesign/qa-20261019.json`.
Reproducir: ejecutar el gateway local y usar `scripts/check_module_surface.cjs`
y `scripts/check_crm_states.cjs` con Playwright instalado; puede indicarse un
binario existente mediante `BROQUER_CHROMIUM_EXECUTABLE`. Los tests de navegador
no requieren API, claves secretas ni base de datos.

No se ha publicado en Cloudflare ni se ha certificado iPhone/WebView real.
Sigue pendiente la exportación del esquema, su migración exacta al Supabase
limpio, la auditoría de automatizaciones de PostgreSQL y la prueba real completa.
