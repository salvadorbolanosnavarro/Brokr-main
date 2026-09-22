// Broquer · Directorio — la ficha del contacto.
//
// Misma superficie que la de Clientes (ver ficha-comun.js y el bloque FICHA
// de brokr-theme.css), con lo propio del Directorio: aquí vive TODA la
// agenda, no sólo el pipeline, así que el control de cabecera es "¿este
// contacto es un cliente potencial?" y la etapa sólo aparece cuando lo es.
//
// Usa los globales de contactos.html: _sb, _userId, restGet, restPost,
// restDelete, patchRemoto, esc, showToast, fechaCorta, initials, avColor,
// rolBadge, domicilio, ETAPAS, etapaInfo, PROBS, patchContacto, renderActual,
// cargar, abrirModal, abrirWA, cargarRemoto, eliminarRemoto, cargarPropsMin,
// propSubtitulo, buscarPropInput, propBuscarKeydown, detContacto.

/* ══════════════════════════════════════════════════════════════════
   Abrir / cerrar
   ══════════════════════════════════════════════════════════════════ */
function abrirDetalle(id) {
  clearTimeout(_busqT);
  id = String(id || '');
  const c = cargar().find(x => String(x.id) === id);
  if (!c) return;
  ctDescartarBorrador();
  detContacto = c;

  const av = document.getElementById('f-av');
  av.textContent = initials(c.nombre || '??');
  av.className = 'bk-ficha__av ' + avColor(c.nombre || '');
  document.getElementById('f-nombre').textContent = c.nombre || 'Sin nombre';
  document.getElementById('f-rol').innerHTML = rolBadge(c.tipo);
  const meta = [c.empresa, c.fuente ? 'Vía ' + c.fuente : ''].filter(Boolean).join(' · ');
  const metaEl = document.getElementById('f-meta');
  metaEl.textContent = meta;
  metaEl.hidden = !meta;

  ctRenderAsignacion(c);
  ctRenderEstado(c);
  ctRenderAcciones(c);
  ctRenderResumen(c);

  document.getElementById('f-bitacora-feed').innerHTML = '';
  document.getElementById('props-feed').innerHTML = '';
  document.getElementById('tareas-feed').innerHTML = '';
  ['bitacora', 'props', 'tareas'].forEach(t => {
    const n = document.getElementById('f-n-' + t);
    if (n) { n.textContent = ''; n.hidden = true; }
  });

  setDetTab('info');
  document.getElementById('detail-ov').classList.add('is-open');
  document.body.classList.add('bk-sin-scroll');
}

function cerrarDetalle() {
  bkCerrarMenu();
  ctDescartarBorrador();
  document.getElementById('detail-ov').classList.remove('is-open');
  document.body.classList.remove('bk-sin-scroll');
  detContacto = null;
}

function ctDescartarBorrador() {
  if (typeof haTomarAdjuntosListos === 'function') haTomarAdjuntosListos('f-nota-preview');
  const comp = document.getElementById('f-composer');
  if (comp) comp.hidden = true;
  const ta = document.getElementById('f-nota-texto');
  if (ta) ta.value = '';
  CT_NOTA_CATS = [];
  ctQuitarPropNota();
}

