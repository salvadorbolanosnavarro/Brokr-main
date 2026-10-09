/* Enforce the iOS font floor even against old ID-specific !important rules. */
(() => {
  const selector = 'input,textarea,select,[contenteditable="true"]';
  function floor(element) {
    if (element.matches(selector) && parseFloat(getComputedStyle(element).fontSize) < 16) {
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
