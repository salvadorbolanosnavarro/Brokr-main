/* Optional visual experience. Eligibility is always rechecked by the real API.
 *
 * Exit rules while inside /cecil/ (never clears the business session):
 *  - Leave ONLY when the server explicitly answers enabled:false or a different
 *    user_id. That is the revocation signal.
 *  - 401: the access token expired (Supabase JWTs last ~1 h). Ask the shell for
 *    a fresh token and retry once; if it still fails, try again next cycle.
 *  - Network error, timeout or 5xx: unknown state. Retry next cycle, never leave.
 *  - If a form has unsaved changes, wait until it is saved before redirecting.
 */
(() => {
  'use strict';
  const prefix = '/cecil/';
  const inside = location.pathname.startsWith(prefix);
  const INTERVAL = 15000, TIMEOUT = 6000;
  function original() {
    return (inside ? '/' + location.pathname.slice(prefix.length) : location.pathname) + location.search + location.hash;
  }
  function key(id) { return 'broquer-ui-cecil:' + id; }
  function preference(id, value) {
    try { if(value === undefined) return localStorage.getItem(key(id)) === 'on'; localStorage.setItem(key(id), value ? 'on' : 'off'); } catch (_) {}
    return false;
  }
  function debugMode() {
    try { return new URLSearchParams(location.search).get('debug') === '1'; } catch (_) { return false; }
  }

  /* ── Unsaved changes ─────────────────────────────────────────────
   * A field edited by the person marks the page as dirty until a form is
   * submitted or a save-like button is pressed (then a short grace period lets
   * the request finish). Search boxes, filters and the assistant do not count. */
  let dirty = false, savedTimer = null;
  const SAVE = /guardar|enviar|crear|firmar|generar|aceptar|actualizar|listo|confirmar|agregar|a[ñn]adir/i;
  function ignoredField(el) {
    if (!el || !el.tagName) return true;
    const tag = String(el.tagName).toLowerCase();
    if (!['input', 'textarea', 'select'].includes(tag) && !el.isContentEditable) return true;
    const type = String(el.type || '').toLowerCase();
    if (['search', 'checkbox', 'radio', 'button', 'submit', 'hidden', 'range'].includes(type)) return true;
    if (el.closest && el.closest('#cecil-rollout-controls,[data-rollout-ignore],[role="search"],.bk-shk,.bk-filters,[data-filters]')) return true;
    const name = String(el.name || el.id || '');
    return /buscar|search|filtro|filter|cecil-ia-prompt/i.test(name);
  }
  function markSaved() {
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { dirty = false; maybeLeave(); }, 2500);
  }
  function watchEdits() {
    if (!document.addEventListener) return;
    document.addEventListener('input', e => { if (!ignoredField(e.target)) { clearTimeout(savedTimer); dirty = true; } }, true);
    document.addEventListener('submit', markSaved, true);
    document.addEventListener('click', e => {
      const button = e.target && e.target.closest && e.target.closest('button,[type="submit"],[role="button"]');
      if (!button || button.closest('#cecil-rollout-controls')) return;
      if (button.type === 'submit' || SAVE.test(button.textContent || '')) markSaved();
    }, true);
  }

  /* ── Eligibility request ────────────────────────────────────────
   * Returns 'eligible' | 'revoked' | 'unknown'. Only 'revoked' may send the
   * person back to Broquer. */
  function makeChecker({api, userId, currentToken, refreshToken}) {
    const endpoint = () => new URL(api, location.origin).href.replace(/\/$/, '') + '/ui/cecil';
    async function ask(tok) {
      if (!tok) return {status: 401};
      const response = await fetch(endpoint(), {
        headers: {Authorization: 'Bearer ' + tok}, cache: 'no-store', signal: AbortSignal.timeout(TIMEOUT)
      });
      if (!response.ok) return {status: response.status};
      return {status: response.status, data: await response.json()};
    }
    return async function check() {
      try {
        const base = new URL(api, location.origin);
        if (!['https:', 'http:'].includes(base.protocol)) return 'unknown';
        let result = await ask(currentToken());
        if (result.status === 401) {
          // Expired access token: refresh via the shell and retry once.
          let fresh = null;
          try { fresh = await refreshToken(); } catch (_) {}
          result = await ask(fresh || currentToken());
        }
        const d = result.data;
        if (!d || typeof d !== 'object') return 'unknown';
        if (d.enabled === false) return 'revoked';
        if (d.user_id !== undefined && d.user_id !== userId) return 'revoked';
        return d.enabled === true && d.user_id === userId ? 'eligible' : 'unknown';
      } catch (_) { return 'unknown'; }
    };
  }

  let pendingLeave = null;
  function leave(id) { if(id) preference(id, false); location.replace(original()); }
  function maybeLeave() {
    if (!pendingLeave || dirty) return;
    const id = pendingLeave; pendingLeave = null; leave(id);
  }

  /* ── Pilot control (small, collapsible, app typography) ───────── */
  function installStyle() {
    if (!document.getElementById || document.getElementById('cecil-rollout-style') || !document.head) return;
    const style = document.createElement('style'); style.id = 'cecil-rollout-style';
    style.textContent = [
      '#cecil-rollout-controls{position:fixed;left:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;max-width:calc(100vw - 32px);font:500 13px/1.4 var(--ui-font,var(--font-sans,"Manrope",system-ui,-apple-system,"Segoe UI",sans-serif));color:var(--ui-ink,#191c1f)}',
      '@media (max-width:880px){#cecil-rollout-controls{bottom:calc(76px + env(safe-area-inset-bottom,0px));left:12px}}',
      '#cecil-rollout-controls button{font:inherit;cursor:pointer;color:inherit}',
      '#cecil-rollout-controls .crc-toggle{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:999px;border:1px solid var(--ui-line,#e3e6ea);background:var(--ui-surface,#fff);box-shadow:0 1px 3px rgba(16,24,40,.08);font-size:12px;font-weight:600;opacity:.85}',
      '#cecil-rollout-controls .crc-toggle:hover,#cecil-rollout-controls .crc-toggle[aria-expanded="true"]{opacity:1}',
      '#cecil-rollout-controls .crc-dot{width:6px;height:6px;border-radius:50%;background:var(--ui-action,#ff7a33)}',
      '#cecil-rollout-controls .crc-panel{position:absolute;left:0;bottom:36px;width:260px;max-width:calc(100vw - 32px);background:var(--ui-surface,#fff);border:1px solid var(--ui-line,#e3e6ea);border-radius:12px;padding:12px;box-shadow:0 8px 24px rgba(16,24,40,.12)}',
      '#cecil-rollout-controls .crc-panel[hidden]{display:none}',
      '#cecil-rollout-controls p{margin:0 0 10px;color:var(--ui-muted,#5c6670);font-weight:400}',
      '#cecil-rollout-controls .crc-panel button{display:block;width:100%;height:36px;padding:0 12px;border-radius:8px;border:1px solid var(--ui-line,#d5d9dd);background:var(--ui-surface,#fff);font-weight:600;text-align:left}',
      '#cecil-rollout-controls .crc-panel button+button,#cecil-rollout-controls .crc-panel button+p{margin-top:8px}',
      '#cecil-rollout-controls .crc-try{height:36px;padding:0 14px;border-radius:8px;border:1px solid transparent;background:var(--ui-action,#ff9257);color:#fff;font-weight:600;box-shadow:0 1px 3px rgba(16,24,40,.12)}'
    ].join('\n');
    document.head.append(style);
  }

  window.bkCecilRollout = async function({api, token, getToken, refreshToken, userId}) {
    if (document.getElementById('cecil-rollout-controls')) return;
    // Accept a function (preferred: always reads the current session) or the
    // legacy fixed value.
    const currentToken = typeof getToken === 'function' ? () => { try { return getToken(); } catch (_) { return null; } }
      : typeof token === 'function' ? token : () => token;
    const refresh = typeof refreshToken === 'function' ? refreshToken
      : async () => (window.brokrSb && typeof window.brokrSb.refreshNow === 'function') ? window.brokrSb.refreshNow() : null;
    if (!currentToken() || !userId) { if(inside) leave(userId); return; }
    const check = makeChecker({api, userId, currentToken, refreshToken: refresh});
    const first = await check();
    if (first === 'revoked') { preference(userId, false); if(inside) leave(userId); return; }
    if (!inside && first !== 'eligible') return; // Broquer: offer Cecil only when confirmed.
    if (!inside && preference(userId)) {
      location.replace(prefix + location.pathname.replace(/^\//, '') + location.search + location.hash); return;
    }
    if (inside) watchEdits();

    // Revoke the visual pilot while open; never clear the business session.
    let checking = false;
    async function refreshPilot() {
      if (checking || document.hidden) return; checking = true;
      try {
        const result = await check();
        if (result !== 'revoked') return; // eligible or unknown: stay.
        preference(userId, false);
        if (inside) { pendingLeave = userId; if (dirty) waiting(); else maybeLeave(); }
        else document.getElementById('cecil-rollout-controls')?.remove();
      } finally { checking = false; }
    }
    setInterval(refreshPilot, INTERVAL);
    document.addEventListener('visibilitychange', refreshPilot);

    installStyle();
    const bar = document.createElement('aside'); bar.id = 'cecil-rollout-controls';
    bar.setAttribute('aria-label', 'Diseño de la aplicación');
    const go = () => { preference(userId, !inside); location.assign(inside ? original() : prefix + location.pathname.replace(/^\//, '') + location.search + location.hash); };
    let note = null;
    function waiting() {
      if (note) return;
      note = document.createElement('p'); note.setAttribute('role', 'status');
      note.textContent = 'El piloto terminó. Guarda tus cambios y volverás a Broquer.';
      panel && panel.append(note); open(true);
    }
    let panel = null, toggle = null;
    function open(value) {
      if (!panel || !toggle) return;
      panel.hidden = !value; toggle.setAttribute('aria-expanded', value ? 'true' : 'false');
    }
    if (!inside) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'crc-try';
      button.textContent = 'Probar el diseño Cecil'; button.onclick = go;
      bar.append(button); document.body.append(bar); return;
    }
    toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'crc-toggle';
    toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-controls', 'cecil-rollout-panel');
    const dot = document.createElement('span'); dot.className = 'crc-dot'; dot.setAttribute('aria-hidden', 'true');
    toggle.append(dot); toggle.append('Cecil · piloto');
    panel = document.createElement('div'); panel.id = 'cecil-rollout-panel'; panel.className = 'crc-panel'; panel.hidden = true;
    const label = document.createElement('p'); label.textContent = 'Datos reales: los cambios y envíos son reales.';
    const back = document.createElement('button'); back.type = 'button'; back.className = 'crc-action';
    back.textContent = 'Volver a Broquer'; back.onclick = go;
    panel.append(label); panel.append(back);
    toggle.onclick = () => open(panel.hidden);
    bar.append(panel); bar.append(toggle); document.body.append(bar);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') open(false); });
    document.addEventListener('pointerdown', e => { if (bar.contains && !bar.contains(e.target)) open(false); });
    if (debugMode()) {
      const probe = document.createElement('script'); probe.src = '/ui/cecil-error-probe.js';
      probe.onload = () => window.bkCecilErrorProbe?.(panel); document.head.append(probe);
    }
  };
  window.bkCecilRollout.unsaved = () => dirty;
})();
