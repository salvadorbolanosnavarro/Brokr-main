# Copia de pruebas del rediseño Broquer

Base: `salvadorbolanosnavarro/Brokr-main`, commit `3d792b52c1265cfd09ed05b41df8a7d4bc02da2f`.
Rama: `work/redesign-preview-20261003`.

Esta rama adapta la aplicación existente a las referencias de octubre: Manrope,
cabecera horizontal, fondo blanco, tarjetas celestes y acciones naranja. Conserva
los formularios, permisos y llamadas de la aplicación. No constituye todavía una
réplica visual exacta ni una migración lista para producción. No se han modificado
los tests existentes, el backend, la base de datos ni la rama principal.

## Ejecutar la copia aislada

```bash
python scripts/serve_staging.py --port 8080
```

Abrir `http://127.0.0.1:8080/login.html`. Sin configuración, el acceso a servicios
responde 503 de forma explícita: no hay usuarios falsos ni acceso a producción.
Las páginas protegidas requieren una sesión real del entorno separado.

Para usar autenticación y guardar registros, configurar en el entorno del proceso:

- `BROQUER_STAGING_API_URL`: instancia separada del backend original.
- `BROQUER_STAGING_SUPABASE_URL`: proyecto Supabase separado, con esquema,
  políticas RLS y almacenamiento equivalentes.
- `BROQUER_STAGING_SUPABASE_KEY`: clave pública/anon de ese proyecto.

El backend de pruebas debe apuntar al mismo Supabase separado. Crear un usuario de
pruebas y registros de prueba; no copiar credenciales ni información de clientes.
Las claves privadas permanecen exclusivamente en el backend. El gateway rechaza
los destinos de producción conocidos y las claves privilegiadas.

**Usar este gateway, no un servidor estático genérico**: los archivos originales
conservan sus destinos de producción y el gateway los sustituye al servirlos.
El CSP restringe las conexiones del navegador al gateway. El servidor escucha en
loopback y está pensado para revisión local, no para exposición pública directa.

OAuth, pagos, WhatsApp, campañas, correo y webhooks requieren configuraciones de
pruebas propias. Los redireccionamientos de upstream están bloqueados; OAuth no
está certificado en este gateway. Límite de peticiones/subidas: 32 MiB. No se ha
publicado una URL de pruebas ni realizado un despliegue.

## Alcance visual y funcional

Adaptados: inicio, acceso, clientes, inmuebles, agenda, finanzas, campañas y
directorio, además de la cabecera compartida. Los datos de las referencias no se
insertan como contenido real. Los filtros, pestañas y acciones existentes siguen
presentes, aunque no aparezcan en las referencias; falta terminar su composición
visual y revisar estados con registros, errores, permisos y modales.

La navegación móvil usa la cabecera nueva; el menú inferior anterior se oculta.
Inicio conserva enlaces a las demás herramientas y favoritos locales. La próxima
cita obtiene datos reales de agenda y, si existe, imagen del inmueble relacionado.

## Verificación reproducible

```bash
python scripts/check_staging.py
# Instalar Playwright y Chromium en el entorno de verificación.
node scripts/check_redesign.cjs
# O bien PLAYWRIGHT_MODULE=/ruta/a/playwright node scripts/check_redesign.cjs
bash scripts/run_quality.sh
```

El navegador comprueba 16 vistas (8 pantallas a 1440 y 390 px), ausencia de errores
JavaScript/desbordamiento horizontal, legibilidad, tamaños de títulos, favoritos,
navegación y apertura de formularios. Las respuestas simuladas viven únicamente en
el script de verificación. NO prueban autenticación real ni persistencia. El informe
y las capturas se generan en `test-results/redesign/`.

El gateway tiene siete pruebas de aislamiento/configuración. El conjunto original
ejecuta 886 tests: queda una incompatibilidad conocida con cuatro subcasos que
exigen Inter para los alias de fuente. El diseño solicitado usa Manrope y los tests
existentes no se han cambiado para ocultar esa diferencia.

Antes de considerar la migración: completar la comparación de las ocho pantallas
con las referencias, probar creación/edición/lectura con el backend separado,
comprobar roles y archivos y resolver explícitamente el contrato de tipografía.
La validación visual exacta y la validación funcional con servicios reales siguen
pendientes. Mantener este cambio como borrador hasta terminarlas.
