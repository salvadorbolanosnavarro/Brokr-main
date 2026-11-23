// ─────────────────────────────────────────────────────────────────────────
// avm-v2.js · Vista "AVM Broquer v2" dentro del módulo de Opinión de valor.
// Solo aparece si el backend responde activo=true en /avm/v2/estado
// (AVM_V2=true, únicamente en staging). Con el flag apagado no pinta nada.
// Todo el texto que viene del servidor se inserta con textContent (sin HTML).
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var BASE = window.API_BASE || 'https://api.broquer.app';
  var TIPOS = [['casa', 'Casa'], ['depto', 'Departamento'], ['terreno', 'Terreno'], ['local', 'Local comercial']];
  var CONSERVACION = [['5', 'Excelente / nueva'], ['4', 'Muy buena'], ['3', 'Buena'], ['2', 'Regular'], ['1', 'Mala']];
  var AMENIDADES = [['jardin', 'Jardín'], ['alberca', 'Alberca'], ['roof_garden', 'Roof garden'],
                    ['seguridad_24h', 'Seguridad 24 h'], ['esquina', 'Esquina'], ['remodelada', 'Remodelada']];

  function el(tag, cls, texto) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (texto !== undefined && texto !== null) n.textContent = String(texto);
    return n;
  }
  function dinero(n) {
    if (n === null || n === undefined) return '—';
    return window.bkDinero ? window.bkDinero(n, 'MXN') : '$' + Math.round(n).toLocaleString('es-MX');
  }
  function campo(etiqueta, input) {
    var f = el('div', 'field');
    var l = el('label', null, etiqueta);
    f.appendChild(l); f.appendChild(input);
    return f;
  }
  function numero(nombre, ph) {
    var i = el('input');
    i.type = 'number'; i.inputMode = 'decimal'; i.name = nombre; i.placeholder = ph || ''; i.min = '0';
    return i;
  }
  function selector(nombre, opciones, valor) {
    var s = el('select'); s.name = nombre;
    opciones.forEach(function (o) { var op = el('option', null, o[1]); op.value = o[0]; s.appendChild(op); });
    if (valor) s.value = valor;
    return s;
  }

  function formulario(raiz) {
    var card = el('div', 'avm-card avm2-card');
    var cab = el('div', 'card-label', 'AVM Broquer v2 · prueba interna');
    card.appendChild(cab);
    card.appendChild(el('p', 'avm2-nota', 'Tres motores (comparables, modelo estadístico y enfoque físico) con rango y nivel de confianza. Solo visible en staging.'));

    var tipo = selector('tipo', TIPOS, 'casa');
    var dir = el('input'); dir.type = 'text'; dir.name = 'direccion'; dir.autocomplete = 'street-address';
    dir.placeholder = 'Calle y número, colonia, ciudad';
    var f1 = el('div', 'field-row'); f1.appendChild(campo('Tipo', tipo)); card.appendChild(f1);
    var f2 = el('div', 'field-row'); var cDir = campo('Dirección *', dir); f2.appendChild(cDir); card.appendChild(f2);
    // Sugerencias de colonias (mismo buscador que el formulario de abajo).
    // Al elegir una se mandan sus coordenadas y no hace falta geocodificar.
    var sug = el('div', 'avm2-sug avm2-oculto'); cDir.appendChild(sug);
    var punto = null, espera = null, consulta = 0;
    dir.addEventListener('input', function () {
      punto = null;
      clearTimeout(espera);
      var t = dir.value.trim();
      if (t.length < 3) { sug.classList.add('avm2-oculto'); return; }
      espera = setTimeout(async function () {
        var mia = ++consulta;
        try {
          var r = await fetch(BASE + '/api/colonias?texto=' + encodeURIComponent(t) + '&pais=MX');
          var d = await r.json();
          if (mia !== consulta) return;
          var lista = (d && d.colonias || []).filter(function (c) { return c.latitud && c.longitud; }).slice(0, 6);
          sug.textContent = '';
          lista.forEach(function (c) {
            var b = el('button', 'avm2-sug-op', c.display || c.nombre); b.type = 'button';
            b.addEventListener('click', function () {
              dir.value = c.display || c.nombre;
              punto = { lat: c.latitud, lon: c.longitud, colonia: c.nombre };
              sug.classList.add('avm2-oculto');
            });
            sug.appendChild(b);
          });
          sug.classList.toggle('avm2-oculto', lista.length === 0);
        } catch (_) { sug.classList.add('avm2-oculto'); }
      }, 300);
    });

    var m2c = numero('m2_construidos', '150'), m2t = numero('m2_terreno', '160');
    var f3 = el('div', 'field-row avm2-row');
    var cM2c = campo('m² construidos', m2c), cM2t = campo('m² de terreno', m2t);
    f3.appendChild(cM2c); f3.appendChild(cM2t); card.appendChild(f3);

    var rec = numero('recamaras', '3'), ban = numero('banos', '2'), edad = numero('edad_anios', '10');
    var f4 = el('div', 'field-row avm2-row');
    f4.appendChild(campo('Recámaras', rec)); f4.appendChild(campo('Baños', ban)); f4.appendChild(campo('Edad (años)', edad));
    card.appendChild(f4);

    var cons = selector('conservacion', CONSERVACION, '4'), caj = numero('cajones', '2');
    var f5 = el('div', 'field-row avm2-row');
    f5.appendChild(campo('Conservación', cons)); f5.appendChild(campo('Cajones', caj));
    card.appendChild(f5);

    var amen = el('div', 'avm2-chips');
    AMENIDADES.forEach(function (a) {
      var lab = el('label', 'avm2-chip');
      var cb = el('input'); cb.type = 'checkbox'; cb.name = a[0];
      lab.appendChild(cb); lab.appendChild(el('span', null, a[1]));
      amen.appendChild(lab);
    });
    card.appendChild(amen);

    var err = el('div', 'alert warn avm2-oculto');
    var btn = el('button', 'btn-primary teal', 'Calcular con AVM v2'); btn.type = 'button';
    card.appendChild(err); card.appendChild(btn);
    var salida = el('div', 'avm2-salida');
    raiz.appendChild(card); raiz.appendChild(salida);

    function ajustarTipo() {
      var t = tipo.value;
      cM2c.style.display = t === 'terreno' ? 'none' : '';
      f4.style.display = t === 'terreno' || t === 'local' ? 'none' : '';
      f5.style.display = t === 'terreno' ? 'none' : '';
    }
    tipo.addEventListener('change', ajustarTipo); ajustarTipo();

    function num(i) { var v = parseFloat(i.value); return isFinite(v) && v > 0 ? v : null; }

    btn.addEventListener('click', async function () {
      err.classList.add('avm2-oculto');
      var cuerpo = {
        tipo: tipo.value, direccion: dir.value.trim() || null,
        m2_construidos: tipo.value === 'terreno' ? null : num(m2c), m2_terreno: num(m2t),
        recamaras: num(rec), banos: num(ban), edad_anios: num(edad) === null && edad.value === '0' ? 0 : num(edad),
        conservacion: tipo.value === 'terreno' ? null : parseInt(cons.value, 10),
        amenidades: { cajones: num(caj) }
      };
      AMENIDADES.forEach(function (a) { cuerpo.amenidades[a[0]] = !!amen.querySelector('input[name=' + a[0] + ']').checked; });
      if (punto) { cuerpo.lat = punto.lat; cuerpo.lon = punto.lon; cuerpo.colonia = punto.colonia; }
      if (!cuerpo.direccion) { err.textContent = 'Escribe la dirección.'; err.classList.remove('avm2-oculto'); return; }
      btn.disabled = true; btn.textContent = 'Calculando…';
      try {
        var data = await window.bkApi('/avm/v2/estimar', { method: 'POST', json: cuerpo });
        pintar(salida, data);
        salida.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (e) {
        err.textContent = (e && e.message) || 'No se pudo calcular. Intenta de nuevo.';
        err.classList.remove('avm2-oculto');
      } finally {
        btn.disabled = false; btn.textContent = 'Calcular con AVM v2';
      }
    });
  }

  function pintar(salida, d) {
    salida.textContent = '';
    if (d.datos === 'sinteticos') {
      salida.appendChild(el('div', 'alert warn', 'Modelo de demostración entrenado con datos sintéticos: no usar con clientes.'));
    }
    var card = el('div', 'avm-card avm2-card');
    card.appendChild(el('div', 'card-label', d.tipo_documento || 'Opinión Comercial de Valor'));
    var cabeza = el('div', 'avm2-cabeza');
    var conf = (d.confianza || '').toLowerCase();
    var sello = el('span', 'ia-conf ' + (conf === 'alta' ? 'alta' : conf === 'media' ? 'media' : 'baja'),
      d.emitido ? 'Confianza ' + d.confianza.toLowerCase() : 'Sin valor');
    if (d.emitido) {
      cabeza.appendChild(el('div', 'avm2-valor', dinero(d.valor)));
      cabeza.appendChild(sello);
      card.appendChild(cabeza);
      // Barra de rango: el marcador es el valor dentro de [bajo, alto].
      var lo = d.rango[0], hi = d.rango[1];
      var barra = el('div', 'avm2-barra');
      var marca = el('div', 'avm2-marca');
      marca.style.left = Math.max(0, Math.min(100, 100 * (d.valor - lo) / Math.max(1, hi - lo))) + '%';
      barra.appendChild(marca);
      card.appendChild(barra);
      var ext = el('div', 'avm2-extremos');
      ext.appendChild(el('span', null, dinero(lo))); ext.appendChild(el('span', null, dinero(hi)));
      card.appendChild(ext);
      card.appendChild(el('p', 'avm2-nota', 'Rango con 80 % de probabilidad de contener el precio de cierre · incluye ' +
        d.descuento_negociacion_pct + ' % de negociación típica de la zona.'));
    } else {
      cabeza.appendChild(sello); card.appendChild(cabeza);
      card.appendChild(el('p', 'avm2-nota', 'La incertidumbre es demasiado alta para dar un valor. Se recomienda visitar el inmueble.'));
    }
    salida.appendChild(card);

    var mot = el('div', 'avm-card avm2-card');
    mot.appendChild(el('div', 'card-label', 'Desglose por motor'));
    ['A', 'B', 'C'].forEach(function (k) {
      var m = d.motores[k]; if (!m) return;
      var fila = el('div', 'avm2-motor');
      fila.appendChild(el('span', 'avm2-motor-n', m.nombre));
      fila.appendChild(el('span', 'avm2-motor-v', m.calculado ? dinero(m.valor) : 'No calculó'));
      fila.appendChild(el('span', 'avm2-motor-p', m.calculado ? Math.round(100 * (m.peso || 0)) + ' %' : ''));
      mot.appendChild(fila);
      if (!m.calculado && m.motivo) mot.appendChild(el('div', 'avm2-motivo', m.motivo));
    });
    salida.appendChild(mot);

    if (d.explicacion && d.explicacion.length) {
      var ex = el('div', 'avm-card avm2-card');
      ex.appendChild(el('div', 'card-label', 'Por qué este valor'));
      var ul = el('ul', 'avm2-lista');
      d.explicacion.forEach(function (t) { ul.appendChild(el('li', null, t)); });
      ex.appendChild(ul);
      salida.appendChild(ex);
    }

    if (d.comparables && d.comparables.length) {
      var cp = el('div', 'avm-card avm2-card');
      cp.appendChild(el('div', 'card-label', 'Comparables consultados (' + d.comparables.length + ')'));
      d.comparables.forEach(function (c) {
        var a = el('a', 'avm2-comp');
        a.href = c.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.appendChild(el('span', 'avm2-comp-p', dinero(c.precio)));
        a.appendChild(el('span', 'avm2-comp-d', c.m2 + ' m² · ' + dinero(c.precio_m2) + '/m² · a ' + c.distancia_m + ' m'));
        cp.appendChild(a);
      });
      salida.appendChild(cp);
    }

    if (d.advertencias && d.advertencias.length) {
      d.advertencias.forEach(function (t) { salida.appendChild(el('div', 'alert warn', t)); });
    }
    salida.appendChild(el('p', 'avm2-pie', 'Opinión Comercial de Valor, no es un avalúo. Versión ' + d.version + '.'));
  }

  async function iniciar() {
    var raiz = document.getElementById('avm-v2-raiz');
    if (!raiz) return;
    try {
      var r = await fetch(BASE + '/avm/v2/estado');
      var e = await r.json();
      if (!e || !e.activo) return;
    } catch (_) { return; }
    raiz.hidden = false;
    formulario(raiz);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
