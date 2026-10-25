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

  /* Lo llama app-shell.js al cargar el perfil. `guardado` es la fila
     {pais} de usuarios (o nada). Si la cuenta aún no tiene país (recién
     creada), se fija UNA vez con el que eligió en el landing; después la
     base de datos ya no deja cambiarlo desde el navegador. Los módulos
     que no aplican en el país se suman a los apagados de la cuenta. */
  function bkPaisSesion(perfil, guardado, fijar) {
    var c = valido(guardado && guardado.pais);
    if (!c) {
      c = leerLocal() || 'MX';
      try { fijar(c); } catch (_) {}
    }
    window.__BK_PAIS = c;
    perfil.pais = c;
    perfil.modulos_desactivados = (perfil.modulos_desactivados || []).concat(PAISES[c].sinModulos);
    bkPaisAplicarEnlaces(document);
    try { document.dispatchEvent(new CustomEvent('bk:pais', { detail: c })); } catch (_) {}
    return c;
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
  window.bkModuloDisponible = bkModuloDisponible;
  window.bkPaisSelector = bkPaisSelector;
})();
