// Broquer · Adjuntos de historial — fotos, videos y archivos ligados a una
// nota de "actividades" (Directorio/Contactos, Clientes e Inmuebles).
// Módulo compartido para no triplicar esta lógica en cada página (ver
// scripts/architecture_debt.py: contactos.html y propiedades.html tienen
// techo de bytes). Usa window.brokrSb (app-shell.js) para subir con el
// mismo auto-refresh de sesión que ya usa el resto de la app.
//
// Cómo se usa desde cada página:
//   1) Un <input type="file" multiple> oculto + botón de clip que lo abre,
//      con onchange="haAgregarArchivos(this.files, 'ID-DEL-PREVIEW')".
//   2) Un <div id="ID-DEL-PREVIEW"></div> junto al composer para la
//      previsualización de lo que se subió y aún no se guarda.
//   3) Al guardar la nota: haTomarAdjuntosListos('ID-DEL-PREVIEW') regresa
//      el arreglo listo para mandar en actividades.adjuntos (o [] si no
//      había nada) y limpia el estado/preview.
//   4) Al pintar el feed: haRenderAdjuntos(actividad.adjuntos) regresa el
//      HTML de la galería de esa nota.

const HA_BUCKET = 'adjuntos-historial';
const HA_MAX_BYTES = 25 * 1024 * 1024; // 25 MB por archivo
const HA_ACCEPT = 'image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.txt';

// Estado de los adjuntos que el usuario ya eligió/subió para la nota que
// está escribiendo, agrupado por el id del contenedor de preview (así
// varias páginas/composers no se pisan si algún día conviven).
const _haPendientesPorPreview = new Map();

function haCategoria(mime) {
  if (typeof mime !== 'string') return 'archivo';
  if (mime.startsWith('image/')) return 'imagen';
  if (mime.startsWith('video/')) return 'video';
  return 'archivo';
}

