// Broquer · Filtro de fecha con periodo a la medida.
//
// Se engancha a cualquier <select data-rango-fecha> de filtros de fecha
// (hoy / esta semana / este mes…) y le agrega "Elegir periodo". Al elegirlo
// aparecen junto al select dos campos de fecha, Desde y Hasta, con el
// calendario normal (input type="date", el mismo que el periodo de
// Finanzas). Cada cambio dispara el onchange del select, así que la página
// vuelve a pintar como siempre; solo pregunta bkRangoFecha.contiene(select,
// iso) cuando el valor es "rango".

(function () {
  const campos = new WeakMap();   // select → { caja, desde, hasta }

  function enlazar(sel) {
    if (campos.has(sel)) return;
    const opt = document.createElement('option');
    opt.value = 'rango';
    opt.textContent = 'Elegir periodo';
    sel.appendChild(opt);

    const caja = document.createElement('span');
    caja.className = 'filtro-fecha-rango';
    caja.hidden = true;
    caja.innerHTML =
      '<input type="date" class="filtro-select" aria-label="Desde" title="Desde"/>' +
      '<span aria-hidden="true">–</span>' +
      '<input type="date" class="filtro-select" aria-label="Hasta" title="Hasta"/>';
    sel.insertAdjacentElement('afterend', caja);
    const [desde, hasta] = caja.querySelectorAll('input');
    campos.set(sel, { caja, desde, hasta });

    const repintar = () => {
      if (desde.value && hasta.value && hasta.value < desde.value) {
        [desde.value, hasta.value] = [hasta.value, desde.value];
      }
      sel.dispatchEvent(new Event('change'));
    };
    desde.addEventListener('change', repintar);
    hasta.addEventListener('change', repintar);

    sel.addEventListener('change', () => {
      const mostrar = sel.value === 'rango';
      if (mostrar && caja.hidden) {
        caja.hidden = false;
        try { desde.showPicker(); } catch { desde.focus(); }
      } else if (!mostrar) {
        caja.hidden = true;
      }
    });
  }

  // Sin fechas puestas no filtra; con solo una, el periodo queda abierto de
  // ese lado. Ambos días se incluyen completos.
  function contiene(sel, iso) {
    const c = campos.get(typeof sel === 'string' ? document.getElementById(sel) : sel);
    if (!c || (!c.desde.value && !c.hasta.value)) return true;
    if (!iso) return false;
    const d = new Date(iso);
    if (c.desde.value && d < new Date(c.desde.value + 'T00:00:00')) return false;
    if (c.hasta.value) {
      const fin = new Date(c.hasta.value + 'T00:00:00');
      fin.setDate(fin.getDate() + 1);
      if (d >= fin) return false;
    }
    return true;
  }

  function enlazarTodos() {
    document.querySelectorAll('select[data-rango-fecha]').forEach(enlazar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enlazarTodos);
  else enlazarTodos();

  window.bkRangoFecha = { enlazar, contiene };
})();