function ctRenderAsignacion(c) {
  const wrap = document.getElementById('f-asignado');
  if (!cEsEmpresa || !cMiembros.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  const sel = document.getElementById('f-asignado-sel');
  const txt = document.getElementById('f-asignado-txt');
  sel.hidden = false; txt.hidden = true;
  sel.innerHTML = '<option value="">Sin asignar</option>' +
    cMiembros.map(m => `<option value="${esc(m.user_id)}">${esc(m.nombre || m.email)}</option>`).join('');
  sel.value = c.asignado_a || '';
}

/* ══════════════════════════════════════════════════════════════════
   Estado
   Un contacto del Directorio puede ser sólo una entrada de agenda (un
   notario, un colega) o un cliente potencial. Etapa y probabilidad
   describen un proceso de venta: sólo tienen sentido —y sólo se
   muestran— cuando el contacto está en el pipeline.
   ══════════════════════════════════════════════════════════════════ */
const CT_ESTRELLA = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2l-6.1 3.4 1.4-6.8L2.2 9.1l6.9-.8L12 2z"/></svg>';

function ctProbInfo(v) {
  const mapa = {
    alta:  { l: 'Alta',  color: 'var(--success)' },
    media: { l: 'Media', color: 'var(--warn)' },
    baja:  { l: 'Baja',  color: 'var(--mute-2)' },
  };
  return mapa[String(v || '').toLowerCase()] || null;
}

function ctRenderEstado(c) {
  const esPotencial = !!c.es_potencial;

  const pot = document.getElementById('f-potencial');
  pot.innerHTML = CT_ESTRELLA + '<span class="bk-pill__txt">' +
    (esPotencial ? 'En el pipeline' : 'Pasar al pipeline') + '</span>';
  pot.classList.toggle('is-on', esPotencial);
  pot.title = esPotencial
    ? 'Sacar del pipeline de Clientes (se queda en el Directorio)'
    : 'Marcarlo como cliente potencial y mandarlo al pipeline';

  document.getElementById('f-etapa-btn').hidden = !esPotencial;
  document.getElementById('f-prob-btn').hidden = !esPotencial;
  if (!esPotencial) return;

  const etapa = etapaInfo(c.estatus);
  const tieneEtapa = !!String(c.estatus || '').trim();
  document.getElementById('f-etapa-btn').innerHTML =
    `<span class="bk-punto" style="background:${tieneEtapa ? etapa.color : 'var(--mute-3)'}"></span>
     <span class="bk-pill__txt">${tieneEtapa ? esc(etapa.nombre) : 'Sin etapa'}</span>${BK_CHEVRON}`;

  const prob = ctProbInfo(c.probabilidad);
  document.getElementById('f-prob-btn').innerHTML =
    `<span class="bk-pill__lbl">Probabilidad</span>
     <span class="bk-pill__txt"${prob ? ` style="color:${prob.color}"` : ''}>${prob ? prob.l : 'Sin definir'}</span>${BK_CHEVRON}`;
}

async function toggleDetPotencial() {
  if (!detContacto) return;
  const c = cargar().find(x => String(x.id) === String(detContacto.id));
  if (!c) return;
  const nuevo = !c.es_potencial;
  c.es_potencial = nuevo;             // optimista
  detContacto.es_potencial = nuevo;
  ctRenderEstado(detContacto);
  try {
    await patchRemoto(c.id, { es_potencial: nuevo });
    try { localStorage.setItem(LS_CACHE, JSON.stringify(_contactosMem)); } catch (_) {}
    renderActual();
    showToast(nuevo ? 'Ahora aparece en Clientes' : 'Salió del pipeline de Clientes');
  } catch (e) {
    c.es_potencial = !nuevo;
    detContacto.es_potencial = !nuevo;
    ctRenderEstado(detContacto);
    showToast('No se pudo guardar el cambio');
  }
}

function ctMenuEtapa(btn) {
  if (!detContacto) return;
  const actual = String(detContacto.estatus || '').toLowerCase();
  const items = ETAPAS.map(e => ({ id: e.clave, etiqueta: e.nombre, color: e.color, activo: actual === e.clave }));
  if (actual) items.push({ id: '', etiqueta: 'Quitar etapa', separa: true });
  bkAbrirMenu(btn, items, (v) => setEtapa(v));
}

function ctMenuProb(btn) {
  if (!detContacto) return;
  const actual = String(detContacto.probabilidad || '').toLowerCase();
  const items = PROBS.map(p => {
    const info = ctProbInfo(p.v);
    return { id: p.v, etiqueta: p.l, color: info && info.color, activo: actual === p.v };
  });
  if (actual) items.push({ id: '', etiqueta: 'Sin definir', separa: true });
  bkAbrirMenu(btn, items, (v) => setProbabilidad(v));
}

function ctMenuMas(btn) {
  if (!detContacto) return;
  bkAbrirMenu(btn, [
    { id: 'editar', etiqueta: 'Editar contacto' },
    { id: 'eliminar', etiqueta: 'Eliminar contacto', peligro: true, separa: true },
  ], (v) => {
    if (v === 'editar') editarDesdeDetalle();
    if (v === 'eliminar') eliminarDesdeDetalle();
  });
}

async function setEtapa(v) {
  if (!detContacto) return;
  const prev = String(detContacto.estatus || '').toLowerCase();
  if (prev === v) return;
  detContacto.estatus = v;
  ctRenderEstado(detContacto);
  try {
    await patchContacto(detContacto.id, { estatus: v || null });
    renderActual();
    showToast(v ? 'Etapa: ' + etapaInfo(v).nombre : 'Etapa quitada');
    ctRegistrarCambioEtapa(detContacto.id, prev, v);
  } catch (e) {
    detContacto.estatus = prev;
    ctRenderEstado(detContacto);
    showToast('No se pudo guardar la etapa');
  }
}

async function setProbabilidad(v) {
  if (!detContacto) return;
  const prev = String(detContacto.probabilidad || '').toLowerCase();
  if (prev === v) return;
  detContacto.probabilidad = v;
  ctRenderEstado(detContacto);
  try {
    await patchContacto(detContacto.id, { probabilidad: v || null });
    renderActual();
    const info = ctProbInfo(v);
    showToast(info ? 'Probabilidad: ' + info.l : 'Probabilidad quitada');
  } catch (e) {
    detContacto.probabilidad = prev;
    ctRenderEstado(detContacto);
    showToast('No se pudo guardar la probabilidad');
  }
}

function ctRegistrarCambioEtapa(contactoId, previo, nuevo) {
  const de = previo ? etapaInfo(previo).nombre : 'Sin etapa';
  const a = nuevo ? etapaInfo(nuevo).nombre : 'Sin etapa';
  restPost('actividades', {
    tipo: 'cambio_estatus',
    texto: 'Etapa: ' + de + ' → ' + a,
    contacto_id: contactoId,
    org_id: cOrgId,
  }).then(() => {
    if (detContacto && String(detContacto.id) === String(contactoId) && detTabActual === 'bitacora') cargarBitacora();
  }).catch(() => {});
}

function ctRenderAcciones(c) {
  const wa = c.wa || c.telefono;
  const waBtn = document.getElementById('f-wa');
  bkAccion(waBtn, !!wa, 'https://wa.me/52' + String(wa || '').replace(/\D/g, ''));
  if (wa) waBtn.onclick = (ev) => abrirWA(ev, wa);
  bkAccion(document.getElementById('f-tel'), !!c.telefono, 'tel:' + (c.telefono || ''));
  bkAccion(document.getElementById('f-mail'), !!c.email, 'mailto:' + (c.email || ''));
}

/* ══════════════════════════════════════════════════════════════════
   Pestañas
   ══════════════════════════════════════════════════════════════════ */
function setDetTab(tab) {
  detTabActual = tab;
  ['info', 'bitacora', 'props', 'tareas'].forEach(t => {
    document.getElementById('f-pane-' + t).hidden = t !== tab;
    const btn = document.getElementById('f-tab-' + t);
    btn.classList.toggle('is-active', t === tab);
    btn.setAttribute('aria-selected', t === tab ? 'true' : 'false');
  });
  if (!detContacto) return;
  if (tab === 'bitacora') cargarBitacora();
  if (tab === 'props') cargarVinculos();
  if (tab === 'tareas') cargarTareasVinculadas();
}

/* ══════════════════════════════════════════════════════════════════
   Resumen
   ══════════════════════════════════════════════════════════════════ */
function ctRenderResumen(c) {
  const tel = c.telefono ? `<a href="tel:${esc(c.telefono)}">${esc(c.telefono)}</a>` : '';
  const wa = c.wa ? `<a href="#" onclick="return abrirWA(event,'${esc(c.wa)}')">${esc(c.wa)}</a>` : '';
  const mail = c.email ? `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : '';

  let html = '<div class="bk-datos">' +
    bkDato('Teléfono', tel) +
    bkDato('WhatsApp', wa) +
    bkDato('Correo', mail) +
    bkDato('Fuente', esc(c.fuente || '')) +
    bkDato('Domicilio', esc(domicilio(c)), true) +
    bkDato('Sexo', c.sexo === 'F' ? 'Femenino' : 'Masculino') +
    bkDato('En el directorio desde', esc(fechaCorta(c.created_at))) +
    '</div>';

  if (Array.isArray(c.etiquetas) && c.etiquetas.length) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Etiquetas</h3>
      <div class="bk-tags">${c.etiquetas.map(t => `<span class="tag-chip">${esc(t)}</span>`).join('')}</div></div>`;
  }
  if (c.notas) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Notas</h3><p class="bk-prosa">${esc(c.notas)}</p></div>`;
  }
  if (c.descripcion_privada) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Perfil que arma Broq</h3>
      <p class="bk-prosa bk-prosa--broq">${esc(c.descripcion_privada)}</p></div>`;
  }

  const faltan = [];
  if (!c.email) faltan.push('el correo');
  if (!c.wa && !c.telefono) faltan.push('un teléfono');
  if (!domicilio(c)) faltan.push('el domicilio');
  if (faltan.length) {
    const lista = faltan.length > 1
      ? faltan.slice(0, -1).join(', ') + ' y ' + faltan[faltan.length - 1]
      : faltan[0];
    html += `<div class="bk-aviso">
      <p>Falta ${esc(lista)}. Con la ficha completa puedes mandarle un contrato o una ficha sin andar buscando el dato.</p>
      <button class="bk-btn bk-btn--ghost bk-btn--sm" onclick="editarDesdeDetalle()">Completar datos</button>
    </div>`;
  }
  document.getElementById('f-pane-info').innerHTML = html;
}

