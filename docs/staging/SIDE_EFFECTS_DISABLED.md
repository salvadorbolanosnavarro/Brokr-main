# Interruptor de llamadas externas para staging

Este ajuste no necesita nuevas variables en Railway: staging queda bloqueado
por defecto. La publicación está limitada a staging con autorización del usuario. Base: `work/redesign-preview-20261003`, commit `086fd40e`.

## Configuración para la futura activación autorizada

```
BROQUER_ENV=staging
SIDE_EFFECTS_DISABLED=true
```

**Si BROQUER_ENV=staging, la ausencia del flag, un valor vacío o inválido activa
el bloqueo. Solo SIDE_EFFECTS_DISABLED=false lo desactiva explícitamente.**
Fuera de staging se mantiene apagado por defecto.

El interruptor se instala antes de importar los routers. Aun si existen llaves
reales o listas de destinatarios de prueba, bloquea las llamadas HTTP síncronas
y asíncronas a Stripe, Meta/WhatsApp, Instagram/Facebook, Resend, APNs de sandbox
y producción y EasyBroker. También bloquea SMTP/SMTP_SSL antes de conectar,
negociar TLS o iniciar sesión. Una URL de otro proveedor no puede usar un
redirect automático para llegar a estas integraciones mientras el flag está activo.

Supabase de staging, la IA y las fuentes de datos de mercado conservan su
funcionamiento. Esto no es un bloqueo de todos los accesos a Internet ni una
transacción que deshaga escrituras locales. Un router puede registrar en la BD
el intento o su error. No se crean IDs falsos del proveedor ni se finge entrega.

## Contratos de respuesta

Operación bloqueada: HTTP **409**, `Cache-Control: no-store`,
`X-Broquer-Simulated: true` y JSON:

```json
{
  "ok": false,
  "simulated": true,
  "external_call_performed": false,
  "code": "SIDE_EFFECTS_DISABLED",
  "message": "Simulación: no se enviaron mensajes, cobros ni solicitudes al proveedor bloqueado.",
  "blocked_operations": [{"provider": "meta", "method": "POST", "kind": "simulation"}]
}
```

El estado no es 2xx: un cliente antiguo que solo compruebe `response.ok` no debe
marcar un mensaje como entregado ni un cobro como completado. El middleware
conserva esta respuesta incluso si un router antiguo captura el error de red.
Los trabajos de fondo no tienen una respuesta HTTP: reciben el bloqueo y dejan
el mismo log, sin contactar al proveedor.

Los logs de este módulo contienen únicamente proveedor, método y motivo.
No contienen llaves, URLs, parámetros, cuerpos, destinatarios ni device tokens.

## Stripe: el error de configuración tiene prioridad

En staging, `STRIPE_SECRET_KEY` vacía, live, restringida `rk_test_` o sin contenido
tras `sk_test_` devuelve HTTP **503**, código
`STAGING_STRIPE_TEST_KEY_REQUIRED`, sin contactar a Stripe. También se valida la
credencial efectiva del request (Bearer o Basic): una llave distinta no puede
eludir la política global. Solo se verifica el formato/modo; que una llave tenga
ese prefijo no acredita que sea una credencial válida ante Stripe.

El backend puede arrancar aunque Stripe esté mal configurado. La validación se
realiza al operar, también en checkout personal, empresarial, asientos y cancelación.
Un webhook en staging exige llave de prueba, firma y `livemode=false`; con el
interruptor activo se simula antes de activar suscripciones en la BD.

Con flag apagado y fuera de staging no cambian los contratos de los proveedores.
La validación de aislamiento de Supabase de `staging_safety` se conserva.

## EasyBroker y config.json

La búsqueda en el código de aplicación encontró un lector de `config.json` en
`core/easybroker.py` y ningún escritor de ese archivo. Staging ahora ignora ese
lector, incluso si un archivo es montado o aparece durante la ejecución.
La prueba escribe un archivo temporal con llave ficticia y confirma que no se
lee en staging, y que producción conserva la compatibilidad anterior.
Esto no afirma que el archivo no exista en el contenedor desplegado: para esa
comprobación sigue haciendo falta acceso al contenedor. Se debe mantener
`EB_API_KEY` vacía; el interruptor bloquea además las llamadas con claves por organización.

## Evidencia automatizada

`python -m unittest tests.test_side_effects_safety -v` cubre:

- 45 combinaciones síncronas (9 hosts × 5 métodos) y 9 llamadas asíncronas,
  con transporte espía: cero llamadas recibidas cuando el flag está activo.
- SMTP y SMTP_SSL: cero conexiones de socket.
- Listas de teléfono/correo de prueba: tampoco permiten saltarse el interruptor.
- Supabase/IA permitidos y redirecciones automáticas detenidas.
- Llaves Stripe vacías/live/restringidas, Bearer/Basic, precedencia de 503 y
  endpoints reales de checkout/cancelación/asientos.
- Webhooks Stripe firmados: sin activación por eventos live o flag activo.
- Simulación explícita, errores sin 500, aislamiento entre peticiones concurrentes,
  trabajos sin contexto HTTP y ausencia de información sensible en los nuevos logs.
- Flag apagado en producción y respaldo local de EasyBroker.

No se usan cuentas, llaves, destinatarios ni operaciones reales. Las pruebas de
integración con Railway y el frontend de Cecil siguen pendientes de autorización.

## Mantenimiento

Todas las integraciones actuales identificadas usan HTTPX o SMTP. Nuevos SDK,
transportes o dominios necesitan extender la protección y sus pruebas antes de
usarse en staging. Este control de aplicación no sustituye un firewall de salida.

## Resultado de esta revisión

- 17 pruebas nuevas correctas.
- Suite completa: 1,170 pruebas correctas, 4 omitidas. El entorno local necesitó
  `socksio` para el proxy de pruebas; no se modificaron dependencias de la app.
- Compilación Python y auditorías de UI correctas.
- El gate completo no está verde: `architecture_debt.py` falla por React DOM
  vendorizado y el tamaño de `legal.html`. Se reprodujeron los mismos dos errores
  en un worktree limpio del commit base; no se tocaron esos archivos ni límites.
- No se ha configurado Railway ni ejecutado contra servicios reales.
