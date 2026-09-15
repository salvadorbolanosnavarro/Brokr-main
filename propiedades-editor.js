// Broquer · Tus Inmuebles — fotos que llegan desde el Editor de imágenes.
// Separado de propiedades.html para no hacer crecer ese archivo (ver
// scripts/architecture_debt.py). Usa los globales de la página: SB_URL, SB_KEY,
// g, openPropForm, getValidToken, renderFotosPreview, mostrarToast,
// uploadedFotoUrls y propFormDirty.

// Sube un blob de foto al bucket "fotos-propiedades" y regresa su URL pública.
// Compartido entre el <input type=file> normal y las fotos que llegan ya
// editadas desde el Editor de imágenes (ver preloadFotosDesdeEditor).
async function subirFotoABucket(blob, ext, contentType, userToken) {
  const name = `prop_${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`;
  const r = await fetch(`${SB_URL}/storage/v1/object/fotos-propiedades/${name}`, { method:'POST', headers:{ 'apikey':SB_KEY, 'Authorization':'Bearer '+userToken, 'Content-Type':contentType, 'x-upsert':'true' }, body:blob });
  if (!r.ok) {
    const errTxt = await r.text();
    if (r.status === 401 || r.status === 403 || errTxt.includes('row-level security')) {
      throw new Error('Tu sesión expiró. Vuelve a iniciar sesión.');
    }
    throw new Error(errTxt);
  }
  return `${SB_URL}/storage/v1/object/public/fotos-propiedades/${name}`;
}

// ── Fotos enviadas desde el Editor de imágenes ──────────────────────────────
// El botón "Nuevo inmueble con estas imágenes" del editor guarda las fotos
// editadas en IndexedDB (sessionStorage aguanta ~5MB por origen y con 2-3
// fotos editadas ya revienta) y navega hasta acá. Se abre el alta de
// inmueble y se suben esas fotos al bucket, igual que si el agente las
// hubiera elegido desde su equipo.
const IDB_TRANSFER_MAX_AGE_MS = 30 * 60 * 1000; // 30 minutos

// Lee y borra `clave` de la base 'broquer-transfer' (object store 'kv').
// Regresa null si no hay nada, si algo falla, o si el dato tiene más de
// IDB_TRANSFER_MAX_AGE_MS (una pestaña vieja que se quedó abierta no debe
// resucitar una transferencia obsoleta).
function tomarTransferenciaIDB(clave) {
  return new Promise((resolve) => {
    let req;
    try { req = indexedDB.open('broquer-transfer', 1); }
    catch (e) { resolve(null); return; }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv');
    };
    req.onerror = () => resolve(null);
    req.onsuccess = () => {
      const db = req.result;
      try {
        const tx = db.transaction('kv', 'readwrite');
        const store = tx.objectStore('kv');
        const getReq = store.get(clave);
        let registro = null;
        getReq.onsuccess = () => { registro = getReq.result; store.delete(clave); };
        tx.oncomplete = () => {
          db.close();
          if (!registro || typeof registro !== 'object') { resolve(null); return; }
          const vieja = !registro.ts || (Date.now() - registro.ts) > IDB_TRANSFER_MAX_AGE_MS;
          resolve(vieja ? null : registro.valor);
        };
        tx.onerror = () => { db.close(); resolve(null); };
      } catch (e) { db.close(); resolve(null); }
    };
  });
}

async function preloadFotosDesdeEditor() {
  let imgs = await tomarTransferenciaIDB('editor_images_prop');
  if (!imgs) {
    let raw = null;
    try { raw = sessionStorage.getItem('broquer_editor_images_prop'); } catch(_) {}
    if (raw) {
      try { sessionStorage.removeItem('broquer_editor_images_prop'); } catch(_) {}
      try { imgs = JSON.parse(raw); } catch(_) { imgs = null; }
    }
  }
  if (!Array.isArray(imgs) || !imgs.length) return;

  openPropForm(null);
  const progress = g('fotos-progress');
  const userToken = await getValidToken();
  if (!userToken) {
    if (progress) progress.textContent = 'Tu sesión expiró. Vuelve a iniciar sesión.';
    return;
  }
  let subidas = 0;
  let fallidas = 0;
  let ultimoError = '';
  for (let i = 0; i < imgs.length; i++) {
    const img = imgs[i];
    if (!img || !img.url) continue;
    if (progress) progress.textContent = `Subiendo ${i + 1} de ${imgs.length} imágenes del editor…`;
    try {
      const blob = await (await fetch(img.url)).blob();
      const mime = blob.type || 'image/jpeg';
      const ext = (mime.split('/')[1] || 'jpg').replace('jpeg', 'jpg');
      const url = await subirFotoABucket(blob, ext, mime, userToken);
      uploadedFotoUrls.push(url);
      renderFotosPreview();
      subidas++;
    } catch (err) {
      fallidas++;
      ultimoError = (err && err.message) || String(err);
    }
  }
  if (subidas) {
    propFormDirty = true;
    mostrarToast(subidas + ' imagen' + (subidas !== 1 ? 'es' : '') + ' del editor cargada' + (subidas !== 1 ? 's' : ''));
  }
  // Se escribe DESPUÉS del ciclo: renderFotosPreview() (llamado en cada
  // subida exitosa) sobrescribe fotos-progress con el conteo de fotos.
  if (fallidas && progress) {
    progress.textContent = (fallidas === 1 ? 'No se pudo subir ' : 'No se pudieron subir ')
      + fallidas + ' de ' + imgs.length + ' imágenes: ' + ultimoError;
  }
}