/* ══════════════════════════════════════════════════════════════════
   Bitácora
   ══════════════════════════════════════════════════════════════════ */
async function cargarBitacora() {
  if (!detContacto) return;
  const feed = document.getElementById('f-bitacora-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando la bitácora…</div>';
  const cid = detContacto.id;
  let acts = [];
  try {
    acts = await restGet('actividades?select=*&contacto_id=eq.' + encodeURIComponent(cid) + '&order=created_at.desc&limit=200');
  } catch { acts = []; }
  if (!detContacto || detContacto.id !== cid) return;

  let catsPorActividad = {};
  if (acts.length) {
    try {
      const ids = acts.map(a => '"' + a.id + '"').join(',');
      const links = await restGet('actividades_categorias?select=actividad_id,categoria_id&actividad_id=in.(' + ids + ')');
      (Array.isArray(links) ? links : []).forEach(l => {
        const cat = cCategorias.find(c => String(c.id) === String(l.categoria_id));
        if (cat) (catsPorActividad[l.actividad_id] = catsPorActividad[l.actividad_id] || []).push(cat.nombre);
      });
    } catch {}
  }

  const entradas = acts.map(a => ({
    id: a.id, tipo: a.tipo || 'nota', texto: a.texto || '', adjuntos: a.adjuntos, fecha: a.created_at,
    categorias: catsPorActividad[a.id], editado_en: a.editado_en,
  }));

  // Las operaciones históricas traen la fecha como texto libre: sólo entran
  // en la línea de tiempo las que sí se pueden fechar.
  const ops = Array.isArray(detContacto.operaciones) ? detContacto.operaciones : [];
  const opsSinFecha = [];
  ops.forEach(op => {
    const t = Date.parse(op.fecha);
    if (isFinite(t)) entradas.push({ tipo: 'operacion', texto: op.desc || '', fecha: new Date(t).toISOString() });
    else opsSinFecha.push(op);
  });

  if (detContacto.created_at) {
    entradas.push({ tipo: 'alta', texto: 'Se agregó a ' + (detContacto.nombre || 'el contacto') + ' al directorio.', fecha: detContacto.created_at });
  }

  bkContador('f-n-bitacora', entradas.length + opsSinFecha.length);

  if (!entradas.length && !opsSinFecha.length) {
    feed.innerHTML = `<div class="bk-vacio">
      <h3>Todavía no hay nada anotado</h3>
      <p>Cada nota, archivo y cambio de etapa queda aquí con su fecha y hora, para que dentro de un año sepas exactamente qué pasó con este contacto.</p>
    </div>`;
    return;
  }

  let html = bkRenderBitacora(entradas, { alta: 'Alta del contacto', cambio_estatus: 'Cambio de etapa' });
  if (opsSinFecha.length) {
    html += '<div class="bk-bita__dia">Sin fecha registrada</div>' +
      opsSinFecha.map(op => bkItemBitacora({
        tipo: 'operacion', titulo: 'Operación', texto: op.desc || '', hora: op.fecha || '',
      })).join('');
  }
  feed.innerHTML = html;
}

let CT_NOTA_CATS = []; // categorías elegidas para la nota que se está redactando

// Adjuntar un inmueble a la nota (cualquiera del usuario, no solo el de la
// ficha en la que se está parado) — la nota queda también en la bitácora
// de esa propiedad, porque actividades.propiedad_id ya existe y se usa así
// en otros flujos (ver pdAgregarTarea/cambio de estatus).
const _buscCtNotaProp = bkBuscadorPropiedades('f-nota-prop-buscar', 'f-nota-prop-sel', 'f-nota-prop-sug', 'No tienes inmuebles todavía');
document.addEventListener('click', (ev) => {
  if (_buscCtNotaProp.manejarClick(ev.target)) return;
  _buscCtNotaProp.cerrarSiClickAfuera(ev.target);
});
async function ctBuscarPropNotaInput() {
  const props = await cargarPropsMin();
  _buscCtNotaProp.onInput(props);
}
function ctBuscarPropNotaKeydown(ev) { _buscCtNotaProp.onKeydown(ev); }
function ctQuitarPropNota() {
  document.getElementById('f-nota-prop-buscar').value = '';
  document.getElementById('f-nota-prop-sel').value = '';
}

// Historial de edición/eliminación de notas — no usa restPost() porque esa
// función inyecta siempre user_id, y actividades_historial usa usuario_id;
// va directo por _sb().fetch() como restGet()/eliminarRemoto().
async function _bkInsertarHistorial(payload) {
  try {
    const r = await _sb().fetch('rest/v1/actividades_historial', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Prefer: 'return=minimal' },
      body: JSON.stringify(payload),
    });
    if (!r.ok && r.status !== 201 && r.status !== 204) throw new Error('Supabase: ' + r.status);
  } catch { /* si falla la auditoría, no debe tumbar la edición/eliminación en sí */ }
}

