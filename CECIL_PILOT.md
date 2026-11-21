# Cecil sobre Broquer: piloto privado (pendiente de publicación)

Esta propuesta conserva el frontend actual de main. Construye una alternativa en
`/cecil/` desde el snapshot del rediseño `086fd40e`, que incluye la base de
producción `dac7118c` (#216). Las dos vistas usan los mismos servicios y la misma
sesión; guardar, borrar, enviar WhatsApp o pagar tiene efectos reales.

## Revisión antes de publicar

1. Identificar la cuenta de Salvador por su UUID de Supabase Auth; no por nombre,
   rol admin ni un parámetro de URL. Un administrador copia el UUID desde
   Supabase → Authentication → Users → buscar el correo de Salvador → abrir
   la ficha → copiar User UID. No se necesita ninguna llave secreta.
2. Aprobar este PR. Todavía no se ha fusionado ni se ha cambiado producción.
3. Comprobar el directorio y comando actuales de publicación en Cloudflare antes
   de cambiarlos. El constructor se ejecuta **después** de preparar los archivos
   normales. Si el sitio publica la raíz del repositorio, añadir al comando:
   `python scripts/build_cecil_canary.py --output cecil`.
   Si publica otro directorio, usar `--output DIRECTORIO_PUBLICADO/cecil`.
   Se necesita historial Git completo y el commit del rediseño accesible. En un
   checkout limitado: `git fetch origin work/redesign-preview-20261003`.
   No usar `build_staging.py`, no cambiar APIs, Supabase ni credenciales, y no
   publicar `dist` como si fuera el frontend completo: contiene solo la alternativa.
4. Publicar primero el backend con el flag apagado, y luego el frontend completo
   (actual + alternativa). Comprobar que el sitio habitual sigue funcionando.
5. Railway → proyecto Broquer → entorno producción → servicio API → Variables:
   `CECIL_UI_ENABLED=false`, `CECIL_UI_USER_IDS=UUID_DE_SALVADOR`. Desplegar.
   Con esto nadie ve el botón. No cambiar ninguna otra variable.
6. Probar respuesta autenticada de `/ui/cecil`: sin sesión debe rechazar; cuentas
   ajenas deben obtener `enabled:false`. Verificar que `/cecil/` no contiene el
   runtime demo, credenciales ni archivos de backend.
7. Con la autorización para activar el piloto: cambiar exclusivamente
   `CECIL_UI_ENABLED=true` y desplegar. Salvador verá «Probar el diseño Cecil».
8. Probar inicio, inmuebles, contactos, agenda, finanzas, ISR actualizado #216,
   permisos y documentos; documentar cada operación antes de abrir a más cuentas.
   Las pruebas aisladas del PR no certifican estos flujos con servicios reales.

## Regreso y desactivación

- «Volver a Broquer» conserva sesión/datos y quita la preferencia solo de esa cuenta.
- `CECIL_UI_ENABLED=false` y redesplegar: en la siguiente navegación o recarga,
  la vista Cecil vuelve a Broquer, aunque quede una preferencia local antigua.
- Si el endpoint falla, tarda más de seis segundos, devuelve otro UUID o no existe,
  se conserva Broquer. No se obtiene acceso por `?cecil=1` ni por ser administrador.
- La preferencia se guarda por UUID; al cambiar de cuenta no se hereda.

## Límites y mantenimiento

Este PR prepara el piloto, no declara producción certificada. Falta aprobar la
publicación, configurar la cuenta y hacer pruebas conectadas. El constructor
rechaza cambios de producción posteriores que no se hayan incorporado al
snapshot; no puede mantenerse sincronizado ignorando sus nuevas funciones.
La disponibilidad del frontend no sustituye los permisos/RLS existentes: la
misma API debe seguir validándolos en todas las operaciones.

Validación local: tests de autenticación/allowlist/no-cache y constructor;
16 comprobaciones de navegador a 1440 y 390 px para activar, volver, conservar
preferencia, cambiar de usuario, revocar acceso y tolerar fallos del endpoint.
Ninguna prueba hace operaciones en producción.


## Cierre requerido antes de pedir activación (21/11/2026)

Este PR sigue DRAFT, apagado y sin publicar. No fusionar #220: su worker,
variables públicas, tablas y artefactos son exclusivamente de staging.

- [ ] Completar por interfaz con A3 contactos, leads, contratos y opinión de valor; incluir salida/reingreso. La autenticación de la API no sustituye esta prueba.
- [ ] Ensayar ida/vuelta, revocación y sesión en staging; evidencia del servidor y del navegador por separado. El cambio añade revalidación cada15s y al volver a la pestaña, sin borrar la sesión del negocio.
- [ ] Comprobar iPhone Safari y WebView físico, teclado/campos y zoom.
- [ ] Respaldo previo completo y restauración de ensayo, incluyendo bytes de Storage. Registrar herramienta, operador, checksum, tiempos medidos y validaciones. No existe todavía una restauración verificada ni un RTO prometido.
- [ ] Confirmar el UUID real asociado exclusivamente a salvadorbolanosnavarro@gmail.com mediante un administrador; nunca usar UUID A3/B2 ni correo editable del cliente.
- [ ] Revisar DSN y environment de errores de producción, enviar un error controlado sin datos personales y verificar su recepción. La evidencia de staging no certifica la configuración de producción.
- [ ] Obtener aprobación explícita para publicar y otra para activar. Hasta entonces CECIL_UI_ENABLED=false y allowlist vacía.

### Activación futura: operador autorizado, después del OK

1. Verificar que main sigue en la base fijada por el constructor; si avanzó, integrar la nueva lógica y repetir staging. Nunca forzar el constructor ni suprimir su protección.
2. Conservar hashes del backend/frontend anteriores y un respaldo restaurable. Preparar una ventana y responsables. Este documento no autoriza ejecutarla.
3. Publicar backend y ambas vistas con flag apagado; comprobar Broquer habitual, auth y errores.
4. Configurar CECIL_UI_USER_IDS únicamente con el UUID verificado de Salvador, mantener flag apagado y comprobar rechazo anónimo y de otra cuenta.
5. Solo con aprobación explícita: CECIL_UI_ENABLED=true, comprobar Salvador/otra cuenta, entrar en Cecil, volver a Broquer y conservar sesión. Registrar errores y cada cambio de datos.
6. Mantener piloto restringido. No ampliar allowlist sin nuevo OK.

### Reversión futura

1. Apagar CECIL_UI_ENABLED y redesplegar; al revalidar (máximo15s en pestaña visible, o al recuperar visibilidad) Cecil vuelve a Broquer. Si no puede consultar al servidor, vuelve a Broquer. No se borran tokens de sesión.
2. Si la página está completamente bloqueada, abrir la ruta habitual de Broquer y revertir al artefacto frontend anterior comprobado.
3. Verificar login y operaciones habituales, y que la otra cuenta sigue fuera del piloto.
4. No restaurar toda la base por un fallo visual. Restaurar solo ante corrupción real, con ventana aprobada, control de escrituras y conciliación de operaciones posteriores. Un rollback visual no revierte mensajes ni cargos.

El defecto de Guardar inmueble verificado en staging se incorpora al constructor
para que el piloto no vuelva a introducirlo. No se incluyen credenciales ni un
UUID de producción sin verificar. La preparación no equivale a autorizar producción.
