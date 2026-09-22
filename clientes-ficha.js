// Broquer · Clientes — la ficha del cliente.
//
// Vive fuera de clientes.html por dos razones: ese archivo ya rozaba el techo
// de bytes de scripts/architecture_debt.py, y la ficha es una superficie con
// vida propia (identidad, estado, bitácora, propiedades, tareas) que se lee
// mejor completa que intercalada con el tablero.
//
// Usa los globales que define clientes.html: _sb, _userId, restGet, restPost,
// restDelete, esc, showToast, fecha*, initials, avColor, rolBadge, domicilio,
// ETAPAS, etapaInfo, PROBS, patchContacto, renderActual, cargar, abrirModal,
// abrirWA, cargarRemoto, eliminarRemoto, cargarPropsMin, propSubtitulo,
// crearBuscadorPropiedades, detContacto, y las de historial-adjuntos.js.

/* ══════════════════════════════════════════════════════════════════
   Abrir / cerrar la ficha
   ══════════════════════════════════════════════════════════════════ */
function abrirDetalle(id) {
  const c = cargar().find(x => String(x.id) === String(id));
  if (!c) return;
  clDescartarBorrador();
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

  clRenderAsignacion(c);
  clRenderEstado(c);
  clRenderAcciones(c);
  clRenderResumen(c);

  document.getElementById('f-bitacora-feed').innerHTML = '';
  document.getElementById('props-feed').innerHTML = '';
  document.getElementById('tareas-feed').innerHTML = '';
  document.getElementById('bp-resultados-feed').innerHTML = '';
  ['bitacora', 'props', 'tareas', 'requerimiento'].forEach(t => {
    const n = document.getElementById('f-n-' + t);
    if (n) { n.textContent = ''; n.hidden = true; }
  });

  setDetTab('info');
  document.getElementById('detail-ov').classList.add('is-open');
  document.body.classList.add('bk-sin-scroll');
}

function cerrarDetalle() {
  bkCerrarMenu();
  clDescartarBorrador();
  document.getElementById('detail-ov').classList.remove('is-open');
  document.body.classList.remove('bk-sin-scroll');
  detContacto = null;
}

function clDescartarBorrador() {
  if (typeof haTomarAdjuntosListos === 'function') haTomarAdjuntosListos('f-nota-preview');
  const comp = document.getElementById('f-composer');
  if (comp) comp.hidden = true;
  const ta = document.getElementById('f-nota-texto');
  if (ta) ta.value = '';
  CL_NOTA_CATS = [];
  clQuitarPropNota();
}