async function bkEditarNota(id) {
  let fila;
  try {
    const rows = await restGet('actividades?id=eq.' + encodeURIComponent(id) + '&select=*');
    fila = Array.isArray(rows) ? rows[0] : null;
  } catch {}
  if (!fila) { alert('No se pudo cargar la nota.'); return; }
  const nuevoTexto = prompt('Editar nota:', fila.texto || '');
  if (nuevoTexto === null) return;
  const limpio = nuevoTexto.trim();
  if (!limpio) { alert('La nota no puede quedar vacía. Para borrarla usa Eliminar.'); return; }
  if (limpio === (fila.texto || '').trim()) return;
  const uid = await _userId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  await _bkInsertarHistorial({
    actividad_id: fila.id, org_id: fila.org_id || cOrgId, accion: 'editar', usuario_id: uid,
    tipo: fila.tipo, texto_anterior: fila.texto, adjuntos_anterior: fila.adjuntos,
    contacto_id: fila.contacto_id, propiedad_id: fila.propiedad_id,
  });
  try {
    await restPatch('actividades', fila.id, { texto: limpio, editado_en: new Date().toISOString(), editado_por: uid });
    await cargarBitacora();
    showToast('Nota actualizada');
  } catch (e) {
    alert('No se pudo guardar la edición.\n\n' + (e.message || e));
  }
}

