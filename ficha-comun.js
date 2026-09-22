// Broquer · Ficha — las piezas que comparten Clientes, Directorio e Inmuebles.
//
// Los tres módulos abren el mismo tipo de pantalla de detalle, y hasta ahora
// cada uno traía su propia copia del menú de estado y del feed de historial,
// con tres juegos de clases que se fueron separando entre sí. Aquí vive la
// mecánica común; el CSS correspondiente está en brokr-theme.css (bloque
// "FICHA") y cada módulo pone lo suyo: qué datos pinta y a qué tabla escribe.

/* ══════════════════════════════════════════════════════════════════
   Menú anclado a un botón
   Se dibuja en <body> con position:fixed porque la ficha tiene
   contenedores con overflow y un popover absoluto dentro de ellos se
   recorta (y así tampoco hereda el z-index de su fila).
   ══════════════════════════════════════════════════════════════════ */
let _bkMenuAbierto = null;   // { caja, anchor }

const BK_ICONO_CHECK = '<svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>';
const BK_CHEVRON = '<svg class="bk-pill__chev" width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.4"><path stroke-linecap="round" stroke-linejoin="round" d="M6 9l6 6 6-6"/></svg>';

function bkEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function bkCerrarMenu() {
  if (!_bkMenuAbierto) return;
  const { caja, anchor } = _bkMenuAbierto;
  _bkMenuAbierto = null;
  caja.remove();
  if (anchor) anchor.setAttribute('aria-expanded', 'false');
  document.removeEventListener('keydown', _bkMenuTecla, true);
}

function bkHayMenuAbierto() { return !!_bkMenuAbierto; }

function _bkMenuTecla(ev) {
  if (!_bkMenuAbierto) return;
  const items = Array.from(_bkMenuAbierto.caja.querySelectorAll('.bk-menu__item:not([disabled])'));
  const i = items.indexOf(document.activeElement);
  if (ev.key === 'Escape') {
    ev.preventDefault();
    const a = _bkMenuAbierto.anchor;
    bkCerrarMenu();
    if (a) a.focus();
  } else if (ev.key === 'ArrowDown') {
    ev.preventDefault();
    (items[i + 1] || items[0]).focus();
  } else if (ev.key === 'ArrowUp') {
    ev.preventDefault();
    (items[i - 1] || items[items.length - 1]).focus();
  } else if (ev.key === 'Tab') {
    bkCerrarMenu();
  }
}

// items: [{ id, etiqueta, nota?, color?, activo?, peligro?, separa? }]
function bkAbrirMenu(anchor, items, onElegir) {
  const yaEra = _bkMenuAbierto && _bkMenuAbierto.anchor === anchor;
  bkCerrarMenu();
  if (yaEra) return;                      // segundo clic en el mismo botón: cierra

  const caja = document.createElement('div');
  caja.className = 'bk-menu bk-menu--anclado';
  caja.setAttribute('role', 'menu');
  caja.innerHTML = items.map((it, i) => `
    ${it.separa ? '<div class="bk-menu__sep"></div>' : ''}
    <button type="button" role="menuitem" data-i="${i}"
            class="bk-menu__item${it.activo ? ' is-on' : ''}${it.peligro ? ' bk-menu__item--danger' : ''}">
      ${it.color ? `<span class="bk-punto" style="background:${it.color}"></span>` : ''}
      <span class="bk-menu__txt">${bkEsc(it.etiqueta)}${it.nota ? `<small>${bkEsc(it.nota)}</small>` : ''}</span>
      <span class="bk-menu__check">${it.activo ? BK_ICONO_CHECK : ''}</span>
    </button>`).join('');
  document.body.appendChild(caja);

  const r = anchor.getBoundingClientRect();
  const alto = caja.offsetHeight;
  const ancho = Math.max(caja.offsetWidth, r.width);
  const cabeAbajo = r.bottom + alto + 8 <= window.innerHeight;
  caja.style.minWidth = r.width + 'px';
  caja.style.top = (cabeAbajo ? r.bottom + 6 : Math.max(8, r.top - alto - 6)) + 'px';
  caja.style.left = Math.min(Math.max(8, r.left), window.innerWidth - ancho - 8) + 'px';

  anchor.setAttribute('aria-expanded', 'true');
  _bkMenuAbierto = { caja, anchor };

  caja.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.bk-menu__item');
    if (!btn) return;
    const it = items[Number(btn.dataset.i)];
    bkCerrarMenu();
    if (it) onElegir(it.id);
  });
  document.addEventListener('keydown', _bkMenuTecla, true);
  const activo = caja.querySelector('.bk-menu__item.is-on') || caja.querySelector('.bk-menu__item');
  if (activo) activo.focus();
}