/* Asignación de agente (solo cuentas Broquer para Empresas). */
function clRenderAsignacion(c) {
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
   Estado: etapa y probabilidad, cada una en un menú desplegable.
   Antes eran nueve pastillas siempre visibles (seis etapas + tres
   probabilidades) compitiendo con el nombre del cliente. Lo que
   importa de un vistazo es en qué etapa está, no la lista completa.
   ══════════════════════════════════════════════════════════════════ */
function clProbInfo(v) {
  const mapa = {
    alta:  { l: 'Alta',  color: 'var(--success)' },
    media: { l: 'Media', color: 'var(--warn)' },
    baja:  { l: 'Baja',  color: 'var(--mute-2)' },
  };
  return mapa[String(v || '').toLowerCase()] || null;
}

function clRenderEstado(c) {
  const etapa = etapaInfo(c.estatus);
  const tieneEtapa = !!String(c.estatus || '').trim();
  document.getElementById('f-etapa-btn').innerHTML =
    `<span class="bk-punto" style="background:${tieneEtapa ? etapa.color : 'var(--mute-3)'}"></span>
     <span class="bk-pill__txt">${tieneEtapa ? esc(etapa.nombre) : 'Sin etapa'}</span>${BK_CHEVRON}`;

  const prob = clProbInfo(c.probabilidad);
  document.getElementById('f-prob-btn').innerHTML =
    `<span class="bk-pill__lbl">Probabilidad</span>
     <span class="bk-pill__txt"${prob ? ` style="color:${prob.color}"` : ''}>${prob ? prob.l : 'Sin definir'}</span>${BK_CHEVRON}`;
}

function clMenuEtapa(btn) {
  if (!detContacto) return;
  const actual = String(detContacto.estatus || '').toLowerCase();
  const items = ETAPAS.map(e => ({ id: e.clave, etiqueta: e.nombre, color: e.color, activo: actual === e.clave }));
  if (actual) items.push({ id: '', etiqueta: 'Quitar etapa', separa: true });
  bkAbrirMenu(btn, items, (v) => setEtapa(v));
}

function clMenuProb(btn) {
  if (!detContacto) return;
  const actual = String(detContacto.probabilidad || '').toLowerCase();
  const items = PROBS.map(p => {
    const info = clProbInfo(p.v);
    return { id: p.v, etiqueta: p.l, color: info && info.color, activo: actual === p.v };
  });
  if (actual) items.push({ id: '', etiqueta: 'Sin definir', separa: true });
  bkAbrirMenu(btn, items, (v) => setProbabilidad(v));
}

function clMenuMas(btn) {
  if (!detContacto) return;
  bkAbrirMenu(btn, [
    { id: 'editar', etiqueta: 'Editar cliente' },
    { id: 'eliminar', etiqueta: 'Eliminar cliente', peligro: true, separa: true },
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
  clRenderEstado(detContacto);
  try {
    await patchContacto(detContacto.id, { estatus: v || null });
    renderActual();
    showToast(v ? 'Etapa: ' + etapaInfo(v).nombre : 'Etapa quitada');
    clRegistrarCambioEtapa(detContacto.id, prev, v);
  } catch (e) {
    detContacto.estatus = prev;
    clRenderEstado(detContacto);
    showToast('No se pudo guardar la etapa');
  }
}

async function setProbabilidad(v) {
  if (!detContacto) return;
  const prev = String(detContacto.probabilidad || '').toLowerCase();
  if (prev === v) return;
  detContacto.probabilidad = v;
  clRenderEstado(detContacto);
  try {
    await patchContacto(detContacto.id, { probabilidad: v || null });
    renderActual();
    const info = clProbInfo(v);
    showToast(info ? 'Probabilidad: ' + info.l : 'Probabilidad quitada');
  } catch (e) {
    detContacto.probabilidad = prev;
    clRenderEstado(detContacto);
    showToast('No se pudo guardar la probabilidad');
  }
}

// Deja constancia del cambio de etapa en la bitácora. Se llama tanto desde
// la ficha como desde el tablero (arrastrar una tarjeta a otra columna):
// si no, la bitácora contaba notas pero no el avance real del cliente.
function clRegistrarCambioEtapa(contactoId, previo, nuevo) {
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

/* Acciones de contacto: sin dato, el botón se deshabilita de verdad. */
function clRenderAcciones(c) {
  const wa = c.wa || c.telefono;
  const waBtn = document.getElementById('f-wa');
  const telBtn = document.getElementById('f-tel');
  const mailBtn = document.getElementById('f-mail');

  bkAccion(waBtn, !!wa, 'https://wa.me/52' + String(wa || '').replace(/\D/g, ''));
  if (wa) waBtn.onclick = (ev) => abrirWA(ev, wa);
  bkAccion(telBtn, !!c.telefono, 'tel:' + (c.telefono || ''));
  bkAccion(mailBtn, !!c.email, 'mailto:' + (c.email || ''));
}

function bkAccion(el, activo, href) {
  el.href = activo ? href : '#';
  el.setAttribute('aria-disabled', activo ? 'false' : 'true');
  el.tabIndex = activo ? 0 : -1;
  el.onclick = activo ? null : (ev) => { ev.preventDefault(); };
}

/* ══════════════════════════════════════════════════════════════════
   Pestañas
   ══════════════════════════════════════════════════════════════════ */
function setDetTab(tab) {
  detTabActual = tab;
  ['info', 'bitacora', 'props', 'tareas', 'requerimiento'].forEach(t => {
    document.getElementById('f-pane-' + t).hidden = t !== tab;
    const btn = document.getElementById('f-tab-' + t);
    btn.classList.toggle('is-on', t === tab);
    btn.setAttribute('aria-selected', t === tab ? 'true' : 'false');
  });
  if (!detContacto) return;
  if (tab === 'bitacora') cargarBitacora();
  if (tab === 'props') cargarVinculos();
  if (tab === 'tareas') cargarTareasVinculadas();
  if (tab === 'requerimiento') bpCargarRequerimiento();
}

/* ══════════════════════════════════════════════════════════════════
   Resumen — los datos duros del cliente
   ══════════════════════════════════════════════════════════════════ */
function clRenderResumen(c) {
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
    bkDato('En el pipeline desde', esc(fechaCorta(c.created_at))) +
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

  // Una ficha a medias se cobra sola el día que necesitas el correo para
  // mandar un contrato: si faltan datos de contacto, se dice cuáles.
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
   Bitácora — todo lo que le ha pasado a este cliente, con fecha y hora.
   Reúne las actividades del CRM (notas, archivos, cambios de etapa,
   tareas completadas), las operaciones históricas del contacto y su
   alta, en una sola línea de tiempo agrupada por día.
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
    id: a.id,
    tipo: a.tipo || 'nota',
    texto: a.texto || '',
    adjuntos: a.adjuntos,
    fecha: a.created_at,
    categorias: catsPorActividad[a.id],
    editado_en: a.editado_en,
  }));

  // Operaciones históricas del contacto: su fecha es texto libre, así que
  // solo se mezclan en la línea de tiempo las que sí se pueden fechar.
  const ops = Array.isArray(detContacto.operaciones) ? detContacto.operaciones : [];
  const opsSinFecha = [];
  ops.forEach(op => {
    const t = Date.parse(op.fecha);
    if (isFinite(t)) entradas.push({ tipo: 'operacion', texto: op.desc || '', fecha: new Date(t).toISOString() });
    else opsSinFecha.push(op);
  });

  if (detContacto.created_at) {
    entradas.push({ tipo: 'alta', texto: 'Se agregó a ' + (detContacto.nombre || 'el cliente') + ' al pipeline.', fecha: detContacto.created_at });
  }

  entradas.sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
  bkContador('f-n-bitacora', entradas.length + opsSinFecha.length);

  if (!entradas.length && !opsSinFecha.length) {
    feed.innerHTML = `<div class="bk-vacio">
      <h3>Todavía no hay nada anotado</h3>
      <p>Cada nota, archivo y cambio de etapa queda aquí con su fecha y hora, para que dentro de un año sepas exactamente qué pasó con este cliente.</p>
    </div>`;
    return;
  }

  let html = bkRenderBitacora(entradas, { alta: 'Alta del cliente', cambio_estatus: 'Cambio de etapa' });

  if (opsSinFecha.length) {
    html += '<div class="bk-bita__dia">Sin fecha registrada</div>' +
      opsSinFecha.map(op => bkItemBitacora({
        tipo: 'operacion', titulo: 'Operación', texto: op.desc || '', hora: op.fecha || '',
      })).join('');
  }
  feed.innerHTML = html;
}

/* ── Escribir en la bitácora ──────────────────────────────────────
   Dos caminos, ninguno de ellos un campo de texto permanente robando
   espacio al historial: "Nota" abre el editor, "Archivo" abre
   directamente el selector y guarda la entrada en cuanto suben. */
let CL_NOTA_CATS = []; // categorías elegidas para la nota que se está redactando

const _buscClNotaProp = bkBuscadorPropiedades('f-nota-prop-buscar', 'f-nota-prop-sel', 'f-nota-prop-sug', 'No tienes inmuebles todavía');
document.addEventListener('click', (ev) => {
  if (_buscClNotaProp.manejarClick(ev.target)) return;
  _buscClNotaProp.cerrarSiClickAfuera(ev.target);
});
async function clBuscarPropNotaInput() {
  const props = await cargarPropsMin();
  _buscClNotaProp.onInput(props);
}
function clBuscarPropNotaKeydown(ev) { _buscClNotaProp.onKeydown(ev); }
function clQuitarPropNota() {
  document.getElementById('f-nota-prop-buscar').value = '';
  document.getElementById('f-nota-prop-sel').value = '';
}

// Historial de edición/eliminación — va directo por _sb().fetch() porque
// restPost() inyecta siempre user_id, y actividades_historial usa
// usuario_id en su lugar.
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

function clPintarCategoriasNota() {
  const chipsEl = document.getElementById('f-nota-cat-chips');
  const selectEl = document.getElementById('f-nota-cat-sel');
  if (!chipsEl || !selectEl) return;
  catPintarPicker({
    chipsEl, selectEl, catalogo: cCategorias, seleccionadas: CL_NOTA_CATS,
    onQuitar: id => { CL_NOTA_CATS = CL_NOTA_CATS.filter(x => x !== String(id)); clPintarCategoriasNota(); },
    onAgregar: id => { if (!CL_NOTA_CATS.includes(String(id))) CL_NOTA_CATS.push(String(id)); clPintarCategoriasNota(); },
  });
}

async function clNuevaCategoriaNota() {
  const nombre = prompt('Nombre de la nueva categoría:');
  if (!nombre || !nombre.trim()) return;
  const uid = await _userId();
  if (!uid || !cOrgId) return;
  const cat = await catCrear(cOrgId, uid, nombre);
  if (!cat) { alert('No se pudo crear la categoría.'); return; }
  if (!cCategorias.some(c => String(c.id) === String(cat.id))) cCategorias.push(cat);
  if (!CL_NOTA_CATS.includes(String(cat.id))) CL_NOTA_CATS.push(String(cat.id));
  clPintarCategoriasNota();
}

function clAbrirNota() {
  const comp = document.getElementById('f-composer');
  comp.hidden = false;
  document.getElementById('f-nota-texto').focus();
  CL_NOTA_CATS = [];
  clPintarCategoriasNota();
  clQuitarPropNota();
}

function clCancelarNota() {
  clDescartarBorrador();
}

async function clGuardarNota() {
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
      tipo: texto ? 'nota' : 'archivo',
      texto: texto,
      adjuntos: adjuntos,
      contacto_id: detContacto.id,
      propiedad_id: propAdjunta,
      org_id: cOrgId,
    });
    const nueva = Array.isArray(rows) ? rows[0] : rows;
    if (nueva && nueva.id) {
      for (const catId of CL_NOTA_CATS) await catVincular('actividades_categorias', 'actividad_id', nueva.id, catId);
    }
    ta.value = '';
    CL_NOTA_CATS = [];
    clQuitarPropNota();
    document.getElementById('f-composer').hidden = true;
    await cargarBitacora();
    showToast(texto ? 'Nota guardada' : 'Archivos guardados');
  } catch (e) {
    alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  } finally {
    btn.disabled = false;
  }
}

