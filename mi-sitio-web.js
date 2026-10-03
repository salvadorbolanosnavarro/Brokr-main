// ─────────────────────────────────────────────────────────────────────────
// mi-sitio-web.js · Sitio web completo (routers/sitios.py) dentro de Mi sitio.
//   Pestañas: Mi perfil (lo que ya existía en mi-sitio.html) · Sitio de la
//   inmobiliaria (sólo el administrador lo edita) · Mi sitio web de asesor.
//   Cada sitio: link de prueba, identidad, contacto, contenido, SEO,
//   analítica (GA4 / Pixel), código propio (admin), páginas con editor de
//   texto enriquecido y dominio propio con instrucciones DNS.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  var esc = function (s) { return window.bkEsc(s); };
  var estado = { tab: 'perfil', datos: null, paginas: [], dns: null };
  var API = window.API_BASE || 'https://api.broquer.app';

  function montar() {
    var body = document.getElementById('ms-body');
    if (!body || document.getElementById('msw-tabs')) return;
    body.insertAdjacentHTML('beforebegin',
      '<div class="msw-tabswrap"><div class="bk-seg msw-tabs" id="msw-tabs" role="tablist">' +
        '<button class="bk-seg__btn is-active" data-t="perfil">Mi perfil</button>' +
        '<button class="bk-seg__btn" data-t="organizacion">Sitio de la inmobiliaria</button>' +
        '<button class="bk-seg__btn" data-t="agente">Mi sitio web</button>' +
      '</div></div><div class="ms-body msw-body" id="msw-body" hidden></div>');
    document.getElementById('msw-tabs').onclick = function (ev) {
      var b = ev.target.closest('[data-t]'); if (!b) return;
      estado.tab = b.dataset.t;
      [].forEach.call(this.children, function (x) { x.classList.toggle('is-active', x === b); });
      body.hidden = estado.tab !== 'perfil';
      document.getElementById('msw-body').hidden = estado.tab === 'perfil';
      if (estado.tab !== 'perfil') cargar();
    };
    var t = new URLSearchParams(location.search).get('sitio');
    if (t === 'organizacion' || t === 'agente') document.querySelector('#msw-tabs [data-t="' + t + '"]').click();
  }

  async function cargar() {
    var cont = document.getElementById('msw-body');
    cont.innerHTML = '<div class="ms-loading">Cargando…</div>';
    try { estado.datos = await window.bkApi('/sitios/mios'); }
    catch (e) { cont.innerHTML = '<div class="ms-loading">' + esc(e.message) + '</div>'; return; }
    var s = estado.datos[estado.tab];
    estado.paginas = [];
    estado.dns = null;
    if (s) { try { estado.paginas = (await window.bkApi('/sitios/' + s.id + '/paginas')).paginas || []; } catch (e) {} }
    pintar();
  }

  function campo(id, etiqueta, valor, extra) {
    extra = extra || {};
    var tipo = extra.tipo || 'text';
    return '<label class="bk-field' + (extra.full ? ' full' : '') + '"><span class="bk-label">' + esc(etiqueta) + '</span>' +
      '<input class="bk-input" id="' + id + '" type="' + tipo + '" value="' + esc(valor || '') + '"' +
      (extra.ph ? ' placeholder="' + esc(extra.ph) + '"' : '') + (extra.dis ? ' disabled' : '') + '/>' +
      (extra.hint ? '<span class="ms-hint">' + extra.hint + '</span>' : '') + '</label>';
  }
  function interruptor(id, etiqueta, on, hint, dis) {
    return '<label class="bk-switch msw-switch"><input type="checkbox" id="' + id + '"' + (on ? ' checked' : '') + (dis ? ' disabled' : '') + '/>' +
      '<span class="bk-switch__track"></span><span><b>' + esc(etiqueta) + '</b>' + (hint ? '<br><span class="ms-hint">' + esc(hint) + '</span>' : '') + '</span></label>';
  }
  function imagen(id, etiqueta, url, dis) {
    return '<div class="bk-field msw-img"><span class="bk-label">' + esc(etiqueta) + '</span><div class="msw-img__row">' +
      '<div class="msw-img__prev" id="' + id + '-prev">' + (url ? '<img src="' + esc(url) + '" alt=""/>' : 'Sin imagen') + '</div>' +
      '<input type="hidden" id="' + id + '" value="' + esc(url || '') + '"/>' +
      (dis ? '' : '<label class="bk-btn bk-btn--ghost bk-btn--sm">Subir<input type="file" accept="image/*" hidden data-img="' + id + '"/></label>' +
        (url ? '<button class="bk-btn bk-btn--quiet bk-btn--sm" data-quitar-img="' + id + '">Quitar</button>' : '')) +
      '</div></div>';
  }
  function barraEditor(id) {
    var b = function (cmd, txt, val) { return '<button type="button" class="msw-ed__btn" data-ed="' + id + '" data-cmd="' + cmd + '"' + (val ? ' data-val="' + val + '"' : '') + '>' + txt + '</button>'; };
    return '<div class="msw-ed__bar">' + b('bold', '<b>B</b>') + b('italic', '<i>I</i>') + b('formatBlock', 'Título', 'h2') + b('formatBlock', 'Subtítulo', 'h3') +
      b('formatBlock', 'Párrafo', 'p') + b('insertUnorderedList', 'Lista') + b('insertOrderedList', 'Lista 1-2-3') + b('formatBlock', 'Cita', 'blockquote') +
      b('createLink', 'Liga') + b('insertImage', 'Imagen') + b('removeFormat', 'Quitar formato') + '</div>';
  }
  function editor(id, html, dis) {
    return '<div class="msw-ed">' + (dis ? '' : barraEditor(id)) + '<div class="msw-ed__area prosa" id="' + id + '" contenteditable="' + (dis ? 'false' : 'true') + '">' + (html || '') + '</div></div>';
  }

  function pintar() {
    var cont = document.getElementById('msw-body');
    var d = estado.datos, tipo = estado.tab, s = d[tipo] || {};
    var esAdmin = d.es_admin, soloLectura = tipo === 'organizacion' && !esAdmin;
    var dis = soloLectura;
    var html = '';
    if (soloLectura) html += '<div class="msw-aviso">El sitio de la inmobiliaria lo configura el administrador de la cuenta. Aquí puedes verlo y compartir su link.</div>';
    var urlPrueba = s.url_prueba || '';
    html += '<div class="ms-activar"><div class="ms-activar__info"><h3>' + (tipo === 'organizacion' ? 'Sitio web de la inmobiliaria' : 'Tu sitio web de asesor') + '</h3>' +
      '<div class="ms-activar__url">' + (s.url_publica ? '<a href="' + esc(s.url_publica) + '" target="_blank" rel="noopener">' + esc(s.url_publica.replace('https://', '')) + '</a>' : 'Aún no lo has creado') + '</div>' +
      '<div class="ms-activar__hint">' + (tipo === 'organizacion' ? 'Muestra todo el inventario activo de la inmobiliaria.' : 'Muestra los inmuebles que captaste o tienes asignados.') + '</div></div>' +
      interruptor('msw-activo', 'Publicado', s.activo, '', dis) + '</div>';

    html += sec('Link del sitio', '<div class="ms-row">' +
      campo('msw-slug', 'Link de prueba', s.slug || sugerirSlug(), { ph: 'mi-inmobiliaria', dis: dis,
        hint: 'Tu sitio queda en ' + esc(API.replace('https://', '')) + '/s/<b id="msw-slug-ver">' + esc(s.slug || sugerirSlug()) + '</b> mientras conectas tu dominio.' }) + '</div>' +
      (urlPrueba ? '<p class="ms-hint"><a href="' + esc(urlPrueba) + '" target="_blank" rel="noopener">Abrir dirección de prueba</a></p>' : ''));

    html += sec('Identidad', '<div class="ms-row">' +
      campo('msw-nombre', 'Nombre', s.nombre, { dis: dis }) + campo('msw-eslogan', 'Frase de portada', s.eslogan, { dis: dis, ph: 'Encuentra tu próximo hogar' }) +
      '</div><div class="ms-row">' + imagen('msw-logo', 'Logotipo', s.logo_url, dis) + imagen('msw-favicon', 'Ícono de pestaña (favicon)', s.favicon_url, dis) +
      imagen('msw-hero', 'Foto de portada', s.hero_url, dis) + '</div><div class="ms-row">' +
      campo('msw-c1', 'Color principal', s.color_primario || '#0b2545', { tipo: 'color', dis: dis }) +
      campo('msw-c2', 'Color de acento', s.color_secundario || '#13a89e', { tipo: 'color', dis: dis }) +
      '<label class="bk-field"><span class="bk-label">Plantilla</span><select class="bk-select" id="msw-plantilla"' + (dis ? ' disabled' : '') + '>' +
        '<option value="clasica"' + (s.plantilla !== 'moderna' ? ' selected' : '') + '>Clásica</option><option value="moderna"' + (s.plantilla === 'moderna' ? ' selected' : '') + '>Moderna</option></select></label></div>');

    var r = s.redes || {};
    html += sec('Contacto', '<div class="ms-row">' +
      campo('msw-wa', 'WhatsApp', s.whatsapp, { tipo: 'tel', dis: dis, ph: '443 123 4567' }) + campo('msw-tel', 'Teléfono', s.telefono, { tipo: 'tel', dis: dis }) +
      campo('msw-email', 'Correo', s.email, { tipo: 'email', dis: dis }) + campo('msw-dir', 'Dirección de la oficina', s.direccion, { dis: dis, full: true }) + '</div>' +
      '<div class="ms-row">' + ['facebook', 'instagram', 'tiktok', 'youtube', 'linkedin', 'x'].map(function (k) {
        return campo('msw-red-' + k, k === 'x' ? 'X (Twitter)' : k.charAt(0).toUpperCase() + k.slice(1), r[k], { tipo: 'url', dis: dis, ph: 'https://' });
      }).join('') + '</div>');

    html += sec('Contenido', '<div class="msw-switches">' +
      interruptor('msw-asesor', 'Mostrar al asesor en cada inmueble', s.mostrar_asesor !== false, 'Foto, nombre y WhatsApp del agente asignado.', dis) +
      interruptor('msw-bolsa', 'Incluir inmuebles de la Bolsa Broquer', s.incluir_bolsa, 'Suma inmuebles de otras inmobiliarias que comparten comisión.', dis) +
      interruptor('msw-trad', 'Traductor de idioma', s.traductor, 'Botón para ver el sitio en inglés y otros idiomas.', dis) + '</div>' +
      '<div class="bk-field"><span class="bk-label">Acerca de nosotros</span>' + editor('msw-acerca', s.acerca_html, dis) + '</div>');

    html += sec('Buscadores (SEO)', '<div class="ms-row">' +
      campo('msw-seo-t', 'Título para Google', s.seo_titulo, { dis: dis, full: true, ph: 'Casas en venta en Morelia | ' + (s.nombre || 'Mi inmobiliaria') }) +
      '<label class="bk-field full"><span class="bk-label">Descripción para Google</span><textarea class="bk-textarea" id="msw-seo-d" rows="2" maxlength="300"' + (dis ? ' disabled' : '') + '>' + esc(s.seo_descripcion || '') + '</textarea></label></div>' +
      '<p class="ms-hint">El mapa del sitio (sitemap.xml) y robots.txt se generan solos. Cada inmueble lleva su imagen y descripción para WhatsApp y Facebook.</p>');

    html += sec('Analítica', '<div class="ms-row">' +
      campo('msw-ga4', 'Google Analytics 4 (ID de medición)', s.ga4_id, { dis: dis, ph: 'G-XXXXXXXXXX' }) +
      campo('msw-pixel', 'Pixel de Meta (ID)', s.meta_pixel_id, { dis: dis, ph: '123456789012345' }) + '</div>');

    if (esAdmin) {
      html += sec('Código propio (sólo administrador)', '<p class="ms-hint">Se pega tal cual en todas las páginas del sitio. Úsalo sólo con código de confianza (chat, verificación de Google, etiquetas de anuncios).</p>' +
        '<label class="bk-field"><span class="bk-label">Dentro de &lt;head&gt;</span><textarea class="bk-textarea msw-code" id="msw-head" rows="4" spellcheck="false">' + esc(s.codigo_head || '') + '</textarea></label>' +
        '<label class="bk-field"><span class="bk-label">Al final de &lt;body&gt;</span><textarea class="bk-textarea msw-code" id="msw-bodycode" rows="4" spellcheck="false">' + esc(s.codigo_body || '') + '</textarea></label>');
    }

    if (!dis) html += '<div class="ms-guardar-bar"><button class="bk-btn bk-btn--primary" id="msw-guardar">Guardar sitio</button></div>';

    if (s.id) {
      html += sec('Páginas propias', '<p class="ms-hint">Crea páginas como "Vende con nosotros", "Avalúos" o "Aviso de privacidad". Las publicadas aparecen en el sitio y, si quieres, en el menú.</p>' +
        '<div class="msw-paginas">' + (estado.paginas.length ? estado.paginas.map(function (p) {
          return '<div class="msw-pagina"><div><b>' + esc(p.titulo) + '</b><div class="ms-hint">/p/' + esc(p.slug) + ' · ' + (p.publicada ? 'Publicada' : 'Borrador') + (p.en_menu ? ' · En el menú' : '') + '</div></div>' +
            (dis ? '<a class="bk-btn bk-btn--quiet bk-btn--sm" target="_blank" rel="noopener" href="' + esc(s.url_publica + '/p/' + p.slug) + '">Ver</a>' :
              '<button class="bk-btn bk-btn--ghost bk-btn--sm" data-editar-pagina="' + esc(p.id) + '">Editar</button>') + '</div>';
        }).join('') : '<div class="ms-hint">Aún no hay páginas.</div>') + '</div>' +
        (dis ? '' : '<button class="bk-btn bk-btn--ghost bk-btn--sm" id="msw-nueva-pagina" style="margin-top:12px">Nueva página</button>'));
      html += sec('Dominio propio', pintarDominio(s, dis));
    }
    cont.innerHTML = html;
    conectar(s, dis);
  }

  function sec(titulo, cuerpo) { return '<section class="ms-section"><span class="bk-eyebrow">' + esc(titulo) + '</span>' + cuerpo + '</section>'; }

  function sugerirSlug() {
    var n = (document.querySelector('#ms-nombre, #f-nombre') || {}).value || '';
    return n.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
  }

  function pintarDominio(s, dis) {
    var d = estado.datos;
    var est = { activo: 'Activo con candado (HTTPS)', pendiente: 'Esperando el registro DNS', sin_dominio: '' }[s.dominio_estado || 'sin_dominio'];
    var h = '';
    if (!d.dominios_disponibles) h += '<div class="msw-aviso">La conexión automática de dominios aún no está encendida en Broquer. Puedes dejar tu dominio registrado y se activará en cuanto esté lista.</div>';
    if (s.dominio) {
      h += '<div class="msw-dom"><div><b>' + esc(s.dominio) + '</b><div class="ms-hint ' + (s.dominio_estado === 'activo' ? 'is-ok' : '') + '">' + esc(est) + '</div>' +
        (s.dominio_detalle ? '<div class="ms-hint">' + esc(s.dominio_detalle) + '</div>' : '') + '</div>' +
        (dis ? '' : '<div class="msw-dom__acc"><button class="bk-btn bk-btn--ghost bk-btn--sm" id="msw-dom-verificar">Verificar ahora</button>' +
          '<button class="bk-btn bk-btn--quiet bk-btn--sm" id="msw-dom-quitar">Desconectar</button></div>') + '</div>';
      h += tablaDns(estado.dns || instrucciones(s.dominio));
    } else if (!dis) {
      h += '<p class="ms-hint">¿Ya tienes un dominio (por ejemplo www.miinmobiliaria.mx)? Escríbelo y te decimos exactamente qué registro poner donde lo compraste (GoDaddy, Google, Hostinger, Akky…).</p>' +
        '<div class="msw-dom-form"><input class="bk-input" id="msw-dominio" placeholder="www.miinmobiliaria.mx" inputmode="url" autocapitalize="off"/>' +
        '<button class="bk-btn bk-btn--primary bk-btn--sm" id="msw-dom-conectar">Conectar</button></div>';
    } else {
      h += '<p class="ms-hint">Sin dominio propio.</p>';
    }
    return h;
  }
  function instrucciones(dom) {
    var destino = estado.datos.cname_destino;
    if (dom.split('.').length === 2) return [{ tipo: 'CNAME (o ALIAS/ANAME)', nombre: '@', valor: destino, nota: 'Si tu proveedor no permite CNAME en la raíz, usa ALIAS/ANAME o usa www.' }, { tipo: 'CNAME', nombre: 'www', valor: destino, nota: '' }];
    return [{ tipo: 'CNAME', nombre: dom.split('.')[0], valor: destino, nota: '' }];
  }
  function tablaDns(filas) {
    return '<p class="ms-hint" style="margin-top:12px">En el panel de tu dominio crea este registro (puede tardar de minutos a 24 horas):</p>' +
      '<div class="msw-dns">' + filas.map(function (f) {
        return '<div class="msw-dns__fila"><div><span class="ms-hint">Tipo</span><b>' + esc(f.tipo) + '</b></div><div><span class="ms-hint">Nombre / Host</span><b>' + esc(f.nombre) + '</b></div>' +
          '<div><span class="ms-hint">Valor / Apunta a</span><b class="msw-copiable" data-copiar="' + esc(f.valor) + '">' + esc(f.valor) + '</b></div>' +
          (f.nota ? '<div class="ms-hint msw-dns__nota">' + esc(f.nota) + '</div>' : '') + '</div>';
      }).join('') + '</div>';
  }

  async function subirImagen(file, id) {
    var prev = document.getElementById(id + '-prev');
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { window.bkToast('La imagen pesa más de 5 MB.'); return; }
    prev.textContent = 'Subiendo…';
    try {
      var sb = window.brokrSb, tok = await sb.ensureToken();
      var ext = (file.name.split('.').pop() || 'png').toLowerCase().replace(/[^a-z0-9]/g, '');
      var nombre = 'sitio_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8) + '.' + ext;
      var r = await fetch(sb.url + '/storage/v1/object/fotos-propiedades/' + nombre, {
        method: 'POST', headers: { apikey: sb.key, Authorization: 'Bearer ' + tok, 'Content-Type': file.type, 'x-upsert': 'true' }, body: file });
      if (!r.ok) throw new Error('No se pudo subir');
      var url = sb.url + '/storage/v1/object/public/fotos-propiedades/' + nombre;
      document.getElementById(id).value = url;
      prev.innerHTML = '<img src="' + esc(url) + '" alt=""/>';
    } catch (e) { prev.textContent = e.message; }
  }

  function val(id) { var el = document.getElementById(id); return el ? el.value.trim() : ''; }
  function chk(id) { var el = document.getElementById(id); return !!(el && el.checked); }

  function conectar(s, dis) {
    var cont = document.getElementById('msw-body');
    cont.querySelectorAll('[data-img]').forEach(function (inp) { inp.onchange = function () { subirImagen(inp.files[0], inp.dataset.img); }; });
    cont.querySelectorAll('[data-quitar-img]').forEach(function (b) {
      b.onclick = function () { var id = b.dataset.quitarImg; document.getElementById(id).value = ''; document.getElementById(id + '-prev').textContent = 'Sin imagen'; b.remove(); };
    });
    cont.querySelectorAll('.msw-ed__btn').forEach(function (b) { b.onmousedown = function (ev) { ev.preventDefault(); }; b.onclick = function () { comandoEditor(b); }; });
    cont.querySelectorAll('[data-copiar]').forEach(function (b) {
      b.onclick = function () { try { navigator.clipboard.writeText(b.dataset.copiar); window.bkToast('Copiado'); } catch (e) {} };
    });
    var slug = document.getElementById('msw-slug');
    if (slug) slug.oninput = function () {
      slug.value = slug.value.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/--+/g, '-').slice(0, 50);
      var v = document.getElementById('msw-slug-ver'); if (v) v.textContent = slug.value;
    };
    var g = document.getElementById('msw-guardar'); if (g) g.onclick = guardar;
    var np = document.getElementById('msw-nueva-pagina'); if (np) np.onclick = function () { abrirPagina(s, null); };
    cont.querySelectorAll('[data-editar-pagina]').forEach(function (b) {
      b.onclick = function () { abrirPagina(s, estado.paginas.find(function (p) { return p.id === b.dataset.editarPagina; })); };
    });
    var dc = document.getElementById('msw-dom-conectar');
    if (dc) dc.onclick = async function () {
      var dom = val('msw-dominio'); if (!dom) return;
      dc.disabled = true;
      try { var r = await window.bkApi('/sitios/' + s.id + '/dominio', { method: 'POST', json: { dominio: dom } }); estado.datos[estado.tab] = Object.assign(s, r.sitio); estado.dns = r.dns; pintar(); }
      catch (e) { window.bkToast(e.message); dc.disabled = false; }
    };
    var dv = document.getElementById('msw-dom-verificar');
    if (dv) dv.onclick = async function () {
      dv.disabled = true; dv.textContent = 'Verificando…';
      try { var r = await window.bkApi('/sitios/' + s.id + '/dominio/verificar'); estado.datos[estado.tab] = Object.assign(s, r.sitio); estado.dns = r.dns; pintar(); }
      catch (e) { window.bkToast(e.message); dv.disabled = false; dv.textContent = 'Verificar ahora'; }
    };
    var dq = document.getElementById('msw-dom-quitar');
    if (dq) dq.onclick = async function () {
      if (!confirm('¿Desconectar ' + s.dominio + '? El sitio seguirá en su dirección de prueba.')) return;
      try { await window.bkApi('/sitios/' + s.id + '/dominio', { method: 'DELETE' }); cargar(); } catch (e) { window.bkToast(e.message); }
    };
  }

  function comandoEditor(b) {
    var area = document.getElementById(b.dataset.ed); if (!area) return;
    area.focus();
    var cmd = b.dataset.cmd, v = b.dataset.val || null;
    if (cmd === 'createLink') { v = prompt('Dirección de la liga (https://…)'); if (!v) return; }
    if (cmd === 'insertImage') { v = prompt('Dirección de la imagen (https://…)'); if (!v || v.indexOf('https://') !== 0) return; }
    if (cmd === 'formatBlock') v = '<' + v + '>';
    document.execCommand(cmd, false, v);
  }

  async function guardar() {
    var tipo = estado.tab, btn = document.getElementById('msw-guardar');
    var redes = {};
    ['facebook', 'instagram', 'tiktok', 'youtube', 'linkedin', 'x'].forEach(function (k) { var v = val('msw-red-' + k); if (v) redes[k] = v; });
    var cuerpo = {
      slug: val('msw-slug'), activo: chk('msw-activo'), nombre: val('msw-nombre'), eslogan: val('msw-eslogan'), plantilla: val('msw-plantilla'),
      logo_url: val('msw-logo'), favicon_url: val('msw-favicon'), hero_url: val('msw-hero'), color_primario: val('msw-c1'), color_secundario: val('msw-c2'),
      whatsapp: val('msw-wa'), telefono: val('msw-tel'), email: val('msw-email'), direccion: val('msw-dir'), redes: redes,
      ga4_id: val('msw-ga4'), meta_pixel_id: val('msw-pixel'), mostrar_asesor: chk('msw-asesor'), incluir_bolsa: chk('msw-bolsa'), traductor: chk('msw-trad'),
      acerca_html: (document.getElementById('msw-acerca') || {}).innerHTML || '', seo_titulo: val('msw-seo-t'), seo_descripcion: val('msw-seo-d')
    };
    if (document.getElementById('msw-head')) { cuerpo.codigo_head = document.getElementById('msw-head').value; cuerpo.codigo_body = document.getElementById('msw-bodycode').value; }
    if (!cuerpo.slug) { window.bkToast('Escribe el link de tu sitio.'); return; }
    btn.disabled = true; btn.textContent = 'Guardando…';
    try { await window.bkApi('/sitios/' + tipo, { method: 'PUT', json: cuerpo }); window.bkToast('Sitio guardado'); await cargar(); }
    catch (e) { window.bkToast(e.message); btn.disabled = false; btn.textContent = 'Guardar sitio'; }
  }

  function abrirPagina(s, p) {
    p = p || { titulo: '', slug: '', contenido_html: '', publicada: true, en_menu: false, orden: estado.paginas.length };
    var ov = document.createElement('div');
    ov.className = 'bk-overlay bk-overlay--full msw-modal is-open';
    ov.innerHTML = '<div class="bk-modal" role="dialog" aria-modal="true"><div class="bk-modal__head"><div class="bk-modal__title">' + (p.id ? 'Editar página' : 'Nueva página') + '</div>' +
      '<button class="bk-icon-btn" data-cerrar aria-label="Cerrar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>' +
      '<div class="bk-modal__body"><div class="ms-row">' + campo('msw-pg-t', 'Título', p.titulo) + campo('msw-pg-s', 'Link', p.slug, { ph: 'vende-con-nosotros', hint: 'Queda en …/p/<span id="msw-pg-sv">' + esc(p.slug) + '</span>' }) + '</div>' +
      '<div class="bk-field"><span class="bk-label">Contenido</span>' + editor('msw-pg-c', p.contenido_html) + '</div>' +
      '<div class="ms-row">' + campo('msw-pg-mt', 'Título para Google', p.meta_titulo) + campo('msw-pg-md', 'Descripción para Google', p.meta_descripcion) + '</div>' +
      '<div class="msw-switches">' + interruptor('msw-pg-pub', 'Publicada', p.publicada) + interruptor('msw-pg-menu', 'Mostrar en el menú', p.en_menu) + '</div></div>' +
      '<div class="bk-modal__foot">' + (p.id ? '<button class="bk-btn bk-btn--quiet" data-borrar style="margin-right:auto">Eliminar</button>' : '') +
      '<button class="bk-btn bk-btn--ghost" data-cerrar>Cancelar</button><button class="bk-btn bk-btn--primary" data-guardar>Guardar página</button></div></div>';
    document.body.appendChild(ov);
    var cerrar = function () { ov.remove(); };
    ov.querySelectorAll('[data-cerrar]').forEach(function (b) { b.onclick = cerrar; });
    ov.querySelectorAll('.msw-ed__btn').forEach(function (b) { b.onmousedown = function (ev) { ev.preventDefault(); }; b.onclick = function () { comandoEditor(b); }; });
    var t = ov.querySelector('#msw-pg-t'), sl = ov.querySelector('#msw-pg-s');
    var auto = !p.slug;
    var limpiar = function (x) { return x.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60); };
    t.oninput = function () { if (auto) { sl.value = limpiar(t.value); ov.querySelector('#msw-pg-sv').textContent = sl.value; } };
    sl.oninput = function () { auto = false; ov.querySelector('#msw-pg-sv').textContent = limpiar(sl.value); };
    ov.querySelector('[data-guardar]').onclick = async function () {
      var b = this;
      var cuerpo = { titulo: t.value.trim(), slug: limpiar(sl.value || t.value), contenido_html: ov.querySelector('#msw-pg-c').innerHTML,
        meta_titulo: ov.querySelector('#msw-pg-mt').value.trim(), meta_descripcion: ov.querySelector('#msw-pg-md').value.trim(),
        publicada: ov.querySelector('#msw-pg-pub').checked, en_menu: ov.querySelector('#msw-pg-menu').checked, orden: p.orden || 0 };
      if (!cuerpo.titulo) { window.bkToast('Escribe el título.'); return; }
      b.disabled = true;
      try {
        await window.bkApi('/sitios/' + s.id + '/paginas' + (p.id ? '/' + p.id : ''), { method: p.id ? 'PATCH' : 'POST', json: cuerpo });
        cerrar(); window.bkToast('Página guardada'); cargar();
      } catch (e) { window.bkToast(e.message); b.disabled = false; }
    };
    var br = ov.querySelector('[data-borrar]');
    if (br) br.onclick = async function () {
      if (!confirm('¿Eliminar la página «' + p.titulo + '»?')) return;
      try { await window.bkApi('/sitios/' + s.id + '/paginas/' + p.id, { method: 'DELETE' }); cerrar(); cargar(); } catch (e) { window.bkToast(e.message); }
    };
    t.focus();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montar); else montar();
})();
