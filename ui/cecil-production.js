/* Cecil production layer: presentation only. Never changes stored values,
 * IDs or business handlers; elements are moved, never cloned. */
(() => {
  'use strict';
  const mobile = window.matchMedia('(max-width: 720px)');

  /* ── Names typed in capitals are shown as proper names on screen only ── */
  const KEEP_LOWER = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'e', 'en', 'el', 'al', 'a', 'van', 'von', 'da', 'do', 'dos']);
  const ABBR = new Set(['sa', 'cv', 'sc', 'rl', 'ac', 'sapi', 'srl', 'sas', 'ii', 'iii', 'iv']);
  function properName(text) {
    let first = true;
    return text.toLocaleLowerCase('es-MX').replace(/[\p{L}][\p{L}'’.]*/gu, word => {
      const isFirst = first; first = false;
      const bare = word.replace(/\./g, '');
      if (!isFirst && KEEP_LOWER.has(bare)) return word;
      if (bare.length === 1 || ABBR.has(bare)) return word.toLocaleUpperCase('es-MX'); // initials, SA, CV
      return word.charAt(0).toLocaleUpperCase('es-MX') + word.slice(1);
    });
  }
  const NAME_SELECTORS = '.contact-name,.kb-card__name,.tk-link>span,.bz-lead__name,.w2-conv__name,.cp-name';
  function fixNames(root) {
    (root.querySelectorAll ? root : document).querySelectorAll(NAME_SELECTORS).forEach(el => {
      for (const node of el.childNodes) {
        if (node.nodeType !== 3) continue;
        const t = node.data;
        const letters = t.replace(/[^\p{L}]/gu, '');
        if (letters.length < 3 || letters !== letters.toLocaleUpperCase('es-MX')) continue;
        if (!el.title) el.title = t.trim();
        node.data = properName(t);
      }
    });
  }

  /* ── Mobile: filters in a bottom sheet ── */
  const BARS = '.filters-row,.props-toolbar,.tk-toolbar,.cp-filterbar';
  const SEARCH = ':is(.head-search,.tk-search-wrap,.props-search,[data-ui-search=true])';
  let openSheet = null;
  function closeSheets() {
    if (!openSheet) return;
    const {bar, sheet, back, moved} = openSheet;
    moved.forEach(({el, next}) => { if (next && next.parentNode === bar) bar.insertBefore(el, next); else bar.insertBefore(el, bar.querySelector('.cp-filter-btn')); });
    sheet.remove(); back.remove(); openSheet = null;
    updateCount(bar);
  }
  window.cpCloseSheets = closeSheets;
  function activeFilters(bar) {
    let n = 0;
    bar.querySelectorAll('select').forEach(s => { if (!s.hidden && s.selectedIndex > 0) n++; });
    return n;
  }
  function updateCount(bar) {
    const btn = bar.querySelector(':scope>.cp-filter-btn'); if (!btn) return;
    const n = activeFilters(bar); if (n) btn.dataset.active = n; else delete btn.dataset.active;
  }
  function openFilters(bar) {
    window.bkCloseFloating?.('sheet');
    closeSheets();
    const back = document.createElement('div'); back.className = 'cp-sheet-back';
    const sheet = document.createElement('div'); sheet.className = 'cp-sheet'; sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-label', 'Filtros');
    sheet.innerHTML = '<h3>Filtros</h3><div class="cp-sheet__body"></div>';
    const body = sheet.querySelector('.cp-sheet__body');
    const moved = [];
    [...bar.children].forEach(el => {
      if (el.matches(SEARCH) || el.classList.contains('cp-filter-btn') || el.hidden || el.style.display === 'none') return;
      moved.push({el, next: el.nextElementSibling}); body.append(el);
    });
    const done = document.createElement('button'); done.type = 'button'; done.className = 'cp-sheet__done';
    done.setAttribute('data-ui-kind', 'primary'); done.setAttribute('data-ui-size', 'default'); done.textContent = 'Ver resultados';
    done.onclick = closeSheets; sheet.append(done);
    back.onclick = closeSheets;
    document.body.append(back, sheet);
    openSheet = {bar, sheet, back, moved};
    sheet.querySelector('select,input,button')?.focus();
  }
  function setupBars(root) {
    (root.querySelectorAll ? root : document).querySelectorAll(BARS).forEach(bar => {
      if (bar.querySelector(':scope>.cp-filter-btn')) return;
      const others = [...bar.children].filter(el => !el.matches(SEARCH));
      if (!others.length) return;
      const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'cp-filter-btn';
      btn.innerHTML = '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" d="M3 6h18M7 12h10M10 18h4"/></svg>Filtros';
      btn.onclick = () => openFilters(bar);
      bar.append(btn);
      bar.addEventListener('change', () => updateCount(bar));
      updateCount(bar);
    });
  }
  mobile.addEventListener?.('change', closeSheets);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && openSheet) { e.preventDefault(); closeSheets(); } });

  /* ── Mobile: the module's primary action floats above the tab bar ── */
  const PRIMARY = '.btn-new-tarea,.btn-new-prop,#add-btn-top';
  function setupFab(root) {
    (root.querySelectorAll ? root : document).querySelectorAll(PRIMARY).forEach(el => el.classList.add('cp-fab-primary'));
  }

  /* ── Is a dialog open? Lock the page behind it (phones) ── */
  const OVERLAYS = '.bk-overlay,.prop-modal-overlay,.ac-ov,.pick-overlay,.eb-import-overlay,.bk-ficha-ov,.overlay,.wac-modal,.lightbox-overlay,dialog[open],.cp-sheet,.bk-profile-overlay';
  function dialogOpen() {
    for (const el of document.querySelectorAll(OVERLAYS)) {
      if (el.hidden || !el.getClientRects().length) continue;
      const cs = getComputedStyle(el);
      // Opacity is ignored on purpose: several dialogs fade in from 0.
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.pointerEvents === 'none') continue;
      const r = el.getBoundingClientRect();
      if (el.matches('dialog[open],.cp-sheet') || (r.width >= innerWidth * 0.9 && r.height >= innerHeight * 0.6)) return true;
    }
    return false;
  }
  let modalQueued = false;
  function syncModalState() {
    if (modalQueued) return; modalQueued = true;
    requestAnimationFrame(() => { modalQueued = false; document.documentElement.classList.toggle('cp-modal-open', dialogOpen()); });
  }
  window.cpSyncModalState = syncModalState;

  function enhance(root) { fixNames(root); setupBars(root); setupFab(root); }
  function start() {
    enhance(document);
    let pending = false;
    new MutationObserver(() => {
      if (pending) return; pending = true;
      requestAnimationFrame(() => { pending = false; fixNames(document); setupBars(document); });
    }).observe(document.body, {childList: true, subtree: true});
    // Open/close of any dialog flips a class, style, hidden or open attribute.
    new MutationObserver(syncModalState).observe(document.body, {subtree: true, attributes: true, attributeFilter: ['class', 'style', 'hidden', 'open']});
    document.addEventListener('transitionend', syncModalState, true);
    document.addEventListener('animationend', syncModalState, true);
    syncModalState();
  }
  window.cpProperName = properName;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true}); else start();
})();