async function bkEliminarNota(id) {
  if (!confirm('¿Eliminar esta nota? No se puede deshacer.')) return;
  let fila;
  try {
    const rows = await restGet('actividades?id=eq.' + encodeURIComponent(id) + '&select=*');
    fila = Array.isArray(rows) ? rows[0] : null;
  } catch {}
  if (!fila) { alert('No se pudo cargar la nota.'); return; }
  const uid = await _userId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  await _bkInsertarHistorial({
    actividad_id: fila.id, org_id: fila.org_id || cOrgId, accion: 'eliminar', usuario_id: uid,
    tipo: fila.tipo, texto_anterior: fila.texto, adjuntos_anterior: fila.adjuntos,
    contacto_id: fila.contacto_id, propiedad_id: fila.propiedad_id,
  });
  try {
    await restDelete('actividades', fila.id);
    await cargarBitacora();
    showToast('Nota eliminada');
  } catch (e) {
    alert('No se pudo eliminar la nota.\n\n' + (e.message || e));
  }
}

function ctPintarCategoriasNota() {
  const chipsEl = document.getElementById('f-nota-cat-chips');
  const selectEl = document.getElementById('f-nota-cat-sel');
  if (!chipsEl || !selectEl) return;
  catPintarPicker({
    chipsEl, selectEl, catalogo: cCategorias, seleccionadas: CT_NOTA_CATS,
    onQuitar: id => { CT_NOTA_CATS = CT_NOTA_CATS.filter(x => x !== String(id)); ctPintarCategoriasNota(); },
    onAgregar: id => { if (!CT_NOTA_CATS.includes(String(id))) CT_NOTA_CATS.push(String(id)); ctPintarCategoriasNota(); },
  });
}

async function ctNuevaCategoriaNota() {
  const nombre = prompt('Nombre de la nueva categoría:');
  if (!nombre || !nombre.trim()) return;
  const uid = await _userId();
  if (!uid || !cOrgId) return;
  const cat = await catCrear(cOrgId, uid, nombre);
  if (!cat) { alert('No se pudo crear la categoría.'); return; }
  if (!cCategorias.some(c => String(c.id) === String(cat.id))) cCategorias.push(cat);
  if (!CT_NOTA_CATS.includes(String(cat.id))) CT_NOTA_CATS.push(String(cat.id));
  ctPintarCategoriasNota();
}

function ctAbrirNota() {
  document.getElementById('f-composer').hidden = false;
  document.getElementById('f-nota-texto').focus();
  CT_NOTA_CATS = [];
  ctPintarCategoriasNota();
  ctQuitarPropNota();
}

function ctCancelarNota() { ctDescartarBorrador(); }

async function ctGuardarNota() {
  if (!detContacto) return;
  const ta = document.getElementById('f-nota-texto');
  const btn = document.getElementById('f-nota-guardar');
  const texto = (ta.value || '').trim();
  if (haHaySubiendoPendiente('f-nota-preview')) { showToast('Espera a que terminen de subir los adjuntos'); return; }
  if (!texto && !haHayAdjuntosListos('f-nota-preview')) { ta.focus(); return; }
  const adjuntos = haTomarAdjuntosListos('f-nota-preview');
  const propAdjunta = document.getElementById('f-nota-prop-sel').value || null;
  btn.disabled = true;
  try {
    const rows = await restPost('actividades', {
      tipo: texto ? 'nota' : 'archivo', texto: texto, adjuntos: adjuntos, contacto_id: detContacto.id,
      propiedad_id: propAdjunta, org_id: cOrgId,
    });
    const nueva = Array.isArray(rows) ? rows[0] : rows;
    if (nueva && nueva.id) {
      for (const catId of CT_NOTA_CATS) await catVincular('actividades_categorias', 'actividad_id', nueva.id, catId);
    }
    ta.value = '';
    CT_NOTA_CATS = [];
    ctQuitarPropNota();
    document.getElementById('f-composer').hidden = true;
    await cargarBitacora();
    showToast(texto ? 'Nota guardada' : 'Archivos guardados');
  } catch (e) {
    alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  } finally {
    btn.disabled = false;
  }
}