function haFormatoTamano(bytes) {
  if (typeof bytes !== 'number' || !isFinite(bytes)) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function haEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const HA_ICONOS = {
  imagen: '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 16l-5.5-5.5a2 2 0 00-2.8 0L3 20"/></svg>',
  video: '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><rect x="2.5" y="6" width="13" height="12" rx="2" stroke-linejoin="round"/><path stroke-linecap="round" stroke-linejoin="round" d="M15.5 10.5l5.5-3.2v9.4l-5.5-3.2"/></svg>',
  archivo: '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M8 3.5h5.5L18 8v10.5a2 2 0 01-2 2H8a2 2 0 01-2-2v-13a2 2 0 012-2z"/><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 3.5V8H18"/></svg>',
  clip: '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M17.5 8.5l-7.1 7.1a2.5 2.5 0 003.5 3.5l7.1-7.1a4.5 4.5 0 00-6.4-6.4l-7.1 7.1a6.5 6.5 0 009.2 9.2"/></svg>',
  quitar: '<svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.4"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>',
};

function _haInyectarEstilos() {
  if (document.getElementById('ha-estilos')) return;
  const style = document.createElement('style');
  style.id = 'ha-estilos';
  style.textContent = `
.ha-clip-btn { border: 1px solid var(--line,#ddd); background: var(--bone,#f5f5f3); color: var(--ink-2,#555); border-radius: var(--r,8px); width: 40px; flex-shrink: 0; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.ha-clip-btn:hover { opacity: .85; }
.ha-preview { display: flex; flex-wrap: wrap; gap: 8px; margin: -4px 0 12px; }
.ha-preview:empty { display: none; margin: 0; }
.ha-chip { position: relative; display: flex; align-items: center; gap: 6px; background: var(--bone,#f5f5f3); border: 1px solid var(--line,#ddd); border-radius: var(--r-sm,6px); padding: 5px 9px 5px 5px; font-size: 12px; max-width: 220px; }
.ha-chip--error { border-color: #d33; color: #d33; }
.ha-chip__thumb { width: 26px; height: 26px; border-radius: 4px; object-fit: cover; flex-shrink: 0; background: var(--line,#ddd); }
.ha-chip__nombre { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-chip__quitar { border: none; background: none; cursor: pointer; color: inherit; opacity: .6; padding: 2px; flex-shrink: 0; }
.ha-chip__quitar:hover { opacity: 1; }
.ha-chip__spin { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--line,#ddd); border-top-color: var(--ink-2,#555); flex-shrink: 0; animation: ha-spin .7s linear infinite; }
@keyframes ha-spin { to { transform: rotate(360deg); } }
.ha-grid { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.ha-item { display: block; }
.ha-item--imagen img { width: 92px; height: 92px; object-fit: cover; border-radius: var(--r-sm,6px); display: block; }
.ha-item--video video { width: 180px; max-height: 130px; border-radius: var(--r-sm,6px); display: block; background: #000; }
.ha-item--archivo { display: flex; align-items: center; gap: 6px; background: var(--bone,#f5f5f3); border: 1px solid var(--line,#ddd); border-radius: var(--r-sm,6px); padding: 6px 10px; font-size: 12px; color: var(--ink,#222); text-decoration: none; max-width: 220px; }
.ha-item--archivo:hover { opacity: .85; }
.ha-item__nombre { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-item__peso { color: var(--mute,#888); flex-shrink: 0; }
`;
  document.head.appendChild(style);
}
_haInyectarEstilos();

async function haSubirArchivo(file) {
  if (!window.brokrSb) throw new Error('La app aún se está cargando. Intenta de nuevo en un segundo.');
  if (file.size > HA_MAX_BYTES) throw new Error('pesa más de 25 MB');
  const extMatch = /\.([a-zA-Z0-9]+)$/.exec(file.name || '');
  const ext = (extMatch ? extMatch[1] : 'bin').toLowerCase();
  const ruta = `${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`;
  const r = await window.brokrSb.fetch('storage/v1/object/' + HA_BUCKET + '/' + ruta, {
    method: 'POST',
    headers: { 'Content-Type': file.type || 'application/octet-stream', 'x-upsert': 'true' },
    body: file,
    timeoutMs: 120000, // archivos hasta 25 MB en redes lentas necesitan más que el timeout default de 15 s
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    if (r.status === 401 || r.status === 403 || txt.includes('row-level security')) {
      throw new Error('tu sesión expiró');
    }
    throw new Error(txt || ('HTTP ' + r.status));
  }
  return {
    url: window.brokrSb.url + '/storage/v1/object/public/' + HA_BUCKET + '/' + ruta,
    nombre: file.name || ruta,
    tipo: file.type || 'application/octet-stream',
    tamano: file.size,
    categoria: haCategoria(file.type),
  };
}

function _haChipHtml(item) {
  const cls = 'ha-chip' + (item.estado === 'error' ? ' ha-chip--error' : '');
  let icono;
  if (item.estado === 'subiendo') icono = '<span class="ha-chip__spin"></span>';
  else if (item.categoria === 'imagen' && item.previewUrl) icono = `<img class="ha-chip__thumb" src="${haEsc(item.previewUrl)}" alt=""/>`;
  else icono = HA_ICONOS[item.categoria] || HA_ICONOS.archivo;
  const titulo = item.estado === 'error' ? `No se pudo subir: ${haEsc(item.error || '')}` : haEsc(item.nombre);
  return `<span class="${cls}" title="${titulo}">${icono}<span class="ha-chip__nombre">${haEsc(item.nombre)}</span>
    <button type="button" class="ha-chip__quitar" onclick="haQuitarPendiente('${item.id}','${item._previewElId}')" title="Quitar" aria-label="Quitar">${HA_ICONOS.quitar}</button></span>`;
}

function _haRenderPreview(previewElId) {
  const el = document.getElementById(previewElId);
  if (!el) return;
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  el.innerHTML = lista.map(_haChipHtml).join('');
}

// Encola y sube en paralelo los archivos elegidos con el <input type=file>.
// No bloquea el composer: cada archivo se sube en cuanto se elige y la nota
// se puede escribir mientras tanto; al guardar se usan los que ya hayan
// terminado (ver haHaySubiendoPendiente/haTomarAdjuntosListos).
function haAgregarArchivos(fileList, previewElId) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  if (!_haPendientesPorPreview.has(previewElId)) _haPendientesPorPreview.set(previewElId, []);
  const lista = _haPendientesPorPreview.get(previewElId);

  files.forEach((file) => {
    const id = Date.now() + '_' + Math.random().toString(36).slice(2);
    const item = {
      id,
      nombre: file.name || 'archivo',
      tipo: file.type || 'application/octet-stream',
      tamano: file.size,
      categoria: haCategoria(file.type),
      estado: 'subiendo',
      url: null,
      error: null,
      previewUrl: null,
      _previewElId: previewElId,
    };
    if (item.categoria === 'imagen') {
      try { item.previewUrl = URL.createObjectURL(file); } catch (e) { /* sin preview local, no es grave */ }
    }
    lista.push(item);
    _haRenderPreview(previewElId);

    haSubirArchivo(file).then((meta) => {
      item.estado = 'ok';
      item.url = meta.url;
      _haRenderPreview(previewElId);
    }).catch((err) => {
      item.estado = 'error';
      item.error = (err && err.message) || String(err);
      _haRenderPreview(previewElId);
    });
  });
}

function haQuitarPendiente(id, previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  const idx = lista.findIndex((it) => it.id === id);
  if (idx === -1) return;
  const [item] = lista.splice(idx, 1);
  if (item && item.previewUrl) { try { URL.revokeObjectURL(item.previewUrl); } catch (e) {} }
  _haRenderPreview(previewElId);
}

// true si algún archivo todavía se está subiendo (para no guardar la nota
// a medias mientras el adjunto no tiene URL final).
function haHaySubiendoPendiente(previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  return lista.some((it) => it.estado === 'subiendo');
}

// true si ya hay al menos un adjunto subido con éxito esperando a guardarse
// (a diferencia de haTomarAdjuntosListos, no limpia nada: sirve para decidir
// si la nota se puede guardar sin descartar la previsualización de paso).
function haHayAdjuntosListos(previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  return lista.some((it) => it.estado === 'ok');
}

function haHayPendientesConError(previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  return lista.some((it) => it.estado === 'error');
}

// Los adjuntos ya subidos, en el mismo formato que haTomarAdjuntosListos,
// pero SIN limpiar nada (para guardar y, solo si sale bien, limpiar).
function haAdjuntosListos(previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  return lista.filter((it) => it.estado === 'ok').map((it) => ({
    url: it.url, nombre: it.nombre, tipo: it.tipo, tamano: it.tamano, categoria: it.categoria,
  }));
}

// Se llama al guardar la nota: regresa los adjuntos listos (subidos con
// éxito) en el formato que va a actividades.adjuntos, y limpia el estado y
// la previsualización para la siguiente nota.
function haTomarAdjuntosListos(previewElId) {
  const lista = _haPendientesPorPreview.get(previewElId) || [];
  const listos = lista.filter((it) => it.estado === 'ok').map((it) => ({
    url: it.url, nombre: it.nombre, tipo: it.tipo, tamano: it.tamano, categoria: it.categoria,
  }));
  lista.forEach((it) => { if (it.previewUrl) { try { URL.revokeObjectURL(it.previewUrl); } catch (e) {} } });
  _haPendientesPorPreview.set(previewElId, []);
  _haRenderPreview(previewElId);
  return listos;
}

// HTML de la galería de adjuntos de una nota ya guardada, para el feed de
// historial. Imágenes con miniatura clicable, videos reproducibles inline,
// y cualquier otro archivo como liga de descarga con su nombre y peso.
// Los archivos de adjuntos-historial se pintan con data-ha-url: el bloque de
// "ligas temporales" de abajo les pone una liga firmada (el bucket es privado).
function haRenderAdjuntos(adjuntos) {
  if (!Array.isArray(adjuntos) || !adjuntos.length) return '';
  return '<div class="ha-grid">' + adjuntos.map((a) => {
    const cat = a && (a.categoria || haCategoria(a.tipo));
    const url = (a && a.url) || '';
    if (!url) return '';
    const privado = haEsLigaPrivada(url);
    const ref = (attr) => privado
      ? `data-ha-url="${haEsc(url)}" data-ha-attr="${attr}"`
      : `${attr}="${haEsc(url)}"`;
    if (cat === 'imagen') {
      return `<a class="ha-item ha-item--imagen" ${ref('href')} target="_blank" rel="noopener" title="${haEsc(a.nombre || '')}">
        <img ${ref('src')} loading="lazy" decoding="async" alt="${haEsc(a.nombre || 'Imagen adjunta')}"/>
      </a>`;
    }
    if (cat === 'video') {
      return `<div class="ha-item ha-item--video"><video ${ref('src')} controls preload="metadata"></video></div>`;
    }
    return `<a class="ha-item ha-item--archivo" ${ref('href')} target="_blank" rel="noopener" download="${haEsc(a.nombre || '')}">
      ${HA_ICONOS.archivo}<span class="ha-item__nombre">${haEsc(a.nombre || 'Archivo')}</span>
      <span class="ha-item__peso">${haEsc(haFormatoTamano(a.tamano))}</span>
    </a>`;
  }).join('') + '</div>';
}

// ── Ligas temporales (bucket adjuntos-historial privado) ─────────────────
// La liga pública guardada en actividades/tareas.adjuntos sirve de "nombre"
// del archivo. Cualquier elemento con data-ha-url recibe, en cuanto aparece
// en la página, una liga firmada que da el backend (/adjuntos/ligas) y que
// dura una hora. El backend solo la da si el usuario puede ver esa nota o
// tarea. Si el backend no contesta, se usa la liga original (sirve mientras
// el bucket siga público).
const HA_LIGA_RE = /\/storage\/v1\/object\/public\/adjuntos-historial\//;
const _haLigas = new Map(); // url guardada → { liga, vence }
let _haPorFirmar = new Set();
let _haTimer = null;

function haEsLigaPrivada(url) {
  return typeof url === 'string' && HA_LIGA_RE.test(url);
}

// Atributos para pintar una liga a un adjunto fuera de haRenderAdjuntos
// (por ejemplo, la lista de archivos de una tarea).
function haAttrLiga(url, attr) {
  attr = attr || 'href';
  return haEsLigaPrivada(url)
    ? `data-ha-url="${haEsc(url)}" data-ha-attr="${attr}"`
    : `${attr}="${haEsc(url)}"`;
}

function _haAplicar(el, liga) {
  const attr = el.getAttribute('data-ha-attr') || 'href';
  el.setAttribute(attr, liga);
  el.setAttribute('data-ha-estado', 'listo');
}

function _haLigaVigente(url) {
  const c = _haLigas.get(url);
  return c && c.vence > Date.now() ? c.liga : null;
}

async function _haPedirLigas(urls) {
  const sb = window.brokrSb;
  const tok = sb && sb.ensureToken ? await sb.ensureToken() : null;
  if (!tok) throw new Error('sin sesión');
  const base = window.API_BASE || 'https://api.broquer.app';
  const r = await fetch(base + '/adjuntos/ligas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok },
    body: JSON.stringify({ urls: urls }),
  });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const d = await r.json();
  const vence = Date.now() + Math.max(60, ((d && d.segundos) || 3600) - 300) * 1000;
  Object.entries((d && d.ligas) || {}).forEach(([url, liga]) => {
    if (liga) _haLigas.set(url, { liga: liga, vence: vence });
  });
}

