// ─────────────────────────────────────────────────────────────────────────
// bk-api.js · Llamadas al backend de Broquer desde módulos nuevos.
//   bkApi('/crm/catalogos')                         → GET
//   bkApi('/crm/etapas', { method:'POST', json:{…} }) → POST JSON
// Usa la sesión de app-shell.js (window.brokrSb) con refresh automático en
// 401, y convierte los errores del backend ({detail}) en Error legibles.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var BASE = window.API_BASE || 'https://api.broquer.app';
  function esperarShell() {
    if (window.brokrSb && window.brokrSb.ensureToken) return Promise.resolve();
    return new Promise(function (res) {
      var n = 0, t = setInterval(function () {
        if ((window.brokrSb && window.brokrSb.ensureToken) || ++n > 100) { clearInterval(t); res(); }
      }, 50);
    });
  }
  window.bkApi = async function (path, opts) {
    opts = opts || {};
    await esperarShell();
    var sb = window.brokrSb;
    if (!sb || !sb.ensureToken) throw new Error('La app aún se está cargando. Intenta en un segundo.');
    var tok = await sb.ensureToken();
    var headers = Object.assign({}, opts.headers || {});
    if (tok) headers.Authorization = 'Bearer ' + tok;
    var body = opts.body;
    if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json); }
    var r = await fetch(BASE + path, { method: opts.method || 'GET', headers: headers, body: body });
    if (r.status === 401 && sb.refreshNow) {
      tok = await sb.refreshNow();
      if (tok) { headers.Authorization = 'Bearer ' + tok; r = await fetch(BASE + path, { method: opts.method || 'GET', headers: headers, body: body }); }
    }
    var data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && (data.detail || data.message)) || ('Error ' + r.status));
    return data;
  };
  // Supabase REST con la sesión del usuario (espera a que app-shell esté listo).
  window.bkRest = async function (path, opts) {
    await esperarShell();
    if (!window.brokrSb || !window.brokrSb.rest) throw new Error('La app aún se está cargando.');
    return window.brokrSb.rest(path, opts);
  };
  window.bkEsc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  // Aviso breve abajo de la pantalla (mismo estilo en todos los módulos nuevos).
  window.bkToast = function (texto) {
    var t = document.createElement('div');
    t.className = 'bk-toast-mini';
    t.setAttribute('role', 'status');
    t.textContent = texto;
    t.style.cssText = 'position:fixed;left:50%;bottom:calc(88px + env(safe-area-inset-bottom));transform:translateX(-50%);' +
      'background:var(--ink-2);color:var(--bone);padding:10px 18px;border-radius:var(--r-pill);font-size:var(--fs-sm);' +
      'z-index:var(--z-toast);box-shadow:var(--shadow-lg);max-width:calc(100vw - 32px);text-align:center';
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  };
})();
