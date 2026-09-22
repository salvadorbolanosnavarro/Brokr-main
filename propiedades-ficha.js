// Broquer · Inmuebles — la ficha del inmueble.
//
// Misma superficie que las de Clientes y Directorio (ficha-comun.js y el
// bloque FICHA de brokr-theme.css), con lo propio de un inmueble: fotos,
// precio, y un estatus que no es una etapa de pipeline sino el estado
// comercial de la propiedad.
//
// Usa los globales de propiedades.html: g, esc, sbFetch, restGet, restPost,
// getCurrentUserId, getValidToken, mostrarToast, fmtPrecio, fechaCorta,
// allProps, currentDetailId, loadProps, openPropForm, openLightbox,
// duplicarProp, archivarDesdeDetalle, deleteProp, crearFichaDesde,
// pEsEmpresa, pMiembros, pEsAdminOrg, pNombreAgente, pAsignarAgente.

let pdTabActual = 'detalles';

// propiedades.html no trae un formateador de fecha corta (el suyo vivía en
// el detalle viejo), así que la ficha trae el suyo.
function fechaCorta(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return ''; }
}

const PF_ESTATUS = [
  { v: 'activa',     l: 'Activa',          color: 'var(--success)' },
  { v: 'reservada',  l: 'Reservada',       color: 'var(--info)' },
  { v: 'en_proceso', l: 'En proceso',      color: 'var(--warn)' },
  { v: 'vendida',    l: 'Vendida',         color: 'var(--forest)' },
  { v: 'rentada',    l: 'Rentada',         color: 'var(--info)' },
  { v: 'suspendida', l: 'Suspendida',      color: 'var(--warn)' },
  { v: 'no_activa',  l: 'No activo',       color: 'var(--mute-2)', nota: 'Por revisar' },
  { v: 'ajena',      l: 'Ajena',           color: 'var(--wa-ia)',  nota: 'De otro colega' },
];
function pfEstatusInfo(v) {
  return PF_ESTATUS.find(e => e.v === String(v || 'activa')) || PF_ESTATUS[0];
}

/* ══════════════════════════════════════════════════════════════════
   Abrir / cerrar
   ══════════════════════════════════════════════════════════════════ */
function openPropDetail(id) {
  clearTimeout(_filtT);
  id = String(id || '');
  const p = allProps.find(x => String(x.id) === id);
  if (!p) return;
  pfDescartarBorrador();
  currentDetailId = id;

  const fotos = Array.isArray(p.fotos) ? p.fotos.filter(Boolean) : [];
  const av = g('f-av');
  av.className = 'bk-ficha__av bk-ficha__av--foto';
  av.innerHTML = fotos.length
    ? `<img src="${esc(fotos[0])}" alt="" loading="lazy" decoding="async"/>`
    : '<svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10"/></svg>';
  av.style.background = fotos.length ? 'var(--paper-2)' : 'var(--sky-navy)';

  g('f-nombre').textContent = p.titulo || 'Sin título';
  const clave = p.clave_interna || (p.eb_public_id ? 'EB · ' + p.eb_public_id : '');
  const claveEl = g('f-clave');
  claveEl.textContent = clave;
  claveEl.hidden = !clave;
  const ubic = [p.colonia, p.ciudad].filter(Boolean).join(', ');
  const metaEl = g('f-meta');
  metaEl.textContent = ubic;
  metaEl.hidden = !ubic;

  pfRenderAsignacion(p);
  pfRenderEstado(p);
  pfRenderDetalles(p, fotos);

  g('f-bitacora-feed').innerHTML = '';
  g('pd-int-feed').innerHTML = '';
  g('pd-tareas-feed').innerHTML = '';
  ['bitacora', 'int', 'tareas'].forEach(t => {
    const n = g('f-n-' + t);
    if (n) { n.textContent = ''; n.hidden = true; }
  });

  pdSetTab('detalles');
  g('prop-detail-modal').classList.add('is-open');
  document.body.classList.add('bk-sin-scroll');
}

function closePropDetail() {
  bkCerrarMenu();
  pfDescartarBorrador();
  g('prop-detail-modal').classList.remove('is-open');
  document.body.classList.remove('bk-sin-scroll');
  currentDetailId = null;
}

