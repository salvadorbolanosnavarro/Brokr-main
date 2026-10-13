// Broquer · Filtro de fecha con periodo a la medida.
//
// Se engancha a cualquier <select data-rango-fecha> de filtros de fecha
// (hoy / esta semana / este mes…) y le agrega "Elegir periodo…", que abre un
// calendario para marcar del día X al día Y. Al aplicar, el select queda en
// la opción "rango" (con las fechas como texto) y dispara su propio
// onchange, así que la página no cambia su forma de volver a pintar. La
// página solo pregunta bkRangoFecha.contiene(select, iso) cuando el valor es
// "rango".

(function () {
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const MES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const DIAS = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
  const ICO_ANT = '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>';
  const ICO_SIG = '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>';

  const rangos = new WeakMap();   // select → { desde: Date, hasta: Date }
  let abierto = null;             // { sel, caja, desde, hasta, mes, anterior }

  const dia0 = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const mismoDia = (a, b) => a && b && a.getTime() === b.getTime();
  const corto = d => d.getDate() + ' ' + MES_CORTO[d.getMonth()] +
    (d.getFullYear() !== new Date().getFullYear() ? ' ' + d.getFullYear() : '');
  const etiqueta = (a, b) => mismoDia(a, b) ? corto(a) : corto(a) + ' – ' + corto(b);

  function enlazar(sel) {
    if (sel._bkRango) return;
    sel._bkRango = true;
    const nuevo = document.createElement('option');
    nuevo.value = 'rango-nuevo';
    nuevo.textContent = 'Elegir periodo…';
    sel.appendChild(nuevo);
    let anterior = sel.value;
    let pasando = false;

    // Captura: corre antes del onchange de la página y lo detiene mientras
    // el calendario está abierto.
    sel.addEventListener('change', (ev) => {
      if (pasando) return;
      if (sel.value === 'rango-nuevo') {
        ev.stopImmediatePropagation();
        abrir(sel, anterior, (desde, hasta) => {
          rangos.set(sel, { desde, hasta });
          let opt = sel.querySelector('option[value="rango"]');
          if (!opt) {
            opt = document.createElement('option');
            opt.value = 'rango';
            sel.insertBefore(opt, nuevo);
          }
          opt.textContent = etiqueta(desde, hasta);
          sel.value = 'rango';
          anterior = 'rango';
          pasando = true;
          sel.dispatchEvent(new Event('change'));
          pasando = false;
        });
        return;
      }
      anterior = sel.value;
    }, true);
  }

  function contiene(sel, iso) {
    const r = rangos.get(typeof sel === 'string' ? document.getElementById(sel) : sel);
    if (!r) return true;
    if (!iso) return false;
    const d = new Date(iso);
    const fin = new Date(r.hasta); fin.setDate(fin.getDate() + 1);
    return d >= r.desde && d < fin;
  }

  function abrir(sel, anterior, alAplicar) {
    cerrar(false);
    const previo = rangos.get(sel);
    const hoy = dia0(new Date());
    const caja = document.createElement('div');
    caja.className = 'bk-cal';
    caja.setAttribute('role', 'dialog');
    caja.setAttribute('aria-label', 'Elegir periodo');
    document.body.appendChild(caja);
    abierto = {
      sel, caja, anterior, alAplicar,
      desde: previo ? previo.desde : null,
      hasta: previo ? previo.hasta : null,
      mes: new Date((previo ? previo.hasta : hoy).getFullYear(), (previo ? previo.hasta : hoy).getMonth(), 1),
    };
    pintar();
    colocar();
    setTimeout(() => {
      document.addEventListener('mousedown', fuera, true);
      document.addEventListener('touchstart', fuera, true);
      document.addEventListener('keydown', tecla, true);
      window.addEventListener('resize', colocar);
      const foco = caja.querySelector('.bk-cal__dia.is-ini, .bk-cal__dia.is-hoy') || caja.querySelector('.bk-cal__dia');
      if (foco) foco.focus();
    }, 0);
  }

  function cerrar(aplicar) {
    if (!abierto) return;
    const a = abierto;
    abierto = null;
    document.removeEventListener('mousedown', fuera, true);
    document.removeEventListener('touchstart', fuera, true);
    document.removeEventListener('keydown', tecla, true);
    window.removeEventListener('resize', colocar);
    a.caja.remove();
    if (aplicar && a.desde) {
      a.alAplicar(a.desde, a.hasta || a.desde);
    } else {
      a.sel.value = a.anterior;   // "Cancelar": el filtro queda como estaba
    }
    a.sel.focus();
  }

  function fuera(ev) {
    if (abierto && !abierto.caja.contains(ev.target)) cerrar(false);
  }

  function tecla(ev) {
    if (!abierto) return;
    if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); cerrar(false); }
  }

  function colocar() {
    if (!abierto) return;
    const { sel, caja } = abierto;
    if (window.innerWidth <= 520) { caja.classList.add('is-hoja'); caja.style.left = caja.style.top = ''; return; }
    caja.classList.remove('is-hoja');
    const r = sel.getBoundingClientRect();
    const ancho = caja.offsetWidth;
    const alto = caja.offsetHeight;
    let left = Math.min(r.left, window.innerWidth - ancho - 12);
    let top = r.bottom + 6;
    if (top + alto > window.innerHeight - 12) top = Math.max(12, r.top - alto - 6);
    caja.style.left = Math.max(12, left) + 'px';
    caja.style.top = top + 'px';
  }

  function elegir(d) {
    const a = abierto;
    if (!a.desde || a.hasta) { a.desde = d; a.hasta = null; }
    else if (d < a.desde) { a.hasta = a.desde; a.desde = d; }
    else { a.hasta = d; }
    pintar();
    const foco = a.caja.querySelector(`[data-t="${d.getTime()}"]`);
    if (foco) foco.focus();
  }

  function pintar() {
    const a = abierto;
    const hoy = dia0(new Date());
    const y = a.mes.getFullYear();
    const m = a.mes.getMonth();
    const vacios = (new Date(y, m, 1).getDay() + 6) % 7;   // semana empieza en lunes
    const total = new Date(y, m + 1, 0).getDate();
    let celdas = '';
    for (let i = 0; i < vacios; i++) celdas += '<span></span>';
    for (let n = 1; n <= total; n++) {
      const d = new Date(y, m, n);
      const fin = a.hasta || a.desde;
      const cls = ['bk-cal__dia'];
      if (mismoDia(d, hoy)) cls.push('is-hoy');
      if (mismoDia(d, a.desde)) cls.push('is-ini');
      if (mismoDia(d, fin)) cls.push('is-fin');
      if (a.desde && fin && d > a.desde && d < fin) cls.push('is-entre');
      celdas += `<button type="button" class="${cls.join(' ')}" data-t="${d.getTime()}"
        aria-pressed="${cls.includes('is-ini') || cls.includes('is-fin')}"
        aria-label="${n} de ${MESES[m]} de ${y}">${n}</button>`;
    }
    const resumen = a.desde
      ? (a.hasta ? 'Del ' + corto(a.desde) + ' al ' + corto(a.hasta) : 'Desde el ' + corto(a.desde) + ' · elige el último día')
      : 'Elige el primer día';
    a.caja.innerHTML = `
      <div class="bk-cal__head">
        <button type="button" class="bk-icon-btn bk-icon-btn--sm" data-mes="-1" aria-label="Mes anterior">${ICO_ANT}</button>
        <span class="bk-cal__mes">${MESES[m]} ${y}</span>
        <button type="button" class="bk-icon-btn bk-icon-btn--sm" data-mes="1" aria-label="Mes siguiente">${ICO_SIG}</button>
      </div>
      <div class="bk-cal__semana">${DIAS.map(d => `<span>${d}</span>`).join('')}</div>
      <div class="bk-cal__dias">${celdas}</div>
      <p class="bk-cal__resumen" aria-live="polite">${resumen}</p>
      <div class="bk-cal__pie">
        <button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" data-acc="cancelar">Cancelar</button>
        <button type="button" class="bk-btn bk-btn--sm" data-acc="aplicar"${a.desde ? '' : ' disabled'}>Aplicar</button>
      </div>`;
    a.caja.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.mes) { a.mes = new Date(y, m + Number(b.dataset.mes), 1); pintar(); return; }
      if (b.dataset.t) { elegir(new Date(Number(b.dataset.t))); return; }
      if (b.dataset.acc) cerrar(b.dataset.acc === 'aplicar');
    };
  }

  function enlazarTodos() {
    document.querySelectorAll('select[data-rango-fecha]').forEach(enlazar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enlazarTodos);
  else enlazarTodos();

  window.bkRangoFecha = { enlazar, contiene };
})();