document.addEventListener('mousedown', (ev) => {
  if (!_bkMenuAbierto) return;
  if (ev.target.closest('.bk-menu--anclado') || ev.target.closest('[data-bk-menu]')) return;
  bkCerrarMenu();
});
window.addEventListener('resize', bkCerrarMenu);
document.addEventListener('scroll', bkCerrarMenu, true);

/* ══════════════════════════════════════════════════════════════════
   Bitácora — la línea de tiempo del registro
   ══════════════════════════════════════════════════════════════════ */
const BK_BITA_ICONOS = {
  nota:             '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M16.86 4.49l1.69-1.69a1.88 1.88 0 112.65 2.65L6.83 19.82a4.5 4.5 0 01-1.9 1.13l-2.68.8.8-2.69a4.5 4.5 0 011.13-1.9L16.86 4.5z"/></svg>',
  archivo:          '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M17.5 8.5l-7.1 7.1a2.5 2.5 0 003.5 3.5l7.1-7.1a4.5 4.5 0 00-6.4-6.4l-7.1 7.1a6.5 6.5 0 009.2 9.2"/></svg>',
  cambio_estatus:   '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M7 16l-4-4 4-4m-4 4h18M17 8l4 4-4 4"/></svg>',
  tarea_completada: '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  alta:             '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM19 8v6M22 11h-6"/></svg>',
  operacion:        '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.59a1 1 0 01.7.29l4.42 4.42a1 1 0 01.29.7V19a2 2 0 01-2 2z"/></svg>',
};
const BK_BITA_TITULOS = {
  nota: 'Nota', archivo: 'Archivos', cambio_estatus: 'Cambio de estatus',
  tarea_completada: 'Tarea completada', alta: 'Alta', operacion: 'Operación',
};

function bkDiaEtiqueta(d) {
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const dia = new Date(d); dia.setHours(0, 0, 0, 0);
  const difDias = Math.round((hoy - dia) / 86400000);
  if (difDias === 0) return 'Hoy';
  if (difDias === 1) return 'Ayer';
  const opts = { day: 'numeric', month: 'long' };
  if (dia.getFullYear() !== hoy.getFullYear()) opts.year = 'numeric';
  return dia.toLocaleDateString('es-MX', opts);
}

function bkHora(iso) {
  try { return new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }); }
  catch { return ''; }
}

// El renglón ya dice de qué tipo es el evento; el texto guardado suele
// repetir ese prefijo ("Tarea completada: Llamar a…"). Se quita para no
// leerlo dos veces.
function bkSinPrefijo(tipo, texto) {
  const prefijos = {
    tarea_completada: /^Tarea completada:\s*/i,
    cambio_estatus: /^(Etapa|Estatus):\s*/i,
  };
  const p = prefijos[tipo];
  return p ? String(texto || '').replace(p, '') : (texto || '');
}

// entradas: [{ tipo, texto, fecha, adjuntos? }] — ya ordenadas o no.
// titulos: mapa opcional para renombrar el encabezado de un tipo.
function bkRenderBitacora(entradas, titulos) {
  const lista = entradas.slice().sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
  const nombres = Object.assign({}, BK_BITA_TITULOS, titulos || {});
  let html = '';
  let diaActual = '';
  lista.forEach(e => {
    const dia = bkDiaEtiqueta(e.fecha);
    if (dia !== diaActual) {
      diaActual = dia;
      html += `<div class="bk-bita__dia">${bkEsc(dia)}</div>`;
    }
    html += bkItemBitacora({
      id: e.id,
      tipo: e.tipo,
      titulo: nombres[e.tipo] || 'Actividad',
      texto: bkSinPrefijo(e.tipo, e.texto),
      hora: bkHora(e.fecha),
      adjuntos: e.adjuntos,
      categorias: e.categorias,
      editadoEn: e.editado_en,
    });
  });
  return html;
}