function pfDescartarBorrador() {
  if (typeof haTomarAdjuntosListos === 'function') haTomarAdjuntosListos('f-nota-preview');
  const comp = g('f-composer');
  if (comp) comp.hidden = true;
  const ta = g('f-nota-texto');
  if (ta) ta.value = '';
  PD_NOTA_CATS = [];
}

function pfRenderAsignacion(p) {
  const wrap = g('f-asignado');
  if (!pEsEmpresa || !pMiembros.length) { wrap.hidden = true; return; }
  wrap.hidden = false;
  const sel = g('f-asignado-sel');
  const txt = g('f-asignado-txt');
  if (pEsAdminOrg) {
    sel.hidden = false; txt.hidden = true;
    sel.innerHTML = '<option value="">Sin asignar</option>' +
      pMiembros.map(m => `<option value="${esc(m.user_id)}">${esc(m.nombre || m.email || 'Agente')}</option>`).join('');
    sel.value = p.asignado_a || '';
  } else {
    sel.hidden = true; txt.hidden = false;
    txt.textContent = p.asignado_a ? pNombreAgente(p.asignado_a) : 'Sin asignar';
  }
}

/* ══════════════════════════════════════════════════════════════════
   Estado: estatus comercial y operación
   ══════════════════════════════════════════════════════════════════ */
function pfRenderEstado(p) {
  const est = pfEstatusInfo(p.estatus);
  g('f-estatus-btn').innerHTML =
    `<span class="bk-punto" style="background:${est.color}"></span>
     <span class="bk-pill__txt">${esc(est.l)}</span>${BK_CHEVRON}`;

  const op = p.operacion === 'renta' ? 'En renta' : (p.operacion === 'venta' ? 'En venta' : 'Sin operación');
  g('f-operacion').innerHTML =
    `<span class="bk-pill__lbl">${esc(op)}</span>
     <span class="bk-pill__txt bk-num">${esc(fmtPrecio(p.precio))} ${esc(p.moneda || 'MXN')}</span>`;

  const arch = g('f-archivada');
  arch.hidden = !p.archivada;
}

function pfMenuEstatus(btn) {
  const p = allProps.find(x => String(x.id) === String(currentDetailId));
  if (!p) return;
  const actual = String(p.estatus || 'activa');
  bkAbrirMenu(btn, PF_ESTATUS.map(e => ({
    id: e.v, etiqueta: e.l, nota: e.nota, color: e.color, activo: actual === e.v,
  })), (v) => pdCambiarEstatus(v));
}

function pfMenuMas(btn) {
  const p = allProps.find(x => String(x.id) === String(currentDetailId));
  if (!p) return;
  bkAbrirMenu(btn, [
    { id: 'editar', etiqueta: 'Editar inmueble' },
    { id: 'ficha', etiqueta: 'Generar ficha técnica' },
    { id: 'duplicar', etiqueta: 'Duplicar', separa: true },
    { id: 'archivar', etiqueta: p.archivada ? 'Restaurar del archivo' : 'Archivar' },
    { id: 'eliminar', etiqueta: 'Eliminar inmueble', peligro: true, separa: true },
  ], (v) => {
    const id = currentDetailId;
    if (v === 'editar') { closePropDetail(); openPropForm(id); }
    if (v === 'ficha') crearFichaDesde(id);
    if (v === 'duplicar') duplicarProp();
    if (v === 'archivar') archivarDesdeDetalle();
    if (v === 'eliminar') { closePropDetail(); deleteProp(id); }
  });
}

/* ══════════════════════════════════════════════════════════════════
   Pestaña Detalles
   ══════════════════════════════════════════════════════════════════ */
