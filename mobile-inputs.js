/* Enforce the iOS font floor (phones/touch only) even against old ID-specific
   !important rules. Desktop fields keep the 14px token. */
(() => {
  const selector = 'input,textarea,select,[contenteditable="true"]';
  const phone = window.matchMedia('(max-width: 720px), (pointer: coarse)');
  function floor(element) {
    if (!phone.matches) {
      if (element.dataset && element.dataset.iosFloor) { element.style.removeProperty('font-size'); delete element.dataset.iosFloor; }
      return;
    }
    if (element.matches(selector) && parseFloat(getComputedStyle(element).fontSize) < 16) {
      element.dataset.iosFloor = '1';
      element.style.setProperty('font-size', '16px', 'important');
    }
  }
  function scan() { document.querySelectorAll(selector).forEach(floor); }
  function start() {
    scan();
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; scan(); });
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
    document.addEventListener('focusin', event => floor(event.target));
    window.addEventListener('resize', scan);
    window.addEventListener('load', scan, { once: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
