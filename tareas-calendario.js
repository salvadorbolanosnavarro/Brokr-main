// ─────────────────────────────────────────────────────────────────────────
// tareas-calendario.js · Vista de calendario de Tareas (vive fuera de
// tareas.html). Día / Semana / Mes, color por categoría, arrastrar una tarea
// a otro día (u hora, en la vista de día) para cambiarle la fecha, y los
// mismos filtros de la lista (búsqueda, estado, vínculo y asignado).
// Usa los globales de tareas.html: tareas, tareasFiltradas, tkCategorias,
// TAREA_CATS, tkAbrirEditar, tkNombreAgente, tkEsEmpresa, sbFetch, setTab.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var COLORES = ['var(--sky-blue)', 'var(--success)', 'var(--warn)', 'var(--danger)', 'var(--sky-navy)', 'var(--ink-3)'];
  var DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  var vista = 'mes', ancla = new Date();
  try { vista = localStorage.getItem('tk-cal-vista') || (innerWidth < 640 ? 'semana' : 'mes'); } catch (e) {}
  ancla.setHours(0, 0, 0, 0);
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };

  function clave(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function lunes(d) { var x = new Date(d); var w = (x.getDay() + 6) % 7; x.setDate(x.getDate() - w); x.setHours(0, 0, 0, 0); return x; }
  function sumar(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function colorCat(id) {
    var cats = (typeof tkCategorias !== 'undefined' && tkCategorias) || [];
    var i = cats.findIndex(function (c) { return String(c.id) === String(id); });
    return COLORES[(i < 0 ? 0 : i) % COLORES.length];
  }
  function colorTarea(t) {
    var cs = (typeof TAREA_CATS !== 'undefined' && TAREA_CATS[t.id]) || [];
    return cs.length ? colorCat(cs[0]) : 'var(--mute-2)';
  }
  function hora(t) { var d = new Date(t.fecha_entrega); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function lista() { return (typeof tareasFiltradas === 'function' ? tareasFiltradas() : tareas).filter(function (t) { return t.fecha_entrega; }); }
  function porDia(ts) {
    var m = {};
    ts.forEach(function (t) { var k = clave(new Date(t.fecha_entrega)); (m[k] = m[k] || []).push(t); });
    Object.keys(m).forEach(function (k) { m[k].sort(function (a, b) { return new Date(a.fecha_entrega) - new Date(b.fecha_entrega); }); });
    return m;
  }
  function chip(t, conHora) {
    var hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    var vencida = !t.completada && new Date(t.fecha_entrega) < hoy;
    var quien = (typeof tkEsEmpresa !== 'undefined' && tkEsEmpresa && t.asignado_a && typeof tkNombreAgente === 'function') ? ' · ' + tkNombreAgente(t.asignado_a) : '';
    return '<div class="tkc-ev' + (t.completada ? ' is-done' : '') + (vencida ? ' is-late' : '') + '" data-id="' + esc(String(t.id)) + '" style="--c:' + colorTarea(t) + '" title="' + esc(t.titulo + quien) + '">' +
      (conHora ? '<span class="tkc-ev__h">' + hora(t) + '</span>' : '') + '<span class="tkc-ev__t">' + esc(t.titulo) + '</span></div>';
  }

  function montar() {
    var tabs = document.querySelector('.tk-tabs');
    var pane = document.getElementById('pane-actividad');
    if (!tabs || !pane || document.getElementById('tk-tab-cal')) return;
    var act = document.getElementById('tk-tab-act');
    act.insertAdjacentHTML('beforebegin', '<button class="tk-tab" id="tk-tab-cal" onclick="setTab(\'calendario\')">Calendario</button>');
    pane.insertAdjacentHTML('afterend', '<div id="pane-calendario" style="display:none"><div class="tkc-bar">' +
      '<div class="bk-seg" id="tkc-vistas"><button class="bk-seg__btn" data-v="dia">Día</button><button class="bk-seg__btn" data-v="semana">Semana</button><button class="bk-seg__btn" data-v="mes">Mes</button></div>' +
      '<div class="tkc-nav"><button class="bk-btn bk-btn--ghost bk-btn--sm" data-mover="-1" aria-label="Anterior">‹</button>' +
      '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-mover="0">Hoy</button><button class="bk-btn bk-btn--ghost bk-btn--sm" data-mover="1" aria-label="Siguiente">›</button></div>' +
      '<div class="tkc-titulo" id="tkc-titulo"></div></div><div class="tkc-leyenda" id="tkc-leyenda"></div><div id="tkc-cuerpo"></div>' +
      '<p class="tkc-ayuda">Arrastra una tarea a otro día para cambiarle la fecha' + ' (en la vista de día, a otra hora). Toca una tarea para abrirla.</p></div>');
    document.getElementById('tkc-vistas').onclick = function (ev) {
      var b = ev.target.closest('[data-v]'); if (!b) return;
      vista = b.dataset.v; try { localStorage.setItem('tk-cal-vista', vista); } catch (e) {}
      pintar();
    };
    document.querySelector('#pane-calendario .tkc-nav').onclick = function (ev) {
      var b = ev.target.closest('[data-mover]'); if (!b) return;
      var n = +b.dataset.mover;
      if (!n) { ancla = new Date(); ancla.setHours(0, 0, 0, 0); }
      else if (vista === 'mes') { ancla = new Date(ancla.getFullYear(), ancla.getMonth() + n, 1); }
      else ancla = sumar(ancla, n * (vista === 'semana' ? 7 : 1));
      pintar();
    };
    var cuerpo = document.getElementById('tkc-cuerpo');
    cuerpo.addEventListener('pointerdown', iniciarArrastre);
    cuerpo.addEventListener('click', function (ev) {
      if (arrastro) { arrastro = false; return; }
      var e = ev.target.closest('.tkc-ev'); if (e) { tkAbrirEditar(e.dataset.id); return; }
      var dia = ev.target.closest('[data-dia]');
      if (dia && vista === 'mes' && ev.target.closest('.tkc-num')) { ancla = new Date(dia.dataset.dia + 'T00:00:00'); vista = 'dia'; pintar(); }
    });

    // setTab de tareas.html sólo conoce sus dos pestañas: se envuelve.
    var _setTab = window.setTab;
    window.setTab = function (tab) {
      document.getElementById('tk-tab-cal').classList.toggle('active', tab === 'calendario');
      document.getElementById('pane-calendario').style.display = tab === 'calendario' ? '' : 'none';
      if (tab === 'calendario') {
        tabActual = 'calendario';
        document.getElementById('tk-tab-tareas').classList.remove('active');
        document.getElementById('tk-tab-act').classList.remove('active');
        document.getElementById('pane-tareas').style.display = 'none';
        document.getElementById('pane-actividad').style.display = 'none';
        pintar();
        return;
      }
      return _setTab.apply(this, arguments);
    };
    // Repintar cuando la lista se repinta (filtros, cambios, carga).
    var _render = window.renderTareas;
    if (typeof _render === 'function') {
      window.renderTareas = function () { var r = _render.apply(this, arguments); if (tabActual === 'calendario') pintar(); return r; };
    }
    if (new URLSearchParams(location.search).get('vista') === 'calendario') window.setTab('calendario');
  }

  function pintar() {
    var cuerpo = document.getElementById('tkc-cuerpo'); if (!cuerpo) return;
    [].forEach.call(document.querySelectorAll('#tkc-vistas [data-v]'), function (b) { b.classList.toggle('is-active', b.dataset.v === vista); });
    var m = porDia(lista()), hoyK = clave(new Date()), html = '', titulo = '';
    if (vista === 'mes') {
      var ini = lunes(new Date(ancla.getFullYear(), ancla.getMonth(), 1));
      titulo = MESES[ancla.getMonth()] + ' ' + ancla.getFullYear();
      html = '<div class="tkc-mes"><div class="tkc-mes__cab">' + DIAS.map(function (d) { return '<div>' + d + '</div>'; }).join('') + '</div><div class="tkc-mes__grid">';
      for (var i = 0; i < 42; i++) {
        var d = sumar(ini, i), k = clave(d), evs = m[k] || [];
        if (i === 35 && d.getMonth() !== ancla.getMonth()) break;
        html += '<div class="tkc-dia' + (d.getMonth() !== ancla.getMonth() ? ' is-fuera' : '') + (k === hoyK ? ' is-hoy' : '') + '" data-dia="' + k + '">' +
          '<button class="tkc-num" type="button">' + d.getDate() + '</button>' + evs.slice(0, 3).map(function (t) { return chip(t, false); }).join('') +
          (evs.length > 3 ? '<div class="tkc-mas">+' + (evs.length - 3) + ' más</div>' : '') + '</div>';
      }
      html += '</div></div>';
    } else if (vista === 'semana') {
      var l = lunes(ancla), f = sumar(l, 6);
      titulo = l.getDate() + (l.getMonth() !== f.getMonth() ? ' ' + MESES[l.getMonth()].slice(0, 3) : '') + ' – ' + f.getDate() + ' ' + MESES[f.getMonth()].slice(0, 3) + ' ' + f.getFullYear();
      html = '<div class="tkc-semana">' + [0, 1, 2, 3, 4, 5, 6].map(function (n) {
        var d = sumar(l, n), k = clave(d), evs = m[k] || [];
        return '<div class="tkc-col' + (k === hoyK ? ' is-hoy' : '') + '" data-dia="' + k + '"><div class="tkc-col__cab"><span>' + DIAS[n] + '</span><b>' + d.getDate() + '</b></div>' +
          (evs.length ? evs.map(function (t) { return chip(t, true); }).join('') : '<div class="tkc-vacio">—</div>') + '</div>';
      }).join('') + '</div>';
    } else {
      var k2 = clave(ancla), evs2 = m[k2] || [];
      titulo = DIAS[(ancla.getDay() + 6) % 7] + ' ' + ancla.getDate() + ' de ' + MESES[ancla.getMonth()] + ' ' + ancla.getFullYear();
      html = '<div class="tkc-diaview">';
      for (var h = 6; h <= 22; h++) {
        var deHora = evs2.filter(function (t) { var x = new Date(t.fecha_entrega).getHours(); return x === h || (h === 6 && x < 6) || (h === 22 && x > 22); });
        html += '<div class="tkc-hora" data-dia="' + k2 + '" data-hora="' + h + '"><span class="tkc-hora__l">' + ('0' + h).slice(-2) + ':00</span><div class="tkc-hora__evs">' +
          deHora.map(function (t) { return chip(t, true); }).join('') + '</div></div>';
      }
      html += '</div>';
    }
    document.getElementById('tkc-titulo').textContent = titulo;
    cuerpo.innerHTML = html;
    var cats = (typeof tkCategorias !== 'undefined' && tkCategorias) || [];
    document.getElementById('tkc-leyenda').innerHTML = cats.length ? cats.map(function (c) {
      return '<span class="tkc-ley"><i style="--c:' + colorCat(c.id) + '"></i>' + esc(c.nombre) + '</span>';
    }).join('') + '<span class="tkc-ley"><i style="--c:var(--mute-2)"></i>Sin categoría</span>' : '';
  }

  // ── Arrastrar (mouse y dedo) ──
  var arrastro = false;
  function iniciarArrastre(ev) {
    var el = ev.target.closest('.tkc-ev'); if (!el || ev.button > 0) return;
    var x0 = ev.clientX, y0 = ev.clientY, fantasma = null, destino = null, pid = ev.pointerId;
    var temporizador = null;
    function empezar() {
      if (fantasma) return;
      fantasma = el.cloneNode(true); fantasma.classList.add('tkc-fantasma');
      fantasma.style.width = el.offsetWidth + 'px';
      document.body.appendChild(fantasma);
      el.classList.add('is-arrastrando');
      try { el.setPointerCapture(pid); } catch (e) {}
      if (navigator.vibrate) try { navigator.vibrate(10); } catch (e) {}
    }
    function mover(e) {
      if (!fantasma) {
        if (Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) < 6) return;
        empezar();
      }
      e.preventDefault();
      fantasma.style.left = (e.clientX - 20) + 'px'; fantasma.style.top = (e.clientY - 14) + 'px';
      fantasma.style.display = 'none';
      var bajo = document.elementFromPoint(e.clientX, e.clientY);
      fantasma.style.display = '';
      var d = bajo && bajo.closest('[data-dia]');
      if (destino && destino !== d) destino.classList.remove('is-destino');
      destino = d; if (d) d.classList.add('is-destino');
    }
    function soltar() {
      clearTimeout(temporizador);
      var habia = !!fantasma;
      limpiar();
      if (!habia) return;
      arrastro = true; setTimeout(function () { arrastro = false; }, 50);
      if (destino) { destino.classList.remove('is-destino'); mover_(el.dataset.id, destino.dataset.dia, destino.dataset.hora); }
    }
    function limpiar() {
      document.removeEventListener('pointermove', mover); document.removeEventListener('pointerup', soltar); document.removeEventListener('pointercancel', soltar);
      if (fantasma) fantasma.remove();
      el.classList.remove('is-arrastrando');
    }
    document.addEventListener('pointermove', mover, { passive: false });
    document.addEventListener('pointerup', soltar); document.addEventListener('pointercancel', soltar);
  }

  async function mover_(id, dia, horaNueva) {
    var t = tareas.find(function (x) { return String(x.id) === String(id); }); if (!t) return;
    var antes = t.fecha_entrega, d = new Date(antes), p = dia.split('-');
    var n = new Date(+p[0], +p[1] - 1, +p[2], horaNueva != null ? +horaNueva : d.getHours(), horaNueva != null ? 0 : d.getMinutes());
    if (n.getTime() === d.getTime()) return;
    t.fecha_entrega = n.toISOString();
    pintar();
    try {
      await sbFetch('tareas?id=eq.' + encodeURIComponent(id), 'PATCH', { fecha_entrega: t.fecha_entrega });
      if (typeof showToast === 'function') showToast('Fecha cambiada al ' + n.getDate() + ' de ' + MESES[n.getMonth()]);
      if (typeof window.renderTareas === 'function') window.renderTareas();
    } catch (e) {
      t.fecha_entrega = antes; pintar();
      if (typeof showToast === 'function') showToast('No se pudo cambiar la fecha: ' + (e.message || e));
    }
  }
  window.tkcPintar = pintar;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montar); else montar();
})();
