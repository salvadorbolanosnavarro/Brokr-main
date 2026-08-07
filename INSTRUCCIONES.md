# Broquer Cierres — Cómo publicarlo en cierres.broquer.app

Tiempo total: unos 15 minutos. Solo necesitas tu GitHub y tu GoDaddy.

---

## PASO 0 — Lo ÚNICO que debes editar antes de subir

Abre `index.html` con cualquier editor de texto y busca la palabra:

```
EDITAR-AQUI
```

Vas a encontrar esta línea:

```
WHATSAPP: "5214430000000",           // ← EDITAR-AQUI
```

Cambia el número por TU número de WhatsApp con este formato:
**521 + lada + número, todo pegado, sin espacios ni signos.**
Ejemplo: si tu número es 443 123 4567 → escribe `5214431234567`

Guarda el archivo. Listo, no toques nada más.

---

## PASO 1 — Crear el repositorio en GitHub

1. Entra a github.com y crea un repositorio nuevo llamado: `broquer-cierres`
2. Déjalo **Public**.
3. Sube el archivo `index.html` (botón "Add file" → "Upload files" → arrastra el archivo → "Commit changes").

---

## PASO 2 — Activar GitHub Pages

1. Dentro del repositorio: **Settings → Pages** (menú izquierdo).
2. En "Source" elige: **Deploy from a branch**.
3. Branch: **main** · Carpeta: **/ (root)** → **Save**.
4. Espera 1-2 minutos. Te dará una dirección tipo `TUUSUARIO.github.io/broquer-cierres`. Ábrela para confirmar que el sitio carga.

---

## PASO 3 — Conectar el subdominio cierres.broquer.app

**En GitHub (mismo lugar, Settings → Pages):**
1. En "Custom domain" escribe: `cierres.broquer.app` → **Save**.
2. Deja marcada la casilla **Enforce HTTPS** (si no aparece de inmediato, regresa en 30 min y márcala).

**En GoDaddy:**
1. Entra a tu dominio `broquer.app` → **DNS** → **Agregar registro**.
2. Llénalo así:
   - Tipo: **CNAME**
   - Nombre (host): `cierres`
   - Valor (apunta a): `TUUSUARIO.github.io`  ← tu usuario de GitHub, el mismo que usas para Broquer
   - TTL: el que venga por defecto
3. Guarda. Puede tardar de 10 minutos a 1 hora en propagarse.

Cuando cargue **https://cierres.broquer.app** con candado verde, está publicado.

---

## PASO 4 — Probarlo (checklist de 2 minutos)

- [ ] Abre el sitio en tu iPhone.
- [ ] Haz el diagnóstico completo eligiendo "Voy a vender".
- [ ] Toca "Enviar mi diagnóstico por WhatsApp" → debe abrir TU WhatsApp con el resumen ya escrito.
- [ ] Toca "Guardar en PDF" → debe salir el diagnóstico limpio, como documento.
- [ ] Prueba el botón "Regresar" y "Empezar de nuevo".

---

## Qué hace la página (por si se te olvida en 3 meses)

- **Landing** que vende el servicio de coordinación de cierres.
- **Diagnóstico interactivo**: hasta 9 preguntas que se adaptan al caso (venta, compra, herencia, regularización) y generan un "Diagnóstico de Cierre" con folio, checklist de documentos personalizado, focos rojos, exención de ISR si aplica y tiempo estimado.
- **Todos los caminos llevan a tu WhatsApp** con el resumen del caso ya escrito — ese mensaje es tu lead calificado.
- No usa base de datos ni servidor: es un solo archivo HTML. Si un día quieres guardar los diagnósticos en Supabase, se le agrega — pero para el piloto no lo necesitas: cada lead te llega completo por WhatsApp.

## Cosas que puedes cambiar tú mismo sin miedo

- **Textos y precios**: busca el texto en `index.html` y edítalo directo (por ejemplo `$15,000`).
- **Nombre del servicio**: en el mismo bloque CONFIG está `MARCA`.

Si algo se descompone al editar: vuelve a subir la versión anterior desde GitHub (pestaña "History" del archivo) y listo.