async function _haFirmarPendientes() {
  _haTimer = null;
  const urls = Array.from(_haPorFirmar).filter((u) => !_haLigaVigente(u));
  _haPorFirmar = new Set();
  for (let i = 0; i < urls.length; i += 50) {
    try { await _haPedirLigas(urls.slice(i, i + 50)); } catch (e) { /* se usa la liga original */ }
  }
  document.querySelectorAll('[data-ha-url][data-ha-estado="pidiendo"]').forEach((el) => {
    const url = el.getAttribute('data-ha-url');
    _haAplicar(el, _haLigaVigente(url) || url);
  });
}

function haFirmarLigas(raiz) {
  const els = (raiz || document).querySelectorAll
    ? (raiz || document).querySelectorAll('[data-ha-url]:not([data-ha-estado])') : [];
  els.forEach((el) => {
    const url = el.getAttribute('data-ha-url');
    const liga = _haLigaVigente(url);
    if (liga) { _haAplicar(el, liga); return; }
    el.setAttribute('data-ha-estado', 'pidiendo');
    _haPorFirmar.add(url);
  });
  if (_haPorFirmar.size && !_haTimer) _haTimer = setTimeout(_haFirmarPendientes, 30);
}

// Si alguien da clic antes de que llegue la liga, se abre en cuanto llegue.
document.addEventListener('click', (ev) => {
  const a = ev.target && ev.target.closest ? ev.target.closest('a[data-ha-url]') : null;
  if (!a || a.getAttribute('data-ha-estado') === 'listo') return;
  ev.preventDefault();
  const url = a.getAttribute('data-ha-url');
  const ventana = window.open('', '_blank');
  _haPedirLigas([url]).catch(() => {}).then(() => {
    const liga = _haLigaVigente(url) || url;
    _haAplicar(a, liga);
    if (ventana) ventana.location.href = liga; else window.location.href = liga;
  });
}, true);

if (typeof MutationObserver === 'function') {
  new MutationObserver(() => haFirmarLigas(document)).observe(document.documentElement, { childList: true, subtree: true });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => haFirmarLigas(document));
} else {
  haFirmarLigas(document);
}
