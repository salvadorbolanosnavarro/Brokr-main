/* Formulario de soporte.
 *
 * Reemplaza los enlaces mailto: (que no hacen nada si el usuario no tiene un
 * programa de correo configurado). Uso: cualquier elemento con
 * data-soporte-abrir abre el formulario, o window.bkSoporte.abrir().
 * El usuario solo escribe su mensaje y, si quiere, adjunta una imagen; el
 * servidor agrega sus datos de cuenta a partir de la sesión.
 */
(function () {
  'use strict';
  if (window.bkSoporte) return;

  var EMAIL = 'hola@broquer.app';
  var MAX_IMG = 5 * 1024 * 1024;
  var TIPOS = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif'];

  var css = [
    '.bks-ov{position:fixed;inset:0;z-index:var(--z-modal,1000);background:rgba(10,20,30,.45);display:flex;align-items:center;justify-content:center;padding:16px}',
    '.bks-box{background:var(--paper);color:var(--ink);border-radius:var(--r-lg);box-shadow:var(--shadow-xl);width:100%;max-width:480px;max-height:calc(var(--vvh,100vh) - 32px);overflow:auto;padding:24px;font-family:var(--font-sans);font-size:var(--fs-sm)}',
    '.bks-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px}',
    '.bks-h{font-family:var(--font-display);font-size:var(--fs-h5);font-weight:700;margin:0}',
    '.bks-x{background:none;border:none;cursor:pointer;color:var(--mute);padding:4px;line-height:0}',
    '.bks-sub{color:var(--mute);margin:0 0 16px}',
    '.bks-sub a{color:var(--ink);font-weight:600}',
    '.bks-ta{width:100%;min-height:130px;box-sizing:border-box;border:1px solid var(--line);border-radius:var(--r);padding:12px;font:inherit;font-size:var(--fs-body);color:var(--ink);background:var(--paper);resize:vertical}',
    '.bks-ta:focus{outline:none;border-color:var(--ink-3);box-shadow:var(--focus)}',
    '.bks-file{display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap}',
    '.bks-pick{display:inline-flex;align-items:center;gap:6px;border:1px dashed var(--line-2);border-radius:var(--r-pill);padding:8px 14px;cursor:pointer;color:var(--ink-2);background:var(--paper-2);font-size:var(--fs-xs);font-weight:600}',
    '.bks-prev{display:flex;align-items:center;gap:8px;font-size:var(--fs-xs);color:var(--mute)}',
    '.bks-prev img{width:44px;height:44px;object-fit:cover;border-radius:var(--r-sm);border:1px solid var(--line)}',
    '.bks-prev button{background:none;border:none;color:var(--danger);cursor:pointer;font-size:var(--fs-xs);padding:0}',
    '.bks-note{margin-top:14px;padding:10px 12px;background:var(--paper-2);border-radius:var(--r);color:var(--mute);font-size:var(--fs-xs)}',
    '.bks-err{margin-top:12px;color:var(--danger);font-size:var(--fs-xs)}',
    '.bks-acts{display:flex;justify-content:flex-end;gap:10px;margin-top:18px}',
    '.bks-btn{border-radius:var(--r-pill);padding:10px 20px;font:inherit;font-size:var(--fs-xs);font-weight:600;cursor:pointer;border:1px solid var(--line);background:var(--paper);color:var(--ink)}',
    '.bks-btn.pri{background:var(--sky-blue);color:var(--paper);border-color:var(--sky-blue)}',
    '.bks-btn[disabled]{opacity:.6;cursor:default}',
    '.bks-ok{text-align:center;padding:12px 0}',
    '.bks-ok svg{width:44px;height:44px;color:var(--success)}'
  ].join('\n');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  async function token() {
    try {
      if (window.brokrSb && window.brokrSb.ensureToken) {
        var t = await window.brokrSb.ensureToken();
        if (t) return t;
      }
    } catch (e) { /* sin sesión */ }
    try { return localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || null; }
    catch (e) { return null; }
  }

  function dispositivo() {
    var nat = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
    return (nat ? 'App ' : 'Web ') + window.innerWidth + 'x' + window.innerHeight + ' · ' + navigator.userAgent;
  }

  var ICON_X = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>';
  var ICON_CLIP = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 12.5l-8.5 8.5a5 5 0 01-7-7L14 5.5a3.5 3.5 0 015 5L10.5 19a2 2 0 01-3-3l8-8"/></svg>';
  var ICON_OK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path stroke-linecap="round" stroke-linejoin="round" d="M8 12.5l3 3 5-6"/></svg>';

  function abrir() {
    if (!document.getElementById('bks-css')) {
      var st = document.createElement('style'); st.id = 'bks-css'; st.textContent = css;
      document.head.appendChild(st);
    }
    var ov = document.createElement('div');
    ov.className = 'bks-ov';
    ov.innerHTML =
      '<div class="bks-box" role="dialog" aria-modal="true" aria-labelledby="bks-h">' +
        '<div class="bks-head"><h2 class="bks-h" id="bks-h">Contactar soporte</h2>' +
        '<button type="button" class="bks-x" aria-label="Cerrar">' + ICON_X + '</button></div>' +
        '<div class="bks-body"><p class="bks-sub">Cargando…</p></div>' +
      '</div>';
    document.body.appendChild(ov);
    var body = ov.querySelector('.bks-body');
    function cerrar() { ov.remove(); document.removeEventListener('keydown', onKey); }
    function onKey(e) { if (e.key === 'Escape') cerrar(); }
    document.addEventListener('keydown', onKey);
    ov.querySelector('.bks-x').onclick = cerrar;
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) cerrar(); });

    token().then(function (t) {
      if (!t) {
        body.innerHTML =
          '<p class="bks-sub">Para mandarnos un mensaje desde aquí, inicia sesión en tu cuenta de Broquer. ' +
          'También puedes escribirnos directo a <a href="mailto:' + EMAIL + '">' + EMAIL + '</a>.</p>' +
          '<div class="bks-acts"><button type="button" class="bks-btn" data-c>Cerrar</button>' +
          '<a class="bks-btn pri" href="login.html" style="text-decoration:none">Iniciar sesión</a></div>';
        body.querySelector('[data-c]').onclick = cerrar;
        return;
      }
      formulario(t);
    });

    function formulario(t) {
      var archivo = null;
      body.innerHTML =
        '<p class="bks-sub">Cuéntanos qué pasó. Tus datos de cuenta se agregan solos y te respondemos a tu correo. ' +
        'Soporte: <a href="mailto:' + EMAIL + '">' + EMAIL + '</a></p>' +
        '<textarea class="bks-ta" maxlength="5000" placeholder="Escribe tu mensaje…"></textarea>' +
        '<div class="bks-file"><label class="bks-pick">' + ICON_CLIP + ' Adjuntar imagen' +
        '<input type="file" accept="image/*" hidden></label><div class="bks-prev"></div></div>' +
        '<div class="bks-note">Opcional: una captura de pantalla nos ayuda a resolverlo más rápido (máximo 5 MB).</div>' +
        '<div class="bks-err" hidden></div>' +
        '<div class="bks-acts"><button type="button" class="bks-btn" data-c>Cancelar</button>' +
        '<button type="button" class="bks-btn pri" data-s>Enviar</button></div>';
      var ta = body.querySelector('.bks-ta');
      var inp = body.querySelector('input[type=file]');
      var prev = body.querySelector('.bks-prev');
      var err = body.querySelector('.bks-err');
      var btn = body.querySelector('[data-s]');
      body.querySelector('[data-c]').onclick = cerrar;
      if (!matchMedia('(pointer: coarse)').matches) ta.focus();

      function error(m) { err.textContent = m || ''; err.hidden = !m; }

      inp.onchange = function () {
        var f = inp.files && inp.files[0];
        inp.value = '';
        if (!f) return;
        if (f.type && TIPOS.indexOf(f.type.toLowerCase()) < 0) { error('La imagen debe ser JPG, PNG, WEBP, GIF o HEIC.'); return; }
        if (f.size > MAX_IMG) { error('La imagen pesa más de 5 MB.'); return; }
        error('');
        archivo = f;
        var url = URL.createObjectURL(f);
        prev.innerHTML = '<img alt=""><span></span><button type="button">Quitar</button>';
        prev.querySelector('img').src = url;
        prev.querySelector('span').textContent = f.name;
        prev.querySelector('button').onclick = function () { archivo = null; prev.innerHTML = ''; URL.revokeObjectURL(url); };
      };

      btn.onclick = async function () {
        var msg = ta.value.trim();
        if (msg.length < 3) { error('Escribe tu mensaje.'); ta.focus(); return; }
        error('');
        btn.disabled = true; btn.textContent = 'Enviando…';
        var fd = new FormData();
        fd.append('mensaje', msg);
        fd.append('pagina', location.pathname + location.search);
        fd.append('dispositivo', dispositivo());
        if (archivo) fd.append('imagen', archivo, archivo.name || 'captura');
        try {
          var r = await fetch((window.API_BASE || 'https://api.broquer.app') + '/soporte/mensaje', {
            method: 'POST', headers: { Authorization: 'Bearer ' + t }, body: fd
          });
          var j = {};
          try { j = await r.json(); } catch (e) { /* sin cuerpo */ }
          if (!r.ok) throw new Error(j.detail || ('No pudimos enviar tu mensaje. Escríbenos a ' + EMAIL + '.'));
          body.innerHTML =
            '<div class="bks-ok">' + ICON_OK +
            '<p class="bks-h" style="margin-top:10px">Mensaje enviado</p>' +
            '<p class="bks-sub" style="margin-top:6px">Te responderemos' + (j.email ? ' a <strong>' + esc(j.email) + '</strong>' : ' a tu correo') +
            '.</p></div>' +
            '<div class="bks-acts"><button type="button" class="bks-btn pri" data-c>Listo</button></div>';
          body.querySelector('[data-c]').onclick = cerrar;
        } catch (e) {
          error(e.message);
          btn.disabled = false; btn.textContent = 'Enviar';
        }
      };
    }
  }

  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-soporte-abrir]');
    if (!el) return;
    e.preventDefault();
    abrir();
  });

  window.bkSoporte = { abrir: abrir, email: EMAIL };
})();
