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
