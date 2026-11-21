# Respaldo y restauración de Storage

Supabase conserva metadatos de Storage en PostgreSQL; sus backups de base no incluyen bytes de fotos/documentos. El piloto exige **respaldo de base + Storage antes de activar**.

## Ensayo realizado únicamente en staging

Proyecto tymhlvawnqadqgwnpruk, cuenta A3, bucket fotos-propiedades. Se generó una foto ficticia nueva de12665bytes. Se copió mediante Storage API a una carpeta de respaldo de A3, se descargó y comprobó SHA256, se borró SOLO el original recién creado, se comprobó que el objeto autenticado ya no existía (400), se copió el respaldo de vuelta a la ruta original y se descargó otra vez. Tamaño y SHA256 idénticos.7comprobaciones OK en32.606s; copia3.610s, restauración4.675s. No se borraron archivos preexistentes, ni se cambió RLS ni variables ni producción. Original restaurado y copia ficticia conservados para revisión.

Manifiesto y tiempos: storage-restore-20261121.json. Script reproducible: scripts/staging_storage_restore_drill.py, con archivo privado de cuenta A3 fuera de Git. Solo acepta el host de staging mediante el helper de pruebas; no usa service_role ni acceso a otras cuentas.

Este ensayo acredita la recuperación de un objeto borrado mediante Storage, **no** un respaldo completo de todos los buckets ni resiliencia ante pérdida del proyecto: una carpeta dentro del mismo proyecto también se pierde si se elimina el proyecto.

## Procedimiento previo al piloto de producción (preparado; no ejecutado)

Responsable: administrador de Supabase designado por Salvador. Ejecutar durante la ventana autorizada con credenciales mediante gestor privado, nunca en chat/Git.

1. Verificar proyecto/ref y tomar respaldo de PostgreSQL inmediatamente previo al piloto. Conservar fecha, ubicación, custodio y evidencia de restauración. No activar con una copia diaria anterior a escrituras relevantes sin aceptar ese RPO.
2. Inventariar TODOS los buckets, públicos y privados: configuración (public, límites/MIME), políticas RLS, objetos con bucket/ruta, tamaño, contentType y cacheControl. Paginar listados y recorrer subcarpetas; no asumir que una lista de1000archivos es completa.
3. Descargar los bytes por Storage API/cliente oficial autorizado a un destino privado cifrado FUERA del proyecto. Mantener manifiesto de cada ruta, bytes y SHA256. Incluir fotos, firmas, contratos y videos; no solo fotos-propiedades. El backup debe estar accesible al operador de recuperación sin depender del proyecto afectado.
4. Verificar que número de objetos, suma de bytes y hashes concuerdan; registrar inicio/fin, cifrado, retención y custodio. No inventar tiempo de producción a partir de32.6s del ensayo.
5. Probar restauración de una muestra representativa en destino aislado aprobado: preparar buckets/configuración y RLS; subir bytes en su ruta exacta con MIME/cacheControl y verificar descarga/hash. Para recuperación de un objeto borrado, copiarlo desde el respaldo a su bucket/ruta original. Para recuperación total, restaurar esquema/RLS/roles y todos los objetos, conciliando ownership y metadatos antes de habilitar escrituras. No insertar solamente filas en storage.objects.
6. Validar lectura pública/privada, aislamiento entre cuentas y descargas desde la aplicación. Una muestra funcional no sustituye verificar el manifiesto completo.
7. Solo tras respaldo verificado de base Y Storage y revisión iPhone por Salvador, solicitar el OK de activación para la cuenta real. Un fallo visual se revierte apagando el flag, sin restaurar toda la base. Restaurar datos/archivos en producción únicamente con autorización explícita y conciliación de cambios posteriores.

Documentación oficial consultada: https://supabase.com/docs/guides/storage/management/copy-move-objects y https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore.