// Editar/eliminar solo aplica a notas y archivos escritos a mano — los
// demás tipos (alta, cambio de etapa, tarea completada) son un registro
// automático de lo que pasó, no algo que tenga sentido "corregir".
const BK_TIPOS_EDITABLES = ['nota', 'archivo'];

function bkItemBitacora({ id, tipo, titulo, texto, hora, adjuntos, categorias, editadoEn }) {
  const adj = (typeof haRenderAdjuntos === 'function') ? haRenderAdjuntos(adjuntos) : '';
  const cats = (categorias && categorias.length)
    ? '<div class="tke-chips" style="margin-top:6px">' +
      categorias.map(n => '<span class="tke-chip" style="cursor:default">' + bkEsc(n) + '</span>').join('') +
      '</div>'
    : '';
  const editable = id && BK_TIPOS_EDITABLES.includes(tipo) &&
    typeof bkEditarNota === 'function' && typeof bkEliminarNota === 'function';
  const acciones = editable
    ? `<div class="bk-bita__acciones">
        ${editadoEn ? '<span class="bk-hint" title="Editada">(editada)</span>' : ''}
        <button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" onclick="bkEditarNota('${bkEsc(String(id))}')">Editar</button>
        <button type="button" class="bk-btn bk-btn--quiet bk-btn--sm" onclick="bkEliminarNota('${bkEsc(String(id))}')">Eliminar</button>
      </div>`
    : '';
  return `<article class="bk-bita__item">
    <span class="bk-bita__ico bk-bita__ico--${bkEsc(tipo)}">${BK_BITA_ICONOS[tipo] || BK_BITA_ICONOS.nota}</span>
    <div class="bk-bita__cuerpo">
      <header class="bk-bita__head">
        <span class="bk-bita__tipo">${bkEsc(titulo)}</span>
        <time class="bk-bita__hora">${bkEsc(hora)}</time>
      </header>
      ${texto ? `<p class="bk-bita__txt">${bkEsc(texto)}</p>` : ''}
      ${cats}
      ${acciones}
      ${adj}
    </div>
  </article>`;
}

/* ══════════════════════════════════════════════════════════════════
   Piezas sueltas de la ficha
   ══════════════════════════════════════════════════════════════════ */

// Un dato del bloque de resumen. `valor` puede traer HTML (ligas).
function bkDato(label, valor, ancho) {
  if (!valor) return '';
  return `<div class="bk-dato${ancho ? ' bk-dato--ancho' : ''}">
    <span class="bk-dato__lbl">${bkEsc(label)}</span>
    <span class="bk-dato__val">${valor}</span>
  </div>`;
}

// Deja un botón/enlace de contacto habilitado o apagado de verdad (no con
// opacidad simulada): sin dato no navega y sale del orden de tabulación.
function bkAccion(el, activo, href) {
  if (!el) return;
  el.href = activo ? href : '#';
  el.setAttribute('aria-disabled', activo ? 'false' : 'true');
  el.tabIndex = activo ? 0 : -1;
  el.onclick = activo ? null : (ev) => { ev.preventDefault(); };
}

// Contador de una pestaña: se esconde cuando vale cero.
function bkContador(id, n) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = n;
  el.hidden = !n;
}

/* ══════════════════════════════════════════════════════════════════
   Buscador con sugerencias en vivo — reemplaza los <select> con cientos
   de opciones en orden alfabético, sin filtro, por un campo de texto
   que filtra mientras se escribe (mismo mecanismo que ya traía el
   buscador de propiedades de Clientes, generalizado para cualquier
   lista: contactos, propiedades, lo que sea).

   opciones = {
     filtro(item, q)  → true/false si "item" coincide con la búsqueda q
     render(item)     → { titulo, sub } para pintar la sugerencia
     vacioTexto       → texto cuando no hay nada que ofrecer
     limite           → máximo de sugerencias (default 8)
   }
   Devuelve { onInput(disponibles), onKeydown(ev), manejarClick(target),
              cerrarSiClickAfuera(target) } — mismo contrato que el
   buscador de propiedades original, para no tener que tocar quien ya
   lo usaba.
   ══════════════════════════════════════════════════════════════════ */
