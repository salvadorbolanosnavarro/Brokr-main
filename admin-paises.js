/* ══════════════════════════════════════════════════════════════════
   Consola de dueño · País de cada cuenta.

   Agrega una fila "País" al detalle del usuario en admin.html. Cambiarlo
   llama a /admin/user/pais; si la cuenta es dueña de una empresa, todo su
   equipo cambia con ella (un equipo trabaja en un solo país).

   Si la cuenta no tiene país guardado se muestra el de la lada de su
   teléfono (y si no trae lada, México). Si el guardado no coincide con
   el teléfono, se avisa junto a la fila.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (typeof renderDetail !== 'function' || !window.BK_PAISES) return;

  /* global bkPaisPorTelefono */
  function delTel(u) { return window.bkPaisPorTelefono ? bkPaisPorTelefono(u.telefono) : ''; }
  function paisDe(u) { return u.pais || delTel(u) || 'MX'; }
  window.bkAdmPaisNombre = function (u) { return BK_PAISES[paisDe(u)].nombre; };

  function nota(u) {
    var el = document.getElementById('d-pais-nota');
    if (!el) return;
    var t = delTel(u);
    el.textContent = '';
    if (!u.pais) {
      el.textContent = (t ? 'Según su teléfono. ' : '') + 'Aún no tiene país guardado. ';
      var b = document.createElement('a');
      b.href = '#';
      b.textContent = 'Guardar';
      b.addEventListener('click', function (e) { e.preventDefault(); guardar(); });
      el.appendChild(b);
    } else if (t && t !== u.pais) {
      el.textContent = 'Su teléfono es de ' + BK_PAISES[t].nombre + '.';
    }
    el.style.display = el.textContent ? '' : 'none';
  }

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
    BK_PAISES_ORDEN.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c; o.textContent = BK_PAISES[c].nombre;
      sel.appendChild(o);
    });
    sel.addEventListener('change', guardar);
    nueva.appendChild(sel);
    row.parentNode.insertBefore(nueva, row);
    var aviso = document.createElement('div');
    aviso.id = 'd-pais-nota';
    aviso.style.cssText = 'font-size:var(--fs-caption);color:var(--warn,#b45309);text-align:right;padding:0 0 var(--sp-2)';
    row.parentNode.insertBefore(aviso, row);
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
      sel.value = paisDe(u);
      return;
    }
    sel.disabled = true;
    try {
      var r = await apiJson('/admin/user/pais', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: u.id, pais: nuevo }),
      });
      u.pais = nuevo;
      nota(u);
      if (typeof renderList === 'function') renderList();
      toast('País actualizado' + (r.cuentas > 1 ? ' (' + r.cuentas + ' cuentas).' : '.'));
    } catch (e) {
      sel.value = paisDe(u);
      toast('Error: ' + e.message, true);
    } finally {
      sel.disabled = false;
    }
  }

  var original = renderDetail;
  window.renderDetail = function (u) {
    original(u);
    var sel = fila();
    if (sel) { sel.value = paisDe(u); nota(u); }
  };
})();