// "Adjuntar archivo" sin escribir nota: se sube y se guarda solo.
async function clArchivosSueltos(files) {
  if (!detContacto || !files || !files.length) return;
  const feed = document.getElementById('f-bitacora-feed');
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
    if (feed) alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Propiedades vinculadas
   ══════════════════════════════════════════════════════════════════ */
const _buscadorPropDetalle = crearBuscadorPropiedades(
  'vinculo-prop-buscar', 'vinculo-prop', 'vinculo-prop-sugerencias',
  'No tienes propiedades disponibles para vincular');

let _propsDisponibles = [];
function buscarPropInput() { _buscadorPropDetalle.onInput(_propsDisponibles); }
function propBuscarKeydown(ev) { _buscadorPropDetalle.onKeydown(ev); }

document.addEventListener('click', (ev) => {
  if (_buscadorPropDetalle.manejarClick(ev.target)) return;
  _buscadorPropDetalle.cerrarSiClickAfuera(ev.target);
});

const CL_REL = { interes: 'Interesado', propietario: 'Propietario', relacionado: 'Relacionado' };

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
          <span class="bk-rel">${esc(CL_REL[v.relacion] || v.relacion)}</span>
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
  // Un desplegable deshabilitado que solo dice "no hay nada" es un renglón
  // muerto: si no hay tareas sueltas que vincular, no se muestra.
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
          <button class="bk-quitar" title="Quitar de este cliente" aria-label="Quitar de este cliente" onclick="quitarVinculoTarea('${esc(String(t.id))}')">
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
      // texto en la hora LOCAL del navegador, y toISOString() sí da el
      // instante UTC correcto.
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
    // responde 200 con un arreglo vacío en vez de un error — se verifica
    // aquí para no fingir éxito, igual que en propiedades.html.
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

async function quitarVinculoTarea(tid) {
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
  if (!confirm(`¿Eliminar a ${c.nombre || 'este cliente'}?\n\nSe pierde su bitácora completa: notas, archivos y todo su historial. No se puede deshacer.`)) return;
  try {
    await eliminarRemoto(c.id);
    await cargarRemoto();
    cerrarDetalle();
    renderActual();
    showToast('Cliente eliminado');
  } catch (e) {
    alert('No se pudo eliminar el cliente.\n\n' + (e.message || e));
  }
}

document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape' || bkHayMenuAbierto()) return;
  if (document.getElementById('detail-ov').classList.contains('is-open')) cerrarDetalle();
});