function bkCrearBuscador(inputId, hiddenId, cajaId, opciones) {
  const { filtro, render, vacioTexto, limite } = opciones;
  const tope = limite || 8;
  let sugCache = [];
  let hl = -1;
  const inputEl = () => document.getElementById(inputId);
  const hiddenEl = () => document.getElementById(hiddenId);
  const cajaEl = () => document.getElementById(cajaId);

  function filtrar(q, disponibles) {
    q = (q || '').toLowerCase().trim();
    if (!q) return disponibles.slice(0, tope);
    return disponibles.filter(item => filtro(item, q)).slice(0, tope);
  }
  function pintar(lista, disponibles) {
    sugCache = lista;
    hl = -1;
    const caja = cajaEl();
    if (!lista.length) {
      caja.innerHTML = '<div class="prop-sugerencia prop-sugerencia--vacio">' +
        (disponibles.length ? 'Sin coincidencias' : (vacioTexto || 'Nada para elegir')) + '</div>';
      caja.hidden = false;
      return;
    }
    caja.innerHTML = lista.map((item, i) => {
      const { titulo, sub } = render(item);
      return `<button type="button" class="prop-sugerencia" data-idx="${i}">
        <span class="prop-sugerencia__n">${bkEsc(titulo || 'Sin nombre')}</span>
        ${sub ? `<span class="prop-sugerencia__d">${bkEsc(sub)}</span>` : ''}
      </button>`;
    }).join('');
    caja.hidden = false;
  }
  function onInput(disponibles) {
    hiddenEl().value = '';
    pintar(filtrar(inputEl().value, disponibles), disponibles);
  }
  function elegir(idx) {
    const item = sugCache[idx];
    if (!item) return null;
    hiddenEl().value = item.id;
    inputEl().value = render(item).titulo || '';
    cajaEl().hidden = true;
    return item;
  }
  function resaltar() {
    const caja = cajaEl();
    Array.from(caja.querySelectorAll('.prop-sugerencia[data-idx]')).forEach((el, i) => {
      el.classList.toggle('is-hl', i === hl);
      if (i === hl) el.scrollIntoView({ block: 'nearest' });
    });
  }
  function onKeydown(ev) {
    const caja = cajaEl();
    if (!caja || caja.hidden) return;
    const n = sugCache.length;
    if (ev.key === 'ArrowDown' && n) { ev.preventDefault(); hl = Math.min(hl + 1, n - 1); resaltar(); }
    else if (ev.key === 'ArrowUp' && n) { ev.preventDefault(); hl = Math.max(hl - 1, 0); resaltar(); }
    else if (ev.key === 'Enter') { ev.preventDefault(); elegir(hl >= 0 ? hl : 0); }
    else if (ev.key === 'Escape') { caja.hidden = true; }
  }
  function manejarClick(target) {
    const btn = target.closest('.prop-sugerencia[data-idx]');
    if (btn && cajaEl().contains(btn)) { elegir(Number(btn.dataset.idx)); return true; }
    return false;
  }
  function cerrarSiClickAfuera(target) {
    if (!target.closest('#' + inputId) && !target.closest('#' + cajaId)) cajaEl().hidden = true;
  }
  return { onInput, onKeydown, manejarClick, cerrarSiClickAfuera, elegir };
}

// Atajo: buscador de propiedades por título/colonia/ciudad/tipo — el caso
// más común (Tareas, notas, filtros de "propiedad de interés"…).
function bkBuscadorPropiedades(inputId, hiddenId, cajaId, vacioTexto) {
  return bkCrearBuscador(inputId, hiddenId, cajaId, {
    vacioTexto,
    filtro: (p, q) => ((p.titulo||'') + ' ' + (p.colonia||'') + ' ' + (p.ciudad||'') + ' ' + (p.tipo||'')).toLowerCase().includes(q),
    render: (p) => ({
      titulo: p.titulo || 'Sin título',
      sub: (typeof propSubtitulo === 'function') ? propSubtitulo(p) : (p.clave_interna || p.colonia || ''),
    }),
  });
}

// Atajo: buscador de contactos por nombre/teléfono/correo.
function bkBuscadorContactos(inputId, hiddenId, cajaId, vacioTexto) {
  return bkCrearBuscador(inputId, hiddenId, cajaId, {
    vacioTexto,
    filtro: (c, q) => ((c.nombre||'') + ' ' + (c.telefono||'') + ' ' + (c.email||'')).toLowerCase().includes(q),
    render: (c) => ({ titulo: c.nombre || 'Sin nombre', sub: c.telefono || c.email || '' }),
  });
}
