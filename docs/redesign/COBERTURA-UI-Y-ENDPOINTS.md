# Cobertura de la migración UI — 28 de octubre de 2026

Base de rutas: main `ee9c557969168092644d4ed231a3b84211d83434` integrado en esta rama (355 operaciones HTTP). No hay IDs de controles retirados respecto a esa base. Nada se ha fusionado a main.

**Rediseñado** indica componentes compartidos aplicados; **probado con mock** indica evidencia de navegador/fixtures; **probado real** exige backend y base aislados. Cero pruebas reales se atribuyen a esta entrega. Un HTTP 501 de una integración desactivada queda pendiente, nunca aprobado.

## Pantallas

48 páginas principales + 2 callbacks OAuth + 5 páginas de referencia = 55 ejecutables; 110 vistas a 1440/390 px. Se incluye Impuestos por venta, añadido en el main actual. Los archivos que empiezan con guion bajo son plantillas.

Las pruebas generales verifican superficie, acciones, fuentes, fechas, superposición, montos y errores JavaScript. Guardado/recarga y flujos solo se atribuyen a las pantallas expresamente probadas. Los callbacks no prueban una conexión OAuth real.

| Pantalla | UI | Mock 1440 / 390 | Real | Alcance adicional |
|---|---|---|---|---|
| `404.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `admin.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `alertas.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `aviso-privacidad.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `avm.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `bandeja.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `blog.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `bolsa.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `buscador.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `buzon.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `clientes.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `contactos.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `contratos.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `correo.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `crm-ajustes.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `cumplimiento.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `empresas.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `equipo.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `estadisticas.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `expediente.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `facebook-ads.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `facebook-callback.html` | Rediseñado | Probado con mock | Pendiente | Navegación de callback; OAuth pendiente |
| `ficha-manual.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `finanzas.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `firmar.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `firmas.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `guia-agente.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `image-cleaner.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `impuestos.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `index.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `isr.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `landing.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `leads.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `legal.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `login.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `mi-sitio.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `preview-modo/index.html` | Rediseñado | Probado con mock | Pendiente | Referencia suplementaria |
| `preview-modo/preview-agenda.html` | Rediseñado | Probado con mock | Pendiente | Referencia suplementaria |
| `preview-modo/preview-campanas.html` | Rediseñado | Probado con mock | Pendiente | Referencia suplementaria |
| `preview-modo/preview-inicio.html` | Rediseñado | Probado con mock | Pendiente | Referencia suplementaria |
| `propiedades.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `registro.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `reset-password.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `robin.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `sitio.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `soporte.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `tareas.html` | Rediseñado | Probado con mock | Pendiente | Flujo o estados/rol; ver evidencia JSON |
| `unirse.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `verificador.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `verificar-firma.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `video.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `videos/landing.html` | Rediseñado | Probado con mock | Pendiente | Referencia suplementaria |
| `whatsapp-callback.html` | Rediseñado | Probado con mock | Pendiente | Navegación de callback; OAuth pendiente |
| `whatsapp-chatgpt.html` | Rediseñado | Probado con mock | Pendiente | Superficie |
| `whatsapp.html` | Rediseñado | Probado con mock | Pendiente | Superficie |

## Endpoints HTTP

Cada fila corresponde a una operación del contrato inventariado. "Probado con mock" aquí significa invocado y respondido en una simulación; no demuestra su persistencia, autorización real, efectos externos o contrato completo.

| Método | Endpoint | Estado |
|---|---|---|
| GET | `/` | Pendiente |
| POST | `/adjuntos/ligas` | Pendiente |
| GET | `/admin/me` | Pendiente |
| POST | `/admin/org/convertir` | Pendiente |
| POST | `/admin/org/desconvertir` | Pendiente |
| GET | `/admin/org/lista` | Pendiente |
| POST | `/admin/user/acceso-completo` | Pendiente |
| POST | `/admin/user/activo` | Pendiente |
| POST | `/admin/user/eliminar` | Pendiente |
| POST | `/admin/user/modulos` | Pendiente |
| POST | `/admin/user/pais` | Pendiente |
| POST | `/admin/user/rol` | Pendiente |
| GET | `/admin/user/{user_id}/uso` | Pendiente |
| GET | `/admin/users` | Pendiente |
| POST | `/agent` | Pendiente |
| GET | `/agent/health` | Pendiente |
| GET | `/alertas/clientes-potenciales/{propiedad_id}` | Pendiente |
| GET | `/alertas/coincidencias/{contacto_id}` | Pendiente |
| POST | `/alertas/ligar-interesado` | Pendiente |
| POST | `/alertas/preparar` | Pendiente |
| POST | `/alertas/registrar-envio` | Pendiente |
| GET | `/alertas/requerimiento/{contacto_id}` | Pendiente |
| PUT | `/alertas/requerimiento/{contacto_id}` | Pendiente |
| GET | `/alertas/requerimientos` | Probado con mock |
| DELETE | `/alertas/requerimientos/{rid}` | Pendiente |
| PATCH | `/alertas/requerimientos/{rid}` | Probado con mock |
| POST | `/api/avm-claude` | Pendiente |
| POST | `/api/avm-websearch` | Pendiente |
| GET | `/api/buscador` | Pendiente |
| POST | `/api/buscador/buscar` | Pendiente |
| POST | `/api/buscador/escanear/{contacto_id}` | Pendiente |
| GET | `/api/buscador/requerimiento/{contacto_id}` | Pendiente |
| PUT | `/api/buscador/requerimiento/{contacto_id}` | Pendiente |
| GET | `/api/buscador/resultados/{contacto_id}` | Pendiente |
| GET | `/api/colonias` | Pendiente |
| POST | `/api/comparables` | Pendiente |
| POST | `/api/comparables-cercanos` | Pendiente |
| GET | `/api/inpc/{anio}/{mes}` | Pendiente |
| GET | `/api/udis/{fecha}` | Pendiente |
| GET | `/auth/correo-existe` | Pendiente |
| POST | `/avm` | Pendiente |
| POST | `/avm-pdf` | Pendiente |
| GET | `/avm-pdf/{token}` | Pendiente |
| GET | `/bolsa/mis` | Pendiente |
| GET | `/bolsa/propiedades` | Pendiente |
| POST | `/bolsa/publicar` | Pendiente |
| POST | `/bolsa/retirar` | Pendiente |
| POST | `/bolsa/solicitud` | Pendiente |
| GET | `/buzon` | Probado con mock |
| GET | `/buzon/contador` | Probado con mock |
| POST | `/buzon/entrada/{token}` | Pendiente |
| GET | `/buzon/estadisticas` | Pendiente |
| POST | `/buzon/manual` | Probado con mock |
| GET | `/buzon/reglas` | Pendiente |
| PUT | `/buzon/reglas` | Pendiente |
| GET | `/buzon/respuestas` | Probado con mock |
| POST | `/buzon/respuestas` | Pendiente |
| DELETE | `/buzon/respuestas/{rid}` | Pendiente |
| PATCH | `/buzon/respuestas/{rid}` | Pendiente |
| PATCH | `/buzon/{lead_id}` | Probado con mock |
| POST | `/buzon/{lead_id}/asignar` | Pendiente |
| POST | `/buzon/{lead_id}/respondido` | Pendiente |
| POST | `/chat` | Pendiente |
| POST | `/chat-claude` | Pendiente |
| POST | `/cierres` | Pendiente |
| POST | `/cierres/cobrado/{mov_id}` | Pendiente |
| POST | `/cierres/importar` | Pendiente |
| GET | `/cierres/plantilla.csv` | Pendiente |
| GET | `/cierres/por-cobrar` | Probado con mock |
| GET | `/cierres/propiedad/{propiedad_id}` | Pendiente |
| GET | `/cierres/reporte` | Pendiente |
| GET | `/cierres/reporte.csv` | Pendiente |
| GET | `/colonias` | Pendiente |
| DELETE | `/config/eb-key` | Pendiente |
| GET | `/config/eb-key` | Pendiente |
| POST | `/config/eb-key` | Pendiente |
| GET | `/config/public` | Probado con mock |
| POST | `/contactos/eliminar-masivo` | Pendiente |
| POST | `/contactos/importar-archivo` | Pendiente |
| POST | `/contactos/importar-eb` | Pendiente |
| POST | `/contrato` | Pendiente |
| POST | `/contrato/machote/abrir` | Pendiente |
| POST | `/contrato/machote/crear` | Pendiente |
| POST | `/contrato/machote/sugerir` | Pendiente |
| DELETE | `/contrato/machote/{machote_id}` | Pendiente |
| GET | `/contrato/machote/{machote_id}` | Pendiente |
| PATCH | `/contrato/machote/{machote_id}` | Pendiente |
| POST | `/contrato/machote/{machote_id}/generar` | Pendiente |
| POST | `/contrato/machote/{machote_id}/preview` | Pendiente |
| GET | `/contrato/machotes` | Pendiente |
| GET | `/correo/bandeja` | Pendiente |
| POST | `/correo/conectar` | Pendiente |
| DELETE | `/correo/desconectar` | Pendiente |
| POST | `/correo/enviar` | Pendiente |
| GET | `/correo/estado` | Pendiente |
| GET | `/correo/mensaje/{uid_msg}` | Pendiente |
| GET | `/crm/catalogos` | Probado con mock |
| DELETE | `/crm/categorias/{cat_id}` | Pendiente |
| PATCH | `/crm/categorias/{cat_id}` | Pendiente |
| POST | `/crm/contactos/fusionar` | Pendiente |
| POST | `/crm/contactos/lote` | Pendiente |
| POST | `/crm/etapas` | Pendiente |
| POST | `/crm/etapas/orden` | Pendiente |
| DELETE | `/crm/etapas/{etapa_id}` | Pendiente |
| PATCH | `/crm/etapas/{etapa_id}` | Probado con mock |
| GET | `/crm/etiquetas` | Pendiente |
| POST | `/crm/etiquetas/eliminar` | Pendiente |
| POST | `/crm/etiquetas/renombrar` | Pendiente |
| POST | `/crm/fuentes` | Pendiente |
| POST | `/crm/fuentes/fusionar` | Pendiente |
| DELETE | `/crm/fuentes/{fuente_id}` | Pendiente |
| PATCH | `/crm/fuentes/{fuente_id}` | Pendiente |
| POST | `/crm/tipos` | Pendiente |
| DELETE | `/crm/tipos/{tipo_id}` | Pendiente |
| PATCH | `/crm/tipos/{tipo_id}` | Pendiente |
| POST | `/demo-live/accion` | Pendiente |
| POST | `/demo-live/avm` | Pendiente |
| POST | `/demo-live/chat` | Pendiente |
| POST | `/demo-live/contacto/crear` | Pendiente |
| GET | `/demo-live/estado/{session_id}` | Pendiente |
| POST | `/demo-live/propiedad/crear` | Pendiente |
| POST | `/demo-live/sesion` | Pendiente |
| POST | `/demo-live/whatsapp/enviar` | Pendiente |
| GET | `/demo-live/whatsapp/{session_id}` | Pendiente |
| POST | `/demo/agendar` | Pendiente |
| GET | `/easybroker/diagnostico` | Pendiente |
| GET | `/easybroker/fotos-pendientes` | Pendiente |
| POST | `/easybroker/import-all` | Pendiente |
| POST | `/easybroker/import-stats` | Pendiente |
| GET | `/easybroker/migracion/estado` | Pendiente |
| POST | `/easybroker/migracion/iniciar` | Pendiente |
| POST | `/easybroker/migrar-fotos` | Pendiente |
| GET | `/facebook/ad-accounts` | Pendiente |
| POST | `/facebook/ad-description` | Pendiente |
| GET | `/facebook/audiences` | Pendiente |
| POST | `/facebook/audiences/from-contacts` | Pendiente |
| POST | `/facebook/audiences/lookalike` | Pendiente |
| GET | `/facebook/callback` | Pendiente |
| GET | `/facebook/campaign/review` | Pendiente |
| POST | `/facebook/campaign/toggle` | Pendiente |
| GET | `/facebook/campaigns` | Pendiente |
| GET | `/facebook/city-search` | Pendiente |
| DELETE | `/facebook/connection` | Pendiente |
| GET | `/facebook/connection` | Pendiente |
| POST | `/facebook/create-ad` | Pendiente |
| POST | `/facebook/encrypt-tokens` | Pendiente |
| GET | `/facebook/insights` | Pendiente |
| GET | `/facebook/leadgen/status` | Pendiente |
| POST | `/facebook/leadgen/subscribe` | Pendiente |
| GET | `/facebook/leadgen/webhook` | Pendiente |
| POST | `/facebook/leadgen/webhook` | Pendiente |
| GET | `/facebook/page-posts` | Pendiente |
| GET | `/facebook/pages` | Pendiente |
| POST | `/facebook/publish` | Pendiente |
| POST | `/facebook/publish-property` | Pendiente |
| POST | `/facebook/qa-selfcheck` | Pendiente |
| POST | `/facebook/reconcile` | Pendiente |
| POST | `/facebook/refresh-token` | Pendiente |
| POST | `/facebook/save-page` | Pendiente |
| POST | `/facebook/select-ad-account` | Pendiente |
| POST | `/facebook/select-page` | Pendiente |
| POST | `/ficha-manual/descripcion` | Pendiente |
| POST | `/ficha-pdf` | Pendiente |
| GET | `/ficha-pdf/{token}` | Pendiente |
| GET | `/finanzas/categorias` | Probado con mock |
| POST | `/finanzas/categorias` | Pendiente |
| DELETE | `/finanzas/categorias/{cat_id}` | Pendiente |
| PATCH | `/finanzas/categorias/{cat_id}` | Pendiente |
| GET | `/finanzas/comisiones-pendientes` | Probado con mock |
| GET | `/finanzas/cuentas` | Pendiente |
| POST | `/finanzas/cuentas` | Pendiente |
| DELETE | `/finanzas/cuentas/{cuenta_id}` | Pendiente |
| PATCH | `/finanzas/cuentas/{cuenta_id}` | Pendiente |
| GET | `/finanzas/movimientos` | Probado con mock |
| POST | `/finanzas/movimientos` | Pendiente |
| DELETE | `/finanzas/movimientos/{mov_id}` | Pendiente |
| PATCH | `/finanzas/movimientos/{mov_id}` | Pendiente |
| GET | `/finanzas/movimientos/{mov_id}/comprobante` | Pendiente |
| POST | `/finanzas/movimientos/{mov_id}/comprobante` | Pendiente |
| POST | `/finanzas/reporte` | Pendiente |
| GET | `/finanzas/reporte.csv` | Pendiente |
| GET | `/finanzas/reporte/{token}` | Pendiente |
| GET | `/finanzas/resumen` | Probado con mock |
| POST | `/finanzas/ticket` | Pendiente |
| DELETE | `/firmas/campos/{campo_id}` | Pendiente |
| POST | `/firmas/desde-contrato` | Pendiente |
| GET | `/firmas/desde-contrato/{job_id}` | Pendiente |
| GET | `/firmas/documentos` | Probado con mock |
| POST | `/firmas/documentos` | Pendiente |
| DELETE | `/firmas/documentos/{documento_id}` | Pendiente |
| GET | `/firmas/documentos/{documento_id}` | Pendiente |
| PATCH | `/firmas/documentos/{documento_id}` | Pendiente |
| GET | `/firmas/documentos/{documento_id}/archivo` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/archivo` | Pendiente |
| GET | `/firmas/documentos/{documento_id}/campos` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/campos` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/cancelar` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/enviar` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/firmantes` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/nom151` | Pendiente |
| GET | `/firmas/documentos/{documento_id}/paginas` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/rubricar-todas` | Pendiente |
| POST | `/firmas/documentos/{documento_id}/sellar` | Pendiente |
| DELETE | `/firmas/firmantes/{firmante_id}` | Pendiente |
| PATCH | `/firmas/firmantes/{firmante_id}` | Pendiente |
| POST | `/firmas/firmantes/{firmante_id}/recordar` | Pendiente |
| GET | `/firmas/mi-acceso` | Pendiente |
| POST | `/firmas/probar-correo` | Pendiente |
| GET | `/firmas/publico/{token}` | Pendiente |
| GET | `/firmas/publico/{token}/archivo` | Pendiente |
| POST | `/firmas/publico/{token}/codigo` | Pendiente |
| POST | `/firmas/publico/{token}/firmar` | Pendiente |
| POST | `/firmas/publico/{token}/ine` | Pendiente |
| POST | `/firmas/publico/{token}/rechazar` | Pendiente |
| GET | `/firmas/salud` | Pendiente |
| GET | `/firmas/verificar/{folio}` | Pendiente |
| POST | `/images/clean` | Pendiente |
| GET | `/instagram/feed` | Pendiente |
| POST | `/isr-pdf` | Pendiente |
| GET | `/isr-pdf/{token}` | Pendiente |
| GET | `/noticias` | Pendiente |
| GET | `/org` | Probado con mock |
| POST | `/org/aceptar-invitacion` | Pendiente |
| POST | `/org/asignar` | Pendiente |
| PATCH | `/org/contactos/{contacto_id}` | Pendiente |
| PATCH | `/org/contactos/{contacto_id}/etapa` | Pendiente |
| DELETE | `/org/invitacion/{inv_id}` | Pendiente |
| GET | `/org/invitacion/{token}` | Pendiente |
| GET | `/org/invitaciones` | Pendiente |
| POST | `/org/invitar` | Pendiente |
| POST | `/org/miembro/activo` | Pendiente |
| POST | `/org/miembro/permisos` | Pendiente |
| POST | `/org/miembro/rol` | Pendiente |
| GET | `/org/miembros` | Probado con mock |
| POST | `/org/nombre` | Pendiente |
| POST | `/org/tareas/contactos-vinculados` | Pendiente |
| DELETE | `/org/tareas/{tarea_id}` | Pendiente |
| GET | `/p/{pid}` | Pendiente |
| GET | `/ping` | Pendiente |
| POST | `/pld/avisos/generar` | Pendiente |
| POST | `/pld/avisos/{aviso_id}/descartar` | Pendiente |
| POST | `/pld/avisos/{aviso_id}/modificatorio` | Pendiente |
| POST | `/pld/avisos/{aviso_id}/presentado` | Pendiente |
| POST | `/pld/avisos/{aviso_id}/rechazado` | Pendiente |
| POST | `/pld/avisos/{aviso_id}/subido` | Pendiente |
| GET | `/pld/avisos/{aviso_id}/xml` | Pendiente |
| GET | `/pld/bitacora` | Pendiente |
| GET | `/pld/catalogos` | Pendiente |
| GET | `/pld/config` | Pendiente |
| PUT | `/pld/config` | Pendiente |
| DELETE | `/pld/documentos/{documento_id}` | Pendiente |
| GET | `/pld/documentos/{documento_id}/ver` | Pendiente |
| POST | `/pld/expedientes/{expediente_id}/documentos` | Pendiente |
| POST | `/pld/expedientes/{expediente_id}/liga` | Pendiente |
| GET | `/pld/expedientes/{expediente_id}/revision` | Pendiente |
| POST | `/pld/operaciones` | Pendiente |
| POST | `/pld/operaciones/simular` | Pendiente |
| GET | `/pld/publico/{token}` | Pendiente |
| POST | `/pld/publico/{token}` | Pendiente |
| POST | `/pld/publico/{token}/documentos` | Pendiente |
| GET | `/pld/resumen` | Pendiente |
| GET | `/pld/salud` | Pendiente |
| GET | `/profile/status` | Pendiente |
| GET | `/propiedad/{property_id}` | Pendiente |
| GET | `/propiedades` | Pendiente |
| POST | `/propiedades/eliminar-masivo` | Pendiente |
| POST | `/propiedades/lote` | Pendiente |
| PATCH | `/propiedades/{prop_id}` | Pendiente |
| GET | `/push/estado` | Pendiente |
| POST | `/push/prueba` | Pendiente |
| GET | `/s/{slug}` | Pendiente |
| GET | `/s/{slug}/acerca` | Pendiente |
| GET | `/s/{slug}/buscar` | Pendiente |
| GET | `/s/{slug}/contacto` | Pendiente |
| POST | `/s/{slug}/contacto` | Pendiente |
| GET | `/s/{slug}/inmueble/{pid}` | Pendiente |
| GET | `/s/{slug}/p/{pagina}` | Pendiente |
| GET | `/s/{slug}/renta` | Pendiente |
| GET | `/s/{slug}/rentas-temporales` | Pendiente |
| GET | `/s/{slug}/robots.txt` | Pendiente |
| GET | `/s/{slug}/sitemap.xml` | Pendiente |
| GET | `/s/{slug}/venta` | Pendiente |
| POST | `/sitio/{slug}/lead` | Pendiente |
| GET | `/sitios/mios` | Pendiente |
| DELETE | `/sitios/{sitio_id}/dominio` | Pendiente |
| POST | `/sitios/{sitio_id}/dominio` | Pendiente |
| GET | `/sitios/{sitio_id}/dominio/verificar` | Pendiente |
| GET | `/sitios/{sitio_id}/paginas` | Pendiente |
| POST | `/sitios/{sitio_id}/paginas` | Pendiente |
| DELETE | `/sitios/{sitio_id}/paginas/{pagina_id}` | Pendiente |
| PATCH | `/sitios/{sitio_id}/paginas/{pagina_id}` | Pendiente |
| PUT | `/sitios/{tipo}` | Pendiente |
| POST | `/solicitud-arrendamiento/analizar` | Pendiente |
| POST | `/soporte/mensaje` | Pendiente |
| POST | `/subscription/activate` | Pendiente |
| POST | `/subscription/cancel` | Pendiente |
| POST | `/subscription/checkout` | Pendiente |
| POST | `/subscription/empresa/asientos` | Pendiente |
| POST | `/subscription/empresa/checkout` | Pendiente |
| GET | `/subscription/empresa/plan` | Pendiente |
| POST | `/subscription/revenuecat-webhook` | Pendiente |
| GET | `/subscription/status` | Probado con mock |
| POST | `/subscription/webhook` | Pendiente |
| POST | `/supervision/comentarios` | Pendiente |
| POST | `/supervision/comentarios/{actividad_id}/atendido` | Pendiente |
| GET | `/supervision/contador` | Probado con mock |
| GET | `/supervision/pendientes` | Pendiente |
| POST | `/telemetria/sesion-modulo` | Pendiente |
| POST | `/transcribir` | Pendiente |
| DELETE | `/usuario/eliminar-cuenta` | Pendiente |
| GET | `/video/estado/{job_id}` | Pendiente |
| POST | `/video/generar` | Pendiente |
| GET | `/video/mis-videos` | Pendiente |
| GET | `/video/propiedad/{propiedad_id}` | Pendiente |
| DELETE | `/video/{job_id}` | Pendiente |
| POST | `/whatsapp-chatgpt/complete-signup` | Pendiente |
| GET | `/whatsapp-chatgpt/config` | Pendiente |
| GET | `/whatsapp-chatgpt/numbers` | Pendiente |
| POST | `/whatsapp-chatgpt/send-test` | Pendiente |
| POST | `/whatsapp2/agendar` | Pendiente |
| GET | `/whatsapp2/app-webhook` | Pendiente |
| POST | `/whatsapp2/app-webhook` | Pendiente |
| GET | `/whatsapp2/automatizaciones` | Pendiente |
| POST | `/whatsapp2/automatizaciones` | Pendiente |
| DELETE | `/whatsapp2/automatizaciones/{auto_id}` | Pendiente |
| PATCH | `/whatsapp2/automatizaciones/{auto_id}` | Pendiente |
| GET | `/whatsapp2/campanas` | Pendiente |
| POST | `/whatsapp2/campanas` | Pendiente |
| POST | `/whatsapp2/campanas/audiencia` | Pendiente |
| GET | `/whatsapp2/campanas/{campana_id}` | Pendiente |
| POST | `/whatsapp2/connect` | Pendiente |
| PATCH | `/whatsapp2/contactos/{contacto_id}` | Pendiente |
| POST | `/whatsapp2/contactos/{contacto_id}/notas` | Pendiente |
| GET | `/whatsapp2/conversaciones` | Pendiente |
| DELETE | `/whatsapp2/conversaciones/{conversacion_id}` | Pendiente |
| PATCH | `/whatsapp2/conversaciones/{conversacion_id}` | Pendiente |
| POST | `/whatsapp2/conversaciones/{conversacion_id}/lectura` | Pendiente |
| GET | `/whatsapp2/entrenamiento` | Pendiente |
| PUT | `/whatsapp2/entrenamiento` | Pendiente |
| GET | `/whatsapp2/estadisticas` | Pendiente |
| GET | `/whatsapp2/etiquetas` | Pendiente |
| GET | `/whatsapp2/mensajes` | Probado con mock |
| POST | `/whatsapp2/mensajes` | Pendiente |
| POST | `/whatsapp2/mensajes/plantilla` | Pendiente |
| DELETE | `/whatsapp2/mensajes/{mensaje_id}` | Pendiente |
| GET | `/whatsapp2/numeros` | Pendiente |
| DELETE | `/whatsapp2/numeros/{numero_id}` | Pendiente |
| PATCH | `/whatsapp2/numeros/{numero_id}` | Pendiente |
| GET | `/whatsapp2/numeros/{numero_id}/app-suscrito` | Pendiente |
| GET | `/whatsapp2/numeros/{numero_id}/verificar` | Pendiente |
| GET | `/whatsapp2/plantillas` | Pendiente |
| POST | `/whatsapp2/plantillas` | Pendiente |
| POST | `/whatsapp2/probar` | Pendiente |
| GET | `/whatsapp2/webhook` | Pendiente |
| POST | `/whatsapp2/webhook` | Pendiente |

HTTP: 21 operaciones invocadas con mock; 334 pendientes. Ninguna probada real.

## Cierre de pruebas reales

La demo guarda datos ficticios en el navegador. El backend Railway y Cloudflare existentes siguen siendo los únicos destinos de staging. Las comprobaciones reales de guardado, RLS, funciones, triggers y storage esperan el esquema completo y una base Supabase aislada con su configuración en Railway; no se usa producción ni broquer-beta. Los pasos de configuración están en `STAGING_SETUP.md`. Stripe continúa en test para el entorno conectado; WhatsApp/Meta, push y correos no se envían desde la demo.

La emulación Chromium a 390 px no sustituye una prueba de WKWebView en un iPhone real. El suelo de 16 px y los cambios de viewport se conservan en el código; la comprobación nativa queda pendiente.

La suite histórica completa no se declara aprobada por estos resultados: esta entrega certifica los controles de UI y los flujos mock enumerados. La suite y los límites de arquitectura previos deben revisarse antes de pedir aprobación de merge.