/* ══════════════════════════════════════════════════════════════════
   Requerimiento — lo que busca el cliente, más los enlaces que el
   Buscador de propiedades encuentra por él una vez al día.
   ══════════════════════════════════════════════════════════════════ */
async function _bpApi(path, opts) {
  opts = opts || {};
  const sb = window.brokrSb;
  if (!sb || !sb.ensureToken) throw new Error('La app aún se está cargando. Intenta en un segundo.');
  let tok = await sb.ensureToken();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (tok) headers.Authorization = 'Bearer ' + tok;
  const API = window.API_BASE || 'https://api.broquer.app';
  let r = await fetch(API + path, { method: opts.method || 'GET', headers, body: opts.body });
  if (r.status === 401 && sb.refreshNow) {
    tok = await sb.refreshNow();
    if (tok) {
      headers.Authorization = 'Bearer ' + tok;
      r = await fetch(API + path, { method: opts.method || 'GET', headers, body: opts.body });
    }
  }
  const txt = await r.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = null; }
  if (!r.ok) throw new Error((data && data.detail) || ('HTTP ' + r.status));
  return data;
}

function bpFechaHora(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return fechaCorta(iso) + ', ' + d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

function bpRenderResultados(resultados, ultimaBusqueda) {
  const feed = document.getElementById('bp-resultados-feed');
  const titulo = document.getElementById('bp-resultados-titulo');
  titulo.textContent = ultimaBusqueda
    ? 'Enlaces encontrados · última lectura ' + bpFechaHora(ultimaBusqueda)
    : 'Enlaces encontrados';
  feed.innerHTML = (resultados || []).length
    ? resultados.map(r => {
        const precioTxt = r.precio
          ? ' · $' + Number(r.precio).toLocaleString('es-MX') + (r.precio_confirmado ? '' : ' (sin confirmar)')
          : '';
        return `<div class="bk-fila">
          <span class="bk-fila__ico"><svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path stroke-linecap="round" d="M21 21l-4.35-4.35"/></svg></span>
          <a class="bk-fila__cuerpo" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">
            <span class="bk-fila__t">${esc(r.titulo || r.portal || 'Ver anuncio')}</span>
            <span class="bk-fila__d">${esc(r.portal || '')}${precioTxt}</span>
          </a>
        </div>`;
      }).join('')
    : `<div class="bk-vacio"><h3>Todavía no hay enlaces</h3><p>Guarda el requerimiento o presiona "Buscar ahora" para la primera lectura.</p></div>`;
  bkContador('f-n-requerimiento', (resultados || []).length);
}

async function bpCargarRequerimiento() {
  if (!detContacto) return;
  const feed = document.getElementById('bp-resultados-feed');
  feed.innerHTML = '<div class="bk-cargando"></div>';
  try {
    const [req, datos] = await Promise.all([
      _bpApi('/api/buscador/requerimiento/' + encodeURIComponent(detContacto.id)),
      _bpApi('/api/buscador/resultados/' + encodeURIComponent(detContacto.id)),
    ]);
    sv('bp-operacion', req.operacion || 'venta');
    sv('bp-tipo', req.tipo_inmueble || 'casa');
    sv('bp-colonia', req.colonia || '');
    sv('bp-ciudad', req.ciudad || '');
    sv('bp-estado', req.estado || '');
    sv('bp-precio-min', req.precio_min || '');
    sv('bp-precio-max', req.precio_max || '');
    sv('bp-recamaras', req.recamaras_min || '');
    sv('bp-notas', req.notas || '');
    document.getElementById('bp-activo').checked = req.activo !== false;
    bpRenderResultados(datos.resultados, (datos.requerimiento || {}).ultima_busqueda_en);
  } catch (e) {
    feed.innerHTML = `<div class="bk-vacio"><h3>No se pudo cargar</h3><p>${esc(e.message || '')}</p></div>`;
  }
}

async function bpGuardarRequerimiento() {
  if (!detContacto) return;
  const btn = document.getElementById('bp-guardar');
  btn.disabled = true;
  btn.textContent = 'Guardando…';
  try {
    const body = {
      activo: document.getElementById('bp-activo').checked,
      operacion: gv('bp-operacion') || 'venta',
      tipo_inmueble: gv('bp-tipo') || 'casa',
      colonia: gv('bp-colonia'),
      ciudad: gv('bp-ciudad'),
      estado: gv('bp-estado'),
      precio_min: Number(gv('bp-precio-min')) || 0,
      precio_max: Number(gv('bp-precio-max')) || 0,
      recamaras_min: Number(gv('bp-recamaras')) || 0,
      notas: gv('bp-notas'),
    };
    await _bpApi('/api/buscador/requerimiento/' + encodeURIComponent(detContacto.id), {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    showToast('Requerimiento guardado');
    if (body.activo && body.colonia) {
      await bpBuscarAhora();
    }
  } catch (e) {
    showToast(e.message || 'No se pudo guardar el requerimiento');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Guardar requerimiento';
  }
}

async function bpBuscarAhora() {
  if (!detContacto) return;
  const btn = document.getElementById('bp-buscar-ahora');
  const feed = document.getElementById('bp-resultados-feed');
  btn.disabled = true;
  btn.textContent = 'Buscando…';
  feed.innerHTML = '<div class="bk-cargando"></div>';
  try {
    await _bpApi('/api/buscador/escanear/' + encodeURIComponent(detContacto.id), { method: 'POST' });
    const datos = await _bpApi('/api/buscador/resultados/' + encodeURIComponent(detContacto.id));
    bpRenderResultados(datos.resultados, (datos.requerimiento || {}).ultima_busqueda_en);
  } catch (e) {
    feed.innerHTML = `<div class="bk-vacio"><h3>No se pudo buscar</h3><p>${esc(e.message || '')}</p></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Buscar ahora';
  }
}
