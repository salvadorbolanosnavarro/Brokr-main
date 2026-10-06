# Conectar la copia funcional a servicios de pruebas

El repositorio incluye el backend FastAPI original y su Dockerfile. El rediseño no
requiere sustituirlo. El gateway de la copia necesita tres valores para permitir
operaciones reales; sin ellos devuelve 503 explícitamente.

## Entorno separado necesario

1. Proyecto Supabase de pruebas con Auth, esquema, RLS y buckets equivalentes.
   Los SQL del repositorio son migraciones parciales; no se ha encontrado un
   manifiesto que permita reconstruir con certeza todo el esquema desde cero.
   Preparar un esquema sin datos de clientes a partir del proyecto autorizado y
   comprobar las migraciones aplicadas. No ejecutar todos los SQL a ciegas.
2. Instancia del backend original, con `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`
   y `SUPABASE_SERVICE_KEY` correspondientes únicamente a ese proyecto.
   La clave de servicio se configura en el servidor, nunca en HTML ni en GitHub.
3. Configurar `APP_URL`, `API_BASE_URL` y `FRONTEND_URL` con los destinos de pruebas.
   El backend conserva valores por defecto de producción para estas variables;
   por ello deben establecerse explícitamente antes de usarlo como staging.
4. Crear usuarios y registros ficticios propios del entorno de pruebas y comprobar
   perfiles, roles, suscripciones y permisos de almacenamiento equivalentes.
5. Iniciar el gateway con `BROQUER_STAGING_API_URL`,
   `BROQUER_STAGING_SUPABASE_URL` y `BROQUER_STAGING_SUPABASE_KEY` (clave pública).

## Integraciones

La paridad completa también exige cuentas/configuraciones de prueba para correo,
WhatsApp/Meta, Stripe, EasyBroker, servicios de IA y notificaciones. No heredar las
credenciales, destinatarios ni webhooks del servidor actual. El entorno básico
sin estas configuraciones permite probar solo los módulos que no dependan de ellas.
No presentar respuestas simuladas como una integración funcional.

El gateway actual es local y no certifica los redirects de OAuth: los rechaza.
La publicación y esos callbacks deben configurarse y validarse en el host de
pruebas antes de entregar una URL como réplica funcional completa.

## Evidencia que falta para aprobar la copia

- Crear, editar y volver a leer clientes, inmuebles, tareas y movimientos.
- Adjuntar, consultar y descargar archivos con roles de agente y administrador.
- Probar invitación/equipo y restricciones entre usuarios diferentes.
- Completar firma/expediente con usuarios de pruebas y validar sus documentos.
- Comprobar servicios externos con sus propias credenciales de prueba.

La revisión actual de interfaz, fixtures y conservación de código no prueba estas
operaciones. No hay un proyecto Supabase/API de staging conectado en esta sesión.
