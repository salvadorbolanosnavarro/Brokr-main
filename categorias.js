// ─────────────────────────────────────────────────────────────────────────
// categorias.js · Catálogo de categorías por cuenta
// ─────────────────────────────────────────────────────────────────────────
// Tabla organizacion_categorias: un catálogo compartido por toda la cuenta
// (en empresas, por todo el equipo; en cuentas individuales, solo por el
// dueño — cada cuenta ya tiene su propia organización, incluso las
// personales, ver get_org_context() en routers/organizaciones.py).
// Cualquier miembro activo puede crear categorías nuevas y usarlas para
// etiquetar tareas y notas (varias categorías por tarea/nota).
//
// Requiere que la página ya tenga cargado app-shell.js (window.brokrSb) y
// una función global esc() para escapar HTML.
//
// Usan este módulo: tareas.html, contactos-ficha.js, clientes-ficha.js,
// propiedades-ficha.js.
// ─────────────────────────────────────────────────────────────────────────

async function catCargar(orgId) {
  if (!orgId || !window.brokrSb) return [];
  try {
    return await window.brokrSb.rest(
      'organizacion_categorias?select=id,nombre&org_id=eq.' + encodeURIComponent(orgId) + '&order=nombre.asc'
    );
  } catch {
    return [];
  }
}

async function catCrear(orgId, uid, nombre) {
  const limpio = (nombre || '').trim();
  if (!limpio || !orgId || !uid || !window.brokrSb) return null;
  try {
    const rows = await window.brokrSb.rest('organizacion_categorias', {
      method: 'POST',
      body: { org_id: orgId, nombre: limpio, creado_por: uid },
    });
    return Array.isArray(rows) ? rows[0] : rows;
  } catch {
    // Ya existe (unique org_id+nombre) o hubo un choque de carrera con otro
    // miembro creando la misma categoría: la buscamos y la reusamos.
    try {
      const existentes = await window.brokrSb.rest(
        'organizacion_categorias?select=id,nombre&org_id=eq.' + encodeURIComponent(orgId) +
        '&nombre=eq.' + encodeURIComponent(limpio) + '&limit=1'
      );
      return Array.isArray(existentes) && existentes[0] ? existentes[0] : null;
    } catch {
      return null;
    }
  }
}

// Vincula/desvincula una categoría a una tarea o nota (actividad) usando la
// tabla puente correspondiente (tareas_categorias / actividades_categorias).
async function catVincular(tablaPuente, campoId, entidadId, categoriaId) {
  if (!window.brokrSb) return false;
  try {
    await window.brokrSb.rest(tablaPuente, {
      method: 'POST',
      body: { [campoId]: entidadId, categoria_id: categoriaId },
    });
    return true;
  } catch {
    return false;
  }
}
async function catDesvincular(tablaPuente, campoId, entidadId, categoriaId) {
  if (!window.brokrSb) return false;
  try {
    await window.brokrSb.rest(
      tablaPuente + '?' + campoId + '=eq.' + encodeURIComponent(entidadId) +
      '&categoria_id=eq.' + encodeURIComponent(categoriaId),
      { method: 'DELETE' }
    );
    return true;
  } catch {
    return false;
  }
}

// Pinta chips de categorías ya elegidas + un <select> para agregar del
// catálogo existente. La creación de categorías nuevas la maneja quien
// llama (botón "+ Nueva" aparte), porque necesita orgId/uid del caller.
function catPintarPicker({ chipsEl, selectEl, catalogo, seleccionadas, onQuitar, onAgregar }) {
  chipsEl.innerHTML = seleccionadas.length
    ? seleccionadas.map(id => {
        const cat = catalogo.find(c => String(c.id) === String(id));
        const nombre = cat ? cat.nombre : 'Categoría';
        return '<span class="tke-chip">' + esc(nombre) +
          '<button type="button" data-cat-quitar="' + esc(String(id)) + '">×</button></span>';
      }).join('')
    : '<span class="bk-hint">Sin categorías.</span>';
  chipsEl.querySelectorAll('[data-cat-quitar]').forEach(btn => {
    btn.addEventListener('click', () => onQuitar(btn.getAttribute('data-cat-quitar')));
  });
  const disponibles = catalogo.filter(c => !seleccionadas.includes(String(c.id)));
  selectEl.innerHTML = '<option value="">' + (disponibles.length ? 'Agregar categoría…' : 'No hay más categorías') + '</option>' +
    disponibles.map(c => '<option value="' + esc(String(c.id)) + '">' + esc(c.nombre) + '</option>').join('');
  selectEl.onchange = () => {
    const id = selectEl.value;
    if (id) onAgregar(id);
    selectEl.value = '';
  };
}

// Chips de solo lectura, para pintar categorías en filas de lista o en el
// feed de actividad.
function catChipsSoloLectura(catIds, catalogo) {
  if (!catIds || !catIds.length) return '';
  const nombres = catIds
    .map(id => catalogo.find(c => String(c.id) === String(id)))
    .filter(Boolean)
    .map(c => '<span class="tke-chip" style="cursor:default">' + esc(c.nombre) + '</span>');
  if (!nombres.length) return '';
  return '<div class="tke-chips" style="margin-top:4px">' + nombres.join('') + '</div>';
}