// "Archivo, foto o video" sin escribir nota: se sube y se guarda solo.
async function ctArchivosSueltos(files) {
  if (!detContacto || !files || !files.length) return;
  const cid = detContacto.id;
  haAgregarArchivos(files, 'f-suelto-preview');
  showToast(files.length === 1 ? 'Subiendo el archivo…' : 'Subiendo ' + files.length + ' archivos…');
  while (haHaySubiendoPendiente('f-suelto-preview')) {
    await new Promise(r => setTimeout(r, 300));
  }
  if (!detContacto || detContacto.id !== cid) { haTomarAdjuntosListos('f-suelto-preview'); return; }
  const adjuntos = haTomarAdjuntosListos('f-suelto-preview');
  if (!adjuntos.length) { showToast('No se pudo subir ningún archivo'); return; }
  try {
    await restPost('actividades', { tipo: 'archivo', texto: '', adjuntos: adjuntos, contacto_id: cid, org_id: cOrgId });
    if (detContacto && detContacto.id === cid) await cargarBitacora();
    showToast(adjuntos.length === 1 ? 'Archivo guardado' : adjuntos.length + ' archivos guardados');
  } catch (e) {
    alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Propiedades vinculadas
   ══════════════════════════════════════════════════════════════════ */
const CT_REL = { interes: 'Interesado', propietario: 'Propietario', relacionado: 'Relacionado' };

async function cargarVinculos() {
  if (!detContacto) return;
  const feed = document.getElementById('props-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando…</div>';
  const cid = detContacto.id;

  const [props, vinculos] = await Promise.all([
    cargarPropsMin(),
    restGet('contactos_propiedades?select=*&contacto_id=eq.' + encodeURIComponent(cid) + '&order=created_at.desc').catch(() => []),
  ]);
  if (!detContacto || detContacto.id !== cid) return;

  const yaVinculadas = new Set(vinculos.map(v => String(v.propiedad_id)));
  _propsDisponibles = props.filter(p => !yaVinculadas.has(String(p.id)));
  const buscador = document.getElementById('vinculo-prop-buscar');
  buscador.value = '';
  document.getElementById('vinculo-prop').value = '';
  document.getElementById('vinculo-prop-sugerencias').hidden = true;
  buscador.disabled = !_propsDisponibles.length;
  buscador.placeholder = _propsDisponibles.length
    ? 'Busca por título, colonia o ciudad…'
    : (props.length ? 'Todas tus propiedades ya están vinculadas' : 'No tienes propiedades registradas');

  const porId = Object.fromEntries(props.map(p => [String(p.id), p]));
  feed.innerHTML = vinculos.length
    ? vinculos.map(v => {
        const p = porId[String(v.propiedad_id)] || {};
        return `<div class="bk-fila">
          <span class="bk-fila__ico"><svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10"/></svg></span>
          <a class="bk-fila__cuerpo" href="propiedades.html?id=${encodeURIComponent(String(v.propiedad_id))}">
            <span class="bk-fila__t">${esc(p.titulo || 'Propiedad')}</span>
            <span class="bk-fila__d">${esc(p.id ? propSubtitulo(p) : 'Abrir en Inmuebles')}</span>
          </a>
          <span class="bk-rel">${esc(CT_REL[v.relacion] || v.relacion)}</span>
          <button class="bk-quitar" title="Quitar vínculo" aria-label="Quitar vínculo" onclick="eliminarVinculo('${esc(String(v.id))}')">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>`;
      }).join('')
    : `<div class="bk-vacio"><h3>Sin propiedades vinculadas</h3><p>Liga los inmuebles que le interesan para tenerlos a la mano cuando te marque.</p></div>`;
  bkContador('f-n-props', vinculos.length);
}

async function agregarVinculo() {
  if (!detContacto) return;
  const propId = document.getElementById('vinculo-prop').value;
  const rel = document.getElementById('vinculo-rel').value;
  if (!propId) { showToast('Busca y elige una propiedad de la lista primero'); return; }
  try {
    await restPost('contactos_propiedades', { contacto_id: detContacto.id, propiedad_id: propId, relacion: rel });
    await cargarVinculos();
    showToast('Propiedad vinculada');
  } catch (e) {
    alert('No se pudo vincular.\n\n' + (e.message || e));
  }
}

async function eliminarVinculo(id) {
  try {
    await restDelete('contactos_propiedades', id);
    await cargarVinculos();
    showToast('Vínculo eliminado');
  } catch (e) {
    alert('No se pudo quitar el vínculo.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Tareas
   ══════════════════════════════════════════════════════════════════ */
let _tareasMin = null;
let _tareasVinculos = [];
let _tareas = [];

async function cargarTareasMin() {
  if (_tareasMin) return _tareasMin;
  try {
    _tareasMin = await restGet('tareas?select=id,titulo,fecha_entrega,completada&order=created_at.desc&limit=500');
  } catch { _tareasMin = []; }
  return _tareasMin;
}

async function cargarTareasVinculadas() {
  if (!detContacto) return;
  const feed = document.getElementById('tareas-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando…</div>';
  const cid = detContacto.id;
  let legacy = [], vinculos = [];
  try {
    [legacy, vinculos] = await Promise.all([
      restGet('tareas?select=*&contacto_id=eq.' + encodeURIComponent(cid) + '&order=created_at.desc'),
      restGet('tareas_contactos?select=*&contacto_id=eq.' + encodeURIComponent(cid) + '&order=created_at.desc').catch(() => []),
    ]);
  } catch { legacy = []; vinculos = []; }
  if (!detContacto || detContacto.id !== cid) return;

  _tareasVinculos = vinculos;
  const idsYaVistos = new Set(legacy.map(t => String(t.id)));
  const idsPorVinculo = vinculos.map(v => String(v.tarea_id)).filter(id => !idsYaVistos.has(id));
  let extra = [];
  if (idsPorVinculo.length) {
    try { extra = await restGet('tareas?select=*&id=in.(' + idsPorVinculo.join(',') + ')'); } catch { extra = []; }
  }
  _tareas = [...legacy, ...extra].sort((a, b) => {
    if (!!a.completada !== !!b.completada) return a.completada ? 1 : -1;
    return new Date(a.fecha_entrega || '9999-12-31') - new Date(b.fecha_entrega || '9999-12-31');
  });

  const yaLigadas = new Set(_tareas.map(t => String(t.id)));
  let todas = [];
  try { todas = await cargarTareasMin(); } catch { todas = []; }
  const disponibles = todas.filter(t => !yaLigadas.has(String(t.id)) && !t.completada);
  const sel = document.getElementById('vinculo-tarea');
  sel.innerHTML = '<option value="">Vincular una tarea que ya existe…</option>' +
    disponibles.map(t => `<option value="${esc(String(t.id))}">${esc(t.titulo)}</option>`).join('');
  sel.value = '';
  sel.closest('.bk-forma').hidden = !disponibles.length;

  renderTareas();
}

function renderTareas() {
  const feed = document.getElementById('tareas-feed');
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  feed.innerHTML = _tareas.length
    ? _tareas.map(t => {
        const due = t.fecha_entrega ? new Date(t.fecha_entrega) : null;
        const vencida = due && !t.completada && due < hoy;
        return `<div class="bk-fila${t.completada ? ' is-lista' : ''}">
          <button class="bk-tick${t.completada ? ' is-on' : ''}" onclick="toggleTarea('${esc(String(t.id))}')"
                  title="${t.completada ? 'Reabrir la tarea' : 'Marcar como completada'}"
                  aria-label="${t.completada ? 'Reabrir la tarea' : 'Marcar como completada'}">
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
          </button>
          <div class="bk-fila__cuerpo">
            <span class="bk-fila__t">${esc(t.titulo)}</span>
            ${due ? `<span class="bk-fila__d${vencida ? ' bk-fila__d--alerta' : ''}">${vencida ? 'Venció el ' : 'Para el '}${esc(fechaCorta(t.fecha_entrega))}</span>` : ''}
          </div>
          <button class="bk-quitar" title="Quitar de este contacto" aria-label="Quitar de este contacto" onclick="eliminarVinculoTarea('${esc(String(t.id))}')">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>`;
      }).join('')
    : `<div class="bk-vacio"><h3>Sin tareas pendientes</h3><p>Apunta el siguiente paso —llamarle, mandarle la ficha, agendar la visita— para que no se te pase.</p></div>`;
  bkContador('f-n-tareas', _tareas.filter(t => !t.completada).length);
}

async function crearTareaVinculada() {
  if (!detContacto) return;
  const inp = document.getElementById('tarea-nueva-titulo');
  const titulo = (inp.value || '').trim();
  if (!titulo) { inp.focus(); return; }
  const uid = await _userId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  const fecha = document.getElementById('tarea-nueva-fecha').value;
  const hora = document.getElementById('tarea-nueva-hora').value || '12:00';
  try {
    const creada = await restPost('tareas', {
      user_id: uid, org_id: cOrgId, titulo: titulo, contacto_id: detContacto.id,
      // OJO: nunca mandar "fecha+'T'+hora" pelón — la columna es timestamptz y
      // Postgres lo toma como si YA fuera UTC. new Date(...) interpreta el
      // texto en la hora LOCAL del navegador; toISOString() da el instante
      // UTC real (mismo arreglo que tareas.html).
      fecha_entrega: fecha ? new Date(fecha + 'T' + hora + ':00').toISOString() : null,
    });
    const nueva = Array.isArray(creada) ? creada[0] : creada;
    if (nueva && nueva.id) {
      await restPost('tareas_contactos', { user_id: uid, tarea_id: nueva.id, contacto_id: detContacto.id }).catch(() => {});
    }
    inp.value = '';
    document.getElementById('tarea-nueva-fecha').value = '';
    document.getElementById('tarea-nueva-hora').value = '';
    _tareasMin = null;
    await cargarTareasVinculadas();
    showToast('Tarea creada');
  } catch (e) {
    alert('No se pudo crear la tarea.\n\n' + (e.message || e));
  }
}

async function vincularTareaExistente(tareaId) {
  if (!detContacto || !tareaId) return;
  const uid = await _userId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  try {
    await restPost('tareas_contactos', { user_id: uid, tarea_id: tareaId, contacto_id: detContacto.id });
    await cargarTareasVinculadas();
    showToast('Tarea vinculada');
  } catch (e) {
    alert('No se pudo vincular.\n\n' + (e.message || e));
  }
}

async function toggleTarea(tid) {
  const t = _tareas.find(x => String(x.id) === tid); if (!t) return;
  const completar = !t.completada;
  t.completada = completar;
  t.fecha_completada = completar ? new Date().toISOString() : null;
  renderTareas();
  try {
    // Un PATCH que no toca ninguna fila (RLS, o la tarea ya no existe)
    // responde 200 con un arreglo vacío en vez de un error.
    const r = await _sb().fetch('rest/v1/tareas?id=eq.' + encodeURIComponent(tid), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Prefer: 'return=representation' },
      body: JSON.stringify({ completada: completar, fecha_completada: t.fecha_completada }),
    });
    const data = await r.json().catch(() => []);
    if (!r.ok || !Array.isArray(data) || data.length === 0) {
      throw new Error('No tienes permiso sobre esta tarea o ya no existe.');
    }
    if (completar && detContacto) {
      const cid = detContacto.id;
      restPost('actividades', { tipo: 'tarea_completada', texto: 'Tarea completada: ' + t.titulo, contacto_id: cid, org_id: cOrgId })
        .then(() => { if (detContacto && detContacto.id === cid && detTabActual === 'bitacora') cargarBitacora(); })
        .catch(() => {});
    }
    showToast(completar ? 'Tarea completada' : 'Tarea reabierta');
  } catch (e) {
    t.completada = !completar;
    t.fecha_completada = null;
    renderTareas();
    alert('No se pudo actualizar la tarea.\n\n' + (e.message || e));
  }
}

async function eliminarVinculoTarea(tid) {
  if (!detContacto) return;
  try {
    const vinculo = _tareasVinculos.find(v => String(v.tarea_id) === tid);
    if (vinculo) await restDelete('tareas_contactos', vinculo.id);
    const t = _tareas.find(x => String(x.id) === tid);
    if (t && String(t.contacto_id) === String(detContacto.id)) {
      await _sb().fetch('rest/v1/tareas?id=eq.' + encodeURIComponent(tid), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify({ contacto_id: null }),
      });
    }
    _tareasMin = null;
    await cargarTareasVinculadas();
    showToast('Vínculo eliminado');
  } catch (e) {
    alert('No se pudo quitar el vínculo.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Editar / eliminar
   ══════════════════════════════════════════════════════════════════ */
function editarDesdeDetalle() {
  if (!detContacto) return;
  const id = detContacto.id;
  cerrarDetalle();
  abrirModal(id);
}

async function eliminarDesdeDetalle() {
  if (!detContacto) return;
  const c = detContacto;
  if (!confirm(`¿Eliminar a ${c.nombre || 'este contacto'}?\n\nSe pierde su bitácora completa: notas, archivos y todo su historial. No se puede deshacer.`)) return;
  try {
    await eliminarRemoto(c.id);
    await cargarRemoto();
    cerrarDetalle();
    renderActual();
    showToast('Contacto eliminado');
  } catch (e) {
    alert('No se pudo eliminar el contacto.\n\n' + (e.message || e));
  }
}

document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape' || bkHayMenuAbierto()) return;
  if (document.getElementById('detail-ov').classList.contains('is-open')) cerrarDetalle();
});
