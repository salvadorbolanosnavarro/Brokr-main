// Broquer · Archivos seguros — validación de archivos ANTES de subirlos a
// Supabase Storage desde el navegador. Espejo de core/file_validation.py
// (backend): mismas listas blancas por módulo, mismas extensiones prohibidas
// y la misma regla de fondo: el tipo real lo deciden los primeros bytes del
// archivo, no su extensión ni el tipo que diga el navegador.
//
// Esta es la capa amable (mensajes claros, sin esperar al servidor). La capa
// que no se puede saltar son las reglas del bucket en Supabase
// (sql-manual/20261106-archivos-seguros-buckets.sql).
//
// Uso:  const v = await bkArchivos.validar(file, 'foto_propiedad');
//       → { tipo, mime, extension, nombreInterno, nombreOriginal }
//       o lanza Error con el mensaje en español para el usuario.
(function () {
  'use strict';
  if (window.bkArchivos) return;

  var MB = 1024 * 1024;
  var TIPOS = {
    jpg: ['image/jpeg', 'jpg', ['jpg', 'jpeg', 'jfif', 'jpe']],
    png: ['image/png', 'png', ['png']],
    webp: ['image/webp', 'webp', ['webp']],
    gif: ['image/gif', 'gif', ['gif']],
    heic: ['image/heic', 'heic', ['heic', 'heif']],
    pdf: ['application/pdf', 'pdf', ['pdf']],
    mp4: ['video/mp4', 'mp4', ['mp4', 'm4v']],
    mov: ['video/quicktime', 'mov', ['mov', 'qt']],
    '3gp': ['video/3gpp', '3gp', ['3gp', '3gpp']],
    webm: ['video/webm', 'webm', ['webm']],
    docx: ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx', ['docx', 'dotx']],
    xlsx: ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx', ['xlsx']],
    pptx: ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'pptx', ['pptx']],
    doc: ['application/msword', 'doc', ['doc']],
    xls: ['application/vnd.ms-excel', 'xls', ['xls']],
    ppt: ['application/vnd.ms-powerpoint', 'ppt', ['ppt']],
    zip: ['application/zip', 'zip', ['zip']],
    txt: ['text/plain', 'txt', ['txt']],
    csv: ['text/csv', 'csv', ['csv']]
  };

  var PELIGROSAS = ('html htm xhtml xht shtml mhtml mht webarchive eml svg svgz xml xsl xslt rss atom ' +
    'js mjs cjs jsx ts tsx vbs vbe wsf wsh hta exe msi bat cmd com scr pif cpl dll sys lnk reg ' +
    'sh bash zsh ps1 psm1 jar apk app dmg pkg deb rpm php phtml php3 php4 php5 phar asp aspx jsp ' +
    'cgi pl py rb swf url iso svc htaccess').split(' ');

  var IMAGENES = ['jpg', 'png', 'webp', 'gif', 'heic'];
  var PERFILES = {
    foto_propiedad: { tipos: IMAGENES, max: 25 * MB, desc: 'fotos JPG, PNG, WebP, GIF o HEIC' },
    documento_propiedad: { tipos: ['pdf', 'jpg', 'png', 'webp'], max: 15 * MB, desc: 'PDF o fotos JPG, PNG o WebP' },
    adjunto_historial: {
      tipos: IMAGENES.concat(['pdf', 'mp4', 'mov', '3gp', 'webm', 'docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt', 'zip', 'txt', 'csv']),
      max: 25 * MB, desc: 'fotos, videos, PDF, Word, Excel, PowerPoint, ZIP o texto'
    }
  };

  var MARCAS = ['<!doctype', '<html', '<head', '<body', '<script', '<svg', '<?xml', '<iframe', '<object',
    '<embed', '<meta', '<link', '<style', '<img', '<a ', '<div', '<form', '<base', '<xml', '<xsl',
    'javascript:', 'mime-version:', 'content-type: multipart'];

  function extensiones(nombre) {
    var base = String(nombre || '').split(/[\\/]/).pop().trim().replace(/^\.+|\.+$/g, '');
    return base.split('.').slice(1).map(function (p) { return p.trim().toLowerCase(); }).filter(Boolean);
  }
  function nombrePeligroso(nombre) {
    return extensiones(nombre).some(function (e) { return PELIGROSAS.indexOf(e) !== -1; });
  }
  function empieza(b, firma, desde) {
    desde = desde || 0;
    for (var i = 0; i < firma.length; i++) if (b[desde + i] !== firma[i]) return false;
    return true;
  }
  function ascii(b, desde, hasta) {
    var s = ''; for (var i = desde; i < hasta && i < b.length; i++) s += String.fromCharCode(b[i]); return s;
  }
  function pareceMarkup(b) {
    var s = '';
    for (var i = 0; i < b.length; i++) if (b[i] !== 0) s += String.fromCharCode(b[i]);
    s = s.replace(/^ï»¿|^ÿþ|^þÿ/, '').toLowerCase();
    return MARCAS.some(function (m) { return s.indexOf(m) !== -1; });
  }
  function pareceTexto(b) {
    for (var i = 0; i < b.length; i++) if (b[i] === 0) return false;
    return true;
  }

  // Tipo real por los primeros bytes (null si no se reconoce).
  function detectar(b, ext) {
    if (empieza(b, [0xFF, 0xD8, 0xFF])) return 'jpg';
    if (empieza(b, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) return 'png';
    var cab = ascii(b, 0, 12);
    if (cab.slice(0, 6) === 'GIF87a' || cab.slice(0, 6) === 'GIF89a') return 'gif';
    if (cab.slice(0, 4) === 'RIFF' && cab.slice(8, 12) === 'WEBP') return 'webp';
    if (cab.slice(0, 5) === '%PDF-') return 'pdf';
    if (cab.slice(4, 8) === 'ftyp') {
      var marca = cab.slice(8, 12);
      if (['heic', 'heix', 'hevc', 'hevx', 'heim', 'heis', 'mif1', 'msf1'].indexOf(marca) !== -1) return 'heic';
      if (marca === 'avif') return null;
      if (marca === 'qt  ') return 'mov';
      if (marca.slice(0, 2) === '3g') return '3gp';
      if (['M4A ', 'M4B ', 'M4P '].indexOf(marca) !== -1) return null;
      return 'mp4';
    }
    if (empieza(b, [0x1A, 0x45, 0xDF, 0xA3])) return 'webm';
    if (empieza(b, [0x50, 0x4B, 0x03, 0x04])) {
      // Word/Excel/PowerPoint modernos son ZIP por dentro. En el navegador se
      // distinguen por extensión; el contenido ya se confirmó como ZIP.
      return ['docx', 'xlsx', 'pptx'].indexOf(ext) !== -1 ? ext : (ext === 'dotx' ? 'docx' : 'zip');
    }
    if (empieza(b, [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])) {
      return ['doc', 'xls', 'ppt'].indexOf(ext) !== -1 ? ext : null;
    }
    if (b.length && pareceTexto(b) && !pareceMarkup(b)) return ext === 'csv' ? 'csv' : 'txt';
    return null;
  }

  function nombreInterno(ext) {
    var id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID().replace(/-/g, '')
      : Array.from((window.crypto || {}).getRandomValues ? crypto.getRandomValues(new Uint8Array(16)) : [])
        .map(function (n) { return ('0' + n.toString(16)).slice(-2); }).join('') || (Date.now().toString(36) + Math.random().toString(36).slice(2));
    return id + '.' + String(ext || 'bin').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 8);
  }

  function nombreOriginal(nombre, ext) {
    var base = String(nombre || '').split(/[\\/]/).pop().normalize('NFKC')
      .replace(/[\u0000-\u001f\u007f<>"'`]/g, '').replace(/\s+/g, ' ').trim();
    return (base || ('archivo.' + ext)).slice(0, 120);
  }

  function textoMb(n) { return n >= MB ? Math.floor(n / MB) + ' MB' : Math.max(1, Math.floor(n / 1024)) + ' KB'; }

  async function validar(file, perfil) {
    var regla = PERFILES[perfil];
    if (!regla) throw new Error('Perfil de archivo desconocido: ' + perfil);
    var soloSe = 'Solo se aceptan ' + regla.desc + '.';
    var nombre = (file && file.name) || '';
    if (!file || !file.size) throw new Error('El archivo llegó vacío. Vuelve a seleccionarlo.');
    if (file.size > regla.max) throw new Error('El archivo pesa más de ' + textoMb(regla.max) + '. Sube uno más ligero.');
    if (nombrePeligroso(nombre)) {
      throw new Error('Por seguridad no se aceptan páginas web (HTML), SVG, scripts ni programas, aunque tengan otra extensión. ' + soloSe);
    }
    var exts = extensiones(nombre);
    var ext = exts.length ? exts[exts.length - 1] : '';
    var bytes = new Uint8Array(await file.slice(0, 4096).arrayBuffer());
    var tipo = detectar(bytes, ext);
    if (!tipo || regla.tipos.indexOf(tipo) === -1 || !TIPOS[tipo]) {
      throw new Error('Ese tipo de archivo no está permitido aquí. ' + soloSe);
    }
    if ((tipo === 'txt' || tipo === 'csv') && ext !== 'txt' && ext !== 'csv') {
      throw new Error('Ese tipo de archivo no está permitido aquí. ' + soloSe);
    }
    var t = TIPOS[tipo];
    return { tipo: tipo, mime: t[0], extension: t[1], nombreInterno: nombreInterno(t[1]), nombreOriginal: nombreOriginal(nombre, t[1]) };
  }

  window.bkArchivos = {
    validar: validar,
    nombreInterno: nombreInterno,
    nombrePeligroso: nombrePeligroso,
    PERFILES: PERFILES,
    AVISO_PUBLICO: 'Este archivo será visible para cualquier persona con la liga.'
  };
})();
