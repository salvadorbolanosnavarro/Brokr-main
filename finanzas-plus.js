// finanzas-plus.js · "Comisiones por cobrar" en Finanzas: los ingresos que
// crea solo cada cierre (routers/cierres.py). Marcarlos cobrados actualiza
// el cierre y ya cuentan en tus ingresos.
(function () {
  'use strict';
  var esc = window.bkEsc, api = window.bkApi, toast = window.bkToast;
  function money(n) { return '$' + Number(n || 0).toLocaleString('es-MX', { maximumFractionDigits: 0 }); }
  async function pintar() {
    var ancla = document.getElementById('fin-comisiones'); if (!ancla) return;
    var cont = document.getElementById('fin-por-cobrar');
    if (!cont) { cont = document.createElement('div'); cont.id = 'fin-por-cobrar'; ancla.parentNode.insertBefore(cont, ancla); }
    var lista = [];
    try { lista = (await api('/cierres/por-cobrar')).por_cobrar || []; } catch (e) { cont.innerHTML = ''; return; }
    if (!lista.length) { cont.innerHTML = ''; return; }
    var total = lista.reduce(function (a, m) { return a + Number(m.monto || 0); }, 0);
    cont.innerHTML = '<div class="bk-card bk-card--pad bk-card--raise" style="margin-bottom:var(--sp-4)">' +
      '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline"><strong>Comisiones por cobrar</strong><span>' + money(total) + '</span></div>' +
      lista.map(function (m) {
        return '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line)">' +
          '<span style="min-width:0"><span style="display:block;font-size:var(--fs-sm)">' + esc(m.concepto) + '</span>' +
          '<span style="font-size:var(--fs-xs);color:var(--mute)">' + esc(m.fecha || '') + ' · ' + money(m.monto) + '</span></span>' +
          '<button class="bk-btn bk-btn--sm" data-cobrar="' + esc(m.id) + '">Marcar cobrada</button></div>';
      }).join('') + '</div>';
  }
  document.addEventListener('click', async function (e) {
    var b = e.target.closest('[data-cobrar]'); if (!b) return;
    b.disabled = true;
    try {
      await api('/cierres/cobrado/' + b.dataset.cobrar, { method: 'POST' });
      toast('Comisión cobrada: ya cuenta en tus ingresos');
      pintar();
      var ap = document.getElementById('fin-aplicar'); if (ap) ap.click();   // refresca los totales
    } catch (err) { b.disabled = false; toast(err.message); }
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', pintar); else pintar();
})();
