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

El alcance es toda la aplicación actual: las ocho capturas solo son referencias
visuales. `REDESIGN_COVERAGE.md` y `redesign-inventory.json` inventarían los 52 HTML
(incluidos auxiliares y prototipos) y las 268 declaraciones de endpoints de la base.
Se extiende la cabecera a los 28 módulos que la usan y el lenguaje de componentes
a documentos, finanzas, multimedia, equipo y cumplimiento. Las páginas con interfaz
propia siguen pendientes de revisión visual detallada. Los datos de las referencias no se
insertan como contenido real. Los filtros, pestañas y acciones existentes siguen
presentes, aunque no aparezcan en las referencias; falta terminar su composición
visual y revisar estados con registros, errores, permisos y modales.

La navegación móvil usa la cabecera nueva; el menú inferior anterior se oculta.
Inicio conserva enlaces a las demás herramientas y favoritos locales. La próxima
cita obtiene datos reales de agenda y, si existe, imagen del inmueble relacionado.

## Verificación reproducible

```bash
python scripts/inventory_redesign.py
python scripts/check_staging.py
node scripts/check_module_surface.cjs
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

## Cobertura ampliada

`check_module_surface.cjs` recorre los 51 HTML que no son la plantilla de desarrollo,
a dos tamaños (102 vistas). Comprueba carga, errores JavaScript, desbordamiento,
acceso a Broq/Chats y acciones locales concretas de contratos, perfil y cumplimiento.
Los formularios de la base conservan sus identificadores y el backend permanece
sin modificaciones. Esto no sustituye pruebas de persistencia, integraciones,
roles completos ni validación visual manual. Los informes distinguen los fallos.

El acceso a Broq y el indicador de WhatsApp ahora viven también en la cabecera,
para conservar esas funciones al reemplazar el menú móvil. Los enlaces destacados
respetan los módulos desactivados. Los botones deshabilitados mantienen su estado
visual y funcional. Las reglas originales de móvil/iOS de Mi sitio se conservan.

AVM conserva su JSX original, pero usa React 18.2.0 local y `avm-runtime.js`
precompilado para evitar una pantalla vacía si falla el CDN. Después de editar el
JSX, regenerar con `scripts/compile_avm.cjs` (instrucciones en el archivo).
Consultar los resultados y límites actualizados en `REDESIGN_VALIDATION.md`.
