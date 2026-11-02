/* ══════════════════════════════════════════════════════════════════
   Países donde opera Broquer — la única fuente de verdad del navegador.

   Cada cuenta pertenece a UN país. Se elige en el landing (o en la
   pantalla de crear cuenta) y se guarda en el perfil (usuarios.pais);
   después ya no se vuelve a preguntar. El espejo del servidor es
   core/paises.py: si cambias un dato aquí, cámbialo allá también.

   Uso:
     bkPais()               → 'MX' | 'CO' | 'PE' | 'AR' | 'CL'
     bkPaisCfg()            → datos del país actual (o del que pases)
     bkDinero(1500000)      → "$1.500.000" con el formato del país
     bkModuloDisponible(k)  → false si el módulo no aplica en el país
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var PAISES = {
    MX: {
      codigo: 'MX', nombre: 'México', locale: 'es-MX',
      moneda: 'MXN', monedas: ['MXN', 'USD'],
      lada: '52', digitosTel: 10, telEjemplo: '443 123 4567',
      zonaHoraria: 'America/Mexico_City',
      idFiscal: 'RFC', idPersona: 'INE', autoridadFiscal: 'SAT',
      region: 'Estado', zona: 'Colonia', codigoPostal: 'C.P.',
      // Calculadora de impuestos por venta de inmueble.
      impuesto: { modulo: 'isr', etiqueta: 'ISR', nombre: 'ISR por enajenación' },
      // Módulos que solo existen con la ley de otro país.
      sinModulos: ['impuestos'],
      plan: { max: '$899', moneda: 'MXN' },
      ejemploBroq: 'Calcula el ISR de una venta de $2,400,000',
      monedaAvm: 'MXN',
      portales: ['Lamudi', 'Vivanuncios', 'Inmuebles24'],
    },
    CO: {
      codigo: 'CO', nombre: 'Colombia', locale: 'es-CO',
      moneda: 'COP', monedas: ['COP', 'USD'],
      lada: '57', digitosTel: 10, telEjemplo: '300 123 4567',
      zonaHoraria: 'America/Bogota',
      idFiscal: 'NIT', idPersona: 'cédula de ciudadanía', autoridadFiscal: 'DIAN',
      region: 'Departamento', zona: 'Barrio', codigoPostal: 'Código postal',
      impuesto: { modulo: 'impuestos', etiqueta: 'Impuestos', nombre: 'Ganancia ocasional' },
      sinModulos: ['isr'],
      plan: { max: 'US$49', moneda: 'USD' },
      ejemploBroq: 'Calcula la ganancia ocasional de una venta de $450.000.000',
      monedaAvm: 'COP',
      portales: ['Finca Raíz', 'Metrocuadrado', 'Ciencuadras'],
    },
    PE: {
      codigo: 'PE', nombre: 'Perú', locale: 'es-PE',
      moneda: 'PEN', monedas: ['PEN', 'USD'],
      lada: '51', digitosTel: 9, telEjemplo: '912 345 678',
      zonaHoraria: 'America/Lima',
      idFiscal: 'RUC', idPersona: 'DNI', autoridadFiscal: 'SUNAT',
      region: 'Departamento', zona: 'Distrito', codigoPostal: 'Código postal',
      impuesto: { modulo: 'impuestos', etiqueta: 'Impuestos', nombre: 'Renta de segunda categoría' },
      sinModulos: ['isr'],
      plan: { max: 'US$49', moneda: 'USD' },
      ejemploBroq: 'Calcula el impuesto de una venta de S/ 650,000',
      monedaAvm: 'USD',
      portales: ['Urbania', 'Adondevivir', 'Properati'],
    },
    AR: {
      codigo: 'AR', nombre: 'Argentina', locale: 'es-AR',
      moneda: 'ARS', monedas: ['USD', 'ARS'],
      lada: '54', digitosTel: 10, telEjemplo: '11 2345 6789',
      zonaHoraria: 'America/Argentina/Buenos_Aires',
      idFiscal: 'CUIT', idPersona: 'DNI', autoridadFiscal: 'ARCA',
      region: 'Provincia', zona: 'Barrio', codigoPostal: 'Código postal',
      impuesto: { modulo: 'impuestos', etiqueta: 'Impuestos', nombre: 'Impuesto cedular' },
      sinModulos: ['isr'],
      plan: { max: 'US$49', moneda: 'USD' },
      ejemploBroq: 'Calcula el impuesto cedular de una venta de US$ 180.000',
      monedaAvm: 'USD',
      portales: ['Zonaprop', 'Argenprop', 'Properati'],
    },
    CL: {
      codigo: 'CL', nombre: 'Chile', locale: 'es-CL',
      moneda: 'CLP', monedas: ['CLP', 'UF', 'USD'],
      lada: '56', digitosTel: 9, telEjemplo: '9 1234 5678',
      zonaHoraria: 'America/Santiago',
      idFiscal: 'RUT', idPersona: 'cédula de identidad', autoridadFiscal: 'SII',
      region: 'Región', zona: 'Comuna', codigoPostal: 'Código postal',
      impuesto: { modulo: 'impuestos', etiqueta: 'Impuestos', nombre: 'Mayor valor en bienes raíces' },
      sinModulos: ['isr'],
      plan: { max: 'US$49', moneda: 'USD' },
      ejemploBroq: 'Calcula el impuesto de una venta de 6.500 UF',
      monedaAvm: 'UF',
      portales: ['Portal Inmobiliario', 'TocToc', 'Yapo'],
    },
  };
  var ORDEN = ['MX', 'CO', 'PE', 'AR', 'CL'];
  var CLAVE = 'bk_pais';

  function valido(c) {
    c = String(c || '').trim().toUpperCase();
    return PAISES[c] ? c : '';
  }
  function leerLocal() {
    try { return valido(localStorage.getItem(CLAVE)); } catch (_) { return ''; }
  }

  /* País de la sesión: el del perfil (lo fija app-shell.js al cargar),
     si no, el que se eligió en el landing, si no, México. */
  function bkPais() {
    return valido(window.__BK_PAIS) || leerLocal() || 'MX';
  }
  function bkPaisElegido() { return leerLocal(); }
  function bkPaisGuardar(c) {
    c = valido(c);
    if (!c) return;
    try { localStorage.setItem(CLAVE, c); } catch (_) {}
  }
  function bkPaisCfg(c) { return PAISES[valido(c) || bkPais()]; }

  function bkDinero(n, moneda, opts) {
    var cfg = bkPaisCfg();
    moneda = moneda || cfg.moneda;
    var num = Number(n) || 0;
    if (moneda === 'UF') {
      return 'UF ' + num.toLocaleString(cfg.locale, { maximumFractionDigits: 2 });
    }
    try {
      return num.toLocaleString(cfg.locale, Object.assign({
        style: 'currency', currency: moneda, currencyDisplay: 'narrowSymbol',
        maximumFractionDigits: 0,
      }, opts || {}));
    } catch (_) {
      return '$' + Math.round(num).toLocaleString(cfg.locale);
    }
  }
  function bkNumero(n, dec) {
    return (Number(n) || 0).toLocaleString(bkPaisCfg().locale, { maximumFractionDigits: dec == null ? 0 : dec });
  }

  // Formato de números del país (1.500.000 en Colombia, Argentina y Chile).
  function bkLocale() { return bkPaisCfg().locale; }

  function bkModuloDisponible(key, c) {
    return bkPaisCfg(c).sinModulos.indexOf(key) === -1;
  }

  /* <select> de país listo para insertar. onCambio(codigo) se llama al
     elegir; la elección también se guarda para el registro. */
  function bkPaisSelector(opts) {
    opts = opts || {};
    var sel = document.createElement('select');
    sel.className = opts.className || 'bk-pais-select';
    sel.setAttribute('aria-label', 'País');
    ORDEN.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c;
      o.textContent = PAISES[c].nombre;
      sel.appendChild(o);
    });
    sel.value = opts.valor || bkPais();
    sel.addEventListener('change', function () {
      bkPaisGuardar(sel.value);
      if (opts.onCambio) opts.onCambio(sel.value);
    });
    return sel;
  }

  /* País al que pertenece un teléfono por su lada, o '' si no se sabe.
     Con "+" o "00" basta con la lada. Sin ellos, solo cuenta si el número
     trae lada + número completo (ej. 51 912 345 678): un número local de
     10 dígitos puede ser de México aunque empiece con 55 o 56. En Argentina
     los celulares llevan un 9 después de la lada (54 9 11 …) y en México
     algunos aún traen el 1 (52 1 443 …). */
  function bkPaisPorTelefono(tel) {
    var s = String(tel || '').trim();
    var dig = s.replace(/\D/g, '');
    var intl = /^(\+|00)/.test(s);
    if (/^00/.test(s)) dig = dig.slice(2);
    for (var i = 0; i < ORDEN.length; i++) {
      var p = PAISES[ORDEN[i]];
      if (dig.indexOf(p.lada) !== 0) continue;
      var resto = dig.length - p.lada.length;
      var extra = { AR: '9', MX: '1' }[p.codigo];
      if (intl ? resto >= 6 : (resto === p.digitosTel ||
          (extra && resto === p.digitosTel + 1 && dig.charAt(p.lada.length) === extra))) {
        return p.codigo;
      }
    }
    return '';
  }

  /* El teléfono sirve si tiene los dígitos del país (sin lada) o si trae
     la lada de alguno de los países de Broquer. */
  function bkTelefonoValido(tel, c) {
    var dig = String(tel || '').replace(/\D/g, '');
    return dig.length === bkPaisCfg(c).digitosTel || !!bkPaisPorTelefono(tel);
  }

  /* Teléfono en E.164 (+573001234567) con la lada del país elegido, para
     que el número diga de qué país es aunque la cuenta no tenga país.
     Mismo criterio que core/paises.py:telefono_e164. */
  function bkTelefonoE164(tel, c) {
    var s = String(tel || '').trim();
    var dig = s.replace(/\D/g, '');
    if (/^00/.test(s)) dig = dig.slice(2);
    if (!dig) return '';
    var cfg = bkPaisCfg(c);
    return '+' + (dig.length === cfg.digitosTel ? cfg.lada : '') + dig;
  }

  /* Pone la lada del país ("+57") pegada a la izquierda del campo de
     teléfono. Regresa una función para cambiarla cuando cambia el país. */
  function bkTelefonoLada(input, c) {
    if (!input) return function () {};
    var caja = document.createElement('div');
    caja.style.cssText = 'display:flex;gap:var(--sp-2,8px);align-items:stretch';
    var lada = document.createElement('span');
    lada.className = input.className;
    lada.setAttribute('aria-hidden', 'true');
    lada.style.cssText = 'flex:none;width:auto;display:flex;align-items:center;font-weight:600';
    input.parentNode.insertBefore(caja, input);
    caja.appendChild(lada);
    caja.appendChild(input);
    input.style.flex = '1';
    input.style.minWidth = '0';
    var fijar = function (pais) {
      var cfg = bkPaisCfg(pais);
      lada.textContent = '+' + cfg.lada;
    };
    fijar(c);
    return fijar;
  }

  /* Si el teléfono es de otro país que el elegido, pregunta antes de seguir:
     "Notamos que tu teléfono es de Perú pero seleccionaste México". Regresa
     una promesa con el país con que se queda la cuenta, o null si la
     persona cerró la ventana para corregir el teléfono. Sin conflicto
     resuelve de inmediato con el país elegido. */
  function bkPaisAvisoTelefono(tel, elegido) {
    elegido = valido(elegido) || bkPais();
    var delTel = bkPaisPorTelefono(tel);
    if (!delTel || delTel === elegido) return Promise.resolve(elegido);
    return new Promise(function (resolver) {
      var ov = document.createElement('div');
      ov.className = 'bk-overlay is-open';
      ov.setAttribute('role', 'dialog');
      ov.setAttribute('aria-modal', 'true');
      ov.setAttribute('aria-labelledby', 'bk-pais-aviso-t');
      ov.style.zIndex = '2147483000';
      ov.innerHTML =
        '<div class="bk-modal" style="max-width:440px">' +
          '<div class="bk-modal__head"><div class="bk-modal__title" id="bk-pais-aviso-t">Revisa tu país</div></div>' +
          '<div class="bk-modal__body">' +
            '<p style="margin:0 0 var(--sp-4);color:var(--ink-2)">Notamos que tu teléfono es de <strong>' +
              PAISES[delTel].nombre + '</strong> pero seleccionaste <strong>' + PAISES[elegido].nombre +
              '</strong>. ¿Deseas continuar o cambiar de país?</p>' +
            '<label for="bk-pais-aviso-sel" style="display:block;margin-bottom:var(--sp-2);font-weight:600">País donde trabajas</label>' +
          '</div>' +
          '<div class="bk-modal__foot" style="display:flex;gap:var(--sp-2);flex-wrap:wrap;justify-content:flex-end">' +
            '<button type="button" class="bk-btn bk-btn--ghost" data-r="seguir"></button>' +
            '<button type="button" class="bk-btn bk-btn--forest" data-r="cambiar"></button>' +
          '</div>' +
        '</div>';
      var sel = document.createElement('select');
      sel.id = 'bk-pais-aviso-sel';
      sel.className = 'bk-select';
      sel.style.width = '100%';
      ORDEN.forEach(function (c) {
        var o = document.createElement('option');
        o.value = c;
        o.textContent = PAISES[c].nombre;
        sel.appendChild(o);
      });
      sel.value = delTel;
      ov.querySelector('.bk-modal__body').appendChild(sel);
      var bSeguir = ov.querySelector('[data-r="seguir"]');
      var bCambiar = ov.querySelector('[data-r="cambiar"]');
      bSeguir.textContent = 'Continuar con ' + PAISES[elegido].nombre;
      var rotular = function () {
        bCambiar.textContent = sel.value === elegido ? 'Continuar con ' + PAISES[elegido].nombre : 'Cambiar a ' + PAISES[sel.value].nombre;
      };
      sel.addEventListener('change', rotular);
      rotular();
      var cerrar = function (c) {
        document.removeEventListener('keydown', tecla);
        ov.remove();
        resolver(c);
      };
      var tecla = function (e) { if (e.key === 'Escape') cerrar(null); };
      document.addEventListener('keydown', tecla);
      ov.addEventListener('click', function (e) { if (e.target === ov) cerrar(null); });
      bSeguir.addEventListener('click', function () { cerrar(elegido); });
      bCambiar.addEventListener('click', function () { cerrar(sel.value); });
      document.body.appendChild(ov);
      bCambiar.focus();
    });
  }

  /* Lo llama app-shell.js al cargar el perfil. `guardado` es la fila
     {pais} de usuarios (o nada). Si la cuenta aún no tiene país (recién
     creada), se fija UNA vez con el que eligió en el landing; después la
     base de datos ya no deja cambiarlo desde el navegador. Los módulos
     que no aplican en el país se suman a los apagados de la cuenta. */
  function bkPaisSesion(perfil, guardado, fijar) {
    var c = valido(guardado && guardado.pais);
    // Cuenta nueva que entró sin elegir país (p. ej. con Google desde la
    // app): se le pregunta una vez. `guardado` existe solo si la columna
    // pais existe; sin ella no se pregunta nada.
    if (!c && guardado && !leerLocal()) preguntarPais(fijar);
    if (!c) {
      c = leerLocal() || 'MX';
      if (leerLocal()) { try { fijar(c); } catch (_) {} }
    }
    window.__BK_PAIS = c;
    perfil.pais = c;
    perfil.modulos_desactivados = (perfil.modulos_desactivados || []).concat(PAISES[c].sinModulos);
    bkPaisAplicarEnlaces(document);
    try { document.dispatchEvent(new CustomEvent('bk:pais', { detail: c })); } catch (_) {}
    return c;
  }

  /* Ventana que pregunta el país a una cuenta que todavía no lo tiene. Al
     elegir, se guarda en el perfil y se recarga para pintar ese país. */
  function preguntarPais(fijar) {
    var pintar = function () {
      var ov = document.createElement('div');
      ov.className = 'bk-overlay is-open';
      ov.setAttribute('role', 'dialog');
      ov.setAttribute('aria-modal', 'true');
      ov.style.zIndex = '2147483000';
      ov.innerHTML =
        '<div class="bk-modal" style="max-width:420px">' +
          '<div class="bk-modal__head"><div class="bk-modal__title">¿En qué país trabajas?</div></div>' +
          '<div class="bk-modal__body">' +
            '<p style="margin:0 0 var(--sp-4);color:var(--ink-2)">Con esto ajustamos moneda, impuestos, contratos y ' +
            'documentos. Solo se pregunta una vez.</p>' +
          '</div>' +
          '<div class="bk-modal__foot"><button type="button" class="bk-btn bk-btn--forest">Continuar</button></div>' +
        '</div>';
      var sel = bkPaisSelector({ className: 'bk-select', valor: 'MX' });
      sel.style.width = '100%';
      ov.querySelector('.bk-modal__body').appendChild(sel);
      ov.querySelector('button').addEventListener('click', function () {
        var b = this;
        b.disabled = true;
        bkPaisGuardar(sel.value);
        Promise.resolve()
          .then(function () { return fijar(sel.value); })
          .catch(function () {})
          .then(function () { location.reload(); });
      });
      document.body.appendChild(ov);
    };
    if (document.body) pintar();
    else document.addEventListener('DOMContentLoaded', pintar);
  }

  /* Enlaces fijos a módulos (tarjetas del inicio): se esconden los que no
     aplican en el país. */
  function bkPaisAplicarEnlaces(raiz) {
    var aplicar = function () {
      bkPaisCfg().sinModulos.forEach(function (k) {
        raiz.querySelectorAll('a.home-card[href="' + k + '.html"]').forEach(function (a) { a.style.display = 'none'; });
      });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', aplicar);
    else aplicar();
  }

  /* Página a la que se manda a quien abre un módulo que no aplica en su
     país (ej. isr.html desde Colombia → impuestos.html). null si sí aplica. */
  function bkPaisAlterno(key) {
    var cfg = bkPaisCfg();
    if (cfg.sinModulos.indexOf(key) === -1) return null;
    return (key === 'isr' || key === 'impuestos') ? cfg.impuesto.modulo + '.html' : 'index.html';
  }

  window.BK_PAISES = PAISES;
  window.bkPaisAlterno = bkPaisAlterno;
  window.bkPaisSesion = bkPaisSesion;
  window.bkPaisAplicarEnlaces = bkPaisAplicarEnlaces;
  window.BK_PAISES_ORDEN = ORDEN;
  window.bkPais = bkPais;
  window.bkPaisElegido = bkPaisElegido;
  window.bkPaisGuardar = bkPaisGuardar;
  window.bkPaisCfg = bkPaisCfg;
  window.bkDinero = bkDinero;
  window.bkNumero = bkNumero;
  window.bkLocale = bkLocale;
  window.bkModuloDisponible = bkModuloDisponible;
  window.bkPaisSelector = bkPaisSelector;
  window.bkPaisPorTelefono = bkPaisPorTelefono;
  window.bkTelefonoValido = bkTelefonoValido;
  window.bkTelefonoE164 = bkTelefonoE164;
  window.bkTelefonoLada = bkTelefonoLada;
  window.bkPaisAvisoTelefono = bkPaisAvisoTelefono;
})();
