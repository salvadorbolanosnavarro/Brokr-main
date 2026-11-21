# Checklist del piloto: obligatorio antes de activar

Solo staging ejecutado. No se autoriza main ni producción por completar esta lista.

- [x] Contactos y leads CRUD, etapa y persistencia por interfaz con A3.
- [x] Contrato ficticio generado y Word descargado/verificado por interfaz.
- [x] Flag servidor A3/B2, botones ida/vuelta y revocación conservando sesión.
- [x] Registro de error controlado aceptado por Sentry y acuse guardado.
- [x] Ensayo PostgreSQL: copia staging restaurada en proyecto separado, esquema/datos/RLS verificados; proyecto temporal borrado.
- [x] Ensayo Storage: foto ficticia copiada, borrada y restaurada al mismo nombre, hash y tamaño idénticos;7checks/32.606s.
- [x] Opinión de valor por interfaz después del ajuste #224:7comparables y PDF descargado/verificado con A3.
- [ ] iPhone Safari/WebView: Salvador revisa teclado/campos/zoom.
- [ ] Antes de activar: respaldo previo verificado de la base REAL **Y de todos los bytes de Storage**, en destino privado fuera del proyecto, con manifiesto SHA256 y custodio. El ensayo de una foto no significa que producción ya esté respaldada.
- [ ] Confirmar por administrador UUID real de Salvador; flag apagado y allowlist vacía hasta aprobación.
- [ ] Revisar configuración de errores de producción y fallback antes de activar.
- [ ] Nuevo OK explícito de Salvador para publicar/activar solo su cuenta. #217 continúa draft.

Procedimientos: BACKUP_RUNBOOK_20261121.md y STORAGE_BACKUP_RUNBOOK_20261121.md. Un rollback visual apaga el flag y vuelve a Broquer sin borrar la sesión; no restaurar toda la base por un fallo visual. Recuperación de datos en producción requiere autorización y conciliación de cambios posteriores.
