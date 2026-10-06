# Cobertura completa de Broquer

Las ocho referencias definen el lenguaje visual; todas las pantallas y flujos originales forman parte de la migración.

Inventario reproducible: `3d792b52c1265cfd09ed05b41df8a7d4bc02da2f`. 52 HTML rastreados y 268 declaraciones de endpoints (sin expandir prefijos).
La presencia del código no certifica su funcionamiento. Todos los flujos requieren validación con servicios de pruebas.

| Pantalla | Cabecera compartida | Fuente HTML conservada | IDs de controles retirados |
| --- | --- | --- | --- |
| `404.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `_TEMPLATE-modulo.html` | Sí | Sin cambios | Ninguno |
| `admin.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `aviso-privacidad.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `avm.html` | Sí | Modificada | Ninguno |
| `bandeja.html` | Sí | Sin cambios | Ninguno |
| `blog.html` | Sí | Sin cambios | Ninguno |
| `bolsa.html` | Sí | Sin cambios | Ninguno |
| `buscador.html` | Sí | Sin cambios | Ninguno |
| `clientes.html` | Sí | Modificada | Ninguno |
| `contactos.html` | Sí | Modificada | Ninguno |
| `contratos.html` | Sí | Sin cambios | Ninguno |
| `correo.html` | Sí | Sin cambios | Ninguno |
| `cumplimiento.html` | Sí | Sin cambios | Ninguno |
| `empresas.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `equipo.html` | Sí | Sin cambios | Ninguno |
| `estadisticas.html` | Sí | Sin cambios | Ninguno |
| `expediente.html` | No; revisar flujo propio | Modificada | Ninguno |
| `facebook-ads.html` | Sí | Modificada | Ninguno |
| `facebook-callback.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `ficha-manual.html` | Sí | Sin cambios | Ninguno |
| `finanzas.html` | Sí | Sin cambios | Ninguno |
| `firmar.html` | No; revisar flujo propio | Modificada | Ninguno |
| `firmas.html` | Sí | Sin cambios | Ninguno |
| `guia-agente.html` | Sí | Sin cambios | Ninguno |
| `image-cleaner.html` | Sí | Sin cambios | Ninguno |
| `index.html` | Sí | Modificada | Ninguno |
| `isr.html` | Sí | Sin cambios | Ninguno |
| `landing.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `leads.html` | Sí | Sin cambios | Ninguno |
| `legal.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `login.html` | No; revisar flujo propio | Modificada | Ninguno |
| `mi-sitio.html` | Sí | Sin cambios | Ninguno |
| `preview-modo/index.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `preview-modo/preview-agenda.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `preview-modo/preview-campanas.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `preview-modo/preview-inicio.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `propiedades.html` | Sí | Modificada | Ninguno |
| `registro.html` | No; revisar flujo propio | Modificada | Ninguno |
| `reset-password.html` | No; revisar flujo propio | Modificada | Ninguno |
| `robin.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `sitio.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `soporte.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `tareas.html` | Sí | Modificada | Ninguno |
| `unirse.html` | No; revisar flujo propio | Modificada | Ninguno |
| `verificador.html` | Sí | Sin cambios | Ninguno |
| `verificar-firma.html` | No; revisar flujo propio | Modificada | Ninguno |
| `video.html` | Sí | Sin cambios | Ninguno |
| `videos/landing.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `whatsapp-callback.html` | No; revisar flujo propio | Sin cambios | Ninguno |
| `whatsapp-chatgpt.html` | Sí | Sin cambios | Ninguno |
| `whatsapp.html` | Sí | Sin cambios | Ninguno |

## Criterios de cobertura

- CRM: altas, edición, filtros, etapas, importación/exportación, archivos y permisos.
- Documentos: contratos, firma, verificación pública, expediente, cumplimiento y descargas.
- Finanzas: cuentas, movimientos, reportes, estimación de valor e ISR.
- Comunicación: WhatsApp, números, chats, recepción automática, correo y notificaciones.
- Marketing: fotografías, fichas, video, campañas, sitio público y configuración del agente.
- Cuenta: registro, acceso, recuperación, invitaciones, equipo, roles, suscripción y administración.
- Transversal: Broq, móvil/iOS, navegación, badges, errores, cargas, estados vacíos y accesibilidad.
- Páginas públicas y callbacks: conservar contratos de URL, tokens y redirecciones.

Los módulos ocultos o desactivados mantienen las reglas originales; conservar su código no implica habilitarlos.
Los detalles de controles y rutas se encuentran en `redesign-inventory.json`.
Actualizar con `python scripts/inventory_redesign.py`.