function pfRenderDetalles(p, fotos) {
  // Una sola tira de fotos: antes el mosaico grande y la tira de
  // miniaturas mostraban las mismas imágenes dos veces seguidas.
  let galeria = '';
  if (fotos.length) {
    const json = encodeURIComponent(JSON.stringify(fotos));
    galeria = `<div class="pf-galeria">
      <button type="button" class="pf-galeria__grande" onclick="openLightbox('${json}', 0)" aria-label="Ver las fotos">
        <img src="${esc(fotos[0])}" loading="lazy" decoding="async" alt=""/>
        ${fotos.length > 1 ? `<span class="pf-galeria__n">${fotos.length} fotos</span>` : ''}
      </button>
      ${fotos.length > 1 ? `<div class="pf-galeria__tira">${fotos.slice(1).map((f, i) =>
        `<button type="button" onclick="openLightbox('${json}', ${i + 1})" aria-label="Ver foto ${i + 2}">
          <img src="${esc(f)}" loading="lazy" decoding="async" alt=""/>
        </button>`).join('')}</div>` : ''}
    </div>`;
  }

  const calleNum = [p.calle, p.num_exterior].filter(Boolean).join(' ');
  const calleFull = p.num_interior ? `${calleNum} Int. ${p.num_interior}` : calleNum;
  const ubicLine = [calleFull, p.colonia, p.ciudad, p.estado, p.cp].filter(Boolean).join(' · ');

  // Sólo se listan los datos que existen: una ficha llena de guiones no
  // informa, sólo hace más larga la lectura.
  const m2 = (v) => v ? v + ' m²' : '';
  const datos = [
    ['Tipo', p.tipo ? esc(p.tipo.charAt(0).toUpperCase() + p.tipo.slice(1)) : ''],
    ['Construcción', m2(p.m2_construccion)],
    ['Terreno', m2(p.m2_terreno)],
    ['Superficie no cubierta', m2(p.m2_superficie_no_cubierta)],
    ['Recámaras', p.recamaras || ''],
    ['Baños', p.banos || ''],
    ['Medios baños', p.medio_bano || ''],
    ['Estacionamientos', p.estacionamientos || ''],
    ['Nivel', p.nivel || ''],
    ['Mantenimiento', p.mantenimiento ? esc(fmtPrecio(p.mantenimiento)) : ''],
    ['Año de construcción', p.anio_construccion || ''],
    ['Comisión', p.operacion === 'renta'
      ? (p.comision_renta_meses != null ? p.comision_renta_meses + ' mes(es)' : '')
      : (p.comision_venta_pct != null ? p.comision_venta_pct + '%' : '')],
    ['Exclusiva', p.exclusiva === 'si' ? 'Sí' : (p.exclusiva === 'no' ? 'No' : '')],
    ['Comparte comisión', p.comision_compartida === true ? 'Sí' : (p.comision_compartida === false ? 'No' : '')],
    ['Clave interna', esc(p.clave_interna || '')],
    ['Código de llave', esc(p.codigo_llave || '')],
    ['Agregado', esc(fechaCorta(p.created_at))],
  ];
  const datosHTML = datos.map(([l, v]) => bkDato(l, v)).join('');

  let html = galeria;
  if (ubicLine) html += `<p class="pf-ubic">${esc(ubicLine)}</p>`;
  if (p.descripcion) html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Descripción</h3><p class="bk-prosa">${esc(p.descripcion)}</p></div>`;
  if (datosHTML) html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Datos del inmueble</h3><div class="bk-datos">${datosHTML}</div></div>`;

  if (Array.isArray(p.amenidades) && p.amenidades.length) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Amenidades</h3>
      <div class="bk-tags">${p.amenidades.map(a => `<span class="pd-tag">${esc(a)}</span>`).join('')}</div></div>`;
  }
  if (Array.isArray(p.etiquetas) && p.etiquetas.length) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Etiquetas</h3>
      <div class="bk-tags">${p.etiquetas.map(t => `<span class="pd-tag">${esc(t)}</span>`).join('')}</div></div>`;
  }
  if (p.condiciones_compartir) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Condiciones para compartir</h3>
      <p class="bk-prosa bk-prosa--broq">${esc(p.condiciones_compartir)}</p></div>`;
  }
  if (p.notas) {
    html += `<div class="bk-bloque"><h3 class="bk-bloque__t">Notas internas · sólo las ves tú</h3>
      <p class="bk-prosa">${esc(p.notas)}</p></div>`;
  }
  g('f-pane-detalles').innerHTML = html;
}

/* ══════════════════════════════════════════════════════════════════
   Pestañas
   ══════════════════════════════════════════════════════════════════ */
function pdSetTab(tab) {
  pdTabActual = tab;
  ['detalles', 'bitacora', 'int', 'tareas'].forEach(t => {
    g('f-pane-' + t).hidden = t !== tab;
    const btn = g('f-tab-' + t);
    btn.classList.toggle('is-active', t === tab);
    btn.setAttribute('aria-selected', t === tab ? 'true' : 'false');
  });
  if (!currentDetailId) return;
  if (tab === 'bitacora') pdCargarBitacora();
  if (tab === 'int') pdCargarInteresados();
  if (tab === 'tareas') pdCargarTareas();
}

/* ══════════════════════════════════════════════════════════════════
   Bitácora
   ══════════════════════════════════════════════════════════════════ */
async function pdCargarBitacora() {
  const pid = currentDetailId; if (!pid) return;
  const feed = g('f-bitacora-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando la bitácora…</div>';
  let acts = [];
  try {
    acts = await sbFetch('actividades?select=*&propiedad_id=eq.' + encodeURIComponent(pid) + '&order=created_at.desc&limit=200');
  } catch { acts = []; }
  if (currentDetailId !== pid) return;

  let catsPorActividad = {};
  if (acts.length) {
    try {
      const ids = acts.map(a => '"' + a.id + '"').join(',');
      const links = await sbFetch('actividades_categorias?select=actividad_id,categoria_id&actividad_id=in.(' + ids + ')');
      (Array.isArray(links) ? links : []).forEach(l => {
        const cat = pCategorias.find(c => String(c.id) === String(l.categoria_id));
        if (cat) (catsPorActividad[l.actividad_id] = catsPorActividad[l.actividad_id] || []).push(cat.nombre);
      });
    } catch {}
  }

  const entradas = acts.map(a => ({
    tipo: a.tipo || 'nota', texto: a.texto || '', adjuntos: a.adjuntos, fecha: a.created_at,
    categorias: catsPorActividad[a.id],
  }));
  const p = allProps.find(x => String(x.id) === String(pid));
  if (p && p.created_at) {
    entradas.push({ tipo: 'alta', texto: 'Se dio de alta el inmueble.', fecha: p.created_at });
  }

  bkContador('f-n-bitacora', entradas.length);
  if (!entradas.length) {
    feed.innerHTML = `<div class="bk-vacio">
      <h3>Todavía no hay nada anotado</h3>
      <p>Cada nota, archivo y cambio de estatus queda aquí con su fecha y hora: qué se arregló, qué pidió el dueño, cuándo bajó de precio.</p>
    </div>`;
    return;
  }
  feed.innerHTML = bkRenderBitacora(entradas, { alta: 'Alta del inmueble' });
}

let PD_NOTA_CATS = []; // categorías elegidas para la nota que se está redactando

function pdPintarCategoriasNota() {
  const chipsEl = g('f-nota-cat-chips');
  const selectEl = g('f-nota-cat-sel');
  if (!chipsEl || !selectEl) return;
  catPintarPicker({
    chipsEl, selectEl, catalogo: pCategorias, seleccionadas: PD_NOTA_CATS,
    onQuitar: id => { PD_NOTA_CATS = PD_NOTA_CATS.filter(x => x !== String(id)); pdPintarCategoriasNota(); },
    onAgregar: id => { if (!PD_NOTA_CATS.includes(String(id))) PD_NOTA_CATS.push(String(id)); pdPintarCategoriasNota(); },
  });
}

async function pdNuevaCategoriaNota() {
  const nombre = prompt('Nombre de la nueva categoría:');
  if (!nombre || !nombre.trim()) return;
  const uid = getCurrentUserId();
  if (!uid || !pOrgId) return;
  const cat = await catCrear(pOrgId, uid, nombre);
  if (!cat) { alert('No se pudo crear la categoría.'); return; }
  if (!pCategorias.some(c => String(c.id) === String(cat.id))) pCategorias.push(cat);
  if (!PD_NOTA_CATS.includes(String(cat.id))) PD_NOTA_CATS.push(String(cat.id));
  pdPintarCategoriasNota();
}

function pdAbrirNota() {
  g('f-composer').hidden = false;
  g('f-nota-texto').focus();
  PD_NOTA_CATS = [];
  pdPintarCategoriasNota();
}
function pdCancelarNota() { pfDescartarBorrador(); }

async function pdGuardarNota() {
  const pid = currentDetailId; if (!pid) return;
  const ta = g('f-nota-texto');
  const btn = g('f-nota-guardar');
  const texto = (ta.value || '').trim();
  if (haHaySubiendoPendiente('f-nota-preview')) { mostrarToast('Espera a que terminen de subir los adjuntos'); return; }
  if (!texto && !haHayAdjuntosListos('f-nota-preview')) { ta.focus(); return; }
  const uid = getCurrentUserId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  const adjuntos = haTomarAdjuntosListos('f-nota-preview');
  btn.disabled = true;
  try {
    const rows = await sbFetch('actividades', 'POST', {
      user_id: uid, tipo: texto ? 'nota' : 'archivo', texto: texto,
      adjuntos: adjuntos, propiedad_id: pid,
    });
    const nueva = Array.isArray(rows) ? rows[0] : rows;
    if (nueva && nueva.id) {
      for (const catId of PD_NOTA_CATS) await catVincular('actividades_categorias', 'actividad_id', nueva.id, catId);
    }
    ta.value = '';
    PD_NOTA_CATS = [];
    g('f-composer').hidden = true;
    await pdCargarBitacora();
    mostrarToast(texto ? 'Nota guardada' : 'Archivos guardados');
  } catch (e) {
    alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  } finally {
    btn.disabled = false;
  }
}

async function pdArchivosSueltos(files) {
  const pid = currentDetailId;
  if (!pid || !files || !files.length) return;
  const uid = getCurrentUserId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  haAgregarArchivos(files, 'f-suelto-preview');
  mostrarToast(files.length === 1 ? 'Subiendo el archivo…' : 'Subiendo ' + files.length + ' archivos…');
  while (haHaySubiendoPendiente('f-suelto-preview')) {
    await new Promise(r => setTimeout(r, 300));
  }
  if (currentDetailId !== pid) { haTomarAdjuntosListos('f-suelto-preview'); return; }
  const adjuntos = haTomarAdjuntosListos('f-suelto-preview');
  if (!adjuntos.length) { mostrarToast('No se pudo subir ningún archivo'); return; }
  try {
    await sbFetch('actividades', 'POST', { user_id: uid, tipo: 'archivo', texto: '', adjuntos: adjuntos, propiedad_id: pid });
    if (currentDetailId === pid) await pdCargarBitacora();
    mostrarToast(adjuntos.length === 1 ? 'Archivo guardado' : adjuntos.length + ' archivos guardados');
  } catch (e) {
    alert('No se pudo guardar en la bitácora.\n\n' + (e.message || e));
  }
}

/* Cambio de estatus: queda anotado en la bitácora. */
async function pdCambiarEstatus(v) {
  const pid = currentDetailId; if (!pid) return;
  const p = allProps.find(x => String(x.id) === String(pid)); if (!p) return;
  const previo = String(p.estatus || 'activa');
  if (previo === v) return;
  p.estatus = v;
  pfRenderEstado(p);
  try {
    const filas = await sbFetch('propiedades?id=eq.' + encodeURIComponent(pid), 'PATCH', { estatus: v });
    if (!Array.isArray(filas) || filas.length === 0) throw new Error('No tienes permiso sobre este inmueble o ya no existe.');
    mostrarToast('Estatus: ' + pfEstatusInfo(v).l);
    const uid = getCurrentUserId();
    if (uid) {
      sbFetch('actividades', 'POST', {
        user_id: uid, tipo: 'cambio_estatus', propiedad_id: pid,
        texto: 'Estatus: ' + pfEstatusInfo(previo).l + ' → ' + pfEstatusInfo(v).l,
      }).then(() => { if (currentDetailId === pid && pdTabActual === 'bitacora') pdCargarBitacora(); }).catch(() => {});
    }
    await loadProps();
  } catch (e) {
    p.estatus = previo;
    pfRenderEstado(p);
    alert('No se pudo cambiar el estatus.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Contactos ligados al inmueble
   ══════════════════════════════════════════════════════════════════ */
const PF_REL = { interes: 'Interesado', propietario: 'Propietario', relacionado: 'Relacionado' };
let _pdContactosMin = null;

async function pdCargarContactosMin() {
  if (_pdContactosMin) return _pdContactosMin;
  try { _pdContactosMin = await sbFetch('contactos?select=id,nombre,telefono,wa&order=updated_at.desc&limit=500'); }
  catch { _pdContactosMin = []; }
  return _pdContactosMin;
}

async function pdCargarInteresados() {
  const pid = currentDetailId; if (!pid) return;
  const feed = g('pd-int-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando…</div>';
  let contactos = [], vinculos = [];
  try {
    [contactos, vinculos] = await Promise.all([
      pdCargarContactosMin(),
      sbFetch('contactos_propiedades?select=*&propiedad_id=eq.' + encodeURIComponent(pid) + '&order=created_at.desc'),
    ]);
  } catch { contactos = []; vinculos = []; }
  if (currentDetailId !== pid) return;

  const yaLigados = new Set(vinculos.map(v => String(v.contacto_id)));
  const disponibles = contactos.filter(c => !yaLigados.has(String(c.id)));
  // Sin nadie a quién ligar, la barra entera sobra: un desplegable
  // deshabilitado que sólo dice "no hay" es un renglón muerto.
  const sel = g('pd-int-contacto');
  sel.innerHTML = '<option value="">Elige a quién ligar…</option>' +
    disponibles.map(c => `<option value="${esc(String(c.id))}">${esc(c.nombre)}</option>`).join('');
  sel.value = '';
  sel.closest('.bk-forma').hidden = !disponibles.length;

  const porId = Object.fromEntries(contactos.map(c => [String(c.id), c]));
  feed.innerHTML = vinculos.length
    ? vinculos.map(v => {
        const c = porId[String(v.contacto_id)] || {};
        return `<div class="bk-fila">
          <span class="bk-fila__ico">${esc(pdIniciales(c.nombre || '?'))}</span>
          <a class="bk-fila__cuerpo" href="contactos.html?id=${encodeURIComponent(String(v.contacto_id))}">
            <span class="bk-fila__t">${esc(c.nombre || 'Contacto')}</span>
            <span class="bk-fila__d">${esc(c.telefono || c.wa || 'Abrir en Directorio')}</span>
          </a>
          <span class="bk-rel">${esc(PF_REL[v.relacion] || v.relacion)}</span>
          <button class="bk-quitar" title="Quitar vínculo" aria-label="Quitar vínculo" onclick="pdQuitarContacto('${esc(String(v.id))}')">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>`;
      }).join('')
    : `<div class="bk-vacio"><h3>Nadie ligado todavía</h3><p>Liga a los interesados y al propietario para saber, sin buscar, a quién le toca esta casa.</p></div>`;
  bkContador('f-n-int', vinculos.length);
}

function pdIniciales(nombre) {
  const p = String(nombre).trim().split(/\s+/);
  return (p.length >= 2 ? p[0][0] + p[1][0] : String(nombre).slice(0, 2)).toUpperCase();
}

async function pdVincularContacto() {
  const pid = currentDetailId; if (!pid) return;
  const cid = g('pd-int-contacto').value;
  const rel = g('pd-int-rel').value;
  if (!cid) { mostrarToast('Elige un contacto de la lista'); return; }
  const uid = getCurrentUserId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  try {
    await sbFetch('contactos_propiedades', 'POST', { user_id: uid, contacto_id: cid, propiedad_id: pid, relacion: rel });
    await pdCargarInteresados();
    mostrarToast('Contacto ligado');
  } catch (e) {
    alert('No se pudo ligar.\n\n' + (e.message || e));
  }
}

async function pdQuitarContacto(vinculoId) {
  try {
    await sbFetch('contactos_propiedades?id=eq.' + encodeURIComponent(vinculoId), 'DELETE');
    await pdCargarInteresados();
    mostrarToast('Vínculo eliminado');
  } catch (e) {
    alert('No se pudo quitar el vínculo.\n\n' + (e.message || e));
  }
}

/* ══════════════════════════════════════════════════════════════════
   Tareas del inmueble
   ══════════════════════════════════════════════════════════════════ */
let _pdTareas = [];
let _pdTareasVinculos = [];
let _pdTareasMin = null;

async function pdCargarTareasMin() {
  if (_pdTareasMin) return _pdTareasMin;
  try { _pdTareasMin = await sbFetch('tareas?select=id,titulo,fecha_entrega,completada&order=created_at.desc&limit=500'); }
  catch { _pdTareasMin = []; }
  return _pdTareasMin;
}

async function pdCargarTareas() {
  const pid = currentDetailId; if (!pid) return;
  const feed = g('pd-tareas-feed');
  feed.innerHTML = '<div class="bk-cargando">Cargando…</div>';
  let legacy = [], vinculos = [];
  try {
    [legacy, vinculos] = await Promise.all([
      sbFetch('tareas?select=*&propiedad_id=eq.' + encodeURIComponent(pid) + '&order=created_at.desc'),
      sbFetch('tareas_propiedades?select=*&propiedad_id=eq.' + encodeURIComponent(pid) + '&order=created_at.desc').catch(() => []),
    ]);
  } catch { legacy = []; vinculos = []; }
  if (currentDetailId !== pid) return;

  _pdTareasVinculos = vinculos;
  const vistos = new Set(legacy.map(t => String(t.id)));
  const porVinculo = vinculos.map(v => String(v.tarea_id)).filter(id => !vistos.has(id));
  let extra = [];
  if (porVinculo.length) {
    try { extra = await sbFetch('tareas?select=*&id=in.(' + porVinculo.join(',') + ')'); } catch { extra = []; }
  }
  _pdTareas = [...legacy, ...extra].sort((a, b) => {
    if (!!a.completada !== !!b.completada) return a.completada ? 1 : -1;
    return new Date(a.fecha_entrega || '9999-12-31') - new Date(b.fecha_entrega || '9999-12-31');
  });

  const ligadas = new Set(_pdTareas.map(t => String(t.id)));
  let todas = [];
  try { todas = await pdCargarTareasMin(); } catch { todas = []; }
  const disponibles = todas.filter(t => !ligadas.has(String(t.id)) && !t.completada);
  const sel = g('pd-vinculo-tarea');
  sel.innerHTML = '<option value="">Vincular una tarea que ya existe…</option>' +
    disponibles.map(t => `<option value="${esc(String(t.id))}">${esc(t.titulo)}</option>`).join('');
  sel.value = '';
  sel.closest('.bk-forma').hidden = !disponibles.length;

  pdRenderTareas();
}

function pdRenderTareas() {
  const feed = g('pd-tareas-feed');
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  feed.innerHTML = _pdTareas.length
    ? _pdTareas.map(t => {
        const due = t.fecha_entrega ? new Date(t.fecha_entrega) : null;
        const vencida = due && !t.completada && due < hoy;
        return `<div class="bk-fila${t.completada ? ' is-lista' : ''}">
          <button class="bk-tick${t.completada ? ' is-on' : ''}" onclick="pdToggleTarea('${esc(String(t.id))}')"
                  title="${t.completada ? 'Reabrir la tarea' : 'Marcar como completada'}"
                  aria-label="${t.completada ? 'Reabrir la tarea' : 'Marcar como completada'}">
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
          </button>
          <div class="bk-fila__cuerpo">
            <span class="bk-fila__t">${esc(t.titulo)}</span>
            ${due ? `<span class="bk-fila__d${vencida ? ' bk-fila__d--alerta' : ''}">${vencida ? 'Venció el ' : 'Para el '}${esc(fechaCorta(t.fecha_entrega))}</span>` : ''}
          </div>
          <button class="bk-quitar" title="Quitar de este inmueble" aria-label="Quitar de este inmueble" onclick="pdQuitarTarea('${esc(String(t.id))}')">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>`;
      }).join('')
    : `<div class="bk-vacio"><h3>Sin tareas pendientes</h3><p>Apunta lo que falta —subir fotos nuevas, pedir el avalúo, renovar la exclusiva— para que no se te pase.</p></div>`;
  bkContador('f-n-tareas', _pdTareas.filter(t => !t.completada).length);
}

async function pdAgregarTarea() {
  const pid = currentDetailId; if (!pid) return;
  const inp = g('pd-tarea-input');
  const titulo = (inp.value || '').trim();
  if (!titulo) { inp.focus(); return; }
  const uid = getCurrentUserId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  const fecha = g('pd-tarea-fecha').value;
  try {
    const creada = await sbFetch('tareas', 'POST', {
      user_id: uid, titulo: titulo, propiedad_id: pid,
      // La columna es timestamptz: new Date(texto) lo lee en hora local y
      // toISOString() da el instante UTC correcto.
      fecha_entrega: fecha ? new Date(fecha + 'T12:00:00').toISOString() : null,
    });
    const nueva = Array.isArray(creada) ? creada[0] : creada;
    if (nueva && nueva.id) {
      await sbFetch('tareas_propiedades', 'POST', { user_id: uid, tarea_id: nueva.id, propiedad_id: pid }).catch(() => {});
    }
    inp.value = '';
    g('pd-tarea-fecha').value = '';
    _pdTareasMin = null;
    await pdCargarTareas();
    mostrarToast('Tarea creada');
  } catch (e) {
    alert('No se pudo crear la tarea.\n\n' + (e.message || e));
  }
}

async function pdVincularTareaExistente(tareaId) {
  const pid = currentDetailId;
  if (!pid || !tareaId) return;
  const uid = getCurrentUserId();
  if (!uid) { alert('Tu sesión expiró. Vuelve a iniciar sesión.'); return; }
  try {
    await sbFetch('tareas_propiedades', 'POST', { user_id: uid, tarea_id: tareaId, propiedad_id: pid });
    await pdCargarTareas();
    mostrarToast('Tarea vinculada');
  } catch (e) {
    alert('No se pudo vincular.\n\n' + (e.message || e));
  }
}

async function pdToggleTarea(tid) {
  const t = _pdTareas.find(x => String(x.id) === tid); if (!t) return;
  const completar = !t.completada;
  t.completada = completar;
  t.fecha_completada = completar ? new Date().toISOString() : null;
  pdRenderTareas();
  try {
    const filas = await sbFetch('tareas?id=eq.' + encodeURIComponent(tid), 'PATCH',
      { completada: completar, fecha_completada: t.fecha_completada });
    if (!Array.isArray(filas) || filas.length === 0) {
      throw new Error('No tienes permiso sobre esta tarea o ya no existe.');
    }
    if (completar) {
      const uid = getCurrentUserId();
      const pid = currentDetailId;
      if (uid) {
        sbFetch('actividades', 'POST', {
          user_id: uid, tipo: 'tarea_completada', texto: 'Tarea completada: ' + t.titulo, propiedad_id: pid,
        }).then(() => { if (currentDetailId === pid && pdTabActual === 'bitacora') pdCargarBitacora(); }).catch(() => {});
      }
    }
    mostrarToast(completar ? 'Tarea completada' : 'Tarea reabierta');
  } catch (e) {
    t.completada = !completar;
    t.fecha_completada = null;
    pdRenderTareas();
    alert('No se pudo actualizar la tarea.\n\n' + (e.message || e));
  }
}

async function pdQuitarTarea(tid) {
  const pid = currentDetailId; if (!pid) return;
  try {
    const vinculo = _pdTareasVinculos.find(v => String(v.tarea_id) === tid);
    if (vinculo) await sbFetch('tareas_propiedades?id=eq.' + encodeURIComponent(vinculo.id), 'DELETE');
    const t = _pdTareas.find(x => String(x.id) === tid);
    if (t && String(t.propiedad_id) === String(pid)) {
      await sbFetch('tareas?id=eq.' + encodeURIComponent(tid), 'PATCH', { propiedad_id: null });
    }
    _pdTareasMin = null;
    await pdCargarTareas();
    mostrarToast('Vínculo eliminado');
  } catch (e) {
    alert('No se pudo quitar el vínculo.\n\n' + (e.message || e));
  }
}

document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape' || bkHayMenuAbierto()) return;
  if (g('lightbox-overlay') && g('lightbox-overlay').classList.contains('is-open')) return;
  if (g('prop-detail-modal').classList.contains('is-open')) closePropDetail();
});
