# Marca de staging: Comisión Fácil / Cecil IA

Cambio limitado al branding de la publicación existente del PR #180.

- Logotipo completo en escritorio y monograma «cf» en espacios compactos, favicon e iconos. Los PNG suministrados se conservan sin modificar; los SVG encuadran esos mismos originales.
- Nombre comercial «Comisión Fácil» en títulos, etiquetas y textos de presentación.
- Asistente «Cecil IA», con los alias de voz del nuevo nombre añadidos a los anteriores.
- La transformación se aplica exclusivamente en `scripts/build_staging.py`. No cambia los archivos funcionales originales, IDs, eventos, almacenamiento, endpoints, dominios, destinatarios de correo, permisos ni datos.
- Los colores, controles, distribución y tipografía de la aplicación se mantienen. El CSS nuevo se limita al tamaño y encuadre del logotipo.

Comprobación: cinco pruebas del reemplazo de marca, tres del build demo y siete de aislamiento de staging. Revisión de las 55 pantallas a 1440 y 390 px mediante `measure_ui_application.cjs`; ejecutar el auditor con `BROQUER_TEST_BRAND='Comisión Fácil'`.

La publicación conserva el modo demo existente. No modifica producción ni fusiona la rama en main.
