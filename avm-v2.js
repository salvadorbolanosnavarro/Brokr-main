// ─────────────────────────────────────────────────────────────────────────
// avm-v2.js · Vista "AVM Broquer v2" dentro del módulo de Opinión de valor.
// Solo aparece si el backend responde activo=true en /avm/v2/estado
// (AVM_V2=true, únicamente en staging). Con el flag apagado no pinta nada.
// Todo el texto que viene del servidor se inserta con textContent (sin HTML).
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var BASE = window.API_BASE || 'https://api.broquer.app';
  var modoActual = null;
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

  // La sugerencia puede ser un negocio ("Judo Chapultepec, 8 de Septiembre,
  // Chapultepec Sur, Morelia, Mich., México"): la colonia es la parte que va
  // justo antes de la ciudad, no el nombre del lugar.
  function coloniaDe(c) {
    var partes = String(c.display || '').split(',').map(function (x) { return x.trim(); });
    var i = c.ciudad ? partes.indexOf(c.ciudad) : -1;
    if (i >= 1) return partes[i - 1];
    return null;
  }

  // Sugerencias de colonias bajo un campo de dirección (mismo buscador que el
  // formulario de abajo). Al elegir una se mandan sus coordenadas y no hace
  // falta geocodificar. Devuelve { punto(): {lat, lon, colonia} | null }.
  function conSugerencias(dir, contenedor) {
    var sug = el('div', 'avm2-sug avm2-oculto'); contenedor.appendChild(sug);
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
              punto = { lat: c.latitud, lon: c.longitud, colonia: coloniaDe(c), ciudad: c.ciudad || null };
              sug.classList.add('avm2-oculto');
            });
            sug.appendChild(b);
          });
          sug.classList.toggle('avm2-oculto', lista.length === 0);
        } catch (_) { sug.classList.add('avm2-oculto'); }
      }, 300);
    });
    return { punto: function () { return punto; } };
  }

  function texto(nombre, ph, tipo) {
    var i = el('input'); i.type = tipo || 'text'; i.name = nombre; i.placeholder = ph || '';
    return i;
  }
  function moneda(nombre, ph) {
    var i = texto(nombre, ph); i.inputMode = 'numeric';
    i.addEventListener('input', function () {
      var dig = i.value.replace(/[^0-9]/g, '');
      i.value = dig ? Number(dig).toLocaleString('es-MX') : '';
    });
    return i;
  }
  function valorMoneda(i) { var n = Number(String(i.value).replace(/[^0-9]/g, '')); return n > 0 ? n : null; }
  function aviso(nodo, msg, tipo) {
    nodo.className = 'alert ' + (tipo || 'warn');
    nodo.textContent = msg;
  }

  // ── Datos reales y botón "Entrenar ahora" ─────────────────────────────
  function tarjetaDatos(raiz) {
    var card = el('div', 'avm-card avm2-card');
    card.appendChild(el('div', 'card-label', 'Datos reales del modelo'));
    var cuerpo = el('div'); card.appendChild(cuerpo);
    raiz.appendChild(card);
    var sondeo = null;

    async function cargar() {
      var d;
      try { d = await window.bkApi('/avm/v2/datos'); }
      catch (e) { cuerpo.textContent = ''; cuerpo.appendChild(el('p', 'avm2-nota', (e && e.message) || 'No se pudieron leer los datos.')); return; }
      cuerpo.textContent = '';
      var m = d.modelo || {};
      cuerpo.appendChild(el('p', 'avm2-nota', m.datos === 'reales'
        ? 'Modelo en uso: entrenado con datos reales (' + m.version + ').'
        : (modoActual === 'en_vivo'
          ? 'Hoy valúa en vivo con anuncios leídos al momento. Cada valuación guarda esos anuncios aquí abajo.'
          : 'Modelo en uso: demostración con precios inventados.')));
      Object.keys(d.ciudades || {}).forEach(function (c) {
        var x = d.ciudades[c];
        var fila = el('div', 'avm2-motor');
        fila.appendChild(el('span', 'avm2-motor-n', c));
        fila.appendChild(el('span', 'avm2-motor-v', x.anuncios_utiles.toLocaleString('es-MX') + ' anuncios'));
        fila.appendChild(el('span', 'avm2-motor-p', x.cierres + ' cierres'));
        cuerpo.appendChild(fila);
      });
      var faltan = Math.max(0, d.minimo_para_entrenar - d.anuncios_utiles);
      cuerpo.appendChild(el('p', 'avm2-nota avm2-sep', faltan
        ? 'Faltan ' + faltan.toLocaleString('es-MX') + ' anuncios útiles para entrenar (mínimo ' + d.minimo_para_entrenar + '). La recolección diaria los va juntando.'
        : 'Ya hay anuncios suficientes para entrenar con datos reales.'));
      if (d.cierres < d.minimo_cierres_calibrar) {
        cuerpo.appendChild(el('p', 'avm2-nota', 'Con ' + d.minimo_cierres_calibrar + ' cierres capturados el rango se calibra con ventas reales (hoy: ' + d.cierres + ').'));
      }
      var e = d.entrenamiento || {};
      if (e.estado && e.estado !== 'inactivo') cuerpo.appendChild(estadoEntrenamiento(e));
      if (d.es_admin) {
        var btn = el('button', 'btn-primary teal', e.estado === 'entrenando' ? 'Entrenando…' : 'Entrenar ahora con datos reales');
        btn.type = 'button';
        btn.disabled = faltan > 0 || e.estado === 'entrenando';
        var msg = el('div', 'avm2-oculto');
        btn.addEventListener('click', async function () {
          btn.disabled = true; btn.textContent = 'Iniciando…';
          try {
            await window.bkApi('/avm/v2/entrenar', { method: 'POST' });
            vigilar();
          } catch (err) {
            aviso(msg, (err && err.message) || 'No se pudo iniciar.');
            btn.disabled = false; btn.textContent = 'Entrenar ahora con datos reales';
          }
        });
        cuerpo.appendChild(msg); cuerpo.appendChild(btn);
      }
      if (e.estado === 'entrenando') vigilar();
    }

    function vigilar() {
      if (sondeo) return;
      sondeo = setInterval(async function () {
        try {
          var e = await window.bkApi('/avm/v2/entrenar');
          if (e.estado !== 'entrenando') { clearInterval(sondeo); sondeo = null; cargar(); return; }
          var actual = cuerpo.querySelector('.avm2-entreno');
          var nuevo = estadoEntrenamiento(e);
          if (actual) actual.replaceWith(nuevo); else cuerpo.insertBefore(nuevo, cuerpo.firstChild);
        } catch (_) { /* reintenta en el siguiente ciclo */ }
      }, 10000);
    }
    cargar();
    return { recargar: cargar };
  }

  function estadoEntrenamiento(e) {
    var caja = el('div', 'avm2-entreno');
    if (e.estado === 'entrenando') {
      caja.appendChild(el('div', 'alert warn', 'Entrenando con datos reales: ' + (e.paso || 'en curso') + '. Tarda unos minutos; puedes seguir usando la app.'));
    } else if (e.estado === 'listo') {
      var m = e.metricas || {};
      var t = e.promovido ? 'Modelo nuevo en uso.' : 'El modelo nuevo no se puso en uso: ' + (e.motivo || '') + '.';
      if (m.mdape !== null && m.mdape !== undefined) t += ' Error típico ' + m.mdape + ' %, dentro de ±10 %: ' + m.pe10 + ' % de los casos (medido con ' + (m.fuente_medicion || '') + ').';
      caja.appendChild(el('div', 'alert ' + (e.promovido ? 'success' : 'warn'), t));
    } else if (e.estado === 'insuficiente' || e.estado === 'error') {
      caja.appendChild(el('div', 'alert warn', e.motivo || 'No se pudo entrenar.'));
    }
    return caja;
  }

  // ── Captura de cierres reales ────────────────────────────────────────────
  var FUENTES = [['cierres', 'Venta cerrada por mi equipo'], ['navarro', 'Inmobiliaria Navarro'], ['avaluo', 'Avalúo bancario']];

  function tarjetaCierre(raiz, alGuardar) {
    var det = el('details', 'avm-card avm2-card avm2-plegable');
    var sum = el('summary', 'card-label', 'Capturar un cierre real'); det.appendChild(sum);
    det.appendChild(el('p', 'avm2-nota', 'Cada venta cerrada le enseña al modelo cuánto se negocia en la zona y qué tan cerca estuvo. Es el dato que más mejora la precisión.'));
    var tipo = selector('tipo', TIPOS, 'casa');
    var dir = texto('direccion', 'Colonia o calle y número, ciudad'); dir.autocomplete = 'off';
    var r1 = el('div', 'field-row'); r1.appendChild(campo('Tipo', tipo)); det.appendChild(r1);
    var r2 = el('div', 'field-row'); var cDir = campo('Dirección *', dir); r2.appendChild(cDir); det.appendChild(r2);
    var ubic = conSugerencias(dir, cDir);
    var salida = moneda('precio_oferta_inicial', '3,500,000'), cierre = moneda('precio_cierre', '3,250,000');
    var r3 = el('div', 'field-row avm2-row'); r3.appendChild(campo('Precio de salida', salida)); r3.appendChild(campo('Precio de cierre *', cierre)); det.appendChild(r3);
    var fecha = texto('fecha_cierre', '', 'date'); fecha.value = new Date().toISOString().slice(0, 10);
    var dias = numero('dias_en_mercado', '90');
    var r4 = el('div', 'field-row avm2-row'); r4.appendChild(campo('Fecha de cierre *', fecha)); r4.appendChild(campo('Días en el mercado', dias)); det.appendChild(r4);
    var m2c = numero('m2_construidos', '150'), m2t = numero('m2_terreno', '160');
    var r5 = el('div', 'field-row avm2-row'); var cM2c = campo('m² construidos', m2c); r5.appendChild(cM2c); r5.appendChild(campo('m² de terreno', m2t)); det.appendChild(r5);
    var rec = numero('recamaras', '3'), ban = numero('banos', '2'), edad = numero('edad_anios', '10');
    var r6 = el('div', 'field-row avm2-row'); r6.appendChild(campo('Recámaras', rec)); r6.appendChild(campo('Baños', ban)); r6.appendChild(campo('Edad (años)', edad)); det.appendChild(r6);
    var cons = selector('conservacion', CONSERVACION, '4'), fuente = selector('fuente', FUENTES, 'cierres');
    var r7 = el('div', 'field-row avm2-row'); var cCons = campo('Conservación', cons); r7.appendChild(cCons); r7.appendChild(campo('Origen del dato', fuente)); det.appendChild(r7);
    var notas = el('textarea'); notas.name = 'notas'; notas.rows = 2; notas.placeholder = 'Opcional: crédito, urgencia del vendedor, remodelación…';
    var r8 = el('div', 'field-row'); r8.appendChild(campo('Notas', notas)); det.appendChild(r8);
    var msg = el('div', 'avm2-oculto');
    var btn = el('button', 'btn-primary teal', 'Guardar cierre'); btn.type = 'button';
    det.appendChild(msg); det.appendChild(btn);
    raiz.appendChild(det);

    function ajustar() {
      var t = tipo.value;
      cM2c.style.display = t === 'terreno' ? 'none' : '';
      r6.style.display = t === 'terreno' || t === 'local' ? 'none' : '';
      cCons.style.display = t === 'terreno' ? 'none' : '';
    }
    tipo.addEventListener('change', ajustar); ajustar();
    function num(i) { var v = parseFloat(i.value); return isFinite(v) && v >= 0 && i.value !== '' ? v : null; }

    btn.addEventListener('click', async function () {
      var p = ubic.punto();
      var cuerpo = {
        tipo: tipo.value, precio_cierre: valorMoneda(cierre), precio_oferta_inicial: valorMoneda(salida),
        fecha_cierre: fecha.value, dias_en_mercado: num(dias), fuente: fuente.value,
        m2_construidos: tipo.value === 'terreno' ? null : num(m2c), m2_terreno: num(m2t),
        recamaras: num(rec), banos: num(ban), edad_anios: num(edad),
        conservacion: tipo.value === 'terreno' ? null : parseInt(cons.value, 10),
        direccion: dir.value.trim() || null, notas: notas.value.trim() || null
      };
      if (p) { cuerpo.lat = p.lat; cuerpo.lon = p.lon; cuerpo.colonia = p.colonia; if (p.ciudad) cuerpo.municipio = p.ciudad; }
      if (!cuerpo.direccion) return aviso(msg, 'Escribe la dirección y elige una sugerencia.');
      if (!cuerpo.precio_cierre) return aviso(msg, 'Escribe el precio de cierre.');
      if (!cuerpo.fecha_cierre) return aviso(msg, 'Indica la fecha de cierre.');
      if (cuerpo.precio_oferta_inicial && cuerpo.precio_oferta_inicial < cuerpo.precio_cierre * 0.6) {
        return aviso(msg, 'El precio de salida parece muy bajo frente al de cierre. Revisa las cifras.');
      }
      Object.keys(cuerpo).forEach(function (k) { if (cuerpo[k] === null) delete cuerpo[k]; });
      btn.disabled = true; btn.textContent = 'Guardando…';
      try {
        var r = await window.bkApi('/avm/v2/cierre', { method: 'POST', json: cuerpo });
        var t = 'Cierre guardado.';
        if (r.descuento_pct !== null && r.descuento_pct !== undefined) t += ' Se negoció ' + r.descuento_pct + ' % desde el precio de salida.';
        aviso(msg, t, 'success');
        [cierre, salida, dias, m2c, m2t, rec, ban, edad, dir, notas].forEach(function (i) { i.value = ''; });
        if (alGuardar) alGuardar();
      } catch (e) {
        aviso(msg, (e && e.message) || 'No se pudo guardar el cierre.');
      } finally {
        btn.disabled = false; btn.textContent = 'Guardar cierre';
      }
    });
  }

  function formulario(raiz) {
    var card = el('div', 'avm-card avm2-card');
    var cab = el('div', 'card-label', 'AVM Broquer v2 · prueba interna');
    card.appendChild(cab);
    card.appendChild(el('p', 'avm2-nota', modoActual === 'en_vivo'
      ? 'Hoy calcula en vivo: lee anuncios reales de la zona al momento y los compara (tarda 1 a 2 minutos). Cuando se entrene con datos reales responderá en segundos.'
      : 'Tres motores (comparables, modelo estadístico y enfoque físico) con rango y nivel de confianza. Solo visible en staging.'));

    var tipo = selector('tipo', TIPOS, 'casa');
    var dir = el('input'); dir.type = 'text'; dir.name = 'direccion'; dir.autocomplete = 'street-address';
    dir.placeholder = 'Calle y número, colonia, ciudad';
    var f1 = el('div', 'field-row'); f1.appendChild(campo('Tipo', tipo)); card.appendChild(f1);
    var f2 = el('div', 'field-row'); var cDir = campo('Dirección *', dir); f2.appendChild(cDir); card.appendChild(f2);
    var ubic = conSugerencias(dir, cDir);

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
      var punto = ubic.punto();
      if (punto) { cuerpo.lat = punto.lat; cuerpo.lon = punto.lon; cuerpo.colonia = punto.colonia; }
      if (!cuerpo.direccion) { err.textContent = 'Escribe la dirección.'; err.classList.remove('avm2-oculto'); return; }
      btn.disabled = true; btn.textContent = modoActual === 'en_vivo' ? 'Leyendo anuncios de hoy… (1 a 2 min)' : 'Calculando…';
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
    } else if (d.datos === 'en_vivo') {
      salida.appendChild(el('div', 'alert success', 'Calculado en vivo con ' + (d.anuncios_leidos || 0) +
        ' anuncios reales leídos hoy. El rango todavía no está calibrado con cierres.'));
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
      // Explicar en palabras por qué no hay valor y qué lo resolvería.
      var vals = ['A', 'B', 'C'].map(function (k) { return d.motores[k]; })
        .filter(function (m) { return m && m.calculado; }).map(function (m) { return m.valor; });
      var txt = 'No damos un número porque la incertidumbre es demasiado alta';
      if (vals.length >= 2) {
        txt += ': los métodos no coinciden entre sí (van de ' + dinero(Math.min.apply(null, vals)) + ' a ' +
          dinero(Math.max.apply(null, vals)) + ')';
      }
      txt += '. Esto se corrige con más anuncios y cierres reales en la zona; mientras tanto, conviene visitar el inmueble.';
      card.appendChild(el('p', 'avm2-nota', txt));
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
      ex.appendChild(el('div', 'card-label', d.emitido ? 'Por qué este valor' : 'Qué influye en este inmueble'));
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
      modoActual = e.modo || null;
    } catch (_) { return; }
    raiz.hidden = false;
    formulario(raiz);
    var datos = tarjetaDatos(raiz);
    tarjetaCierre(raiz, function () { datos.recargar(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
