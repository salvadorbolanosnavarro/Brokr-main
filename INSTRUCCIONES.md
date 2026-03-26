# BROKR® — Guía de integración de la nueva estructura modular

## ¿Qué estamos haciendo?
Pasamos de 1 archivo gigante (`index.html` de 2,385 líneas) a 8 archivos organizados
donde cada parte del software es independiente.

## Tu repositorio ANTES:
```
CNAME
Dockerfile
admin.html
avm.html
avm_api.py
contratos.html
ficha-manual.html
ficha.html
generar_contrato.py
icon-192.png
icon-512.png
index.html          ← el monolito actual (este se reemplaza)
login.html
main.py
manifest.json
registro.html
requirements.txt
sw.js
```

## Tu repositorio DESPUÉS:
```
CNAME
Dockerfile
admin.html
avm.html
avm_api.py
contratos.html
css/                    ← NUEVO (carpeta)
  design-system.css     ← NUEVO — toda la identidad visual
  shell.css             ← NUEVO — layout del sidebar/header
ficha-manual.html
ficha.html
generar_contrato.py
icon-192.png
icon-512.png
index.html              ← NUEVO (reemplaza al anterior)
index-backup.html       ← tu index.html actual, renombrado como respaldo
js/                     ← NUEVO (carpeta)
  chat.js               ← NUEVO — chat flotante con IA
  router.js             ← NUEVO — navegación entre módulos
  services.js           ← NUEVO — auth, supabase, utilidades
login.html
main.py
manifest.json
modulos/                ← NUEVO (carpeta)
  isr.html              ← NUEVO — calculadora ISR (independiente)
  propiedades.html      ← NUEVO — gestión de inmuebles (independiente)
registro.html
requirements.txt
sw.js
```

## PASOS (en orden):

### Paso 1 — Respaldo
Renombra tu `index.html` actual a `index-backup.html`.
Si algo sale mal, solo renombras de vuelta y todo vuelve a como estaba.

### Paso 2 — Copiar archivos nuevos
Copia al repositorio:
- La carpeta `css/` completa (con design-system.css y shell.css)
- La carpeta `js/` completa (con chat.js, router.js, services.js)
- La carpeta `modulos/` completa (con isr.html y propiedades.html)
- El nuevo `index.html`

### Paso 3 — Verificar
Abre la app en tu navegador. Deberías ver:
- ✅ El sidebar con todos los módulos
- ✅ El dashboard con las tarjetas de módulos
- ✅ Fichas, contratos, AVM siguen funcionando (son iframes al mismo archivo)
- ✅ La calculadora ISR funciona dentro de su iframe
- ✅ Mis inmuebles funciona dentro de su iframe
- ✅ El chat flotante funciona con el mismo backend
- ✅ Login/logout funciona igual

### Paso 4 — Si algo no funciona
Renombra `index.html` → `index-new.html`
Renombra `index-backup.html` → `index.html`
¡Listo! Estás de vuelta al estado anterior. Cero riesgo.

## ARCHIVOS QUE NO SE TOCAN:
- admin.html — sin cambios
- avm.html — sin cambios
- contratos.html — sin cambios
- ficha-manual.html — sin cambios
- ficha.html — sin cambios
- login.html — sin cambios
- registro.html — sin cambios
- manifest.json — sin cambios
- sw.js — sin cambios
- Todos los archivos Python — sin cambios
- Dockerfile — sin cambios
- CNAME — sin cambios
