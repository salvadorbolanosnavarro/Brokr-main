/* ══════════════════════════════════════════════════════════════════
   Consola de dueño · País de cada cuenta.

   Agrega una fila "País" al detalle del usuario en admin.html. Cambiarlo
   llama a /admin/user/pais; si la cuenta es dueña de una empresa, todo su
   equipo cambia con ella (un equipo trabaja en un solo país).
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (typeof renderDetail !== 'function' || !window.BK_PAISES) return;

  function fila() {
    var ya = document.getElementById('d-pais');
    if (ya) return ya;
    var ref = document.getElementById('d-id');
    var row = ref && ref.closest('.adm-info__row');
    if (!row) return null;
    var nueva = document.createElement('div');
    nueva.className = 'adm-info__row';
    nueva.innerHTML = '<span class="adm-info__lbl">País</span>';
    var sel = document.createElement('select');
    sel.id = 'd-pais';
    sel.className = 'adm-info__val';
    // Cuenta que todavía no eligió país (no es lo mismo que México).
    var vacia = document.createElement('option');
    vacia.value = ''; vacia.textContent = 'Sin elegir'; vacia.disabled = true;
    sel.appendChild(vacia);
    BK_PAISES_ORDEN.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c; o.textContent = BK_PAISES[c].nombre;
      sel.appendChild(o);
    });
    sel.addEventListener('change', guardar);
    nueva.appendChild(sel);
    row.parentNode.insertBefore(nueva, row);
    return sel;
  }

  async function guardar() {
    var sel = document.getElementById('d-pais');
    /* global users, selId, apiJson, toast */
    var u = users.find(function (x) { return x.id === selId; });
    if (!u || !sel) return;
    var nuevo = sel.value;
    if (!confirm('¿Cambiar el país de ' + (u.nombre || u.email) + ' a ' + BK_PAISES[nuevo].nombre +
                 '? Si es dueño de una empresa, cambia también su equipo.')) {
      sel.value = u.pais || '';
      return;
    }
    sel.disabled = true;
    try {
      var r = await apiJson('/admin/user/pais', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: u.id, pais: nuevo }),
      });
      u.pais = nuevo;
      toast('País actualizado' + (r.cuentas > 1 ? ' (' + r.cuentas + ' cuentas).' : '.'));
    } catch (e) {
      sel.value = u.pais || '';
      toast('Error: ' + e.message, true);
    } finally {
      sel.disabled = false;
    }
  }

  var original = renderDetail;
  window.renderDetail = function (u) {
    original(u);
    var sel = fila();
    if (sel) sel.value = u.pais || '';
  };
})();
