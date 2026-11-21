// Broquer · Clientes — apartado "Urgente de supervisión".
//
// Arriba del tablero: los comentarios urgentes que el dueño o un admin de la
// empresa me dejó en la bitácora de mis clientes y que aún no atiendo. Quien
// supervisa ve además los que el equipo tiene pendientes. Tocar uno abre la
// ficha del cliente en su bitácora. Si no hay nada pendiente (o la cuenta no
// es de empresa, o falta la migración), el apartado no aparece.
//
// Usa bkSupApi/bkSupAtender/bkEsc/bkDiaEtiqueta/bkHora de ficha-comun.js y
// abrirDetalle/setDetTab de clientes-ficha.js.

(function () {
  let caja = null;
  let abierto = true;

  function asegurarCaja() {
    if (caja) return caja;
    const kb = document.getElementById('kanban');
    if (!kb) return null;
    caja = document.createElement('section');
    caja.id = 'sup-panel';
    caja.className = 'sup-panel';
    caja.hidden = true;
    caja.setAttribute('aria-label', 'Urgente de supervisión');
    kb.parentNode.insertBefore(caja, kb);
    return caja;
  }

  function fila(c, mostrarPara) {
    const quien = mostrarPara ? `De ${c.autor} para ${c.para}` : `De ${c.autor}`;
    const cuando = c.creado_en ? `${bkDiaEtiqueta(c.creado_en)}, ${bkHora(c.creado_en)}` : '';
    return `<li class="sup-item">
      <button type="button" class="sup-item__abrir" onclick="supAbrir('${bkEsc(String(c.contacto_id))}')">
        <span class="sup-item__cliente">${bkEsc(c.cliente)}</span>
        ${c.texto ? `<span class="sup-item__txt">${bkEsc(c.texto)}</span>` : ''}
        <span class="sup-item__meta">${bkEsc(quien)}${cuando ? ' · ' + bkEsc(cuando) : ''}</span>
      </button>
      <button type="button" class="bk-btn bk-btn--ghost bk-btn--sm" onclick="bkSupAtender('${bkEsc(String(c.id))}', this)">Atendido</button>
    </li>`;
  }

  function pintar(d) {
    const el = asegurarCaja();
    if (!el) return;
    const mios = d.para_mi || [];
    const equipo = d.del_equipo || [];
    const total = mios.length + equipo.length;
    el.hidden = !d.activo || total === 0;
    if (el.hidden) return;
    el.innerHTML = `
      <button type="button" class="sup-panel__head" aria-expanded="${abierto}" onclick="supAlternar()">
        <span class="sup-panel__ico">${BK_ICO_URGENTE}</span>
        <span class="sup-panel__titulo">Urgente de supervisión</span>
        <span class="sup-panel__n">${total}</span>
        <svg class="sup-panel__chev" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 9l6 6 6-6"/></svg>
      </button>
      <div class="sup-panel__cuerpo"${abierto ? '' : ' hidden'}>
        ${mios.length ? `<h3 class="sup-panel__sub">Para ti</h3><ul class="sup-lista">${mios.map(c => fila(c, false)).join('')}</ul>` : ''}
        ${equipo.length ? `<h3 class="sup-panel__sub">Esperando al equipo</h3><ul class="sup-lista">${equipo.map(c => fila(c, true)).join('')}</ul>` : ''}
      </div>`;
  }

  async function cargar() {
    try { pintar(await bkSupApi('/supervision/pendientes')); } catch { /* sin apartado */ }
  }

  window.supAlternar = function () {
    abierto = !abierto;
    const cuerpo = caja && caja.querySelector('.sup-panel__cuerpo');
    const head = caja && caja.querySelector('.sup-panel__head');
    if (cuerpo) cuerpo.hidden = !abierto;
    if (head) head.setAttribute('aria-expanded', String(abierto));
  };

  window.supAbrir = function (contactoId) {
    abrirDetalle(contactoId);
    if (document.getElementById('detail-ov').classList.contains('is-open')) setDetTab('bitacora');
    else showToast('No encuentro a ese cliente en tu lista.');
  };

  window.addEventListener('brokr-supervision-cambio', cargar);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) cargar(); });
  setInterval(() => { if (!document.hidden) cargar(); }, 60000);
  window.supCargar = cargar;
})();
