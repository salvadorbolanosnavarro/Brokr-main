/* ════════════════════════════════════════════════════════════════════
   BROQUER — App Shell compartido
   Inyecta: sidebar desktop, topbar, mobile header, bottom nav, Broq.
   Conserva 1:1 el flujo de Supabase / OpenAI / Railway del repo original.

   Uso en cada módulo:
     <body data-app="isr">         ← clave del módulo activo
        … contenido del módulo …
     <script src="app-shell.js" defer></script>
   Claves válidas: home, props, contactos, contratos, avm, valor, ficha,
                   ficha-manual, isr, image-cleaner, facebook-ads, guia, admin
   ════════════════════════════════════════════════════════════════════ */
(function () {
  if (window.__brokrShellLoaded) return;
  window.__brokrShellLoaded = true;

  /* ── Sentry — monitoreo de errores en producción ──────────────────────
     Captura automáticamente cualquier error JavaScript no manejado en todas
     las páginas de Broquer y lo envía a tu panel de sentry.io.

     PASO ÚNICO: reemplaza PEGAR_URL_AQUI con la URL que Sentry te da al
     crear tu proyecto (la encuentras en Project Settings → Client Keys →
     Loader Script; se ve así: https://js.sentry-cdn.com/TU_CLAVE.min.js).

     No carga nada en localhost — solo en broquer.app.
     ─────────────────────────────────────────────────────────────────── */
  (function initSentry() {
    const h = window.location.hostname;
    if (h === 'localhost' || h === '127.0.0.1' || h === '') return;
    const s = document.createElement('script');
    s.src = 'https://js.sentry-cdn.com/266e3bda223d2a0a211074bde709f4e8.min.js';
    s.crossOrigin = 'anonymous';
    s.onload = function () {
      if (!window.Sentry) return;
      // Etiqueta el módulo activo (ej. "isr", "avm") para filtrar en Sentry por página
      const mod = (document.body && document.body.dataset.app)
        ? document.body.dataset.app
        : (location.pathname.split('/').pop() || 'index').replace('.html', '');
      Sentry.setTag('modulo', mod);
      // Si el usuario ya tiene sesión, adjunta su correo al reporte
      try {
        const u = JSON.parse(
          localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}'
        );
        if (u && u.email) Sentry.setUser({ email: u.email, id: u.id || undefined });
      } catch (_) {}
    };
    document.head.appendChild(s);
  })();

  /* ── Config ── */
  const API_BASE = 'https://api.broquer.app';
  const SB_URL   = 'https://urtgysmtnvoqaljuhntz.supabase.co';
  const SB_KEY   = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';
  window.API_BASE = API_BASE;

  /* ── Contexto nativo iOS (App Store) ──────────────────────────────
     En la app nativa de iOS NO se muestra ningún botón de pago/checkout
     dentro de la app: Apple lo prohíbe salvo vía su propio IAP (30%).
     La suscripción se gestiona solo por web (broquer.app). Detectamos el
     WebView de Capacitor y marcamos <html class="is-ios-native"> para que
     el CSS y la lógica de abajo oculten el cobro únicamente en iOS, sin
     afectar la versión web ni la PWA. */
  const IS_IOS_NATIVE = (function () {
    try {
      if (window.__BROQUER_IOS_NATIVE__) return true;
      if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) return true;
      if (document.documentElement.classList.contains('is-ios-native')) return true;
    } catch (e) {}
    return false;
  })();
  if (IS_IOS_NATIVE) {
    try { document.documentElement.classList.add('is-ios-native'); } catch (e) {}
  }
  window.__BROQUER_IOS_NATIVE__ = IS_IOS_NATIVE;

  /* ── Páginas que NO requieren shell ni auth (login/registro/PDF preview) ── */
  const path = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const NOSHELL = ['login.html', 'registro.html', 'ficha-pdf-preview.html', 'legal.html', 'admin.html'];
  if (NOSHELL.includes(path)) return;

  /* ════════════════════════════════════════════════════════════════
     TELEMETRÍA · auto-auth en fetch + heartbeat de tiempo por módulo
     Backend: POST /telemetria/sesion-modulo cada 30s + en pagehide.
     Fetch patch: añade Authorization Bearer + X-Brokr-Module a llamadas
     a endpoints IA para atribuir uso/costo al usuario actual.
     ════════════════════════════════════════════════════════════════ */
  (function setupTelemetry(){
    if (window.__brokrTelemetryReady) return;
    window.__brokrTelemetryReady = true;

    const BACKEND_HOSTS = new Set([
      'api.broquer.app',
      // permitir también llamadas relativas (mismo origen) por si en algún
      // entorno el backend corre detrás del mismo dominio que el frontend.
      location.hostname,
    ]);
    const AI_PATHS = [
      '/chat', '/chat-claude',
      '/agent', '/transcribir',
      '/api/avm-claude', '/api/avm-websearch',
      '/contrato', '/contrato/analizar',
      '/ficha-manual/descripcion',
      '/images/clean',
      '/solicitud-arrendamiento/analizar',
      '/facebook/ad-description',
      '/telemetria/sesion-modulo',
    ];
    function getToken(){
      try { return localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || ''; }
      catch (_) { return ''; }
    }
    function currentModule(){
      try {
        const m = (document.body && document.body.dataset && document.body.dataset.app) || '';
        return (m || (path.replace(/\.html$/, '') || 'home')).toLowerCase();
      } catch (_) { return 'home'; }
    }
    function pathOf(input){
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (!url) return { path: '', host: '' };
        const u = new URL(url, location.href);
        return { path: u.pathname || '', host: u.host || '' };
      } catch (_) { return { path: '', host: '' }; }
    }

    // Auto-auth: añade Bearer + X-Brokr-Module a llamadas a endpoints IA
    const ORIG_FETCH = window.fetch.bind(window);
    window.fetch = function(input, init){
      try {
        const { path: p, host: h } = pathOf(input);
        const isBackend = !h || BACKEND_HOSTS.has(h);
        const isAI = isBackend && p && AI_PATHS.some(pre => p === pre || p.startsWith(pre + '/') || p.startsWith(pre + '?'));
        if (isAI) {
          const tok = getToken();
          init = init || {};
          // Combinar headers de input (Request) e init.headers preservando lo existente.
          const baseHdrs = (typeof input !== 'string' && input && input.headers) ? input.headers : {};
          const h2 = new Headers(baseHdrs);
          // init.headers gana sobre los de Request
          if (init.headers) {
            try {
              new Headers(init.headers).forEach((v, k) => h2.set(k, v));
            } catch (_) {}
          }
          if (tok && !h2.has('Authorization')) h2.set('Authorization', 'Bearer ' + tok);
          if (!h2.has('X-Brokr-Module')) h2.set('X-Brokr-Module', currentModule());
          init.headers = h2;
        }
      } catch (_) {}
      return ORIG_FETCH(input, init);
    };

    // Heartbeat: cuenta segundos activos del módulo y flushea cada 30s.
    let active = 0;
    let lastActivity = Date.now();
    let lastTick = Date.now();
    const IDLE_MS = 60_000;            // 1 min sin input = idle, no cuenta.
    const FLUSH_INTERVAL_MS = 30_000;  // batch hacia backend cada 30s.

    function markActivity(){ lastActivity = Date.now(); }
    ['mousemove','keydown','touchstart','scroll','click','focus'].forEach(ev =>
      window.addEventListener(ev, markActivity, { passive: true, capture: true })
    );

    function tick(){
      const now = Date.now();
      const elapsed = Math.floor((now - lastTick) / 1000);
      lastTick = now;
      if (document.visibilityState === 'visible' &&
          (now - lastActivity) < IDLE_MS &&
          elapsed > 0 && elapsed < 120) {
        active += elapsed;
      }
    }
    setInterval(tick, 1000);

    function flush(useBeacon){
      tick();
      if (active < 5) return;            // ignora ráfagas <5s para no saturar la tabla.
      const segs = Math.min(active, 3600);
      active = 0;
      const payload = { modulo: currentModule(), segundos: segs };
      const url = (window.API_BASE || 'https://api.broquer.app') + '/telemetria/sesion-modulo';
      const tok = getToken();
      if (useBeacon && navigator.sendBeacon) {
        try {
          // sendBeacon no permite headers personalizados — colamos el token en query string.
          const u = tok ? (url + '?_t=' + encodeURIComponent(tok.slice(0, 8))) : url;
          const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
          // Beacon sin auth se ignorará en backend (silenciosamente). Por eso preferimos fetch keepalive.
          try {
            const fd = new FormData();
            fd.append('payload', JSON.stringify(payload));
            // Mejor: fetch con keepalive — sí permite headers.
            ORIG_FETCH(url, {
              method: 'POST', keepalive: true,
              headers: tok ? { 'Content-Type':'application/json', 'Authorization':'Bearer '+tok, 'X-Brokr-Module': payload.modulo } : { 'Content-Type':'application/json' },
              body: JSON.stringify(payload),
            }).catch(() => navigator.sendBeacon(u, blob));
          } catch (_) {
            navigator.sendBeacon(u, blob);
          }
        } catch (_) {}
        return;
      }
      try {
        // Pasa por el window.fetch parcheado (añadirá Authorization + X-Brokr-Module).
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }).catch(() => {});
      } catch (_) {}
    }

    setInterval(() => flush(false), FLUSH_INTERVAL_MS);
    window.addEventListener('pagehide', () => flush(true));
    window.addEventListener('beforeunload', () => flush(true));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush(false);
    });
  })();

  /* ── Configuración de módulos ──
     Antes el menú era "CRM" más una lista larga de herramientas sueltas. Con
     dieciocho módulos esa lista dejó de leerse: el agente bajaba buscando,
     y buscar en un menú es la señal de que el menú ya no sirve.

     Ahora cada módulo vive en el grupo que corresponde al momento de la
     operación en que se usa — captar, dar seguimiento, documentar, calcular,
     promover — y cada grupo se abre y se cierra igual que CRM, que es el
     patrón que ya conocía el agente. Ningún módulo cambió de dirección: solo
     cambió dónde se encuentra.

     'Equipo' salió del menú y se fue a Perfil. No es una herramienta de
     trabajo diario, es configuración de la cuenta, y vivía en el CRM nada más
     porque no había dónde más ponerlo.

     WhatsApp queda en 'Seguimiento', pero el botón de Chats de la barra
     inferior se queda tal cual: eso no es una entrada de menú duplicada, es
     un atajo al chat, que es lo que el agente abre veinte veces al día. */
  const GRUPOS = [
    { key:'crm',         label:'CRM',         icon:'funnel' },
    { key:'seguimiento', label:'Seguimiento', icon:'handshake' },
    { key:'documentos',  label:'Documentos',  icon:'document' },
    { key:'numeros',     label:'Números',     icon:'peso' },
    { key:'marketing',   label:'Marketing',   icon:'send' },
  ];

  const MODS = [
    // CRM — el inventario y la gente.
    { key:'props',        href:'propiedades.html',   label:'Tus Inmuebles',       group:'crm',         icon:'building' },
    { key:'contactos',    href:'contactos.html',     label:'Contactos',           group:'crm',         icon:'users' },
    { key:'tareas',       href:'tareas.html',        label:'Tareas',              group:'crm',         icon:'check' },
    { key:'estadisticas', href:'estadisticas.html',  label:'Estadísticas',        group:'crm',         icon:'chart' },
    // Seguimiento — hablar con el prospecto hasta que se convierte en cliente.
    { key:'whatsapp',     href:'whatsapp.html',      label:'WhatsApp',            group:'seguimiento', icon:'whatsapp' },
    { key:'leads',        href:'leads.html',         label:'Leads',               group:'seguimiento', icon:'send' },
    // Documentos — en el orden real de la operación: se redacta, se firma, se reporta.
    { key:'contratos',    href:'contratos.html',     label:'Contratos',           group:'documentos',  icon:'document' },
    { key:'firmas',       href:'firmas.html',        label:'Firma electrónica',   group:'documentos',  icon:'pencil' },
    { key:'cumplimiento', href:'cumplimiento.html',  label:'Cumplimiento',        group:'documentos',  icon:'shield' },
    // Números.
    { key:'avm',          href:'avm.html',           label:'Estimación de valor', group:'numeros',     icon:'peso' },
    { key:'isr',          href:'isr.html',           label:'ISR',                 group:'numeros',     icon:'calculator' },
    // Marketing — de la foto cruda al anuncio publicado.
    { key:'image-cleaner',href:'image-cleaner.html', label:'Editor imágenes',     group:'marketing',   icon:'image' },
    { key:'ficha-manual', href:'ficha-manual.html',  label:'Ficha técnica',       group:'marketing',   icon:'landscape' },
    { key:'facebook-ads', href:'facebook-ads.html',  label:'Facebook Ads',        group:'marketing',   icon:'facebook' },
    { key:'video',        href:'video.html',         label:'Video',               group:'marketing',   icon:'video' },
    { key:'mi-sitio',     href:'mi-sitio.html',      label:'Mi sitio',            group:'marketing',   icon:'globo' },
    // Cuenta — fuera de los grupos, pegado al fondo del menú.
    { key:'blog',         href:'blog.html',          label:'Blog',                group:'cuenta',      icon:'feather' },
    { key:'guia',         href:'guia-agente.html',   label:'Ayuda',               group:'cuenta',      icon:'question' },
    { key:'admin',        href:'admin.html',         label:'Admin',               group:'cuenta',      icon:'cog', adminOnly:true },
  ];

  const CONTEXT_LABELS = {
    'home':         'Dashboard principal — menú de módulos',
    'props':        'Tus Inmuebles — catálogo de propiedades',
    'contactos':    'Contactos — CRM de prospectos',
    'equipo':       'Equipo — miembros de la cuenta, roles y permisos',
    'tareas':       'Tareas — pendientes y actividad del CRM',
    'leads':        'Leads — contactos marcados como potenciales, aún sin cerrar',
    'estadisticas': 'Estadísticas — captación, pipeline e inmuebles con más interés',
    'mi-sitio':     'Mi sitio — perfil público, plantilla y sitio web del agente',
    'contratos':    'Contratos — arrendamiento y promesa de compraventa',
    'cumplimiento': 'Cumplimiento PLD/UIF — expediente único de identificación del cliente, umbrales de aviso, acumulación de operaciones, avisos al SPPLD y bitácora',
    'firmas':       'Firma electrónica — mandar contratos a firma de las partes, código de verificación, constancia de firma y verificación pública por folio',
    'avm':          'Estimación de valor AVM — avalúo de mercado automatizado',
    'ficha-manual': 'Ficha Técnica Manual — crear ficha sin EasyBroker',
    'isr':          'Calculadora ISR por enajenación de inmuebles',
    'image-cleaner':'Editor de imágenes — limpieza con IA',
    'video':        'Video — recorrido en video armado con las fotos de la ficha, para reels, stories y feed',
    'admin':        'Panel administrativo',
    'facebook-ads': 'Meta Ads Express — crear, activar y medir anuncios de Facebook e Instagram',
    'whatsapp':     'WhatsApp — varios números, chats, conexión, Recepción automática y entrenamiento de la IA',
  };

  /* ── Encabezado canónico por página (unificación de esqueleto) ──
     Inyectado por el shell arriba del contenido de CADA módulo, idéntico
     en posición/tamaño/estilo. 'home' se excluye (tiene su propio hero). */
  const PAGE_META = {
    'equipo':        { title:'Equipo',                 sub:'Quién trabaja en tu cuenta y qué puede ver cada quien.' },
    'contratos':     { title:'Contratos',              sub:'Genera contratos listos para firma en minutos.' },
    'cumplimiento':  { title:'Cumplimiento',           sub:'El expediente de identificación de cada cliente, el control de umbrales y los avisos a la UIF, en un solo lugar.' },
    'firmas':        { title:'Firma electrónica',      sub:'Manda el contrato, cada parte firma desde su celular y te regresa con constancia.' },
    'avm':           { title:'Estimación de valor',    sub:'Avalúo automático con comparables de tu zona.' },
    'ficha-manual':  { title:'Ficha técnica',          sub:'Crea fichas profesionales de tus propiedades.' },
    'isr':           { title:'Cálculo de ISR',         sub:'ISR por enajenación de inmuebles con el INPC vigente.' },
    'image-cleaner': { title:'Editor de imágenes',     sub:'Limpia y mejora las fotos de tus propiedades con IA.' },
    'facebook-ads':  { title:'Facebook Ads',           sub:'Crea, activa y mide anuncios de Facebook e Instagram.' },
    'whatsapp':      { title:'WhatsApp',                sub:'Varios números, un solo lugar. La IA califica, agenda y te pasa al prospecto cuando toca.' },
    'verificador':   { title:'Verificador',            sub:'Revisión con IA para detectar problemas antes de firmar.' },
    'blog':          { title:'Blog',                   sub:'Recursos profesionales sobre PLD, legal y mercado.' },
    'mi-sitio':      { title:'Mi sitio',               sub:'El sitio web público que tus clientes ven cuando les compartes tu link.' },
    'video':         { title:'Video',                   sub:'Tus fotos se vuelven un recorrido listo para reels, stories y WhatsApp.' },
  };
  const ICONS = {
    home:       '<path stroke-linecap="round" stroke-linejoin="round" d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h4v-6h4v6h4a1 1 0 001-1V10"/>',
    building:   '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955a1.5 1.5 0 012.121 0L22.28 12M4.5 9.75v10.125a1.125 1.125 0 001.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125a1.125 1.125 0 001.125-1.125V9.75"/>',
    users:      '<path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>',
    document:   '<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>',
    chart:      '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941"/>',
    tag:        '<path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/>',
    pencil:     '<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125"/>',
    feather:    '<path stroke-linecap="round" stroke-linejoin="round" d="M20.24 12.24a6 6 0 00-8.49-8.49L5 10.5V19h8.5l6.74-6.76zM16 8L2 22M17.5 15H9"/>',
    calculator: '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 15.75l-2.489-2.489m0 0a3.375 3.375 0 10-4.773-4.773 3.375 3.375 0 004.774 4.774zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" style="display:none"/><rect x="4.5" y="3" width="15" height="18" rx="2.25" ry="2.25" stroke-linejoin="round"/><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 6.75h9v3h-9zM8.25 13.5h.008v.008H8.25V13.5zm0 3h.008v.008H8.25V16.5zm3.75-3h.008v.008H12V13.5zm0 3h.008v.008H12V16.5zm3.75-3h.008v.008h-.008V13.5zm0 3h.008v.008h-.008V16.5z"/>',
    image:      '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"/>',
    shield:     '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z"/>',
    gavel:      '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z"/>',
    cog:        '<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a6.759 6.759 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.28z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
    bell:       '<path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/>',
    peso:       '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v18"/><path stroke-linecap="round" stroke-linejoin="round" d="M16 7.5c0-1.5-1.5-2.5-4-2.5s-4 1-4 2.5S9.5 10 12 10.5s4 1 4 2.5-1.5 3-4 3-4-1-4-2.5"/>',
    landscape:  '<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75l2.25-2.25 1.5 1.5 2.25-2.25 2.25 2.25M8.25 15h7.5M5.625 3H8.25M5.625 3c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>',
    search:     '<circle cx="11" cy="11" r="8"/><path stroke-linecap="round" d="M21 21l-4.35-4.35"/>',
    plus:       '<path stroke-linecap="round" d="M12 5v14M5 12h14"/>',
    arrowOut:   '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75"/>',
    user:       '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>',
    mic:        '<path stroke-linecap="round" stroke-linejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"/>',
    send:       '<path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/>',
    close:      '<path stroke-linecap="round" d="M6 6l12 12M6 18L18 6"/>',
    homeList:   '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6h16.5M3.75 12h16.5M3.75 18h16.5"/>',
    video:      '<rect x="2.25" y="6" width="13.5" height="12" rx="2.25" ry="2.25" stroke-linejoin="round"/><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-2.83a.75.75 0 011.13.64v7.38a.75.75 0 01-1.13.64l-4.72-2.83"/>',
    handshake:  '<path stroke-linecap="round" stroke-linejoin="round" d="M3 12l3-3 3 3 4-4 5 5-3 3-2-2-4 4-2-2-2 2-2-2 0-4z"/>',
    question:   '<path stroke-linecap="round" stroke-linejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"/>',
    check:      '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    globo:      '<path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18zM3.6 9h16.8M3.6 15h16.8M11.5 3a17 17 0 000 18M12.5 3a17 17 0 010 18"/>',
    facebook:   '<path fill="currentColor" stroke="none" d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.886v2.269h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>',
    /* Marca externa: el glifo oficial va sólido, igual que el de Facebook.
       Es la excepción reconocida a la regla de iconos de trazo. */
    whatsapp:   '<path fill="currentColor" stroke="none" d="M12 0C5.373 0 0 5.373 0 12c0 2.127.558 4.126 1.533 5.857L.057 23.882a.5.5 0 00.614.612l6.115-1.598A11.947 11.947 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.967 0-3.805-.538-5.378-1.47l-.385-.23-3.993 1.044 1.012-3.9-.252-.403A9.96 9.96 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/><path fill="currentColor" stroke="none" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>',
    funnel:     '<path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h18l-7.25 8.25v5.1l-3.5 1.75v-6.85L3 4.5z"/>',
    chevron:    '<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>',
    lock:       '<path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"/>',
    trash:      '<path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/>',
  };
  const svg = (name, size = 18, sw = 1.6, cls = '') =>
    `<svg${cls ? ` class="${cls}"` : ''} width="${size}" height="${size}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="${sw}">${ICONS[name] || ''}</svg>`;

  /* Helper local para SVGs dentro de chips de Broq (14×14, stroke 1.7) */
  const _CICO = (name) =>
    `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7" style="flex-shrink:0;vertical-align:-2px;margin-right:6px">${ICONS[name] || ''}</svg>`;

  const SHAARK_CHIPS_MAP = {
    home:         [{l:_CICO('document')+'Contratos', m:'Generar un contrato'}, {l:_CICO('calculator')+'Calc. ISR', m:'Calcular ISR'}, {l:_CICO('tag')+'Fichas téc.', m:'Crear ficha técnica'}, {l:_CICO('building')+'Tus Inmuebles', m:'Ver tus inmuebles'}],
    contratos:    [{l:_CICO('pencil')+'Arrendamiento', m:'Genera un contrato de arrendamiento'}, {l:_CICO('handshake')+'Promesa', m:'Genera una promesa de compraventa'}, {l:_CICO('question')+'¿Cómo funciona?', m:'¿Qué tipos de contrato puedo generar?'}],
    cumplimiento: [{l:_CICO('shield')+'¿Genera aviso?', m:'¿Una operación de 900 mil pesos genera aviso?'}, {l:_CICO('users')+'Expediente', m:'¿Qué documentos necesito de un cliente persona moral?'}, {l:_CICO('question')+'Acumulación', m:'¿Cómo funciona la acumulación de 6 meses?'}],
    avm:          [{l:_CICO('chart')+'Valuación', m:'Valúa una casa de 3 recámaras en'}, {l:_CICO('question')+'¿Cuánto vale?', m:'¿Cuánto vale una propiedad en esta colonia?'}, {l:_CICO('building')+'Comparables', m:'¿Cómo agrego comparables?'}],
    isr:          [{l:_CICO('calculator')+'Calc. ISR', m:'Calcula el ISR para una venta de'}, {l:_CICO('document')+'Descargar PDF', m:'Descarga el reporte de ISR'}, {l:_CICO('question')+'Exención', m:'¿Cuándo aplica la exención de casa habitación?'}],
    ficha:        [{l:_CICO('search')+'Buscar prop.', m:'Genera la ficha para la propiedad EB-'}, {l:_CICO('image')+'Con fotos', m:'¿Cómo se agregan fotos a la ficha?'}],
    'ficha-manual':[{l:_CICO('tag')+'Nueva ficha', m:'Crea una ficha para una casa de 3 recámaras en'}, {l:_CICO('pencil')+'Descripción', m:'Escribe una descripción atractiva para una propiedad en'}],
    props:        [{l:_CICO('search')+'Buscar', m:'Buscar propiedades en Chapultepec'}, {l:_CICO('question')+'EasyBroker', m:'¿Cómo conecto mi cuenta de EasyBroker?'}],
  };

  /* ════════════════════════════════════════════════════════════════
     CSS injection
     ════════════════════════════════════════════════════════════════ */
  const css = `
.bk-shell-root { display: flex; height: 100vh; min-height: 100vh; background: var(--canvas); }
.bk-shell-root.bk-narrow .bk-sidebar { display: none; }

/* ── Sidebar (drawer) ───────────────────────────────────────────────
   Mismo azul de la tarjeta de pendientes del inicio, con el destello
   blanco arriba. Los módulos van en BLANCO y en NEGRITAS. La lista se
   agrupa en tres bloques translúcidos (CRM · herramientas · cuenta)
   separados por aire: nada de líneas divisorias. */
.bk-sidebar {
  width: 268px; flex-shrink: 0;
  background: var(--sb-bg);
  border-right: none;
  padding: 18px 12px 20px;
  display: flex; flex-direction: column;
  overflow-y: auto;
  position: relative;
}
/* Destello superior — el mismo de .ai-card en index.html */
.bk-sidebar::before {
  content: ''; position: absolute; inset: 0;
  background-image: radial-gradient(120% 70% at 100% 0%, rgba(255,255,255,0.18), rgba(255,255,255,0) 58%);
  pointer-events: none; z-index: 0;
}
.bk-sidebar > * { position: relative; z-index: 1; }
.bk-sidebar::-webkit-scrollbar { width: 0; }
@media (max-width: 880px) { .bk-sidebar { display: none; } }

.bk-sidebar__brand {
  padding: 4px 10px 20px;
  border-bottom: none;
  margin-bottom: 4px;
  display: flex; align-items: center;
}
.bk-sidebar__brand a { display: flex; align-items: center; gap: 8px; text-decoration: none; }
.bk-sidebar__brand img {
  height: 27px; width: auto; display: block;
  filter: brightness(0) invert(1); opacity: .96;
  transition: opacity var(--dur) var(--ease);
}
.bk-sidebar__brand a:hover img { opacity: 1; }

/* Bloque: la unidad que agrupa módulos sin usar una línea */
.bk-sb-block {
  background: var(--sb-panel);
  border-radius: var(--r-lg);
  padding: 6px;
  margin-bottom: 12px;
  display: flex; flex-direction: column; gap: 5px;
}
/* El bloque de cuenta (Mi perfil en adelante) se va hasta abajo:
   el aire hace la separación, no una raya. */
.bk-sb-block--cuenta { margin-top: auto; margin-bottom: 0; }

.bk-sb-link {
  position: relative;
  display: flex !important; align-items: center; gap: 12px;
  height: 44px; padding: 0 12px;
  border-radius: var(--r);
  font-size: 14px; color: #FFFFFF !important;
  cursor: pointer;
  transition: background var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
  font-weight: 700; letter-spacing: -0.01em;
  text-decoration: none !important;
  visibility: visible !important;
  opacity: 1 !important;
}
.bk-sidebar .bk-sb-link,
.bk-sidebar a.bk-sb-link {
  color: #FFFFFF !important;
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  background: transparent;
  font-weight: 700;
}
.bk-sb-link svg, .bk-sidebar .bk-sb-link svg {
  flex-shrink: 0; opacity: 1; color: #FFFFFF;
  stroke-width: 2.1;
}
.bk-sb-link:hover,
.bk-sidebar .bk-sb-link:hover,
.bk-sidebar a.bk-sb-link:hover { background: var(--sb-hover) !important; color: #FFFFFF !important; }

.bk-sb-link.is-active,
.bk-sidebar .bk-sb-link.is-active,
.bk-sidebar a.bk-sb-link.is-active {
  background: var(--sb-active) !important; color: #FFFFFF !important; font-weight: 800;
  box-shadow: inset 0 0 0 1px var(--sb-edge), var(--sb-glow);
}
/* Marca del módulo activo: barrita blanca, sin líneas divisorias */
.bk-sidebar .bk-sb-link.is-active::before {
  content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 20px; border-radius: var(--r-pill);
  background: #FFFFFF;
}

.bk-sb-group { display: flex; flex-direction: column; gap: 5px; }
.bk-sb-trigger { width: 100%; border: 0; background: transparent; font-family: inherit; text-align: left; }
.bk-sb-trigger .bk-sb-chevron { margin-left: auto; opacity: .8; transition: transform var(--dur) var(--ease); }
.bk-sb-group.is-open .bk-sb-chevron { transform: rotate(180deg); }
.bk-sb-submenu { display: none; flex-direction: column; gap: 5px; padding: 2px 0 2px 22px; }
.bk-sb-group.is-open .bk-sb-submenu { display: flex; }
.bk-sb-submenu .bk-sb-link { height: 40px; padding: 0 10px; }
.bk-sidebar .bk-sb-submenu .bk-sb-link.is-active::before { left: -6px; height: 16px; }

/* Content area */
.bk-content { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }

/* Flecha de regreso a Inicio (misma en cada módulo, azul tenue) */
.bk-back-wrap {
  max-width: var(--page-max, 1180px);
  margin: 0 auto;
  padding: 14px var(--pad-x, 36px) 0;
  box-sizing: border-box;
}
.bk-back-home {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600;
  color: var(--sky-blue); opacity: 0.55;
  text-decoration: none;
  transition: opacity var(--dur) var(--ease);
}
.bk-back-home:hover { opacity: 1; }
.bk-back-home svg { flex: none; transition: transform var(--dur) var(--ease); }
.bk-back-home:hover svg { transform: translateX(-2px); }
@media (max-width: 720px) { .bk-back-wrap { padding: 10px var(--pad-x, 16px) 0; } }

/* Mobile head */
.bk-mobile-head {
  display: none;
  padding: 14px 16px 12px;
  background: var(--canvas);
  border-bottom: none;
  align-items: center; justify-content: space-between;
}
@media (max-width: 880px) { .bk-mobile-head { display: flex; } }
.bk-mobile-head a { display:flex; align-items:center; }
.bk-mobile-head img { height: 97px; width: auto; display: block; }
.bk-mobile-head__avatar {
  width: 29px; height: 29px; border-radius: 50%;
  background: var(--ink); color: var(--paper);
  font-weight: 600; font-size: 11px;
  display: flex; align-items: center; justify-content: center;
}

/* Topbar (desktop) */
.bk-topbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
  padding: 18px 36px;
  border-bottom: none;
  background: var(--canvas);
  flex-shrink: 0;
  position: relative;
}
@media (max-width: 880px) { .bk-topbar { display: none; } }

/* Quote rotativo (ocupa el espacio donde antes iban título + búsqueda) */
.bk-topbar__quote {
  flex: 1;
  min-width: 0;
  font-family: var(--font-display, 'DM Sans'), -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--ink-2);
  line-height: 1.4;
  opacity: 0;
  transition: opacity .5s ease;
  padding-right: 16px;
  /* Permite hasta 2 renglones sin cortar nada */
  display: -webkit-box;
  display: box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.bk-topbar__quote.is-visible { opacity: 1; }
.bk-topbar__quote .quote-author {
  color: var(--mute);
  font-weight: 400;
  font-size: 13px;
  margin-left: 6px;
  /* El autor puede romper si el span entero no cabe en la línea */
  display: inline;
  white-space: normal;
}

/* Búsqueda expandible (oculta por defecto, se despliega al click en lupa) */
.bk-topbar__search-expand {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex; align-items: center;
  padding: 18px 36px;
  background: var(--paper);
  opacity: 0;
  visibility: hidden;
  transition: opacity .25s ease, visibility .25s ease;
  z-index: 5;
}
.bk-topbar__search-expand.is-open {
  opacity: 1;
  visibility: visible;
}
.bk-topbar__search-expand-inner {
  flex: 1;
  display: flex; align-items: center; gap: 12px;
  background: var(--bone);
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  padding: 0 18px;
  height: 44px;
}
.bk-topbar__search-expand-inner svg { color: var(--mute); flex-shrink: 0; }
.bk-topbar__search-expand-inner input {
  flex: 1; background: none; border: none; outline: none;
  font-size: 15px; letter-spacing: -0.005em;
  font-family: inherit;
  color: var(--ink);
}
.bk-topbar__search-expand-inner input::placeholder { color: var(--mute-2); }
.bk-topbar__search-close {
  background: transparent; border: none; cursor: pointer;
  color: var(--mute); padding: 6px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.bk-topbar__search-close:hover { color: var(--ink); }

.bk-topbar__actions { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.bk-icon-btn {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: var(--bone);
  border: 1px solid var(--line-2);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--ink-2);
  position: relative;
  transition: background var(--dur) var(--ease);
}
.bk-icon-btn:hover { background: var(--paper-2); }
.bk-icon-btn .dot {
  position: absolute; top: 8px; right: 8px;
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--forest); border: 2px solid var(--paper);
}

/* The page's own scroll body */
.bk-page {
  flex: 1; overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 100px;
}
.bk-page::-webkit-scrollbar { width: 0; }

/* ── Encabezado canónico unificado (mismo en todos los módulos) ── */
.bk-ph {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px var(--pad-x, 36px) 4px;
  box-sizing: border-box;
}
.bk-ph__title {
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.05;
  color: var(--ink);
  text-transform: none;
  margin: 0;
}
.bk-ph__sub {
  font-size: 15px;
  color: var(--mute);
  margin: 6px 0 0;
  line-height: 1.5;
  max-width: 70ch;
}
@media (max-width: 720px) {
  .bk-ph { padding: 16px var(--pad-x, 16px) 4px; }
  .bk-ph__title { font-size: 24px; }
}

/* Heros de solo-título reemplazados por el encabezado canónico */
body[data-app="facebook-ads"] .fa-hero,
body[data-app="blog"] .bl-head,
body[data-app="verificador"] .top-header { display: none !important; }

/* Bottom nav (mobile) */
.bk-bnav {
  display: none;
  position: fixed;
  left: 16px; right: 16px;
  bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  z-index: 60;
  align-items: center;
  justify-content: space-around;
  gap: 4px;
  padding: 7px 12px;
  border-radius: 28px;
  /* Liquid glass */
  background: rgba(255,255,255,0.55);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.65);
  box-shadow: 0 10px 34px rgba(5,32,60,0.18), inset 0 1px 0 rgba(255,255,255,0.75);
}
@media (max-width: 880px) { .bk-bnav { display: flex; } }
.bk-bnav__item {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 6px 4px;
  font-size: 10px;
  color: var(--mute);
  text-decoration: none;
  font-weight: 600;
  cursor: pointer;
  border: none; background: transparent;
  font-family: inherit;
  transition: color var(--dur) var(--ease);
  -webkit-tap-highlight-color: transparent;
}
.bk-bnav__item.is-active { color: var(--sky-blue); }
.bk-bnav__item svg { opacity: .9; }
.bk-bnav__item.is-active svg { opacity: 1; }
.bk-bnav__broquer img { height: 28px; width: auto; display: block; margin: -2px 0; }
.bk-bnav__ico { position: relative; display: block; line-height: 0; }

/* Globito rojo de mensajes sin leer (sobre el ícono de Chats) */
.bk-badge {
  position: absolute; top: -5px; right: -8px;
  min-width: 17px; height: 17px; padding: 0 4px;
  border-radius: 9px;
  background: #E5484D; color: #FFFFFF;
  font-size: 10px; font-weight: 800; line-height: 17px; text-align: center;
  border: 2px solid rgba(255,255,255,0.9);
  display: none;
  font-variant-numeric: tabular-nums;
}
.bk-badge.is-on { display: block; }

/* ── Hoja de módulos CRM (solo móvil) ── */
.bk-sheet-back {
  position: fixed; inset: 0; z-index: 95;
  background: rgba(5,32,60,0.38);
  -webkit-backdrop-filter: blur(2px); backdrop-filter: blur(2px);
  opacity: 0; pointer-events: none;
  transition: opacity var(--dur) var(--ease);
}
.bk-sheet-back.is-open { opacity: 1; pointer-events: auto; }
.bk-sheet {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 96;
  max-height: 82vh; overflow-y: auto; overscroll-behavior: contain;
  background: var(--bone);
  border-radius: 22px 22px 0 0;
  padding: 8px 16px calc(22px + env(safe-area-inset-bottom, 0px));
  box-shadow: 0 -12px 44px rgba(5,32,60,0.28);
  transform: translateY(102%);
  transition: transform var(--dur) var(--ease);
}
.bk-sheet.is-open { transform: none; }
.bk-sheet__grip { width: 38px; height: 4px; border-radius: 2px; background: var(--line-2); margin: 6px auto 12px; }
.bk-sheet__eyebrow {
  font-size: 11px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
  color: var(--mute); margin: 14px 4px 8px;
}
.bk-sheet__eyebrow:first-of-type { margin-top: 2px; }
.bk-sheet__grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.bk-sheet__item {
  display: flex; align-items: center; gap: 10px;
  padding: 13px 12px; border-radius: 14px;
  background: var(--paper); border: 1px solid var(--line);
  color: var(--ink); text-decoration: none;
  font-size: 13px; font-weight: 700; font-family: inherit; text-align: left;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
  transition: background var(--dur) var(--ease);
}
.bk-sheet__item:active { background: var(--paper-2); }
.bk-sheet__item.is-active { border-color: var(--sky-blue); color: var(--sky-blue); }
.bk-sheet__item svg { flex: none; }
.bk-sheet__item .bk-sheet__ico { position: relative; display: block; line-height: 0; color: var(--sky-navy); }
.bk-sheet__item.is-active .bk-sheet__ico { color: var(--sky-blue); }
.bk-sheet__item span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (min-width: 881px) { .bk-sheet, .bk-sheet-back { display: none; } }

/* Broq FAB (desktop only — mobile uses bottom-nav center) */
.bk-shaark-fab {
  position: fixed; right: 28px; bottom: 28px; z-index: 80;
  width: 60px; height: 60px; border-radius: 50%;
  background: var(--bone); color: var(--ink);
  border: 1px solid var(--line);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 14px 32px rgba(22,22,22,.18), 0 4px 10px rgba(22,22,22,.08);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
  padding: 0; overflow: hidden;
}
.bk-shaark-fab:hover { transform: translateY(-2px); box-shadow: 0 18px 36px rgba(22,22,22,.22), 0 6px 12px rgba(22,22,22,.12); }
.bk-shaark-fab img { height: 62%; width: auto; object-fit: contain; }
.bk-shaark-fab__pulse {
  position: absolute; inset: -4px; border-radius: 50%;
  border: 1.5px solid var(--ink); opacity: 0;
  animation: bkPulse 2.4s ease-out infinite;
  pointer-events: none;
}
@keyframes bkPulse { 0% { transform: scale(.95); opacity: .35; } 100% { transform: scale(1.25); opacity: 0; } }
.bk-wake-dot {
  position: absolute; top: 6px; right: 6px;
  width: 10px; height: 10px; background: var(--success);
  border-radius: 50%; border: 2px solid var(--bone);
  display: none;
}
.bk-shaark-fab.wake-on .bk-wake-dot { display: block; }
@media (max-width: 880px) { .bk-shaark-fab { display: none; } }

/* Broq popup */
.bk-shaark-popup {
  display: none;
  position: fixed; right: 28px; bottom: 100px; z-index: 90;
  width: min(420px, calc(100vw - 32px));
  max-height: min(600px, calc(100dvh - 140px));
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: 0 32px 80px rgba(0,20,59,0.28), 0 10px 24px rgba(0,20,59,0.12);
  flex-direction: column; overflow: hidden;
  animation: bkShkIn .26s cubic-bezier(.16,1,.3,1);
}
.bk-shaark-popup.is-open { display: flex; }
@keyframes bkShkIn { from { opacity: 0; transform: translateY(12px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@media (max-width: 880px) {
  .bk-shaark-popup { right: 12px; left: 12px; bottom: 84px; width: auto; }
}
/* Cabecera del chat — mismo azul del sidebar, con el destello superior.
   Separa visualmente la identidad de Broq de la zona de conversación. */
.bk-shk-head {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 16px 15px; border-bottom: none;
  background: var(--sb-bg);
  background-image: radial-gradient(120% 90% at 100% 0%, rgba(255,255,255,0.20), rgba(255,255,255,0) 62%);
  position: relative; flex-shrink: 0;
}
.bk-shk-head::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 1px;
  background: rgba(255,255,255,0.14); pointer-events: none;
}
.bk-shk-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: rgba(255,255,255,0.96);
  border: 1px solid rgba(255,255,255,0.55);
  box-shadow: 0 2px 10px rgba(0,20,59,0.28), inset 0 1px 0 rgba(255,255,255,0.9);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  overflow: hidden;
}
.bk-shk-avatar img { height: 62%; width: auto; object-fit: contain; }
.bk-shk-name { font-family: var(--font-display); font-size: 15px; font-weight: 600; letter-spacing: -0.01em; color: rgba(255,255,255,1); line-height: 1.25; }
.bk-shk-status { display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: rgba(255,255,255,0.72); font-family: inherit; letter-spacing: 0; font-weight: 500; margin-top: 1px; }
/* Punto "en línea": núcleo verde con halo suave que respira */
.bk-shk-status::before {
  content: ''; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: rgba(52,211,153,1);
  box-shadow: 0 0 0 3px rgba(52,211,153,0.20), 0 0 8px rgba(52,211,153,0.55);
  animation: bkShkOnline 2.4s ease-in-out infinite;
}
@keyframes bkShkOnline {
  0%, 100% { box-shadow: 0 0 0 3px rgba(52,211,153,0.18), 0 0 8px rgba(52,211,153,0.45); }
  50%      { box-shadow: 0 0 0 5px rgba(52,211,153,0.08), 0 0 12px rgba(52,211,153,0.70); }
}
@media (prefers-reduced-motion: reduce) { .bk-shk-status::before { animation: none; } }
.bk-shk-wake {
  background: none; border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  padding: 5px 10px;
  font-size: 11px; font-weight: 600; color: var(--mute);
  cursor: pointer; display: flex; align-items: center; gap: 4px;
  font-family: inherit; transition: color var(--dur), border-color var(--dur);
}
.bk-shk-wake:hover { color: var(--ink); }
.bk-shk-wake.is-on { color: var(--forest); border-color: var(--forest); }
.bk-shk-close {
  width: 30px; height: 30px;
  background: rgba(255,255,255,0.10); border: none; cursor: pointer;
  border-radius: 9px; color: rgba(255,255,255,0.75);
  display: flex; align-items: center; justify-content: center;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.bk-shk-close:hover { background: rgba(255,255,255,0.20); color: rgba(255,255,255,1); }
.bk-shk-msgs { flex: 1; overflow-y: auto; padding: 16px 16px; display: flex; flex-direction: column; gap: 10px; background: var(--paper); }
.bk-shk-msgs::-webkit-scrollbar { width: 4px; } .bk-shk-msgs::-webkit-scrollbar-thumb { background: var(--line-2); border-radius: 4px; }
.bk-shk-bubble { max-width: 88%; padding: 11px 14px; border-radius: 16px; font-size: 13.5px; line-height: 1.55; letter-spacing: -0.005em; white-space: pre-wrap; }
.bk-shk-bubble.bot { background: var(--paper-2); color: var(--ink); border: 1px solid var(--line); border-bottom-left-radius: 6px; align-self: flex-start; }
.bk-shk-bubble.user { background: var(--sky-blue); color: #FFFFFF; border-bottom-right-radius: 6px; align-self: flex-end; box-shadow: 0 2px 8px rgba(18,64,160,0.22); } /* AUDIT-EXEMPT-LINE */
.bk-shk-bubble.toast { background: transparent; border: none; color: var(--mute); font-size: 12px; padding: 4px 10px; align-self: center; }
/* Pasos del agente — "lo que está haciendo" en vivo */
.bk-shk-bubble.step { background: transparent; border: none; color: var(--mute); font-size: 12px; padding: 3px 8px 3px 22px; align-self: flex-start; position: relative; opacity: 0.95; }
.bk-shk-bubble.step::before { content: ""; position: absolute; left: 6px; top: 50%; width: 9px; height: 9px; margin-top: -4.5px; border: 1.6px solid var(--ink-2, #2E3338); border-right-color: transparent; border-radius: 50%; animation: bkSpin 0.7s linear infinite; }
.bk-shk-bubble.step.done { opacity: 0.6; }
.bk-shk-bubble.step.done::before { content: ""; border: none; width: 10px; height: 10px; margin-top: -5px; animation: none; background: no-repeat center/contain url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2300AA6C' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>"); }
@keyframes bkSpin { to { transform: rotate(360deg); } }
/* Animación "pensando" (3 puntos) */
.bk-shk-bubble.thinking { padding: 12px 14px; }
.bk-dots { display: inline-flex; gap: 4px; align-items: center; }
.bk-dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--mute, #6B7685); display: inline-block; animation: bkBlink 1.2s ease-in-out infinite; }
.bk-dots i:nth-child(2) { animation-delay: 0.2s; }
.bk-dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes bkBlink { 0%, 60%, 100% { opacity: 0.25; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-2px); } }
.bk-shk-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 10px; }
.bk-shk-chip {
  background: var(--paper); border: 1px solid var(--line-2);
  border-radius: var(--r-pill); padding: 7px 12px;
  font-size: 12px; color: var(--ink-2); cursor: pointer; font-weight: 500;
  font-family: inherit;
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.bk-shk-chip:hover { background: var(--paper-2); border-color: var(--ink); }
.bk-shk-input-row { display: flex; gap: 8px; padding: 12px 14px; border-top: 1px solid var(--line); align-items: center; background: var(--paper); }
.bk-shk-input { flex: 1; min-width: 0; background: var(--paper-2); border: 1px solid var(--line-2); border-radius: var(--r-pill); padding: 11px 15px; font-size: 14px; outline: none; font-family: inherit; color: var(--ink); transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease), background var(--dur) var(--ease); }
.bk-shk-input:focus { border-color: var(--sky-blue); background: var(--paper); box-shadow: 0 0 0 3px rgba(18,64,160,0.12); }
.bk-shk-mic, .bk-shk-send {
  width: 40px; height: 40px; border-radius: 50%;
  border: none; cursor: pointer; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.bk-shk-mic { background: var(--paper-2); color: var(--ink-2); border: 1px solid var(--line); }
.bk-shk-mic:hover { background: var(--ink); color: var(--paper); }
.bk-shk-mic.listening { background: var(--danger); color: white; border-color: var(--danger); animation: bkMicPulse 1.2s ease-in-out infinite; }
@keyframes bkMicPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(231,8,102,.5); } 50% { box-shadow: 0 0 0 8px rgba(231,8,102,0); } }
.bk-shk-send { background: var(--sky-blue); color: #FFFFFF; box-shadow: 0 3px 10px rgba(18,64,160,0.30); transition: background var(--dur) var(--ease), box-shadow var(--dur) var(--ease); } /* AUDIT-EXEMPT-LINE */
.bk-shk-send:hover { background: var(--sky-blue-press); box-shadow: 0 5px 14px rgba(18,64,160,0.38); }
@media (hover: hover) and (pointer: fine) { .bk-shk-mic { display: none; } }

/* ── Profile Drawer ─────────────────────────────────────────── */
.bk-profile-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(5,32,60,0.55);
  backdrop-filter: blur(2px);
  opacity: 0; visibility: hidden; pointer-events: none;
  transition: opacity .18s ease, visibility .18s ease;
}
.bk-profile-overlay.is-open { opacity: 1; visibility: visible; pointer-events: auto; }
.bk-profile-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 201;
  width: 384px; max-width: 100vw;
  background: var(--paper); border-left: 1px solid var(--line);
  box-shadow: -24px 0 48px rgba(5,32,60,0.10);
  display: flex; flex-direction: column;
  transform: translate3d(100%,0,0);
  transition: transform .28s cubic-bezier(.16,1,.3,1);
  overflow: hidden;
  contain: layout paint style;
  will-change: transform;
}
.bk-profile-drawer.is-open { transform: translate3d(0,0,0); }

/* Header: fondo navy de marca, avatar en degradé de acción */
.bk-pd-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px;
  padding: 26px 22px 22px;
  background: var(--sky-navy);
  background-image: radial-gradient(120% 140% at 100% 0%, rgba(0,98,227,.35), transparent 55%);
  flex-shrink: 0;
  position: relative;
}
.bk-pd-close {
  width: 30px; height: 30px; border-radius: 8px;
  background: rgba(255,255,255,0.08); border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,0.7); flex-shrink: 0;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.bk-pd-close:hover { background: rgba(255,255,255,0.16); color: #FFFFFF; }
.bk-pd-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 20px; }
.bk-pd-body::-webkit-scrollbar { width: 0; }
.bk-pd-avatar-row {
  display: flex; align-items: center; gap: 14px;
}
.bk-pd-avatar {
  width: 56px; height: 56px; border-radius: 50%;
  background: linear-gradient(135deg, var(--sky-blue), var(--sky-blue-press));
  color: #FFFFFF;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 19px; letter-spacing: -0.02em;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px rgba(255,255,255,0.14), 0 4px 14px rgba(0,98,227,0.35);
}
.bk-pd-avatar-info { flex: 1; min-width: 0; }
.bk-pd-name { font-family: var(--font-display); font-size: 16px; font-weight: 600; color: #FFFFFF; letter-spacing: -0.01em; }
.bk-pd-email { font-size: 12px; color: rgba(255,255,255,0.55); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bk-pd-role-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--fs-label-3); font-weight: 600; letter-spacing: 0.02em;
  padding: 3px 9px; border-radius: var(--r-pill); margin-top: 7px;
  background: rgba(255,255,255,0.14); color: #FFFFFF;
}
.bk-pd-role-badge.admin { background: var(--danger); color: #FFFFFF; }
.bk-pd-section-label {
  font-family: var(--font-sans); font-size: var(--fs-label-3); font-weight: 600;
  letter-spacing: 0.02em; color: var(--mute);
  margin-bottom: 8px;
}
.bk-pd-card {
  background: var(--bone); border: 1px solid var(--line);
  border-radius: var(--r); padding: 16px;
}
.bk-pd-field { margin-bottom: 12px; }
.bk-pd-field:last-child { margin-bottom: 0; }
.bk-pd-field label { display: block; font-size: var(--fs-label-3); font-weight: 600; color: var(--mute); margin-bottom: 5px; letter-spacing: 0.02em; }
.bk-pd-field input {
  width: 100%; background: var(--paper-2); border: 1px solid var(--line-2);
  border-radius: var(--r-sm); padding: 10px 12px;
  font-size: 13px; font-family: inherit; color: var(--ink); outline: none;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.bk-pd-field input:focus { border-color: var(--sky-blue); box-shadow: var(--focus); background: var(--bone); }
.bk-pd-field input[readonly] { color: var(--mute); cursor: default; }
.bk-pd-btn {
  width: 100%; padding: 11px; border-radius: var(--r-pill);
  font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; border: none; transition: opacity .2s, transform .15s;
  display: flex; align-items: center; justify-content: center; gap: 7px;
}
.bk-pd-btn:hover { opacity: .9; }
.bk-pd-btn:active { transform: scale(.98); }
.bk-pd-btn-primary { background: var(--sky-navy); color: #FFFFFF; }
.bk-pd-btn-outline { background: var(--bone); border: 1px solid var(--line-2); color: var(--ink-2); margin-top: 8px; }
.bk-pd-btn-danger  { background: var(--bone); border: 1px solid rgba(231,8,102,.3); color: var(--danger); margin-top: 8px; }
.bk-pd-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--mute); margin-top: 8px;
}
.bk-pd-status .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--mute-3); flex-shrink: 0; }
.bk-pd-status .dot.ok { background: var(--success); }
.bk-pd-status .dot.warn { background: var(--warn); }
.bk-pd-toast {
  padding: 9px 12px; border-radius: var(--r-sm); font-size: 12px; font-weight: 500;
  margin-top: 8px; display: none;
}
.bk-pd-toast.ok   { background: var(--success-soft); color: var(--success); display: block; }
.bk-pd-toast.err  { background: var(--danger-soft);  color: var(--danger);  display: block; }
.bk-pd-foot {
  padding: 16px 20px; border-top: 1px solid var(--line); flex-shrink: 0;
}

/* Accordion menu — cada sección con su ícono en tile, estilo moderno */
.bk-pd-menu { display: flex; flex-direction: column; gap: 2px; }
.bk-pd-menu-item { border-radius: var(--r); transition: background var(--dur) var(--ease); }
.bk-pd-menu-item.is-open { background: var(--paper-2); }
.bk-pd-menu-trigger {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 10px; background: none; border: none; cursor: pointer;
  font-family: inherit; font-size: 13.5px; font-weight: 600; color: var(--ink);
  text-align: left; border-radius: var(--r);
  transition: background var(--dur) var(--ease);
}
.bk-pd-menu-item:not(.is-open) .bk-pd-menu-trigger:hover { background: var(--paper-2); }
.bk-pd-menu-trigger-left { display: flex; align-items: center; gap: 12px; }
.bk-pd-menu-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  background: var(--paper-2); color: var(--ink-2);
  display: flex; align-items: center; justify-content: center;
  position: relative;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.bk-pd-menu-icon svg { width: 16px; height: 16px; }
.bk-pd-menu-item.is-open .bk-pd-menu-icon { background: var(--sky-blue); color: #FFFFFF; }
.bk-pd-menu-icon--danger { color: var(--danger); }
.bk-pd-menu-item.is-open .bk-pd-menu-icon--danger { background: var(--danger); color: #FFFFFF; }
.bk-pd-menu-trigger-dot {
  position: absolute; bottom: -1px; right: -1px;
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--mute-3); border: 2px solid var(--paper);
}
.bk-pd-menu-trigger-dot.ok { background: var(--success); }
.bk-pd-menu-trigger-dot.warn { background: var(--warn); }
.bk-pd-menu-chevron {
  width: 16px; height: 16px; color: var(--mute); flex-shrink: 0;
  transition: transform .22s cubic-bezier(.16,1,.3,1);
}
.bk-pd-menu-item.is-open .bk-pd-menu-chevron { transform: rotate(180deg); color: var(--sky-blue); }
.bk-pd-menu-panel {
  overflow: hidden; display: none;
}
.bk-pd-menu-item.is-open .bk-pd-menu-panel { display: block; }
.bk-pd-menu-panel-inner { padding: 2px 10px 14px; }
/* Suscripcion */
.bk-pd-sub-badge {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: var(--fs-label-3); font-weight: 700; letter-spacing: 0.02em;
  padding: 3px 10px; border-radius: var(--r-pill);
  background: var(--forest-soft); color: var(--forest);
}
.bk-pd-sub-badge.inactive { background: var(--bone); color: var(--mute); }
.bk-pd-sub-info { font-size: 12px; color: var(--mute); margin: 8px 0 14px; line-height: 1.5; }


/* ── Módulos legacy: unificación visual Broquer sin cambiar lógica ── */
body[data-app]{background:var(--paper)!important;color:var(--ink)!important;font-family:var(--font-sans)!important;letter-spacing:-.01em!important}
body[data-app] main,body[data-app] .app-main,body[data-app] .screen,body[data-app] .container,body[data-app] .wrap{background:transparent!important}
body[data-app] .card,body[data-app] .ui-card,body[data-app] .panel,body[data-app] .box,body[data-app] .module,body[data-app] .section,body[data-app] .pf-card,body[data-app] .res-card,body[data-app] .form-card,body[data-app] .calc-card,body[data-app] .result-card{background:var(--bone)!important;border:1px solid var(--line)!important;border-radius:var(--r-lg)!important;box-shadow:var(--shadow-xs)!important;color:var(--ink)!important}
body[data-app] h1,body[data-app] h2,body[data-app] h3,body[data-app] .title,body[data-app] .card-title,body[data-app] .section-title{font-family:var(--font-display)!important;color:var(--ink)!important;letter-spacing:-.02em!important;font-weight:700!important}
body[data-app] label,body[data-app] .label,body[data-app] .field-label,body[data-app] .sec-lbl{color:var(--mute)!important;font-size:11px!important;font-weight:700!important;letter-spacing:.01em!important}
body[data-app] input,body[data-app] select,body[data-app] textarea{background:var(--bone)!important;border:1px solid var(--line-2)!important;border-radius:var(--r)!important;color:var(--ink)!important;box-shadow:none!important;min-height:42px}
body[data-app] input:focus,body[data-app] select:focus,body[data-app] textarea:focus{border-color:var(--sky-blue)!important;box-shadow:var(--focus)!important;outline:none!important}
body[data-app] button,body[data-app] .btn,body[data-app] .ui-btn,body[data-app] .btn-pdf,body[data-app] .isr-calc-btn{border-radius:var(--r-pill)!important;font-family:var(--font-sans)!important;font-weight:700!important;letter-spacing:-.005em!important}
body[data-app] .btn-primary,body[data-app] .ui-btn.forest,body[data-app] .isr-calc-btn,body[data-app] .btn-pdf,body[data-app] #gen-btn,body[data-app] #pdf-btn{background:var(--sky-blue)!important;color:#fff!important;border:1px solid var(--sky-blue)!important;box-shadow:0 1px 2px rgba(0,98,227,.18)!important}
body[data-app] .btn-primary:hover,body[data-app] .ui-btn.forest:hover,body[data-app] .isr-calc-btn:hover,body[data-app] .btn-pdf:hover,body[data-app] #gen-btn:hover,body[data-app] #pdf-btn:hover{background:var(--sky-blue-press)!important;border-color:var(--sky-blue-press)!important}
body[data-app] table{border-collapse:separate!important;border-spacing:0!important;background:var(--bone)!important;border:1px solid var(--line)!important;border-radius:var(--r)!important;overflow:hidden!important}
body[data-app] th{background:var(--paper-2)!important;color:var(--mute)!important;font-size:11px!important;letter-spacing:.01em!important}
body[data-app] td{border-color:var(--line)!important;color:var(--ink)!important}
/* ── Unificación del BOTÓN DE ACCIÓN PRIMARIA: azul en TODOS los módulos ──
   El sistema tenía primarios en negro/gris/navy/azul según el módulo. Aquí se
   fuerza el azul de acción en el botón principal de cada uno. Se dejan intactos
   los secundarios/ghost/cancelar/eliminar y las superficies de MARCA externa
   (verde de conectar WhatsApp, azul de conectar Facebook). Los futuros módulos
   deben usar .btn-primary o .bk-btn--forest para heredar esto. */
body[data-app] .btn-new-tarea,body[data-app] .tk-composer .go,body[data-app] .fa-btn-primary,body[data-app] .btn-new-prop,body[data-app] .eb-import-btn,body[data-app] .pf-save-btn,body[data-app] #ai-btn,body[data-app] #calc-btn,body[data-app] #btn-analizar-ia,body[data-app] #btn-clean,body[data-app] #fa-ai-btn,body[data-app] #fa-submit-btn,body[data-app] #tpl-submit-btn{background:var(--sky-blue)!important;color:#fff!important;border:1px solid var(--sky-blue)!important;box-shadow:0 1px 2px rgba(0,98,227,.18)!important}
body[data-app] .btn-new-tarea:hover,body[data-app] .tk-composer .go:hover,body[data-app] .fa-btn-primary:hover,body[data-app] .btn-new-prop:hover,body[data-app] .eb-import-btn:hover,body[data-app] .pf-save-btn:hover,body[data-app] #ai-btn:hover,body[data-app] #calc-btn:hover,body[data-app] #btn-analizar-ia:hover,body[data-app] #btn-clean:hover,body[data-app] #fa-ai-btn:hover,body[data-app] #fa-submit-btn:hover,body[data-app] #tpl-submit-btn:hover{background:var(--sky-blue-press)!important;border-color:var(--sky-blue-press)!important}
/* ── Unificación de TAMAÑO/FORMA de botones de acción (misma altura 44px,
   padding, tipo y radio píldora en todos los módulos). Se excluyen a propósito
   tiles de selección (.tipo-btn), toggles/segmented, chips de filtro y botones
   de icono, que tienen su propia geometría. */
body[data-app] .btn,body[data-app] .btn-primary,body[data-app] .ui-btn,body[data-app] .fa-btn,body[data-app] .wa-btn,body[data-app] .doc-btn,body[data-app] .gen-btn,body[data-app] .add-btn,body[data-app] .import-btn,body[data-app] .btn-new-tarea,body[data-app] .tk-composer .go,body[data-app] .btn-new-prop,body[data-app] .eb-import-btn,body[data-app] .pf-save-btn,body[data-app] .isr-calc-btn,body[data-app] .btn-pdf{min-height:44px!important;padding:0 18px!important;font-size:var(--fs-sm)!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:8px!important;line-height:1!important}
/* ── Unificación del TÍTULO DE PÁGINA: mismo tamaño que el header canónico
   (.bk-ph=30px) en los módulos que pintan su propio título ── */
body[data-app] .props-head__title h1,body[data-app] .page-head h1,body[data-app] .tk-head__title h1,body[data-app] .ms-head h1,body[data-app] .guide-title,body[data-app] .bx-list__title h1,body[data-app] .es-hero__brand{font-size:30px!important;font-weight:700!important;letter-spacing:-.02em!important;line-height:1.1!important}
/* ── Alineación título↔cuerpo: el header canónico respeta el ancho del módulo ── */
body[data-app] .bk-ph{max-width:var(--page-max,1180px)!important}
body[data-app="isr"],body[data-app="ficha-manual"],body[data-app="avm"],body[data-app="contratos"],body[data-app="mi-sitio"],body[data-app="image-cleaner"]{--page-max:var(--form-max,760px)}
body[data-app="blog"]{--page-max:960px}
body[data-app="facebook-ads"]{--page-max:980px}

/* ── Visor/entrega inmediata de archivos generados ── */
.bk-file-overlay{position:fixed;inset:0;z-index:2147483647;background:rgba(5,32,60,.46);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:18px}
.bk-file-sheet{width:min(920px,100%);height:min(86vh,820px);background:var(--paper);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow-xl);display:flex;flex-direction:column;overflow:hidden}
.bk-file-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line);color:var(--ink);background:var(--paper)}
.bk-file-head strong{display:block;font-size:15px}.bk-file-head span{display:block;font-size:12px;color:var(--mute);margin-top:2px}.bk-file-close{border:0!important;background:transparent!important;color:var(--ink)!important;font-size:28px!important;line-height:1!important;padding:4px 8px!important;box-shadow:none!important}.bk-file-frame{flex:1;width:100%;border:0;background:white}.bk-file-placeholder{flex:1;display:flex;align-items:center;justify-content:center;color:var(--mute);background:var(--bone)}.bk-file-actions{display:flex;gap:10px;padding:12px;border-top:1px solid var(--line);background:var(--paper-2)}.bk-file-primary,.bk-file-secondary{flex:1;text-align:center;border-radius:var(--r-pill)!important;padding:12px 14px!important;font-weight:700!important;text-decoration:none!important;font-family:var(--font-sans)!important}.bk-file-primary{background:var(--sky-blue)!important;color:#fff!important;border:1px solid var(--sky-blue)!important}.bk-file-secondary{background:#fff!important;color:var(--ink)!important;border:1px solid var(--line-2)!important}
@media(max-width:700px){.bk-file-overlay{padding:0;align-items:stretch}.bk-file-sheet{width:100%;height:100%;border-radius:0}.bk-file-actions{padding-bottom:calc(12px + env(safe-area-inset-bottom));}}

`;

  const styleEl = document.createElement('style');
  styleEl.id = '__brokr-shell-css';
  styleEl.textContent = css;
  document.head.appendChild(styleEl);
  // Re-anclar al final del head tras el load para vencer cualquier <style> de módulo
  // que se haya parseado después (orden de cascada de !important = último gana).
  function _reanchorShellCSS() {
    try {
      const s = document.getElementById('__brokr-shell-css');
      if (s && document.head.lastElementChild !== s) {
        document.head.appendChild(s);
      }
    } catch(e){}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _reanchorShellCSS);
  }
  window.addEventListener('load', _reanchorShellCSS);
  // Una pasada más después de un tick por si algún módulo inyecta <style> dinámicamente
  setTimeout(_reanchorShellCSS, 100);
  setTimeout(_reanchorShellCSS, 500);

  /* ════════════════════════════════════════════════════════════════
     Auth — gate + load profile
     ════════════════════════════════════════════════════════════════ */
  function getToken() {
    return localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || null;
  }
  async function sbFetch(p) {
    const tok = getToken() || SB_KEY;
    const r = await fetch(SB_URL + '/rest/v1/' + p, {
      headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok },
    });
    if (!r.ok) return [];
    return r.json();
  }
  function initials(name) {
    if (!name) return 'U';
    const parts = name.trim().split(/\s+/);
    return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || 'U';
  }
  function doLogout() {
    localStorage.removeItem('sb_token');
    localStorage.removeItem('sb_refresh');
    localStorage.removeItem('sb_user');
    localStorage.removeItem('sesion_activa');
    sessionStorage.clear();
    location.href = 'login.html';
  }
  window.doLogout = doLogout;

  /* Renueva el access token usando el refresh token guardado en localStorage.
     Devuelve el nuevo access token o null si falla. */
  async function tryRefreshToken() {
    const refresh = localStorage.getItem('sb_refresh');
    if (!refresh) return null;
    try {
      const r = await fetch(SB_URL + '/auth/v1/token?grant_type=refresh_token', {
        method: 'POST',
        headers: { apikey: SB_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!r.ok) return null;
      const d = await r.json();
      if (!d.access_token) return null;
      // Persistir los nuevos tokens
      localStorage.setItem('sb_token', d.access_token);
      localStorage.setItem('sb_refresh', d.refresh_token || refresh);
      localStorage.setItem('sb_user', JSON.stringify(d.user || {}));
      sessionStorage.setItem('sb_token', d.access_token);
      sessionStorage.setItem('sb_user', JSON.stringify(d.user || {}));
      return d.access_token;
    } catch (e) { return null; }
  }

  /* Destino cuando NO hay sesión: en web mandamos a la página comercial
     (landing.html) para que el visitante conozca Broquer antes de entrar;
     en la app nativa de iOS no existe página comercial, va directo a login. */
  function bkAuthRedirectTarget() {
    return IS_IOS_NATIVE ? 'login.html' : 'landing.html';
  }

  async function authInit() {
    let tok = getToken();

    // Si no hay token, intentar renovar con refresh token antes de redirigir
    if (!tok) {
      tok = await tryRefreshToken();
      if (!tok) { location.href = bkAuthRedirectTarget(); return null; }
    }

    let user = null;
    try {
      user = JSON.parse(localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || 'null');
    } catch (e) {}

    if (!user?.id) {
      // Intentar obtener usuario con el token actual
      try {
        const r = await fetch(SB_URL + '/auth/v1/user', { headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok } });
        if (r.status === 401) {
          // Token expirado — renovar y reintentar
          tok = await tryRefreshToken();
          if (!tok) { location.href = bkAuthRedirectTarget(); return null; }
          const r2 = await fetch(SB_URL + '/auth/v1/user', { headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok } });
          user = await r2.json();
        } else {
          user = await r.json();
        }
        if (user?.id) sessionStorage.setItem('sb_user', JSON.stringify(user));
      } catch (e) {}
    }

    if (!user?.id) { location.href = bkAuthRedirectTarget(); return null; }
    let profile = [];
    try { profile = await sbFetch(`usuarios?id=eq.${user.id}&select=nombre,telefono,rol`); } catch (e) {}
    const fullName = profile[0]?.nombre || user.email?.split('@')[0] || 'Usuario';
    return { user, fullName, profile: profile[0] || {}, isAdmin: profile[0]?.rol === 'admin' };
  }

  /* ════════════════════════════════════════════════════════════════
     DOM injection
     ════════════════════════════════════════════════════════════════ */
  const activeKey = (document.body.getAttribute('data-app') || 'home').toLowerCase();
  const activeMod = MODS.find(m => m.key === activeKey) || MODS[0];

  function buildSidebarLink(m, active) {
    return `<a href="${m.href}" class="bk-sb-link${m.key === active ? ' is-active' : ''}">${svg(m.icon)} ${m.label}</a>`;
  }
  // Un grupo del sidebar: mismo acordeón que ya tenía CRM, ahora para los
  // cinco. Arranca abierto solo el grupo donde está el módulo que se está
  // viendo; los demás cerrados, para que el menú quepa en una pantalla.
  function buildSidebarGroup(grupo, items, active) {
    if (!items.length) return '';
    const isOpen = items.some(m => m.key === active);
    const gid = 'bk-sb-g-' + grupo.key;
    return `<div class="bk-sb-block bk-sb-group${isOpen ? ' is-open' : ''}" id="${gid}">
      <button class="bk-sb-link bk-sb-trigger${isOpen ? ' is-active' : ''}" data-sb-group="${grupo.key}" type="button" aria-expanded="${isOpen ? 'true' : 'false'}" aria-controls="${gid}-sub">
        ${svg(grupo.icon)} ${grupo.label} ${svg('chevron', 16, 2, 'bk-sb-chevron')}
      </button>
      <div class="bk-sb-submenu" id="${gid}-sub">
        ${items.map(m => buildSidebarLink(m, active)).join('')}
      </div>
    </div>`;
  }
  // Todo lo que va de "Mi perfil" hacia abajo vive en su propio bloque,
  // pegado al fondo del drawer. La separación es por aire, no por raya.
  function buildCuentaSidebar(items, active) {
    const profileLink = `<a href="javascript:void(0)" class="bk-sb-link" onclick="openProfileDrawer()">${svg('user')} Mi perfil</a>`;
    return `<div class="bk-sb-block bk-sb-block--cuenta">${profileLink}${items.map(m => buildSidebarLink(m, active)).join('')}</div>`;
  }
  function buildBnavItem(m, active) {
    return `<a href="${m.href}" class="bk-bnav__item${m.key === active ? ' is-active' : ''}">${svg(m.icon, 22)} <span>${m.label.split(' ')[0]}</span></a>`;
  }

  function injectShell(profile) {
    // Wrap existing body content into .bk-page
    const pageWrap = document.createElement('div');
    pageWrap.className = 'bk-page';
    pageWrap.id = 'bk-page';
    while (document.body.firstChild) pageWrap.appendChild(document.body.firstChild);

    // ── Encabezado canónico unificado (idéntico en todos los módulos) ──
    // Se antepone al contenido de cada página. 'home' no está en PAGE_META.
    const _meta = PAGE_META[activeKey];
    if (_meta) {
      const hd = document.createElement('header');
      hd.className = 'bk-ph';
      const h = document.createElement('h1');
      h.className = 'bk-ph__title';
      h.textContent = _meta.title;
      hd.appendChild(h);
      if (_meta.sub) {
        const p = document.createElement('p');
        p.className = 'bk-ph__sub';
        p.textContent = _meta.sub;
        hd.appendChild(p);
      }
      pageWrap.insertBefore(hd, pageWrap.firstChild);
    }

    // ── Flecha sutil (azul tenue) de regreso a Inicio — en cada módulo, no en home ──
    if (activeKey !== 'home') {
      const backWrap = document.createElement('div');
      backWrap.className = 'bk-back-wrap';
      backWrap.innerHTML =
        `<a href="index.html" class="bk-back-home" aria-label="Volver a Inicio">` +
        `<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M19 12H5m0 0l7 7m-7-7l7-7"/></svg>` +
        `<span>Inicio</span></a>`;
      pageWrap.insertBefore(backWrap, pageWrap.firstChild);
    }

    // "Equipo" ya no vive en el menú: se movió a Perfil, que es donde vive el
    // resto de la configuración de la cuenta. Se sigue mostrando solo a
    // usuarios empresariales — los que pertenecen a una organización con tipo
    // 'empresa' (es_empresa, expuesto por /org) — pero eso ahora lo decide el
    // drawer de perfil, no el sidebar.
    const visible = m => (!m.adminOnly || profile?.isAdmin);
    const porGrupo = k => MODS.filter(m => m.group === k && visible(m));
    const cuenta   = porGrupo('cuenta');

    const shell = document.createElement('div');
    shell.className = 'bk-shell-root';
    shell.innerHTML = `
      <aside class="bk-sidebar" id="bk-sidebar">
        <div class="bk-sidebar__brand">
          <a href="index.html" aria-label="Ir al inicio Broquer"><img src="logotipo-white.png" alt="Broquer"/></a>
        </div>
        ${GRUPOS.map(g => buildSidebarGroup(g, porGrupo(g.key), activeKey)).join('')}
        ${buildCuentaSidebar(cuenta, activeKey)}
      </aside>

      <main class="bk-content">
        <div class="bk-mobile-head">
          <a href="index.html" aria-label="Ir al inicio Broquer"><img src="logo-broquer.png" alt="Broquer"/></a>
        </div>

        <div class="bk-topbar">
          <div class="bk-topbar__quote" id="bk-topbar-quote"></div>
          <div class="bk-topbar__actions"></div>
          <div class="bk-topbar__search-expand" id="bk-search-expand">
            <div class="bk-topbar__search-expand-inner">
              ${svg('search', 18, 2)}
              <input type="text" id="bk-search" placeholder="Buscar inmuebles, contactos, contratos…" autocomplete="off"/>
              <button class="bk-topbar__search-close" id="bk-search-close" aria-label="Cerrar búsqueda" type="button">
                <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          </div>
        </div>
      </main>
    `;
    document.body.appendChild(shell);

    // Acordeón de los grupos del sidebar. Abrir uno cierra los demás: son
    // cinco, y con dos abiertos al mismo tiempo ya hay que hacer scroll.
    shell.querySelectorAll('.bk-sb-trigger[data-sb-group]').forEach(trigger => {
      trigger.addEventListener('click', () => {
        const bloque = trigger.closest('.bk-sb-group');
        if (!bloque) return;
        const open = !bloque.classList.contains('is-open');
        shell.querySelectorAll('.bk-sb-group').forEach(otro => {
          if (otro === bloque) return;
          otro.classList.remove('is-open');
          const t = otro.querySelector('.bk-sb-trigger');
          if (t) {
            t.classList.remove('is-active');
            t.setAttribute('aria-expanded', 'false');
          }
        });
        bloque.classList.toggle('is-open', open);
        trigger.classList.toggle('is-active', open);
        trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });

    // ── Diagnóstico de cascada CSS del sidebar ──
    // Si algún módulo override el color de los links del drawer, lo detectamos
    // y forzamos un re-anclaje del style del shell al final del head.
    setTimeout(() => {
      try {
        const link = document.querySelector('.bk-sidebar .bk-sb-link:not(.is-active)');
        if (!link) return;
        const cs = getComputedStyle(link);
        const c = cs.color;
        // El color esperado es rgba(255,255,255,0.78) ≈ rgb(247, 245, 238) con alpha
        // Si en su lugar es muy oscuro (cualquier cosa cercana a negro), hay un override.
        const m = c.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
        if (m) {
          const r = +m[1], g = +m[2], b = +m[3];
          // si el promedio RGB es < 100, es un texto oscuro = invisible sobre fondo negro
          if ((r + g + b) / 3 < 100) {
            console.warn('[brokr-shell] Sidebar link color overriden:', c, '— forzando re-anclaje de CSS');
            _reanchorShellCSS();
            // Reforzar inline como último recurso
            document.querySelectorAll('.bk-sb-link:not(.is-active)').forEach(el => {
              el.style.setProperty('color', '#FFFFFF', 'important');
            });
          }
        }
      } catch(e){}
    }, 300);

    // Place page wrap inside content
    shell.querySelector('.bk-content').appendChild(pageWrap);

    // Bottom nav
    // PWA bottom nav (liquid glass): Inicio · Broquer (isotipo) · Perfil
    // El botón "Menú" se marca activo cuando estás dentro de cualquier módulo
    // agrupado, no solo del CRM.
    const grupoKeys = new Set(GRUPOS.map(g => g.key));
    const crmActive = MODS.some(m => m.key === activeKey && grupoKeys.has(m.group));

    const bnav = document.createElement('nav');
    bnav.className = 'bk-bnav';
    bnav.innerHTML =
      // Menú (hamburguesa): abre la hoja con CRM + herramientas + Mi perfil.
      `<button class="bk-bnav__item${crmActive ? ' is-active' : ''}" id="bk-bnav-crm" type="button" aria-label="Menú">${svg('homeList', 24)} <span>Menú</span></button>` +
      `<button class="bk-bnav__item bk-bnav__broquer" id="bk-bnav-shaark" type="button" aria-label="Abrir Broq">
         <img src="broq-icon.png" alt=""/> <span>Broq</span>
       </button>` +
      // El acceso del pulgar entra directo a la pestaña de chats, no a la de
      // ajustes: el agente aprieta esto para leer, no para configurar.
      // WhatsApp ya está abierto para todos los usuarios, así que este botón
      // es fijo en la barra inferior.
      `<a href="whatsapp.html#chats" class="bk-bnav__item${activeKey === 'whatsapp' ? ' is-active' : ''}" id="bk-bnav-chats" aria-label="Chats de WhatsApp">
         <span class="bk-bnav__ico">${svg('whatsapp', 24)}<i class="bk-badge" id="bk-bnav-badge"></i></span>
         <span>Chats</span>
       </a>`;
    document.body.appendChild(bnav);

    // ── Hoja de módulos (móvil): CRM completo + resto de herramientas ──
    const sheetBack = document.createElement('div');
    sheetBack.className = 'bk-sheet-back';
    sheetBack.id = 'bk-sheet-back';
    document.body.appendChild(sheetBack);

    const sheet = document.createElement('div');
    sheet.className = 'bk-sheet';
    sheet.id = 'bk-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Módulos');

    function sheetItem(m) {
      const act = m.key === activeKey ? ' is-active' : '';
      const badge = m.key === 'whatsapp' ? '<i class="bk-badge" id="bk-sheet-badge"></i>' : '';
      // "Mi sitio" en móvil/iOS no abre la pantalla de configuración: abre el sitio público.
      const attrs = m.key === 'mi-sitio'
        ? `href="javascript:void(0)" onclick="bkOpenMiSitio()"`
        : `href="${m.href}"`;
      return `<a ${attrs} class="bk-sheet__item${act}"><span class="bk-sheet__ico">${svg(m.icon, 19)}${badge}</span><span>${m.label}</span></a>`;
    }

    // "Mi perfil" vive dentro del menú (entre Blog y Ayuda), ya no en el bar inferior.
    const profileSheetItem =
      `<a href="javascript:void(0)" class="bk-sheet__item" onclick="window.bkToggleModsSheet&&window.bkToggleModsSheet(false);openProfileDrawer();">` +
      `<span class="bk-sheet__ico">${svg('user', 19)}</span><span>Mi perfil</span></a>`;

    // Los mismos grupos del sidebar, en el mismo orden. Que el agente encuentre
    // Cumplimiento en el mismo lugar en la compu y en el celular es medio punto
    // del rediseño.
    const seccion = (titulo, items, extra) =>
      items.length
        ? `<div class="bk-sheet__eyebrow">${titulo}</div>` +
          `<div class="bk-sheet__grid">${items.map(sheetItem).join('')}${extra || ''}</div>`
        : '';

    sheet.innerHTML =
      `<div class="bk-sheet__grip"></div>` +
      GRUPOS.map(g => seccion(g.label, porGrupo(g.key))).join('') +
      seccion('Cuenta', cuenta, profileSheetItem);
    document.body.appendChild(sheet);

    function toggleSheet(force) {
      const open = (typeof force === 'boolean') ? force : !sheet.classList.contains('is-open');
      sheet.classList.toggle('is-open', open);
      sheetBack.classList.toggle('is-open', open);
    }
    window.bkToggleModsSheet = toggleSheet;
    document.getElementById('bk-bnav-crm').addEventListener('click', () => toggleSheet());
    sheetBack.addEventListener('click', () => toggleSheet(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') toggleSheet(false); });

    // Broq FAB + popup
    const fab = document.createElement('button');
    fab.className = 'bk-shaark-fab';
    fab.id = 'bk-shaark-fab';
    fab.setAttribute('aria-label', 'Abrir Broq');
    fab.innerHTML = `<span class="bk-shaark-fab__pulse"></span><span class="bk-wake-dot" id="bk-wake-dot"></span><img src="broq-icon.png" alt="Broq"/>`;
    fab.addEventListener('click', () => toggleShaarkPopup());
    document.body.appendChild(fab);

    document.getElementById('bk-bnav-shaark').addEventListener('click', () => toggleShaarkPopup());

    const pop = document.createElement('div');
    pop.className = 'bk-shaark-popup';
    pop.id = 'bk-shaark-popup';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Broq — asistente');
    pop.innerHTML = `
      <div class="bk-shk-head">
        <div class="bk-shk-avatar"><img src="broq-icon.png" alt=""/></div>
        <div style="flex:1;min-width:0">
          <div class="bk-shk-name">Broq</div>
          <div class="bk-shk-status">En línea</div>
        </div>
        <button class="bk-shk-close" type="button" aria-label="Cerrar">${svg('close', 14, 2)}</button>
      </div>
      <div class="bk-shk-msgs" id="bk-shk-msgs">
        <div class="bk-shk-bubble bot" id="bk-welcome-msg">¡Hola! Soy Broq, tu asistente inteligente. ¿Qué puedo hacer por ti?</div>
      </div>
      <div class="bk-shk-input-row">
        <button class="bk-shk-mic" id="bk-shk-mic" type="button" aria-label="Hablar">${svg('mic', 16, 1.8)}</button>
        <input class="bk-shk-input" id="bk-shk-input" type="text" placeholder="Pregunta lo que necesites…"/>
        <button class="bk-shk-send" id="bk-shk-send" type="button" aria-label="Enviar">${svg('send', 15, 2)}</button>
      </div>
    `;
    document.body.appendChild(pop);

    // Wire popup events
    pop.querySelector('.bk-shk-close').addEventListener('click', () => toggleShaarkPopup(false));
    document.getElementById('bk-shk-send').addEventListener('click', shaarkFabSend);
    document.getElementById('bk-shk-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') { shaarkFabSend(); }
    });
    document.getElementById('bk-shk-mic').addEventListener('click', toggleScwVoice);
  }

  /* ════════════════════════════════════════════════════════════════
     Broq — popup, fetch, voice, wake word
     ════════════════════════════════════════════════════════════════ */
  let shaarkOpen = false;
  let shaarkMsgs = [];

  function toggleShaarkPopup(force) {
    const p = document.getElementById('bk-shaark-popup');
    if (!p) return;
    shaarkOpen = (typeof force === 'boolean') ? force : !shaarkOpen;
    p.classList.toggle('is-open', shaarkOpen);
    if (shaarkOpen) {
      refreshShaarkChips();
      setTimeout(() => {
        const m = document.getElementById('bk-shk-msgs');
        if (m) m.scrollTop = m.scrollHeight;
        document.getElementById('bk-shk-input')?.focus();
      }, 60);
    }
  }
  window.toggleShaarkPopup = toggleShaarkPopup;

  function refreshShaarkChips() {
    const el = document.getElementById('bk-shk-chips');
    if (!el) return; // chips eliminados
    const chips = SHAARK_CHIPS_MAP[activeKey] || SHAARK_CHIPS_MAP.home;
    el.innerHTML = chips.map(c => `<button class="bk-shk-chip" type="button" data-msg="${c.m.replace(/"/g, '&quot;')}">${c.l}</button>`).join('');
    el.querySelectorAll('.bk-shk-chip').forEach(b => b.addEventListener('click', () => shaarkChip(b.dataset.msg)));
  }

  function addBubble(text, type) {
    const wrap = document.getElementById('bk-shk-msgs');
    if (!wrap) return null;
    const div = document.createElement('div');
    div.className = 'bk-shk-bubble ' + type;
    div.textContent = text;
    wrap.appendChild(div);
    wrap.scrollTop = wrap.scrollHeight;
    return div;
  }

  function shaarkFabSend() {
    if (!window.__BK_SUB_ACTIVE) { showBroquerMaxModal(); return; }
    const input = document.getElementById('bk-shk-input');
    if (!input) return;
    const text = (input.value || '').trim();
    if (!text) return;
    addBubble(text, 'user');
    input.value = '';
    shaarkMsgs.push({ role: 'user', content: text });
    shaarkFabFetch(text);
  }
  window.shaarkFabSend = shaarkFabSend;

  function shaarkChip(text) {
    if (!window.__BK_SUB_ACTIVE) { showBroquerMaxModal(); return; }
    addBubble(text, 'user');
    shaarkMsgs.push({ role: 'user', content: text });
    shaarkFabFetch(text);
  }
  window.shaarkChip = shaarkChip;

  /* ── Lee el nombre de pila del usuario (para que el agente lo use) ── */
  function _shaarkNombreUsuario() {
    try {
      const raw = localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}';
      const u = JSON.parse(raw);
      const meta = u.user_metadata || u.metadata || {};
      const full = (meta.nombre || meta.full_name || meta.name || u.nombre || u.email || '').trim();
      if (!full) return '';
      return full.split(/[ @.]/)[0]; // primer nombre / antes del @
    } catch (_) { return ''; }
  }

  /* ── Burbuja de estado en vivo ("pensando…", "revisando tu cartera…") ── */
  function _addStepBubble(text) {
    const wrap = document.getElementById('bk-shk-msgs');
    if (!wrap) return null;
    const div = document.createElement('div');
    div.className = 'bk-shk-bubble step';
    div.textContent = text;
    wrap.appendChild(div);
    wrap.scrollTop = wrap.scrollHeight;
    return div;
  }

  async function shaarkFabFetch(text) {
    const wrap = document.getElementById('bk-shk-msgs');
    const typing = addBubble('', 'bot');
    typing.classList.add('thinking');
    typing.innerHTML = '<span class="bk-dots"><i></i><i></i><i></i></span>';

    let data = null, usedFallback = false;
    try {
      const _tokAgente = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || '';
      const r = await fetch(API_BASE + '/agent', {
        method: 'POST',
        // Se manda la sesión para que el backend sepa quién pregunta. Sin esto,
        // Broq quedaba abierto a cualquiera en internet con nuestra cuenta.
        headers: Object.assign({ 'Content-Type': 'application/json' },
                               _tokAgente ? { Authorization: 'Bearer ' + _tokAgente } : {}),
        body: JSON.stringify({
          messages: shaarkMsgs,
          context: getCurrentContext(),
          nombre: _shaarkNombreUsuario(),
        }),
      });
      if (r.status === 404 || r.status === 405) { usedFallback = true; }
      else {
        data = await r.json();
        if (!r.ok) {
          typing.classList.remove('thinking');
          typing.textContent = (data && data.detail) ? data.detail : 'Error del servidor.';
          return;
        }
      }
    } catch (e) {
      usedFallback = true; // sin /agent → intentamos el chat clásico
    }

    // ── Fallback al chat clásico (/chat-claude) si /agent no está disponible ──
    if (usedFallback) {
      try {
        const _tokChat = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || '';
        const r2 = await fetch(API_BASE + '/chat-claude', {
          method: 'POST',
          headers: Object.assign({ 'Content-Type': 'application/json' },
                                 _tokChat ? { Authorization: 'Bearer ' + _tokChat } : {}),
          body: JSON.stringify({ max_tokens: 1200, messages: shaarkMsgs, context: getCurrentContext() }),
        });
        const d2 = await r2.json();
        typing.classList.remove('thinking');
        if (!r2.ok) { typing.textContent = (d2.detail || 'Error del servidor.'); return; }
        const reply = d2.choices?.[0]?.message?.content || '';
        const accionRe = /\[ACCION\](.*?)\[\/ACCION\]/gs; let m;
        while ((m = accionRe.exec(reply)) !== null) {
          try { handleAccion(JSON.parse(m[1].trim())); } catch (_) {}
        }
        const clean = reply.replace(/\[ACCION\].*?\[\/ACCION\]/gs, '').trim() || 'Listo.';
        shaarkMsgs.push({ role: 'assistant', content: clean });
        typing.textContent = clean;
        if (window._scwLastWasVoice) { speak(clean); window._scwLastWasVoice = false; }
      } catch (e) {
        typing.classList.remove('thinking');
        typing.textContent = 'Sin conexión. Revisa tu internet.';
      }
      if (wrap) wrap.scrollTop = wrap.scrollHeight;
      return;
    }

    // ── Respuesta del agente: {reply, client_actions, steps} ──
    typing.classList.remove('thinking');
    const reply   = (data && data.reply) || data?.choices?.[0]?.message?.content || 'Listo.';
    const steps   = (data && Array.isArray(data.steps)) ? data.steps : [];
    const actions = (data && Array.isArray(data.client_actions)) ? data.client_actions : [];

    // Muestra brevemente lo que hizo el agente (efecto "trabajando")
    const uniqSteps = steps.filter((s, i) => steps.indexOf(s) === i);
    for (const s of uniqSteps) {
      const sb = _addStepBubble(s);
      await new Promise(res => setTimeout(res, 280));
      if (sb) sb.classList.add('done');
    }

    shaarkMsgs.push({ role: 'assistant', content: reply });
    typing.textContent = reply;
    if (window._scwLastWasVoice) { speak(reply); window._scwLastWasVoice = false; }

    // Ejecuta las acciones encadenadas (cada una muestra su propio progreso real)
    for (const ac of actions) {
      try { handleAccion(ac); } catch (e) { /* noop */ }
    }

    if (wrap) wrap.scrollTop = wrap.scrollHeight;
  }

  /* Action dispatch — across-page architecture: stash payload in
     sessionStorage and navigate; destination page reads on load. */
  function handleAccion(ac) {
    if (!ac || !ac.tipo) return;
    const stash = (key, payload) => sessionStorage.setItem('shaark_' + key, JSON.stringify(payload));
    switch (ac.tipo) {
      case 'navegar': {
        const m = MODS.find(x => x.key === ac.modulo);
        if (m) location.href = m.href;
        break;
      }
      case 'llenar_isr':         stash('isr', ac);          location.href = 'isr.html'; break;
      case 'llenar_avm':
      case 'opinion_valor_web':  stash('avm', ac);          location.href = 'avm.html'; break;
      case 'llenar_contrato':    stash('contrato', ac);     location.href = 'contratos.html'; break;
      case 'crear_ficha':        // ficha.html eliminada → usar ficha-manual
      case 'crear_ficha_manual': stash('ficha_manual', ac); location.href = 'ficha-manual.html'; break;
      case 'buscar_propiedad':   stash('buscar_props', ac); location.href = 'propiedades.html'; break;
      case 'confirmar_campana':  stash('fb_ads', ac);       location.href = 'facebook-ads.html'; break;

      // ── ACCIONES DIRECTAS — ejecutan en la ventana del asistente ──
      case 'agregar_contacto':         agregarContactoDirecto(ac); break;
      case 'crear_inmueble_directo':    crearInmuebleDirecto(ac); break;
      case 'crear_tarea_directo':      crearTareaDirecto(ac); break;
      case 'generar_contrato_directo': generarContratoDirecto(ac); break;
      case 'calcular_isr_directo':     calcularISRDirecto(ac); break;
      case 'estimar_valor_directo':    estimarValorDirecto(ac); break;
      case 'generar_reporte_estadisticas': generarReporteEstadisticas(ac); break;
      case 'abrir_pdf':                abrirPdfDirecto(ac); break;
    }
  }

  /* Abre/descarga un PDF que el servidor ya generó (p. ej. la ficha técnica).
     No navega a ningún módulo: el documento llega listo. */
  function abrirPdfDirecto(ac) {
    try {
      const API = window.API_BASE || 'https://api.broquer.app';
      let url = ac.url || '';
      if (!url) return;
      if (url.indexOf('http') !== 0) url = API + url;
      const nombre = ac.filename || 'documento.pdf';
      // Abrir en nueva pestaña/visor (en iOS lo muestra; en escritorio descarga).
      const win = window.open(url, '_blank');
      // Respaldo en el chat: enlace por si el navegador bloqueó la ventana.
      _addAssistantBubble(
        'Tu ficha está lista: <a href="' + url + '" target="_blank" rel="noopener" download="' +
        nombre + '" style="color:var(--ink-2,#2E3338);font-weight:600;text-decoration:underline;">abrir el PDF</a>.'
      );
      if (!win) {
        // Popup bloqueado: forzar descarga con un <a> temporal.
        const a = document.createElement('a');
        a.href = url; a.download = nombre; a.target = '_blank'; a.rel = 'noopener';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
      }
    } catch (e) { /* noop */ }
  }


  /* ── Entrega universal de archivos (iPhone/PWA/WebView/Desktop) ─────────
     iOS no siempre respeta <a download> dentro de WKWebView. Este helper
     intenta primero el share sheet nativo con el archivo real y, si no está
     disponible, muestra un visor inmediato con botones de compartir/abrir. */
  async function deliverGeneratedFile(blob, filename, opts = {}) {
    const type = opts.type || blob.type || 'application/octet-stream';
    const title = opts.title || filename || 'Archivo Broquer';
    const safeName = filename || (title.replace(/\s+/g, '_') + (type.includes('pdf') ? '.pdf' : ''));

    // ── WEB (navegador de escritorio o móvil, PWA incluida): descarga
    // directa al dispositivo, igual que cualquier archivo de internet.
    // Nada de hoja de compartir ni vista previa — eso solo aplica a la
    // app nativa de iOS, donde sí hay una carpeta de Descargas visible
    // y el usuario espera compartir/guardar desde ahí.
    if (!IS_IOS_NATIVE) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = safeName;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
      return { method: 'download' };
    }

    let file = null;
    try { file = new File([blob], safeName, { type }); } catch (_) {}

    if (file && navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
      try {
        await navigator.share({ title, text: opts.text || 'Archivo generado por Broquer', files: [file] });
        return { method: 'share' };
      } catch (e) {
        if (e && e.name === 'AbortError') return { method: 'share-cancelled' };
      }
    }

    const url = URL.createObjectURL(blob);
    const isPdf = type.includes('pdf') || /\.pdf$/i.test(safeName);
    const overlay = document.createElement('div');
    overlay.className = 'bk-file-overlay';
    overlay.innerHTML = `
      <div class="bk-file-sheet" role="dialog" aria-modal="true" aria-label="Archivo listo">
        <div class="bk-file-head">
          <div><strong>${title}</strong><span>${safeName}</span></div>
          <button type="button" class="bk-file-close" aria-label="Cerrar">×</button>
        </div>
        ${isPdf ? `<iframe class="bk-file-frame" src="${url}" title="${safeName}"></iframe>` : `<div class="bk-file-placeholder">Archivo listo para compartir.</div>`}
        <div class="bk-file-actions">
          <button type="button" class="bk-file-primary">Compartir / reenviar</button>
          <a class="bk-file-secondary" href="${url}" download="${safeName}" target="_blank" rel="noopener">Abrir / descargar</a>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => { overlay.remove(); setTimeout(() => URL.revokeObjectURL(url), 3000); };
    overlay.querySelector('.bk-file-close')?.addEventListener('click', close);
    overlay.querySelector('.bk-file-primary')?.addEventListener('click', async () => {
      if (file && navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
        try { await navigator.share({ title, text: opts.text || 'Archivo generado por Broquer', files: [file] }); return; } catch (_) {}
      }
      window.open(url, '_blank', 'noopener');
    });
    return { method: 'viewer', url };
  }
  window.broquerDeliverBlob = deliverGeneratedFile;

  /* ── Acciones directas: ejecutan API y muestran resultado en chat ── */
  function _addAssistantBubble(html) {
    const wrap = document.getElementById('bk-shk-msgs');
    if (!wrap) return;
    const b = document.createElement('div');
    b.className = 'bk-shk-bubble bot';
    b.innerHTML = html;
    wrap.appendChild(b);
    wrap.scrollTop = wrap.scrollHeight;
    return b;
  }

  async function agregarContactoDirecto(ac) {
    try {
      const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
      const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';
      const tok = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token');
      const userRaw = localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}';
      const user = JSON.parse(userRaw);
      if (!tok || !user.id) { _addAssistantBubble('No pude crear el contacto: tu sesión expiró.'); return; }
      const payload = {
        user_id: user.id,
        nombre: (ac.nombre || '').trim(),
        telefono: (ac.telefono || '').replace(/[^+\d]/g, '').slice(0, 20),
        email: (ac.email || '').trim(),
        empresa: ac.empresa || null,
        tipo: ac.tipo_contacto || 'prospecto',
        notas: ac.notas || null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      const r = await fetch(`${SB_URL}/rest/v1/contactos`, {
        method: 'POST',
        headers: {
          'apikey': SB_KEY,
          'Authorization': 'Bearer ' + tok,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal'
        },
        body: JSON.stringify(payload)
      });
      if (r.ok) {
        _addAssistantBubble(`✓ Contacto agregado: <strong>${payload.nombre || 'sin nombre'}</strong>${payload.telefono ? ' · ' + payload.telefono : ''}${payload.email ? ' · ' + payload.email : ''}. Ya está en tu CRM.`);
      } else {
        _addAssistantBubble('No pude agregar el contacto. Revisa los datos e inténtalo otra vez.');
      }
    } catch (e) {
      _addAssistantBubble('No pude agregar el contacto: ' + (e.message || e));
    }
  }

  async function crearTareaDirecto(ac) {
    try {
      const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
      const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';
      const tok = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token');
      const userRaw = localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}';
      const user = JSON.parse(userRaw);
      if (!tok || !user.id) { _addAssistantBubble('No pude crear la tarea: tu sesión expiró.'); return; }
      const titulo = (ac.titulo || '').trim();
      if (!titulo) { _addAssistantBubble('Necesito un título para crear la tarea.'); return; }
      const fecha = (ac.fecha || '').trim();
      const hora = (ac.hora || '').trim() || '12:00';
      const payload = {
        user_id: user.id,
        titulo,
        fecha_entrega: fecha ? (fecha + 'T' + hora + ':00') : null,
        notas: ac.notas || null,
        contacto_id: ac.contacto_id || null,
        propiedad_id: ac.propiedad_id || null,
      };
      const headersBase = {
        'apikey': SB_KEY, 'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json',
      };
      const r = await fetch(`${SB_URL}/rest/v1/tareas`, {
        method: 'POST',
        headers: Object.assign({}, headersBase, { 'Prefer': 'return=representation' }),
        body: JSON.stringify(payload)
      });
      if (!r.ok) { _addAssistantBubble('No pude crear la tarea. Revisa los datos e inténtalo otra vez.'); return; }
      const filas = await r.json();
      const nueva = Array.isArray(filas) ? filas[0] : filas;
      // Además de la columna suelta, se deja el vínculo en las tablas de
      // varios-a-varios (tareas_contactos / tareas_propiedades), así la tarea
      // aparece también si más adelante se le agregan más vínculos desde ahí.
      if (nueva && nueva.id) {
        const vinculos = [];
        if (ac.contacto_id) vinculos.push(fetch(`${SB_URL}/rest/v1/tareas_contactos`, {
          method: 'POST', headers: Object.assign({}, headersBase, { 'Prefer': 'return=minimal' }),
          body: JSON.stringify({ user_id: user.id, tarea_id: nueva.id, contacto_id: ac.contacto_id })
        }).catch(() => {}));
        if (ac.propiedad_id) vinculos.push(fetch(`${SB_URL}/rest/v1/tareas_propiedades`, {
          method: 'POST', headers: Object.assign({}, headersBase, { 'Prefer': 'return=minimal' }),
          body: JSON.stringify({ user_id: user.id, tarea_id: nueva.id, propiedad_id: ac.propiedad_id })
        }).catch(() => {}));
        if (vinculos.length) await Promise.all(vinculos);
      }
      const cuando = fecha ? (' para el ' + fecha + (ac.hora ? ' a las ' + hora : '')) : '';
      _addAssistantBubble(`✓ Tarea creada: <strong>${titulo}</strong>${cuando}. Ya está en tu módulo de Tareas.`);
    } catch (e) {
      _addAssistantBubble('No pude crear la tarea: ' + (e.message || e));
    }
  }

  async function crearInmuebleDirecto(ac) {
    try {
      const tok = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token');
      const userRaw = localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}';
      const user = JSON.parse(userRaw);
      if (!tok || !user.id) { _addAssistantBubble('No pude crear el inmueble: tu sesión expiró.'); return; }
      if (!window.brokrSb || !window.brokrSb.rest) { _addAssistantBubble('No pude crear el inmueble: la conexión con Broquer aún no está lista. Intenta otra vez en un segundo.'); return; }

      const num = (v) => {
        if (v === undefined || v === null || v === '') return null;
        const n = Number(String(v).replace(/[$,\s]/g, ''));
        return Number.isFinite(n) ? n : null;
      };
      const txt = (v) => (v === undefined || v === null) ? '' : String(v).trim();
      const tipo = txt(ac.tipo || ac.tipo_inmueble).toLowerCase();
      const operacion = txt(ac.operacion).toLowerCase();
      const titulo = txt(ac.titulo) || [tipo || 'Inmueble', operacion ? 'en ' + operacion : '', txt(ac.colonia)].filter(Boolean).join(' ');
      const payload = {
        user_id: user.id,
        titulo,
        tipo: tipo || 'casa',
        operacion: operacion || 'venta',
        estatus: txt(ac.estatus) || 'activa',
        precio: num(ac.precio),
        moneda: txt(ac.moneda) || 'MXN',
        calle: txt(ac.calle),
        num_exterior: txt(ac.num_exterior),
        num_interior: txt(ac.num_interior),
        colonia: txt(ac.colonia),
        ciudad: txt(ac.ciudad) || 'Morelia',
        estado: txt(ac.estado) || 'Michoacán',
        cp: txt(ac.cp),
        m2_construccion: num(ac.m2_construccion),
        m2_terreno: num(ac.m2_terreno),
        recamaras: num(ac.recamaras),
        banos: num(ac.banos),
        medio_bano: num(ac.medio_bano),
        estacionamientos: num(ac.estacionamientos),
        anio_construccion: num(ac.anio_construccion),
        nivel: txt(ac.nivel),
        mantenimiento: num(ac.mantenimiento),
        amenidades: Array.isArray(ac.amenidades) ? ac.amenidades : txt(ac.amenidades).split(',').map(s => s.trim()).filter(Boolean),
        descripcion: txt(ac.descripcion),
        fotos: Array.isArray(ac.fotos) ? ac.fotos : [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      if (!payload.titulo || !payload.colonia || !payload.precio) {
        _addAssistantBubble('Me faltan datos obligatorios para crear el inmueble: título o descripción, colonia y precio.');
        return;
      }
      const rows = await window.brokrSb.rest('propiedades', { method: 'POST', body: payload });
      const id = Array.isArray(rows) && rows[0] ? rows[0].id : '';
      _addAssistantBubble(`✓ Inmueble creado: <strong>${payload.titulo}</strong>${payload.colonia ? ' · ' + payload.colonia : ''}. Ya está en Tus Inmuebles.`);
      if (id) sessionStorage.setItem('broq_last_property_id', id);
      if (document.body && document.body.dataset.app === 'props' && typeof window.loadProps === 'function') {
        try { window.loadProps(); } catch (_) {}
      }
    } catch (e) {
      _addAssistantBubble('No pude crear el inmueble: ' + (e.message || e));
    }
  }

  async function generarContratoDirecto(ac) {
    try {
      const API = window.API_BASE || 'https://api.broquer.app';
      const tipo = ac.subtipo === 'promesa' ? 'promesa' : 'arrendamiento';
      _addAssistantBubble(`Generando contrato de ${tipo === 'promesa' ? 'promesa de compraventa' : 'arrendamiento'}…`);
      const tok = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token');
      if (!tok) { _addAssistantBubble('No pude generar el contrato: tu sesión expiró.'); return; }
      const r = await fetch(API + '/contrato', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok },
        body: JSON.stringify({ tipo, datos: ac.datos || ac, clausulas_especiales: ac.clausulas_especiales || [] })
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        _addAssistantBubble('No pude generar el contrato: ' + (j.detail || ('error ' + r.status)));
        return;
      }
      const blob = await r.blob();
      const filename = tipo === 'promesa' ? 'Promesa_Compraventa.docx' : 'Contrato_Arrendamiento.docx';
      await deliverGeneratedFile(blob, filename, {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        title: 'Contrato listo',
        text: 'Contrato generado por Broquer'
      });
      _addAssistantBubble(`✓ <strong>Contrato listo.</strong> Se abrió en pantalla para compartirlo o guardarlo.`);
    } catch (e) {
      _addAssistantBubble('No pude generar el contrato: ' + (e.message || e));
    }
  }

  /* ── Calcular ISR + entregar PDF, sin sacar al usuario del chat ── */
  /* Implementación: iframe oculto carga isr.html?asistente=1, que lee los
     datos de sessionStorage, ejecuta el cálculo verificado, dispara la
     descarga del PDF y notifica de vuelta por postMessage. */
  async function calcularISRDirecto(ac) {
    const bubble = _addAssistantBubble('Calculando ISR y preparando tu PDF…');
    try {
      // Limpia handlers previos
      if (window._asistenteISRListener) {
        window.removeEventListener('message', window._asistenteISRListener);
      }
      // Listener para escuchar que el iframe terminó
      let timeoutId = null;
      window._asistenteISRListener = (e) => {
        if (!e.data || e.data.tipo !== 'asistente_isr_done') return;
        clearTimeout(timeoutId);
        window.removeEventListener('message', window._asistenteISRListener);
        const fr = document.getElementById('asistente-isr-frame');
        if (fr && fr.parentNode) fr.parentNode.removeChild(fr);
        if (e.data.ok) {
          bubble.innerHTML = '✓ <strong>Tu PDF de ISR se descargó.</strong> Revisa tu carpeta de descargas. ¿Necesitas otro?';
        } else {
          bubble.textContent = 'No pude generar el PDF: ' + (e.data.error || 'error desconocido');
        }
      };
      window.addEventListener('message', window._asistenteISRListener);

      // Guarda los datos en sessionStorage (mismo canal que el flujo "llenar_isr")
      sessionStorage.setItem('shaark_isr', JSON.stringify(ac));
      // Bandera para que isr.html ejecute en modo asistente
      sessionStorage.setItem('shaark_isr_auto', '1');

      // Crea iframe oculto que carga isr.html en modo asistente
      let fr = document.getElementById('asistente-isr-frame');
      if (fr) fr.remove();
      fr = document.createElement('iframe');
      fr.id = 'asistente-isr-frame';
      fr.src = 'isr.html?asistente=1';
      fr.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1024px;height:768px;border:0;opacity:0;pointer-events:none';
      document.body.appendChild(fr);

      // Si en 60s no recibimos respuesta, asumimos error y limpiamos
      timeoutId = setTimeout(() => {
        window.removeEventListener('message', window._asistenteISRListener);
        const fr2 = document.getElementById('asistente-isr-frame');
        if (fr2 && fr2.parentNode) fr2.parentNode.removeChild(fr2);
        bubble.textContent = 'No pude generar el PDF en 60 segundos. Intenta de nuevo o usa el módulo ISR directamente.';
      }, 60000);
    } catch (e) {
      bubble.textContent = 'No pude calcular el ISR: ' + (e.message || e);
    }
  }

  /* ── Estimación de valor + PDF directo, sin sacar al usuario del chat ── */
  async function estimarValorDirecto(ac) {
    const bubble = _addAssistantBubble('Buscando comparables en internet… (esto puede tomar algunos minutos)');
    try {
      const API = window.API_BASE || 'https://api.broquer.app';
      const body = {
        colonia: (ac.colonia || '').trim(),
        tipo_inmueble: ac.tipo_inmueble || 'casa',
        operacion: ac.operacion || 'venta',
        m2_terreno: parseFloat(ac.m2_terreno) || 0,
        m2_construccion: parseFloat(ac.m2_construccion) || 0,
        recamaras: parseInt(ac.recamaras) || 0,
        banos: parseFloat(ac.banos) || 0,
        estacionamientos: parseInt(ac.estacionamientos) || 0,
        condicion_terreno: ac.condicion_terreno || '',
        ciudad: ac.ciudad || '',
        comentarios: ac.comentarios || '',
      };
      // 1) Pedir la estimación con comparables
      const _tokAvm = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || '';
      const r1 = await fetch(API + '/api/avm-websearch', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' },
                               _tokAvm ? { Authorization: 'Bearer ' + _tokAvm } : {}),
        body: JSON.stringify(body),
      });
      const resultado = await r1.json();
      if (!r1.ok) {
        bubble.textContent = 'No pude completar la estimación: ' + (resultado.detail || 'error del servidor');
        return;
      }

      // 2) Mostrar resumen breve en el chat
      const fmt = (n) => '$' + Math.round(Number(n) || 0).toLocaleString('es-MX');
      const ne = resultado.valor_estimado;
      const lo = resultado.valor_minimo;
      const hi = resultado.valor_maximo;
      const vpm = resultado.valor_por_m2;
      const nc = (resultado.comparables || []).length;
      bubble.innerHTML =
        '<strong>Estimación lista.</strong><br>' +
        'Valor estimado: <strong>' + fmt(ne) + '</strong><br>' +
        'Rango: ' + fmt(lo) + ' – ' + fmt(hi) +
        (vpm > 0 ? ' · ' + fmt(vpm) + '/m²' : '') + '<br>' +
        nc + ' comparables encontrados. Preparando PDF…';

      // 3) Generar PDF
      const r2 = await fetch(API + '/avm-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resultado, agente: 'Agente Broquer®' }),
      });
      const tokData = await r2.json();
      if (!r2.ok) {
        bubble.innerHTML += '<br>No pude generar el PDF: ' + (tokData.detail || 'error');
        return;
      }
      // 4) Descargar el blob
      const pdfResp = await fetch(API + '/avm-pdf/' + tokData.token);
      if (!pdfResp.ok) {
        bubble.innerHTML += '<br>No pude obtener el PDF (' + pdfResp.status + ').';
        return;
      }
      const blob = await pdfResp.blob();
      const filename = tokData.filename || ('Estimacion_Valor_' + (body.colonia || 'inmueble') + '.pdf');
      await deliverGeneratedFile(blob, filename, { type: 'application/pdf', title: 'Estimación de valor lista', text: 'Estimación de valor generada por Broquer' });
      bubble.innerHTML += '<br>✓ <strong>PDF listo.</strong> Se abrió en pantalla para compartirlo o guardarlo.';
    } catch (e) {
      bubble.textContent = 'No pude completar la estimación: ' + (e.message || e);
    }
  }


  async function loadJsPdf() {
    if (window.jspdf && window.jspdf.jsPDF) return window.jspdf.jsPDF;
    await new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-broquer-jspdf="1"]');
      if (existing) { existing.addEventListener('load', resolve, { once:true }); existing.addEventListener('error', reject, { once:true }); return; }
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
      s.async = true;
      s.dataset.broquerJspdf = '1';
      s.onload = resolve;
      s.onerror = () => reject(new Error('No se pudo cargar el generador PDF.'));
      document.head.appendChild(s);
    });
    return window.jspdf && window.jspdf.jsPDF;
  }

  async function generarReporteEstadisticas(ac) {
    const bubble = _addAssistantBubble('Creando reporte ejecutivo de estadísticas…');
    try {
      const jsPDF = await loadJsPdf();
      if (!jsPDF) throw new Error('Generador PDF no disponible.');
      const doc = new jsPDF({ unit: 'pt', format: 'letter' });
      const margin = 54;
      const width = doc.internal.pageSize.getWidth();
      const height = doc.internal.pageSize.getHeight();
      const title = (ac.titulo || 'Reporte ejecutivo de estadísticas').trim();
      const periodo = (ac.periodo || '').trim();
      const contenido = String(ac.contenido || '').trim();
      const fecha = new Date().toLocaleDateString('es-MX', { day:'2-digit', month:'long', year:'numeric' });
      let y = 56;

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(18);
      doc.text(title, margin, y, { maxWidth: width - margin * 2 });
      y += 24;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(10);
      doc.setTextColor(95, 95, 95);
      doc.text(['Broquer · Broq', periodo ? 'Periodo: ' + periodo : '', 'Generado: ' + fecha].filter(Boolean).join('  ·  '), margin, y);
      y += 28;
      doc.setDrawColor(210, 210, 210);
      doc.line(margin, y, width - margin, y);
      y += 26;
      doc.setTextColor(28, 31, 34);
      doc.setFontSize(11);

      const sections = contenido.split(/\n{2,}/).map(x => x.trim()).filter(Boolean);
      const blocks = sections.length ? sections : [contenido];
      blocks.forEach((block) => {
        const lines = doc.splitTextToSize(block.replace(/^[-•]\s*/gm, '• '), width - margin * 2);
        lines.forEach((line) => {
          if (y > height - 64) { doc.addPage(); y = 56; }
          doc.text(line, margin, y);
          y += 15;
        });
        y += 8;
      });

      const pages = doc.getNumberOfPages();
      for (let i = 1; i <= pages; i++) {
        doc.setPage(i);
        doc.setFontSize(9);
        doc.setTextColor(120, 120, 120);
        doc.text('Powered by Broquer.app', margin, height - 28);
        doc.text(String(i) + ' / ' + String(pages), width - margin, height - 28, { align: 'right' });
      }
      const blob = doc.output('blob');
      const safePeriodo = periodo ? '_' + periodo.replace(/[^a-z0-9_-]+/gi, '_') : '';
      await deliverGeneratedFile(blob, 'Reporte_Estadisticas' + safePeriodo + '.pdf', {
        type: 'application/pdf',
        title: 'Reporte de estadísticas listo',
        text: 'Reporte generado por Broquer'
      });
      bubble.innerHTML = '✓ <strong>Reporte listo.</strong> Se abrió en pantalla para compartirlo o guardarlo.';
    } catch (e) {
      bubble.textContent = 'No pude crear el reporte PDF: ' + (e.message || e);
    }
  }

  function getCurrentContext() {
    return CONTEXT_LABELS[activeKey] || 'Broquer';
  }
  window.getCurrentContext = getCurrentContext;

  /* ── Voice (mic) ──────────────────────────────────────────────── */
  let scwRec = null, scwListening = false, scwTimer = null;
  let _micGranted = localStorage.getItem('mic_granted') === '1';

  async function ensureMicPermission() {
    if (navigator.permissions) {
      try {
        const status = await navigator.permissions.query({ name: 'microphone' });
        if (status.state === 'granted') { _micGranted = true; localStorage.setItem('mic_granted','1'); return true; }
        if (status.state === 'denied')  { _micGranted = false; localStorage.removeItem('mic_granted'); return false; }
        _micGranted = false; localStorage.removeItem('mic_granted');
      } catch (e) {}
    }
    if (_micGranted) return true;
    if (!navigator.mediaDevices) return false;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach(t => t.stop());
      _micGranted = true; localStorage.setItem('mic_granted', '1'); return true;
    } catch (e) { _micGranted = false; localStorage.removeItem('mic_granted'); return false; }
  }

  function _normalizarVoz(t) {
    if (!t) return t;
    // Corregir transcripciones de voz comunes
    t = t.replace(/\bbroker\b/gi, 'Broq');
    t = t.replace(/\bbroquer\b/gi, 'Broq');
    t = t.replace(/\bshaark\b/gi, 'Broq');
    t = t.replace(/\bshark\b/gi, 'Broq');
    return t;
  }

  function _addPunctuation(t) {
    if (!t) return t;
    if (/[.?!;,]$/.test(t)) return t;
    if (/\b(qué|que|cómo|como|cuándo|cuando|dónde|donde|cuánto|cuanto|por qué|por que|quién|quien|cuál|cual)\b/i.test(t) || t.trimStart().startsWith('¿')) return t + '?';
    if (/^(dime|dinos|explica|muéstrame|genera|crea|calcula|busca|abre|cierra|descarga)/i.test(t.trimStart())) return t + '.';
    return t + '.';
  }

  function speak(text) {
    if (!('speechSynthesis' in window)) return;
    try {
      const u = new SpeechSynthesisUtterance(text.slice(0, 400));
      u.lang = 'es-MX';
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }

  /* ════════════════════════════════════════════════════════════════
     Dictado por voz — Whisper (Groq) con detección de silencio.
     Graba audio real, detecta cuándo dejas de hablar y lo transcribe
     en el backend (/transcribir). Muy superior a webkitSpeechRecognition
     en iPhone, con ruido de coche y en español mexicano.
     Si el dispositivo no soporta grabación o el backend no responde,
     cae automáticamente al reconocimiento del navegador (legacy).
     ════════════════════════════════════════════════════════════════ */
  let scwStream = null, scwRecorder = null, scwChunks = [];
  let scwAudioCtx = null, scwAnalyser = null, scwRAF = 0;
  let scwSilenceTimer = null, scwMaxTimer = null, scwSpoke = false;

  function _whisperSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
              window.MediaRecorder);
  }

  function toggleScwVoice() {
    if (scwListening) { stopScwVoice(true); return; }
    startScwVoice();
  }
  window.toggleScwVoice = toggleScwVoice;

  async function startScwVoice() {
    if (scwListening) return;
    // Sin soporte de grabación → método clásico del navegador
    if (!_whisperSupported()) { return startScwVoiceLegacy(); }

    _wakePaused = true; stopWakeWordListener();
    const ok = await ensureMicPermission();
    if (!ok) { _wakePaused = false; _resumeWake(); showShaarkToast('Sin permiso de micrófono'); return; }

    const btn = document.getElementById('bk-shk-mic');
    const inp = document.getElementById('bk-shk-input');

    try {
      scwStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
    } catch (e) {
      _wakePaused = false; _resumeWake();
      // Si falla la grabación, intentamos el método clásico
      return startScwVoiceLegacy();
    }

    // Elegir un mimeType soportado (Safari usa mp4, Chrome webm)
    let mime = '';
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    for (const c of candidates) {
      if (window.MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c)) { mime = c; break; }
    }
    try {
      scwRecorder = mime ? new MediaRecorder(scwStream, { mimeType: mime })
                         : new MediaRecorder(scwStream);
    } catch (e) {
      _cleanupScwStream(); _wakePaused = false; _resumeWake();
      return startScwVoiceLegacy();
    }

    scwChunks = [];
    scwSpoke = false;
    scwListening = true;
    btn?.classList.add('listening');
    if (inp) { inp.placeholder = 'Escuchando…'; inp.value = ''; }

    scwRecorder.ondataavailable = ev => { if (ev.data && ev.data.size > 0) scwChunks.push(ev.data); };
    scwRecorder.onstop = () => _onScwRecordingStop(mime);

    try { scwRecorder.start(); } catch (e) {
      _cleanupScwStream(); scwListening = false; btn?.classList.remove('listening');
      _wakePaused = false; _resumeWake();
      return startScwVoiceLegacy();
    }

    // Detección de silencio con AnalyserNode (auto-stop al dejar de hablar)
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      scwAudioCtx = new AC();
      const src = scwAudioCtx.createMediaStreamSource(scwStream);
      scwAnalyser = scwAudioCtx.createAnalyser();
      scwAnalyser.fftSize = 2048;
      src.connect(scwAnalyser);
      const buf = new Uint8Array(scwAnalyser.fftSize);
      const SPEAK = 0.018;   // umbral de voz (RMS)
      const SILENCE = 0.010; // umbral de silencio
      const tick = () => {
        if (!scwListening || !scwAnalyser) return;
        scwAnalyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        const rms = Math.sqrt(sum / buf.length);
        if (rms > SPEAK) {
          scwSpoke = true;
          clearTimeout(scwSilenceTimer); scwSilenceTimer = null;
        } else if (scwSpoke && rms < SILENCE && !scwSilenceTimer) {
          // Silencio sostenido tras haber hablado → cerrar a los 1.3s
          scwSilenceTimer = setTimeout(() => { if (scwListening) stopScwVoice(true); }, 1300);
        }
        scwRAF = requestAnimationFrame(tick);
      };
      scwRAF = requestAnimationFrame(tick);
    } catch (e) { /* sin auto-stop por análisis; queda el tope duro */ }

    // Si no se detecta voz en 8s, o tope duro de 15s, cerrar.
    scwMaxTimer = setTimeout(() => { if (scwListening) stopScwVoice(scwSpoke); }, 15000);
    setTimeout(() => { if (scwListening && !scwSpoke) stopScwVoice(false); }, 8000);
  }
  window.startScwVoice = startScwVoice;

  function stopScwVoice(envia) {
    if (!scwListening && !scwRecorder) {
      // Puede venir del legacy
      return stopScwVoiceLegacy();
    }
    scwListening = false;
    const btn = document.getElementById('bk-shk-mic');
    btn?.classList.remove('listening');
    clearTimeout(scwSilenceTimer); scwSilenceTimer = null;
    clearTimeout(scwMaxTimer); scwMaxTimer = null;
    cancelAnimationFrame(scwRAF); scwRAF = 0;
    window._scwShouldSend = !!envia;
    try {
      if (scwRecorder && scwRecorder.state !== 'inactive') scwRecorder.stop();
      else _onScwRecordingStop('');
    } catch (e) { _onScwRecordingStop(''); }
  }
  window.stopScwVoice = stopScwVoice;

  function _cleanupScwStream() {
    try { if (scwStream) scwStream.getTracks().forEach(t => t.stop()); } catch (_) {}
    scwStream = null;
    try { if (scwAudioCtx) scwAudioCtx.close(); } catch (_) {}
    scwAudioCtx = null; scwAnalyser = null;
  }

  async function _onScwRecordingStop(mime) {
    const inp = document.getElementById('bk-shk-input');
    const chunks = scwChunks.slice();
    scwChunks = [];
    const shouldSend = window._scwShouldSend;
    window._scwShouldSend = false;
    _cleanupScwStream();
    scwRecorder = null;
    if (inp && inp.placeholder === 'Escuchando…') inp.placeholder = 'Pregunta lo que necesites…';
    _wakePaused = false; _resumeWake();

    if (!shouldSend || chunks.length === 0) { return; }

    const type = (mime && mime.split(';')[0]) || (chunks[0] && chunks[0].type) || 'audio/webm';
    const blob = new Blob(chunks, { type });
    if (blob.size < 1200) { return; } // demasiado corto: probablemente silencio

    if (inp) inp.placeholder = 'Entendiendo…';
    try {
      const ext = type.includes('mp4') ? 'mp4' : (type.includes('ogg') ? 'ogg' : 'webm');
      const fd = new FormData();
      fd.append('audio', blob, 'voz.' + ext);
      fd.append('idioma', 'es');
      const _tokVoz = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || '';
      const r = await fetch(API_BASE + '/transcribir', {
        method: 'POST',
        headers: _tokVoz ? { Authorization: 'Bearer ' + _tokVoz } : {},
        body: fd,
      });
      if (!r.ok) throw new Error('status ' + r.status);
      const data = await r.json();
      const texto = (data.texto || '').trim();
      if (inp) inp.placeholder = 'Pregunta lo que necesites…';
      if (texto) {
        if (inp) inp.value = texto;
        window._scwLastWasVoice = true;
        setTimeout(() => shaarkFabSend(), 80);
      } else {
        showShaarkToast('No te escuché bien. Intenta de nuevo.');
      }
    } catch (e) {
      if (inp) inp.placeholder = 'Pregunta lo que necesites…';
      // Si la transcripción falla, ofrecemos el método clásico
      showShaarkToast('No pude transcribir. Probando el micrófono del navegador…');
      setTimeout(() => startScwVoiceLegacy(), 300);
    }
  }

  /* ── Método clásico (fallback): reconocimiento del navegador ── */
  function startScwVoiceLegacy() {
    if (scwListening) return;
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      showShaarkToast('Tu navegador no soporta voz. Usa Chrome o Safari.'); return;
    }
    _wakePaused = true; stopWakeWordListener();
    ensureMicPermission().then(ok => {
      if (!ok) { _wakePaused = false; _resumeWake(); showShaarkToast('Sin permiso de micrófono'); return; }
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      try { scwRec = new SR(); } catch (e) { _wakePaused = false; _resumeWake(); return; }
      scwRec.lang = 'es-MX'; scwRec.continuous = false; scwRec.interimResults = true;
      const btn = document.getElementById('bk-shk-mic');
      const inp = document.getElementById('bk-shk-input');
      scwListening = true;
      btn?.classList.add('listening');
      if (inp) { inp.placeholder = 'Escuchando…'; inp.value = ''; }
      scwTimer = setTimeout(() => stopScwVoiceLegacy(), 12000);
      scwRec.onresult = e => {
        clearTimeout(scwTimer);
        let f = '', i = '';
        for (let k = 0; k < e.results.length; k++) {
          if (e.results[k].isFinal) f += e.results[k][0].transcript;
          else i += e.results[k][0].transcript;
        }
        const raw = _normalizarVoz((f || i).trim());
        if (inp) inp.value = f ? _addPunctuation(raw) : raw;
      };
      scwRec.onerror = ev => {
        clearTimeout(scwTimer);
        if (ev.error === 'not-allowed') {
          _micGranted = false; localStorage.removeItem('mic_granted');
          showShaarkToast('Sin permiso de micrófono. Actívalo en la configuración del navegador.');
        }
        stopScwVoiceLegacy(); _wakePaused = false; _resumeWake();
      };
      scwRec.onend = () => {
        clearTimeout(scwTimer);
        const txt = inp ? inp.value.trim() : '';
        const wasListening = scwListening;
        stopScwVoiceLegacy();
        if (wasListening && txt) {
          window._scwLastWasVoice = true;
          setTimeout(() => shaarkFabSend(), 100);
        }
        _wakePaused = false; _resumeWake();
      };
      try { scwRec.start(); } catch (e) { stopScwVoiceLegacy(); _wakePaused = false; _resumeWake(); }
    });
  }

  function stopScwVoiceLegacy() {
    clearTimeout(scwTimer);
    scwListening = false;
    const btn = document.getElementById('bk-shk-mic');
    btn?.classList.remove('listening');
    if (scwRec) { try { scwRec.abort(); } catch (e) {} scwRec = null; }
    const inp = document.getElementById('bk-shk-input');
    if (inp && inp.placeholder === 'Escuchando…') inp.placeholder = 'Pregunta lo que necesites…';
  }

  /* ── Wake word ─────────────────────────────────────────────── */
  let _wakeRec = null, _wakeActive = false, _wakePaused = false, _wakeRestartT = null;
  let _wakeEnabled = localStorage.getItem('shaark_wake') === '1';
  let _wakeSuppressUntil = 0;
  const WAKE = ['oye broq','broq','oye broquer','oye broker','broquer','broker','oye shaark','oye shark','shaark','oie shaark','hey shaark','hey shark'];

  function toggleWakeWord() {
    if (_wakeEnabled) {
      _wakeEnabled = false; localStorage.setItem('shaark_wake', '0'); stopWakeWordListener();
    } else {
      _wakeEnabled = true; localStorage.setItem('shaark_wake', '1');
      ensureMicPermission().then(ok => {
        if (ok) startWakeWordListener();
        else { _wakeEnabled = false; localStorage.setItem('shaark_wake', '0'); showShaarkToast('Sin permiso de micrófono'); _updateWakeUI(); }
      });
    }
    _updateWakeUI();
  }
  window.toggleWakeWord = toggleWakeWord;

  function startWakeWordListener() {
    if (!_wakeEnabled || _wakeActive || _wakePaused || scwListening) return;
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) return;
    clearTimeout(_wakeRestartT);
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    try { _wakeRec = new SR(); } catch (e) { return; }
    _wakeRec.lang = 'es-MX'; _wakeRec.continuous = true; _wakeRec.interimResults = true; _wakeRec.maxAlternatives = 3;
    _wakeActive = true;
    _wakeRec.onresult = e => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        for (let a = 0; a < e.results[i].length; a++) {
          const t = e.results[i][a].transcript.toLowerCase();
          if (WAKE.some(w => t.includes(w))) {
            try { _wakeRec.stop(); } catch (_) {}
            _wakeActive = false;
            _onWakeWordDetected();
            return;
          }
        }
      }
    };
    _wakeRec.onerror = ev => {
      _wakeActive = false;
      if (ev.error === 'not-allowed') {
        _wakeEnabled = false; localStorage.setItem('shaark_wake', '0');
        _micGranted = false; localStorage.removeItem('mic_granted');
        _updateWakeUI(); return;
      }
      if (ev.error !== 'aborted' && _wakeEnabled && !_wakePaused) {
        _wakeRestartT = setTimeout(startWakeWordListener, 3000);
      }
    };
    _wakeRec.onend = () => {
      _wakeActive = false;
      if (_wakeEnabled && !_wakePaused && !scwListening) {
        _wakeRestartT = setTimeout(startWakeWordListener, 800);
      }
    };
    try { _wakeRec.start(); } catch (e) { _wakeActive = false; _wakeRestartT = setTimeout(startWakeWordListener, 3000); }
  }

  function stopWakeWordListener() {
    clearTimeout(_wakeRestartT);
    _wakeActive = false;
    if (_wakeRec) { try { _wakeRec.abort(); } catch (e) {} _wakeRec = null; }
  }
  function _resumeWake() {
    if (_wakeEnabled && !_wakePaused) _wakeRestartT = setTimeout(startWakeWordListener, 1200);
  }
  function _onWakeWordDetected() {
    if (Date.now() < _wakeSuppressUntil) { _resumeWake(); return; }
    if (navigator.vibrate) navigator.vibrate(60);
    if (!shaarkOpen) toggleShaarkPopup(true);
    setTimeout(() => startScwVoice(), 350);
  }
  function _updateWakeUI() {
    const btn = document.getElementById('bk-shk-wake');
    const fab = document.getElementById('bk-shaark-fab');
    if (btn) {
      btn.classList.toggle('is-on', _wakeEnabled);
      btn.title = _wakeEnabled ? 'Siempre escuchando: ON — toca para desactivar' : 'Activar "Oye Broq"';
    }
    if (fab) fab.classList.toggle('wake-on', _wakeEnabled);
  }

  function showShaarkToast(msg) {
    const wrap = document.getElementById('bk-shk-msgs'); if (!wrap) return;
    const el = document.createElement('div');
    el.className = 'bk-shk-bubble toast';
    el.textContent = msg;
    wrap.appendChild(el); wrap.scrollTop = wrap.scrollHeight;
  }
  window.showShaarkToast = showShaarkToast;

  /* ── Suppress wake during downloads ── */
  window.addEventListener('message', e => {
    if (!e.data || e.data.type !== 'brokr-suppress-wake') return;
    _wakeSuppressUntil = Date.now() + (e.data.duration || 4000);
  });

  /* ── Native bridge (for Capacitor / Cordova app shell) ── */
  window.ShaarkNativeBridge = {
    onWakeWord() { _onWakeWordDetected(); },
    submitText(text) {
      if (!shaarkOpen) toggleShaarkPopup(true);
      setTimeout(() => {
        const inp = document.getElementById('bk-shk-input');
        if (inp) inp.value = text;
        setTimeout(shaarkFabSend, 100);
      }, 300);
    },
    isWakeEnabled() { return _wakeEnabled; },
    nativeWakeActivate() { _onWakeWordDetected(); },
  };

  /* ════════════════════════════════════════════════════════════════
     Panel de Notificaciones
     ════════════════════════════════════════════════════════════════ */
  let _notifOpen = false;

  function toggleNotifPanel(force) {
    _notifOpen = (typeof force === 'boolean') ? force : !_notifOpen;
    let panel = document.getElementById('bk-notif-panel');
    let overlay = document.getElementById('bk-notif-overlay');

    if (_notifOpen) {
      if (!panel) {
        overlay = document.createElement('div');
        overlay.id = 'bk-notif-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:299;background:transparent;';
        overlay.addEventListener('click', () => toggleNotifPanel(false));
        document.body.appendChild(overlay);

        panel = document.createElement('div');
        panel.id = 'bk-notif-panel';
        panel.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 18px 12px;border-bottom:1px solid var(--line-2);">
            <div style="display:flex;align-items:center;gap:8px;">
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></svg>
              <span style="font-size:14px;font-weight:600;color:var(--ink);">Notificaciones</span>
            </div>
            <button onclick="toggleNotifPanel(false)" style="background:none;border:none;cursor:pointer;color:var(--ink-3);font-size:18px;line-height:1;padding:2px 6px;">\u2715</button>
          </div>
          <div style="padding:32px 18px;text-align:center;">
            <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.25;margin:0 auto 12px;display:block;"><path d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></svg>
            <p style="font-size:13px;color:var(--ink-3);margin:0;">Sin notificaciones por ahora</p>
          </div>
        `;
        panel.style.cssText = "position:fixed;top:64px;right:16px;z-index:300;width:min(340px, calc(100vw - 32px));background:var(--paper);border:1px solid var(--line-2);border-radius:16px;box-shadow:0 12px 40px rgba(22,22,22,.14),0 3px 8px rgba(22,22,22,.08);animation:bkNotifIn .18s var(--ease) both;";
        document.body.appendChild(panel);

        if (!document.getElementById('bk-notif-style')) {
          const st = document.createElement('style');
          st.id = 'bk-notif-style';
          st.textContent = '@keyframes bkNotifIn{from{opacity:0;transform:translateY(-8px) scale(.97)}to{opacity:1;transform:none}}';
          document.head.appendChild(st);
        }
      } else {
        panel.style.display = '';
        if (overlay) overlay.style.display = '';
      }
    } else {
      if (panel) panel.style.display = 'none';
      if (overlay) overlay.style.display = 'none';
    }
  }
  window.toggleNotifPanel = toggleNotifPanel;

  /* ════════════════════════════════════════════════════════════════
     Boot
     ════════════════════════════════════════════════════════════════ */

  /* ════════════════════════════════════════════════════════════════
     DRAWER DE PERFIL
     ════════════════════════════════════════════════════════════════ */
  let _pdProfile = null; // datos del usuario cargados

  function openProfileDrawer() {
    let overlay = document.getElementById('bk-profile-overlay');
    if (!overlay) buildProfileDrawer();
    overlay = document.getElementById('bk-profile-overlay');
    overlay.classList.add('is-open');
    document.getElementById('bk-profile-drawer').classList.add('is-open');
    // Diferir las peticiones de red para que la animación de apertura no se trabe
    requestAnimationFrame(() => requestAnimationFrame(() => loadProfileData()));
  }
  window.openProfileDrawer = openProfileDrawer;

  function closeProfileDrawer() {
    document.getElementById('bk-profile-overlay')?.classList.remove('is-open');
    document.getElementById('bk-profile-drawer')?.classList.remove('is-open');
  }
  window.closeProfileDrawer = closeProfileDrawer;

  function buildProfileDrawer() {
    // Overlay
    const overlay = document.createElement('div');
    overlay.id = 'bk-profile-overlay';
    overlay.className = 'bk-profile-overlay';
    overlay.addEventListener('click', closeProfileDrawer);
    document.body.appendChild(overlay);

    // Drawer
    const drawer = document.createElement('div');
    drawer.id = 'bk-profile-drawer';
    drawer.className = 'bk-profile-drawer';
    drawer.innerHTML = `
      <div class="bk-pd-head">
        <div class="bk-pd-avatar-row">
          <div class="bk-pd-avatar" id="pd-avatar">—</div>
          <div class="bk-pd-avatar-info">
            <div class="bk-pd-name" id="pd-name">Cargando…</div>
            <div class="bk-pd-email" id="pd-email"></div>
            <div class="bk-pd-role-badge" id="pd-role-badge">Agente</div>
          </div>
        </div>
        <button class="bk-pd-close" onclick="closeProfileDrawer()" aria-label="Cerrar">
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M6 6l12 12M6 18L18 6"/></svg>
        </button>
      </div>

      <div class="bk-pd-body">
        <div class="bk-pd-menu">

          <!-- Datos personales -->
          <div class="bk-pd-menu-item" id="pdsec-datos">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('datos')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">
                  ${svg('user', 16)}
                  <span class="bk-pd-menu-trigger-dot" id="pdot-datos"></span>
                </span>
                Datos personales
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <div class="bk-pd-field">
                    <label>Nombre completo</label>
                    <input type="text" id="pd-input-nombre" placeholder="Tu nombre"/>
                  </div>
                  <div class="bk-pd-field">
                    <label>Teléfono</label>
                    <input type="tel" id="pd-input-tel" placeholder="Tu teléfono"/>
                  </div>
                  <div class="bk-pd-field">
                    <label>Correo</label>
                    <input type="email" id="pd-input-email" readonly/>
                  </div>
                  <button class="bk-pd-btn bk-pd-btn-primary" onclick="saveProfileData()">Guardar cambios</button>
                  <div class="bk-pd-toast" id="pd-toast-personal"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Contraseña -->
          <div class="bk-pd-menu-item" id="pdsec-pass">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('pass')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">${svg('lock', 16)}</span>
                Contraseña
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <div class="bk-pd-field">
                    <label>Contraseña actual</label>
                    <input type="password" id="pd-pass-current" placeholder="Tu contraseña actual" autocomplete="current-password"/>
                  </div>
                  <div class="bk-pd-field">
                    <label>Nueva contraseña</label>
                    <input type="password" id="pd-pass-new" placeholder="Mínimo 8 caracteres" autocomplete="new-password"/>
                  </div>
                  <div class="bk-pd-field">
                    <label>Confirmar nueva contraseña</label>
                    <input type="password" id="pd-pass-new2" placeholder="Repite la nueva contraseña" autocomplete="new-password"/>
                  </div>
                  <button class="bk-pd-btn bk-pd-btn-primary" id="pd-pass-btn" onclick="changePasswordFromProfile()">Actualizar contraseña</button>
                  <div style="font-size:11px;color:var(--mute);margin-top:8px;line-height:1.4">Al actualizarla, cerraremos tu sesión en todos los demás dispositivos por seguridad. Esta sesión seguirá activa.</div>
                  <div class="bk-pd-toast" id="pd-toast-pass"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- EasyBroker -->
          <div class="bk-pd-menu-item" id="pdsec-eb">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('eb')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">
                  ${svg('building', 16)}
                  <span class="bk-pd-menu-trigger-dot" id="pdot-eb"></span>
                </span>
                EasyBroker
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <div class="bk-pd-status">
                    <span class="dot" id="pd-eb-dot"></span>
                    <span id="pd-eb-status-text">Verificando…</span>
                  </div>
                  <div class="bk-pd-field" style="margin-top:12px">
                    <label>API Key de EasyBroker</label>
                    <input type="text" id="pd-input-ebkey" placeholder="Pega tu API key aquí" autocomplete="off" autocorrect="off" spellcheck="false"/>
                    <div style="font-size:11px;color:var(--mute);margin-top:5px;line-height:1.4">Encuéntrala en EasyBroker → Configuración → API.</div>
                  </div>
                  <button class="bk-pd-btn bk-pd-btn-primary" onclick="saveEbKey()">Conectar EasyBroker</button>
                  <button class="bk-pd-btn bk-pd-btn-outline" id="pd-eb-disconnect-btn" onclick="disconnectEbKey()" style="margin-top:8px;display:none">Desconectar EasyBroker</button>
                  <div class="bk-pd-toast" id="pd-toast-eb"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Facebook -->
          <div class="bk-pd-menu-item" id="pdsec-fb">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('fb')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">
                  ${svg('facebook', 15)}
                  <span class="bk-pd-menu-trigger-dot" id="pdot-fb"></span>
                </span>
                Facebook
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <div class="bk-pd-status">
                    <span class="dot" id="pd-fb-dot"></span>
                    <span id="pd-fb-status-text">Verificando…</span>
                  </div>
                  <button class="bk-pd-btn bk-pd-btn-primary" id="pd-fb-btn" onclick="connectFacebook()" style="margin-top:12px">
                    <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
                    Conectar página de Facebook
                  </button>
                  <button class="bk-pd-btn bk-pd-btn-outline" id="pd-fb-disconnect-btn" onclick="disconnectFacebook()" style="margin-top:8px;display:none">Desconectar Facebook</button>
                  <div class="bk-pd-toast" id="pd-toast-fb"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Suscripcion (solo web; dentro de la app de iOS no se muestra gestión ni cobro de suscripción) -->
          ${IS_IOS_NATIVE ? '' : `
          <div class="bk-pd-menu-item" id="pdsec-sub">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('sub')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">
                  ${svg('peso', 16)}
                  <span class="bk-pd-menu-trigger-dot" id="pdot-sub"></span>
                </span>
                Suscripción
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <div id="pd-sub-badge-wrap"><span class="bk-pd-sub-badge inactive" id="pd-sub-badge">Sin plan activo</span></div>
                  <div class="bk-pd-sub-info" id="pd-sub-info">Activa tu suscripción para acceder a todas las funciones de Broquer.</div>
                  <button class="bk-pd-btn bk-pd-btn-primary" id="pd-sub-btn" onclick="startCheckout()">Activar Broquer Max</button>
                  <button class="bk-pd-btn bk-pd-btn-outline" id="pd-sub-cancel-btn" onclick="cancelSubscription()" style="display:none">Cancelar suscripción</button>
                  <a href="empresas.html" style="display:block;margin-top:12px;font-size:var(--fs-label-3);color:var(--mute);text-decoration:underline;line-height:1.5">¿Tienes equipo? Conoce Broquer para Empresas</a>
                  <div class="bk-pd-toast" id="pd-toast-sub"></div>
                </div>
              </div>
            </div>
          </div>`}

          <!-- Legal -->
          <div class="bk-pd-menu-item" id="pdsec-legal">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('legal')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">${svg('gavel', 16)}</span>
                Documentos legales
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card" style="display:flex;flex-direction:column;gap:8px">
                  <a href="legal.html#tyc" target="_blank" style="text-decoration:none">
                    <button class="bk-pd-btn bk-pd-btn-outline" style="margin:0">Términos y condiciones</button>
                  </a>
                  <a href="legal.html#contrato" target="_blank" style="text-decoration:none">
                    <button class="bk-pd-btn bk-pd-btn-outline" style="margin:0">Contrato de suscripción</button>
                  </a>
                  <a href="legal.html#privacidad" target="_blank" style="text-decoration:none">
                    <button class="bk-pd-btn bk-pd-btn-outline" style="margin:0">Aviso de privacidad</button>
                  </a>
                </div>
              </div>
            </div>
          </div>

          <!-- Eliminar cuenta (requerido por App Store; visible también en iOS) -->
          <div class="bk-pd-menu-item" id="pdsec-del">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('del')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon bk-pd-menu-icon--danger">${svg('trash', 16)}</span>
                Eliminar mi cuenta
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <p style="font-size:13px;color:var(--mute);line-height:1.5;margin-bottom:12px">Esta acción elimina de forma permanente tu cuenta y todos tus datos (propiedades, contactos, contratos e integraciones). No se puede deshacer.</p>
                  <div class="bk-pd-field">
                    <label>Para confirmar, escribe tu correo</label>
                    <input type="email" id="pd-del-input" placeholder="tu@correo.com" autocomplete="off" autocorrect="off" spellcheck="false" oninput="checkDeleteMatch()"/>
                  </div>
                  <button class="bk-pd-btn bk-pd-btn-danger" id="pd-del-confirm-btn" onclick="ejecutarEliminarCuenta()" style="opacity:.4;pointer-events:none">Eliminar mi cuenta permanentemente</button>
                  <div class="bk-pd-toast" id="pd-toast-del"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Equipo (solo cuentas empresariales) -->
          <!-- Vivía en el menú lateral, dentro de CRM. No es una herramienta de
               trabajo diario: es configuración de la cuenta — quién entra, qué
               ve, qué puede tocar — y se consulta dos veces al mes. Su lugar es
               aquí, junto a suscripción y datos fiscales. -->
          <div class="bk-pd-menu-item" id="pdsec-equipo" style="display:none">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('equipo')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">${svg('users', 16)}</span>
                Equipo
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <p style="font-size:13px;color:var(--mute);line-height:1.5;margin-bottom:12px">Quién trabaja en tu cuenta, qué puede ver cada quien e invitaciones pendientes.</p>
                  <a href="equipo.html" style="text-decoration:none">
                    <button class="bk-pd-btn bk-pd-btn-outline" style="width:100%">Administrar equipo</button>
                  </a>
                </div>
              </div>
            </div>
          </div>

          <!-- Admin (solo admin) -->
          <div class="bk-pd-menu-item" id="pdsec-admin" style="display:none">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('admin')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-icon">${svg('shield', 16)}</span>
                Administración
              </span>
              <svg class="bk-pd-menu-chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
            <div class="bk-pd-menu-panel">
              <div class="bk-pd-menu-panel-inner">
                <div class="bk-pd-card">
                  <p style="font-size:13px;color:var(--mute);margin-bottom:12px">Tienes acceso al panel de administrador.</p>
                  <a href="admin.html" style="text-decoration:none">
                    <button class="bk-pd-btn bk-pd-btn-outline" style="width:100%">Ir al panel admin</button>
                  </a>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- Foot: cerrar sesión -->
      <div class="bk-pd-foot">
        <button class="bk-pd-btn bk-pd-btn-danger" onclick="doLogout()">
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75"/></svg>
          Cerrar sesión
        </button>
      </div>
    `;
    document.body.appendChild(drawer);
  }


  // Caché de datos del perfil — evita pegar a 3 endpoints cada vez que el
  // usuario abre el drawer. Se invalida al guardar perfil o al cambiar
  // conexión EB/Facebook. TTL: 60 segundos.
  let _pdCache = null;
  let _pdCacheAt = 0;
  const PD_CACHE_TTL = 60000;

  function invalidateProfileCache() {
    _pdCache = null;
    _pdCacheAt = 0;
  }
  window.invalidateProfileCache = invalidateProfileCache;

  // Accordion toggle
  function togglePdSection(key) {
    const item = document.getElementById('pdsec-' + key);
    if (!item) return;
    const isOpen = item.classList.contains('is-open');
    // Cerrar todos
    document.querySelectorAll('.bk-pd-menu-item.is-open').forEach(el => el.classList.remove('is-open'));
    // Abrir el seleccionado si estaba cerrado
    if (!isOpen) item.classList.add('is-open');
  }
  window.togglePdSection = togglePdSection;

  // Checkout Stripe
  async function startCheckout() {
    // En la app nativa de iOS jamás se inicia un cobro dentro de la app (política de Apple).
    if (IS_IOS_NATIVE) return;
    const tok = getToken();
    if (!tok) return;
    const btn = document.getElementById('pd-sub-btn');
    const toast = document.getElementById('pd-toast-sub');
    if (btn) { btn.disabled = true; btn.textContent = 'Redirigiendo…'; }
    try {
      const r = await fetch(API_BASE + '/subscription/checkout', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_id: 'max',
          success_url: window.location.origin + '/index.html?sub=ok',
          cancel_url: window.location.href
        })
      });
      const d = await r.json();
      if (d.checkout_url) {
        window.location.href = d.checkout_url;
      } else {
        throw new Error(d.detail || 'Error al iniciar pago');
      }
    } catch(e) {
      if (toast) { toast.textContent = e.message || 'No pude conectar con el servidor de pagos. Revisa api.broquer.app, SSL y CORS.'; toast.className = 'bk-pd-toast err'; }
      if (btn) { btn.disabled = false; btn.textContent = 'Activar Broquer Max'; }
    }
  }
  window.startCheckout = startCheckout;

  // Cancelar suscripcion
  async function cancelSubscription() {
    const tok = getToken();
    if (!tok) return;
    if (!confirm('¿Confirmas que deseas cancelar tu suscripción? Seguirás teniendo acceso hasta el fin del período pagado.')) return;
    const toast = document.getElementById('pd-toast-sub');
    try {
      const r = await fetch(API_BASE + '/subscription/cancel', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + tok }
      });
      const d = await r.json();
      if (r.ok) {
        if (toast) { toast.textContent = 'Suscripción cancelada. Tu acceso continúa hasta el fin del período actual.'; toast.className = 'bk-pd-toast ok'; }
        invalidateProfileCache();
      } else {
        throw new Error(d.detail || 'Error al cancelar');
      }
    } catch(e) {
      if (toast) { toast.textContent = e.message || 'Error al cancelar.'; toast.className = 'bk-pd-toast err'; }
    }
  }
  window.cancelSubscription = cancelSubscription;

  async function loadProfileData() {
    const tok = getToken();
    if (!tok) return;
    let user = {};
    try { user = JSON.parse(localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || '{}'); } catch(e) {}

    // Rellenar email de inmediato (lo tenemos en memoria, no necesita red)
    if (user.email) {
      const emEl = document.getElementById('pd-input-email');
      if (emEl) emEl.value = user.email;
    }

    // Si tenemos caché fresco, repintar inmediatamente sin pegar a la red
    if (_pdCache && (Date.now() - _pdCacheAt) < PD_CACHE_TTL) {
      renderProfileData(_pdCache, user);
      return;
    }

    // 2 peticiones EN PARALELO con Promise.allSettled (antes eran 3).
    // /profile/status devuelve EB + FB en una sola llamada al backend.
    // (allSettled = si una falla, las demás siguen — el drawer no se queda en blanco)
    const [usuarioRes, statusRes] = await Promise.allSettled([
      fetch(SB_URL + '/rest/v1/usuarios?id=eq.' + user.id + '&select=nombre,telefono,rol', {
        headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok }
      }).then(r => r.ok ? r.json() : []),
      fetch(API_BASE + '/profile/status', {
        headers: { Authorization: 'Bearer ' + tok }
      }).then(r => r.ok ? r.json() : { eb: { configured: false }, fb: { connected: false } })
    ]);

    const profileStatus = statusRes.status === 'fulfilled' ? statusRes.value : { eb: {}, fb: {} };
    const data = {
      usuario: usuarioRes.status === 'fulfilled' ? (usuarioRes.value[0] || {}) : {},
      eb:      profileStatus.eb || { configured: false },
      fb:      profileStatus.fb || { connected: false },
      sub:     profileStatus.sub || { active: false }
    };

    _pdCache = data;
    _pdCacheAt = Date.now();
    renderProfileData(data, user);
  }

  // Renderiza el drawer con los datos (sin tocar la red). Idempotente.
  function renderProfileData(data, user) {
    const p = data.usuario || {};
    _pdProfile = { ...p, email: user.email, id: user.id };

    const nombre = p.nombre || '';
    const ini2 = initials(nombre);

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const setDot = (id, cls) => { const el = document.getElementById(id); if (el) el.className = 'bk-pd-menu-trigger-dot ' + cls; };

    set('pd-avatar', ini2 || '?');
    set('pd-name', nombre || user.email || '—');
    set('pd-email', user.email || '');
    setVal('pd-input-nombre', nombre);
    setVal('pd-input-tel', p.telefono || '');
    setVal('pd-input-email', user.email || '');

    // Datos dot — siempre ok si hay nombre
    setDot('pdot-datos', nombre ? 'ok' : 'warn');

    const badge = document.getElementById('pd-role-badge');
    const adminSec = document.getElementById('pdsec-admin');

    // Equipo: mismo criterio fail-closed que tenía en el sidebar. Si no se
    // pudo confirmar que la cuenta es empresarial, no se muestra.
    const equipoSec = document.getElementById('pdsec-equipo');
    if (equipoSec) {
      const esEmp = !!(window.__BK_PROFILE?.esEmpresa || p.rol === 'admin');
      equipoSec.style.display = esEmp ? 'block' : 'none';
    }
    if (badge) {
      if (p.rol === 'admin') {
        badge.textContent = 'Admin';
        badge.classList.add('admin');
        if (adminSec) adminSec.style.display = 'block';
      } else {
        badge.textContent = 'Agente';
        badge.classList.remove('admin');
        if (adminSec) adminSec.style.display = 'none';
      }
    }

    // EasyBroker
    const dot = document.getElementById('pd-eb-dot');
    const txt = document.getElementById('pd-eb-status-text');
    const discBtn = document.getElementById('pd-eb-disconnect-btn');
    if (dot && txt) {
      if (data.eb && data.eb.configured) {
        dot.className = 'dot ok';
        txt.textContent = 'Conectado — key: ' + data.eb.masked;
        setDot('pdot-eb', 'ok');
        if (discBtn) discBtn.style.display = 'block';
      } else {
        dot.className = 'dot warn';
        txt.textContent = 'Sin conectar';
        setDot('pdot-eb', 'warn');
        if (discBtn) discBtn.style.display = 'none';
      }
    }

    // Facebook
    const fdot = document.getElementById('pd-fb-dot');
    const ftxt = document.getElementById('pd-fb-status-text');
    const fbtn = document.getElementById('pd-fb-btn');
    const fdisBtn = document.getElementById('pd-fb-disconnect-btn');
    if (fdot && ftxt) {
      if (data.fb && data.fb.connected) {
        fdot.className = 'dot ok';
        ftxt.textContent = 'Conectado — ' + (data.fb.page_name || 'página vinculada');
        setDot('pdot-fb', 'ok');
        if (fbtn) fbtn.textContent = 'Cambiar página de Facebook';
        if (fdisBtn) fdisBtn.style.display = 'block';
      } else {
        fdot.className = 'dot warn';
        ftxt.textContent = 'Sin conectar';
        setDot('pdot-fb', 'warn');
        if (fbtn) fbtn.textContent = 'Conectar página de Facebook';
        if (fdisBtn) fdisBtn.style.display = 'none';
      }
    }

    // Suscripcion
    if (data.sub) {
      const active = data.sub.active;
      const badge2 = document.getElementById('pd-sub-badge');
      const info = document.getElementById('pd-sub-info');
      const btn = document.getElementById('pd-sub-btn');
      const cancelBtn = document.getElementById('pd-sub-cancel-btn');
      setDot('pdot-sub', active ? 'ok' : 'warn');
      if (badge2) {
        badge2.textContent = active ? (data.sub.plan || 'Broquer Max') : 'Sin plan activo';
        badge2.className = 'bk-pd-sub-badge' + (active ? '' : ' inactive');
      }
      if (info) info.textContent = active ? 'Tu suscripción está activa.' : 'Activa tu suscripción para acceder a todas las funciones.';
      if (btn) btn.style.display = active ? 'none' : 'flex';
      if (cancelBtn) cancelBtn.style.display = active ? 'flex' : 'none';
    }
  }

  async function saveProfileData() {
    const tok = getToken();
    if (!tok || !_pdProfile?.id) return;
    const nombre = document.getElementById('pd-input-nombre').value.trim();
    const telefono = document.getElementById('pd-input-tel').value.trim();
    const toast = document.getElementById('pd-toast-personal');
    toast.className = 'bk-pd-toast';
    try {
      const r = await fetch(SB_URL + '/rest/v1/usuarios?id=eq.' + _pdProfile.id, {
        method: 'PATCH',
        headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok,
                   'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify({ nombre, telefono })
      });
      if (!r.ok) throw new Error('Error');
      toast.textContent = 'Guardado correctamente.';
      toast.className = 'bk-pd-toast ok';
      invalidateProfileCache();
      // Actualizar nombre/avatar en el propio drawer y en el header móvil
      document.getElementById('pd-name').textContent = nombre;
      const ini2 = initials(nombre);
      { const _ma = document.getElementById('bk-mob-avatar'); if (_ma) _ma.textContent = ini2; }
      document.getElementById('pd-avatar').textContent = ini2;
    } catch(e) {
      toast.textContent = 'Error al guardar. Intenta de nuevo.';
      toast.className = 'bk-pd-toast err';
    }
    setTimeout(() => { toast.className = 'bk-pd-toast'; }, 3500);
  }
  window.saveProfileData = saveProfileData;

  // ── Cambiar contraseña desde el perfil (usuario ya logueado) ──────────
  // Flujo: 1) reautenticar con la contraseña actual (grant_type=password)
  // para confirmar identidad antes de tocar la contraseña; 2) con el token
  // fresco de esa reautenticación, hacer PUT /auth/v1/user con la nueva
  // contraseña; 3) cerrar TODAS las demás sesiones (scope=others) dejando
  // viva únicamente la sesión actual, para que un dispositivo robado/perdido
  // quede fuera en el momento en que el dueño cambia su contraseña.
  async function changePasswordFromProfile() {
    const toast = document.getElementById('pd-toast-pass');
    const btn = document.getElementById('pd-pass-btn');
    const setToast = (text, kind) => { if (toast) { toast.textContent = text; toast.className = 'bk-pd-toast ' + (kind || ''); } };

    const current = document.getElementById('pd-pass-current').value;
    const p1 = document.getElementById('pd-pass-new').value;
    const p2 = document.getElementById('pd-pass-new2').value;
    const email = _pdProfile?.email || '';

    if (!current) { setToast('Ingresa tu contraseña actual.', 'err'); return; }
    if (!p1 || !p2) { setToast('Ingresa la nueva contraseña dos veces.', 'err'); return; }
    if (p1 !== p2) { setToast('Las contraseñas nuevas no coinciden.', 'err'); return; }
    if (p1.length < 8) { setToast('La nueva contraseña debe tener al menos 8 caracteres.', 'err'); return; }
    if (p1 === current) { setToast('La nueva contraseña debe ser distinta a la actual.', 'err'); return; }
    if (!email) { setToast('No se pudo identificar tu correo. Recarga la página e intenta de nuevo.', 'err'); return; }

    if (btn) { btn.disabled = true; btn.textContent = 'Actualizando…'; }
    setToast('', '');

    try {
      // 1) Confirmar identidad con la contraseña actual.
      const authR = await fetch(SB_URL + '/auth/v1/token?grant_type=password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', apikey: SB_KEY },
        body: JSON.stringify({ email, password: current })
      });
      const authD = await authR.json().catch(() => ({}));
      if (!authR.ok || !authD.access_token) {
        setToast('Tu contraseña actual es incorrecta.', 'err');
        if (btn) { btn.disabled = false; btn.textContent = 'Actualizar contraseña'; }
        return;
      }
      const freshToken = authD.access_token;

      // 2) Actualizar la contraseña con el token recién validado.
      const updR = await fetch(SB_URL + '/auth/v1/user', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', apikey: SB_KEY, Authorization: 'Bearer ' + freshToken },
        body: JSON.stringify({ password: p1 })
      });
      const updD = await updR.json().catch(() => ({}));
      if (!updR.ok) {
        const raw = (updD.msg || updD.error_description || updD.error || '').toString().toLowerCase();
        if (raw.includes('weak') || raw.includes('password should'))
          setToast('La contraseña es demasiado débil. Usa al menos 8 caracteres con letras y números.', 'err');
        else if (raw.includes('same') || raw.includes('different from the old'))
          setToast('La nueva contraseña debe ser distinta a la anterior.', 'err');
        else
          setToast('No se pudo actualizar la contraseña. Intenta de nuevo.', 'err');
        if (btn) { btn.disabled = false; btn.textContent = 'Actualizar contraseña'; }
        return;
      }

      // 3) Cerrar todas las demás sesiones — esta se queda activa.
      try {
        await fetch(SB_URL + '/auth/v1/logout?scope=others', {
          method: 'POST',
          headers: { apikey: SB_KEY, Authorization: 'Bearer ' + freshToken }
        });
      } catch(_){}

      // Sincronizar el token/refresh de esta sesión con los nuevos que
      // emitió Supabase al reautenticar, para no dejarla en un estado raro.
      try {
        localStorage.setItem('sb_token', freshToken);
        sessionStorage.setItem('sb_token', freshToken);
        if (authD.refresh_token) localStorage.setItem('sb_refresh', authD.refresh_token);
      } catch(_){}

      setToast('Contraseña actualizada. Cerramos tu sesión en tus otros dispositivos.', 'ok');
      document.getElementById('pd-pass-current').value = '';
      document.getElementById('pd-pass-new').value = '';
      document.getElementById('pd-pass-new2').value = '';
      if (btn) { btn.disabled = false; btn.textContent = 'Actualizar contraseña'; }
    } catch(e) {
      setToast('Sin conexión. Intenta de nuevo en unos segundos.', 'err');
      if (btn) { btn.disabled = false; btn.textContent = 'Actualizar contraseña'; }
    }
  }
  window.changePasswordFromProfile = changePasswordFromProfile;

  // ── Eliminar cuenta (acción irreversible) ────────────────────
  // Habilita el botón solo cuando el correo escrito coincide con el de la cuenta.
  function checkDeleteMatch() {
    const inp = document.getElementById('pd-del-input');
    const btn = document.getElementById('pd-del-confirm-btn');
    if (!inp || !btn) return;
    const email = (_pdProfile?.email || '').trim().toLowerCase();
    const match = email !== '' && inp.value.trim().toLowerCase() === email;
    btn.style.opacity = match ? '' : '.4';
    btn.style.pointerEvents = match ? 'auto' : 'none';
  }
  window.checkDeleteMatch = checkDeleteMatch;

  // Llama al backend, que borra datos + usuario de Supabase Auth de forma real.
  async function ejecutarEliminarCuenta() {
    const btn = document.getElementById('pd-del-confirm-btn');
    const toast = document.getElementById('pd-toast-del');
    const tok = getToken();
    if (!tok) return;
    if (toast) toast.className = 'bk-pd-toast';
    if (btn) { btn.style.pointerEvents = 'none'; btn.style.opacity = '.6'; btn.textContent = 'Eliminando…'; }
    try {
      const r = await fetch(API_BASE + '/usuario/eliminar-cuenta', {
        method: 'DELETE',
        headers: { Authorization: 'Bearer ' + tok }
      });
      const d = await r.json().catch(() => ({}));
      // Solo damos por buena la baja si el usuario de Auth se eliminó de verdad.
      if (!r.ok || (d && d.borrados && d.borrados.auth === false)) throw new Error('delete failed');
      // Confirmación visible (también para la grabación de App Review).
      const card = btn ? btn.closest('.bk-pd-card') : null;
      if (card) card.innerHTML = '<p style="font-size:14px;color:var(--ink);line-height:1.5">Tu cuenta y todos tus datos fueron eliminados permanentemente.</p>';
      // Limpiar sesión y salir.
      localStorage.removeItem('sb_token');
      localStorage.removeItem('sb_refresh');
      localStorage.removeItem('sb_user');
      localStorage.removeItem('sesion_activa');
      sessionStorage.clear();
      setTimeout(() => { location.href = 'login.html'; }, 1800);
    } catch (e) {
      if (toast) { toast.textContent = 'No se pudo eliminar la cuenta. Intenta de nuevo o escríbenos a soporte.'; toast.className = 'bk-pd-toast err'; }
      if (btn) { btn.style.pointerEvents = 'auto'; btn.style.opacity = ''; btn.textContent = 'Eliminar mi cuenta permanentemente'; }
    }
  }
  window.ejecutarEliminarCuenta = ejecutarEliminarCuenta;

  async function saveEbKey() {
    const tok = getToken();
    const key = document.getElementById('pd-input-ebkey').value.trim();
    const toast = document.getElementById('pd-toast-eb');
    toast.className = 'bk-pd-toast';
    if (!key) { toast.textContent = 'Pega tu API key primero.'; toast.className = 'bk-pd-toast err'; return; }
    try {
      const r = await fetch(API_BASE + '/config/eb-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok },
        body: JSON.stringify({ key })
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Error');
      // La key vive solo en Supabase con RLS. Nunca toca el navegador del usuario.
      invalidateProfileCache();
      toast.textContent = 'EasyBroker conectado correctamente.';
      toast.className = 'bk-pd-toast ok';
      document.getElementById('pd-input-ebkey').value = '';
      document.getElementById('pd-eb-dot').className = 'dot ok';
      // Mostrar últimos 4 caracteres
      const masked = key.length > 4 ? '*'.repeat(key.length - 4) + key.slice(-4) : '';
      document.getElementById('pd-eb-status-text').textContent = 'Conectado — key: ' + masked;
      const discBtn = document.getElementById('pd-eb-disconnect-btn');
      if (discBtn) discBtn.style.display = 'block';
    } catch(e) {
      toast.textContent = e.message || 'API key inválida. Verifica que la copiaste bien.';
      toast.className = 'bk-pd-toast err';
    }
    setTimeout(() => { toast.className = 'bk-pd-toast'; }, 4000);
  }
  window.saveEbKey = saveEbKey;

  async function disconnectEbKey() {
    if (!confirm('¿Desconectar tu cuenta de EasyBroker? Tendrás que volver a pegar tu API key si quieres usarla más adelante.')) return;
    const tok = getToken();
    const toast = document.getElementById('pd-toast-eb');
    toast.className = 'bk-pd-toast';
    try {
      const r = await fetch(API_BASE + '/config/eb-key', {
        method: 'DELETE',
        headers: { Authorization: 'Bearer ' + tok }
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || 'Error');
      }
      invalidateProfileCache();
      toast.textContent = 'EasyBroker desconectado.';
      toast.className = 'bk-pd-toast ok';
      document.getElementById('pd-eb-dot').className = 'dot warn';
      document.getElementById('pd-eb-status-text').textContent = 'Sin conectar';
      document.getElementById('pd-eb-disconnect-btn').style.display = 'none';
    } catch(e) {
      toast.textContent = e.message || 'No se pudo desconectar.';
      toast.className = 'bk-pd-toast err';
    }
    setTimeout(() => { toast.className = 'bk-pd-toast'; }, 4000);
  }
  window.disconnectEbKey = disconnectEbKey;

  async function disconnectFacebook() {
    if (!confirm('¿Desconectar tu página de Facebook? Tendrás que volver a conectarla si quieres publicar propiedades.')) return;
    const tok = getToken();
    const toast = document.getElementById('pd-toast-fb');
    toast.className = 'bk-pd-toast';
    try {
      const r = await fetch(API_BASE + '/facebook/connection', {
        method: 'DELETE',
        headers: { Authorization: 'Bearer ' + tok }
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || 'Error al desconectar');
      }
      invalidateProfileCache();
      toast.textContent = 'Facebook desconectado.';
      toast.className = 'bk-pd-toast ok';
      document.getElementById('pd-fb-dot').className = 'dot warn';
      document.getElementById('pd-fb-status-text').textContent = 'Sin conectar';
      document.getElementById('pd-fb-btn').textContent = 'Conectar página de Facebook';
      document.getElementById('pd-fb-disconnect-btn').style.display = 'none';
    } catch(e) {
      toast.textContent = e.message || 'No se pudo desconectar.';
      toast.className = 'bk-pd-toast err';
    }
    setTimeout(() => { toast.className = 'bk-pd-toast'; }, 4000);
  }
  window.disconnectFacebook = disconnectFacebook;



  function connectFacebook() {
    const tok = getToken();
    if (!tok) return;
    const FB_APP_ID = window._brokrFbAppId || '';
    const redirectUri = encodeURIComponent(location.origin + '/facebook-callback.html');
    const scope = 'pages_show_list,pages_read_engagement,pages_manage_posts,ads_management,ads_read,business_management';
    if (!FB_APP_ID) {
      // Sin App ID configurado — mostrar instrucciones
      const toast = document.getElementById('pd-toast-fb');
      toast.textContent = 'Configura FB_APP_ID en Railway para habilitar esta función.';
      toast.className = 'bk-pd-toast err';
      setTimeout(() => { toast.className = 'bk-pd-toast'; }, 4000);
      return;
    }
    window.open(
      `https://www.facebook.com/v21.0/dialog/oauth?client_id=${FB_APP_ID}&redirect_uri=${redirectUri}&scope=${scope}&response_type=code`,
      'facebook_oauth',
      'width=600,height=700,scrollbars=yes'
    );
    // Escuchar cuando la ventana popup mande el resultado
    window._fbOAuthHandler = async function(code) {
      const tok2 = getToken();
      const toast = document.getElementById('pd-toast-fb');
      try {
        // 1. Intercambiar code por tokens y lista de páginas
        const r = await fetch(API_BASE + '/facebook/callback?code=' + encodeURIComponent(code) + '&redirect_uri=' + redirectUri, {
          headers: { Authorization: 'Bearer ' + tok2 }
        });
        const d = await r.json();
        if (!d.ok) {
          throw new Error(d.error || 'Error al obtener token de Facebook');
        }

        // 2. Si hay más de una página, preguntar cuál usar
        let chosenPage = { id: d.page_id, name: d.page_name, access_token: d.page_token };
        const pages = d.pages || [];
        if (pages.length > 1) {
          const chosen = await _fbPickPage(pages);
          if (!chosen) throw new Error('Selección cancelada.');
          chosenPage = chosen;
        }

        // 3. Guardar en Supabase vía backend
        const r2 = await fetch(API_BASE + '/facebook/save-page', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok2 },
          body: JSON.stringify({ page_id: chosenPage.id, page_name: chosenPage.name, page_token: chosenPage.access_token, user_token: d.user_token || '' })
        });
        if (!r2.ok) throw new Error('Error al guardar la conexión');

        // 4. Invalidar caché y recargar drawer desde Supabase para confirmar
        invalidateProfileCache();
        await loadProfileData();

      } catch(e) {
        if (toast) {
          toast.textContent = e.message || 'Error al conectar. Intenta de nuevo.';
          toast.className = 'bk-pd-toast err';
          setTimeout(() => { toast.className = 'bk-pd-toast'; }, 4000);
        }
      }
    };

    // Helper: modal de selección de página (solo si hay varias)
    function _fbPickPage(pages) {
      return new Promise((resolve) => {
        // Crear modal
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
        const modal = document.createElement('div');
        modal.style.cssText = 'background:var(--bone);border:1px solid var(--line-2);border-radius:16px;padding:28px 24px;max-width:360px;width:100%;box-shadow:0 8px 32px rgba(22,22,22,.18)';
        modal.innerHTML = `
          <div style="font-family:var(--font-display);font-size:16px;font-weight:700;color:var(--ink);margin-bottom:6px;letter-spacing:-.01em">Selecciona tu página</div>
          <div style="font-size:13px;color:var(--mute);margin-bottom:18px;line-height:1.5">Tienes varias páginas de Facebook. Elige con cuál quieres usar Broquer.</div>
          <div id="_fb-page-list" style="display:flex;flex-direction:column;gap:8px;margin-bottom:18px"></div>
          <button id="_fb-cancel-btn" style="width:100%;background:transparent;border:1px solid var(--line-2);border-radius:10px;padding:10px;font-size:13px;font-family:var(--font-sans);color:var(--mute);cursor:pointer">Cancelar</button>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        const list = modal.querySelector('#_fb-page-list');
        pages.forEach(page => {
          const btn = document.createElement('button');
          btn.style.cssText = 'width:100%;background:var(--paper);border:1px solid var(--line-2);border-radius:10px;padding:12px 14px;text-align:left;font-size:14px;font-weight:600;font-family:var(--font-sans);color:var(--ink);cursor:pointer;transition:border-color .15s';
          btn.textContent = page.name || page.id;
          btn.onmouseover = () => btn.style.borderColor = 'var(--ink)';
          btn.onmouseout = () => btn.style.borderColor = 'var(--line-2)';
          btn.onclick = () => { document.body.removeChild(overlay); resolve(page); };
          list.appendChild(btn);
        });

        modal.querySelector('#_fb-cancel-btn').onclick = () => { document.body.removeChild(overlay); resolve(null); };
      });
    }
  }
  window.connectFacebook = connectFacebook;

  async function startSubscriptionCheckoutFromGate() {
    // En iOS nativo no iniciamos checkout dentro de la app (política de Apple).
    if (IS_IOS_NATIVE) return;
    const tok = getToken();
    const btn = document.getElementById('bk-gate-sub-btn');
    const msg = document.getElementById('bk-gate-msg');
    if (btn) { btn.disabled = true; btn.textContent = 'Abriendo pago…'; }
    try {
      const r = await fetch(API_BASE + '/subscription/checkout', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_id: 'max',
          success_url: window.location.origin + '/index.html?suscripcion=ok',
          cancel_url: window.location.href
        })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.checkout_url) throw new Error(d.detail || 'No se pudo iniciar la suscripción.');
      window.location.href = d.checkout_url;
    } catch (e) {
      if (msg) msg.textContent = (e && e.message) ? e.message : 'No pude conectar con el servidor de pagos. Revisa que api.broquer.app tenga DNS y SSL correctos.';
      if (btn) { btn.disabled = false; btn.textContent = 'Suscribirme ahora'; }
    }
  }
  window.startSubscriptionCheckoutFromGate = startSubscriptionCheckoutFromGate;

  // ─── Compra in-app (RevenueCat / App Store) — solo iOS nativo ─────────────
  let RC_CONFIGURED = false;
  let RC_PACKAGE = null;
  const RC_APPLE_KEY = 'appl_JeLrHwOaILyXDQYLShLWzoEAtEA';

  function getUserIdFromToken() {
    try {
      const t = getToken();
      if (!t) return null;
      const json = atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(json).sub || null;
    } catch (_) { return null; }
  }

  async function rcConfigure() {
    if (!IS_IOS_NATIVE) return;
    const RC = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Purchases;
    if (!RC) return;
    const uid = getUserIdFromToken();
    try {
      if (!RC_CONFIGURED) {
        await RC.configure({ apiKey: RC_APPLE_KEY, appUserID: uid || undefined });
        RC_CONFIGURED = true;
      }
      // Siempre identificar al usuario REAL de Supabase ante RevenueCat.
      // Evita que la compra quede ligada a un ID anónimo/viejo, que el backend
      // no puede guardar por el foreign key a auth.users.
      if (uid) {
        await RC.logIn({ appUserID: uid });
      }
    } catch (_) {}
  }

  async function rcLoadOffering() {
    const RC = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Purchases;
    if (!RC) return null;
    await rcConfigure();
    try {
      const offerings = await RC.getOfferings();
      RC_PACKAGE = (offerings && offerings.current && offerings.current.availablePackages && offerings.current.availablePackages[0]) || null;
    } catch (_) { RC_PACKAGE = null; }
    return RC_PACKAGE;
  }

  async function rcRenderPrice() {
    const btn = document.getElementById('bk-iap-buy');
    if (!btn) return;
    const pkg = await rcLoadOffering();
    if (!pkg) { btn.textContent = 'Suscripción no disponible'; btn.disabled = true; return; }
    const price = (pkg.product && pkg.product.priceString) ? pkg.product.priceString : '';
    btn.textContent = price ? ('Suscribirme · ' + price + '/mes') : 'Suscribirme';
    btn.disabled = false;
  }

  async function rcWaitForActiveThenReload() {
    const msg = document.getElementById('bk-gate-msg');
    // La compra YA fue confirmada por Apple/RevenueCat en el dispositivo
    // (este método solo se llama cuando hay entitlement activo). Por eso
    // damos acceso de inmediato y dejamos que el webhook persista el estado
    // en Supabase en segundo plano. No dependemos de que el webhook llegue
    // dentro de una ventana de tiempo — eso era frágil y causaba que la app
    // se quedara "Procesando…" cuando el webhook tardaba unos segundos de más.
    if (msg) { msg.style.color = 'var(--mute)'; msg.textContent = 'Activando tu cuenta…'; }
    try { localStorage.setItem('bk_iap_active', String(Date.now())); } catch (_) {}
    location.reload();
  }

  async function rcBuy() {
    const RC = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Purchases;
    const btn = document.getElementById('bk-iap-buy');
    const msg = document.getElementById('bk-gate-msg');
    if (!RC) { if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'No se pudo iniciar la compra.'; } return; }
    if (!RC_PACKAGE) await rcLoadOffering();
    if (!RC_PACKAGE) { if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'Suscripción no disponible por ahora.'; } return; }
    if (btn) { btn.disabled = true; btn.textContent = 'Procesando…'; }
    if (msg) { msg.textContent = ''; }
    try {
      const res = await RC.purchasePackage({ aPackage: RC_PACKAGE });
      const active = (res && res.customerInfo && res.customerInfo.entitlements && res.customerInfo.entitlements.active) || {};
      if (Object.keys(active).length > 0) { rcWaitForActiveThenReload(); }
      else {
        if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'La compra no otorgó acceso. Escríbenos a hola@broquer.app.'; }
        if (btn) rcRenderPrice();
      }
    } catch (e) {
      if (btn) rcRenderPrice();
      if (!(e && e.userCancelled) && msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'No se pudo completar la compra. Intenta de nuevo.'; }
    }
  }

  async function rcRestore() {
    const RC = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Purchases;
    const msg = document.getElementById('bk-gate-msg');
    if (!RC) return;
    if (msg) { msg.style.color = 'var(--mute)'; msg.textContent = 'Restaurando…'; }
    try {
      await rcConfigure();
      const info = await RC.restorePurchases();
      const active = (info && info.customerInfo && info.customerInfo.entitlements && info.customerInfo.entitlements.active) || {};
      if (Object.keys(active).length > 0) { rcWaitForActiveThenReload(); }
      else if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'No encontramos una compra activa en esta cuenta de Apple.'; }
    } catch (_) {
      if (msg) { msg.style.color = 'var(--danger)'; msg.textContent = 'No se pudo restaurar. Intenta de nuevo.'; }
    }
  }

  window.rcBuy = rcBuy;
  window.rcRestore = rcRestore;

  /* ── Modal Broquer Max (freemium) ──────────────────────────────────
     Ya NO se reemplaza la pantalla completa. Cuando un usuario sin
     suscripción intenta ejecutar una acción premium (calcular ISR,
     estimar valor, limpiar imágenes, generar contrato/ficha, publicar
     anuncio, hablar con Broq, etc.) se abre este modal encima de la
     página. El usuario puede cerrarlo y seguir navegando libremente. */
  function closeBroquerMaxModal() {
    const ov = document.getElementById('bk-max-modal');
    if (ov) ov.remove();
  }
  window.closeBroquerMaxModal = closeBroquerMaxModal;

  function showBroquerMaxModal() {
    if (document.getElementById('bk-max-modal')) return;
    const buyBtn = IS_IOS_NATIVE
      ? `<button id="bk-iap-buy" onclick="rcBuy()" disabled style="width:100%;height:48px;border:none;border-radius:12px;background:var(--sky-blue);color:#FFFFFF;font-weight:700;font-size:14px;cursor:pointer;font-family:inherit;">Cargando…</button>
         <button id="bk-iap-restore" onclick="rcRestore()" style="width:100%;height:42px;border:1px solid var(--line-2);border-radius:12px;background:transparent;color:var(--ink);font-weight:600;font-size:13px;cursor:pointer;margin-top:10px;font-family:inherit;">Restaurar compras</button>`
      : `<button id="bk-gate-sub-btn" onclick="startSubscriptionCheckoutFromGate()" style="width:100%;height:48px;border:none;border-radius:12px;background:var(--sky-blue);color:#FFFFFF;font-weight:700;font-size:14px;cursor:pointer;font-family:inherit;">Suscribirme a Broquer Max</button>`;
    const legal = IS_IOS_NATIVE
      ? `<div style="margin-top:14px;font-size:11px;color:var(--mute);line-height:1.5;">Broquer Max es una suscripción mensual: el pago se cobra a tu cuenta de Apple al confirmar y se renueva automáticamente cada mes, salvo que la canceles desde Ajustes de iOS al menos 24 h antes del fin del periodo. Al continuar aceptas los <a href="legal.html" style="color:var(--mute);text-decoration:underline;">Términos de uso</a> y el <a href="legal.html" style="color:var(--mute);text-decoration:underline;">Aviso de Privacidad</a>.</div>`
      : '';
    const ov = document.createElement('div');
    ov.id = 'bk-max-modal';
    ov.style.cssText = 'position:fixed;inset:0;z-index:2147483646;background:rgba(5,32,60,.46);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;padding:20px;font-family:var(--font-sans);';
    ov.innerHTML = `
      <div style="width:100%;max-width:400px;background:var(--bone);border:1px solid var(--line);border-radius:24px;padding:28px;box-shadow:0 20px 60px rgba(5,32,60,.30);text-align:center;position:relative;">
        <button onclick="closeBroquerMaxModal()" aria-label="Cerrar" style="position:absolute;top:12px;right:14px;border:none;background:transparent;color:var(--mute);font-size:26px;line-height:1;cursor:pointer;padding:4px 8px;font-family:inherit;">&times;</button>
        <img src="isotipo-black.png" alt="Broquer" style="width:52px;height:52px;object-fit:contain;margin-bottom:14px;"/>
        <h2 style="font-family:var(--font-display);font-size:24px;line-height:1.1;margin:0 0 10px;color:var(--ink);letter-spacing:-.02em;">Broquer Max</h2>
        <p style="color:var(--mute);font-size:14px;line-height:1.55;margin:0 0 20px;">Para hacer uso de estos módulos exclusivos de Broquer por favor suscríbete a Broquer Max.</p>
        ${buyBtn}
        <button onclick="closeBroquerMaxModal()" style="width:100%;height:40px;border:none;background:transparent;color:var(--mute);font-weight:600;font-size:13px;cursor:pointer;margin-top:8px;font-family:inherit;">Ahora no</button>
        <div id="bk-gate-msg" style="margin-top:8px;font-size:12px;color:var(--danger);min-height:18px;"></div>
        ${legal}
      </div>`;
    ov.addEventListener('click', (e) => { if (e.target === ov) closeBroquerMaxModal(); });
    document.body.appendChild(ov);
    if (IS_IOS_NATIVE) rcRenderPrice();
  }
  window.showBroquerMaxModal = showBroquerMaxModal;

  /* ── Freemium: acciones premium por página ─────────────────────────
     El CRM (inicio, contactos, leads, tareas, propiedades, perfil) es
     de uso libre. En el resto de módulos el usuario puede entrar,
     navegar y llenar formularios; solo al EJECUTAR la acción de valor
     aparece el modal de Broquer Max si no tiene suscripción activa. */
  const BK_PREMIUM_ACTIONS = {
    'isr.html':            ['#calc-btn'],
    'avm.html':            ['#btn-analizar-ia'],
    'image-cleaner.html':  ['#btn-clean'],
    'contratos.html':      ['#gen-btn'],
    'ficha-manual.html':   ['#ai-btn', '#pdf-btn'],
    'facebook-ads.html':   ['#fa-ai-btn', '#fa-submit-btn'],
    'whatsapp.html':       ['#wa-connect-btn', '#tpl-submit-btn'],
  };

  function bkCurrentPageFile() {
    const p = (location.pathname.split('/').pop() || '').toLowerCase();
    return p || 'index.html';
  }

  function bkInstallFreemiumGate() {
    if (window.__BK_SUB_ACTIVE) return; // suscriptor: sin intercepción
    const sels = BK_PREMIUM_ACTIONS[bkCurrentPageFile()];
    if (!sels || !sels.length) return;
    const selector = sels.join(',');
    // Fase de captura: interceptamos ANTES de que el módulo ejecute su lógica.
    document.addEventListener('click', function (e) {
      if (window.__BK_SUB_ACTIVE) return;
      const t = e.target;
      const hit = t && t.closest ? t.closest(selector) : null;
      if (!hit) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      e.stopPropagation();
      showBroquerMaxModal();
    }, true);
  }

  /* Chequeo de suscripción NO bloqueante (freemium).
     Devuelve true (activa / admin / fail-open), false (confirmada inactiva)
     o null (sesión expirada — ya se redirigió a login). Nunca reemplaza la
     pantalla: el modal de Broquer Max aparece solo al ejecutar acciones
     premium. */
  async function checkSubscriptionActive(profile) {
    if (profile?.isAdmin || profile?.profile?.plan === 'admin' || profile?.profile?.rol === 'equipo' || profile?.profile?.plan === 'equipo') return true;

    // ── iOS nativo: la fuente de verdad es RevenueCat en el dispositivo ──────
    // Apple confirma la compra al instante en el iPhone; Supabase se actualiza
    // unos segundos después vía webhook. Si preguntáramos solo al backend,
    // un comprador legítimo vería el paywall mientras el webhook viaja. Por eso
    // en iOS preguntamos PRIMERO a RevenueCat: si el dispositivo reporta un
    // entitlement activo, damos acceso de inmediato sin depender del backend.
    if (IS_IOS_NATIVE) {
      try {
        const RC = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Purchases;
        if (RC) {
          await rcConfigure();
          const info = await RC.getCustomerInfo();
          const active = (info && info.customerInfo && info.customerInfo.entitlements && info.customerInfo.entitlements.active) || {};
          if (Object.keys(active).length > 0) {
            try { localStorage.setItem('bk_iap_active', String(Date.now())); } catch (_) {}
            return true;
          }
        }
      } catch (_) { /* si RevenueCat falla, caemos al chequeo normal del backend */ }
    }

    // Si el usuario regresa de Stripe con ?suscripcion=ok o ?sub=ok,
    // hacer polling hasta 15 seg mientras el webhook llega a Supabase
    const params = new URLSearchParams(window.location.search);
    const justPaid = params.get('suscripcion') === 'ok' || params.get('sub') === 'ok';

    const maxAttempts = justPaid ? 10 : 3;
    const delay = ms => new Promise(res => setTimeout(res, ms));

    // Solo mostramos el paywall cuando el backend RESPONDE OK con active:false.
    // Cualquier otro escenario (401 sin poder refrescar, 5xx, red caída) NO debe
    // gatillar el gate, porque un cliente que paga jamás debe verlo por un blip.
    let confirmedInactive = false;
    let authExpired = false;

    for (let i = 0; i < maxAttempts; i++) {
      const tok = getToken();
      try {
        let r = await fetch(API_BASE + '/subscription/status', { headers: { Authorization: 'Bearer ' + tok } });

        // Token de acceso expirado tras inactividad: refrescar y reintentar UNA vez.
        if (r.status === 401) {
          const newTok = await tryRefreshToken();
          if (newTok) {
            r = await fetch(API_BASE + '/subscription/status', { headers: { Authorization: 'Bearer ' + newTok } });
          } else {
            // El refresh token también murió → sesión inválida, no es un problema de plan.
            authExpired = true;
            break;
          }
        }

        if (r.ok) {
          const d = await r.json().catch(() => ({}));
          if (d.active) {
            if (justPaid) {
              const clean = window.location.pathname;
              window.history.replaceState({}, '', clean);
            }
            return true;
          }
          confirmedInactive = true;
        }
        // 5xx u otros: reintentar silenciosamente.
      } catch (_) { /* red intermitente — reintentar */ }
      if (i < maxAttempts - 1) await delay(1500);
    }

    if (authExpired) { location.href = 'login.html'; return null; }

    if (confirmedInactive) {
      // Sin suscripción: el usuario entra igual (freemium). El modal de
      // Broquer Max aparecerá solo cuando intente una acción premium.
      return false;
    }

    // Nunca pudimos confirmar inactividad → fail-open: un cliente que paga
    // jamás debe ver el bloqueo por un blip de red.
    return true;
  }

  async function boot() {
    const profile = await authInit();
    if (!profile) return; // redirected to login/landing
    const subActive = await checkSubscriptionActive(profile);
    if (subActive === null) return; // sesión expirada — ya se redirigió
    window.__BK_SUB_ACTIVE = (subActive === true);

    // ── ¿Usuario empresarial? (organización tipo 'empresa') ──
    // Decide si el módulo "Equipo" aparece en el sidebar / menú. Fail-closed:
    // si no podemos confirmarlo, no se muestra.
    try {
      const _tok = getToken();
      const _orgRes = await fetch(API_BASE + '/org', {
        headers: _tok ? { Authorization: 'Bearer ' + _tok } : {},
      });
      if (_orgRes.ok) {
        const _org = await _orgRes.json();
        profile.esEmpresa = !!(_org && _org.tiene_org && _org.es_empresa);
      }
    } catch (_) { /* sin confirmar → no se muestra Equipo */ }

    // El drawer de perfil necesita saber si la cuenta es empresarial para
    // decidir si muestra la sección de Equipo, y se arma después del shell.
    window.__BK_PROFILE = profile;

    injectShell(profile);
    bkInstallFreemiumGate();

    // ── Cargar configuración pública del backend (FB_APP_ID, etc.) ──────────
    try {
      const cfgRes = await fetch(API_BASE + '/config/public');
      if (cfgRes.ok) {
        const cfg = await cfgRes.json();
        if (cfg.fb_app_id) window._brokrFbAppId = cfg.fb_app_id;
      }
    } catch (_) { /* sin conexión — connectFacebook mostrará su propio error */ }

    // ════════════════════════════════════════════════════════════════
    // window.brokrSb — helper centralizado con auto-refresh
    // Lo usan contactos.html, propiedades.html, index.html, etc.
    //
    // Esto resuelve dos bugs históricos:
    //   1) el helper se mencionaba pero nunca se exponía → contactos
    //      fallaba al cargar.
    //   2) cada módulo manejaba 401 tirando "Sesión expirada", forzando
    //      al usuario a hacer login. Ahora: si el access_token expira,
    //      sbFetch hace refresh y reintenta. Solo si el refresh falla
    //      se redirige a login.
    //
    // Además: refresh proactivo cada 30 min (el access_token de Supabase
    // dura 1h, así que renovar a la mitad es seguro y evita ventanas
    // donde el token expire entre clicks).
    // ════════════════════════════════════════════════════════════════
    (function setupBrokrSb() {
      const REFRESH_INTERVAL_MS = 30 * 60 * 1000; // 30 minutos
      let _refreshInFlight = null;                // de-dupea refreshes paralelos

      function _readToken() {
        return localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token') || null;
      }

      async function ensureToken() {
        // Si hay token, lo devolvemos tal cual. Si no, intentamos refresh.
        const t = _readToken();
        if (t) return t;
        return await refreshNow();
      }

      async function refreshNow() {
        // De-dupea: si ya hay un refresh en curso, espera ese mismo.
        if (_refreshInFlight) return await _refreshInFlight;
        _refreshInFlight = (async () => {
          try {
            return await tryRefreshToken();
          } finally {
            _refreshInFlight = null;
          }
        })();
        return await _refreshInFlight;
      }

      // Refresh proactivo periódico — silencioso si falla (al siguiente
      // request real, ensureToken hará el refresh on-demand de todas formas).
      setInterval(() => { refreshNow().catch(() => {}); }, REFRESH_INTERVAL_MS);

      // Wrapper de fetch contra Supabase REST/Auth con auto-retry en 401.
      // path: 'rest/v1/propiedades?...' o 'auth/v1/user', etc.
      async function sbApi(path, init = {}) {
        const tok = await ensureToken();
        const baseHeaders = {
          apikey: SB_KEY,
          ...(tok ? { Authorization: 'Bearer ' + tok } : {}),
        };
        const opts = {
          ...init,
          headers: { ...baseHeaders, ...(init.headers || {}) }
        };
        const url = SB_URL + '/' + path.replace(/^\/+/, '');

        // Timeout de 15 s para evitar que fetch quede colgado en conexiones lentas/inestables.
        function fetchWithTimeout(u, o) {
          const controller = new AbortController();
          const tid = setTimeout(() => controller.abort(), 15000);
          return fetch(u, { ...o, signal: controller.signal })
            .then(res => { clearTimeout(tid); return res; })
            .catch(err => {
              clearTimeout(tid);
              if (err.name === 'AbortError') {
                throw new Error('La conexión tardó demasiado. Verifica tu red e intenta de nuevo.');
              }
              throw err;
            });
        }

        let r = await fetchWithTimeout(url, opts);

        // Token expirado/invalido → refresh y un único reintento
        if (r.status === 401) {
          const newTok = await refreshNow();
          if (newTok) {
            opts.headers = {
              ...baseHeaders,
              Authorization: 'Bearer ' + newTok,
              ...(init.headers || {}),
            };
            r = await fetchWithTimeout(url, opts);
          } else {
            // Refresh falló de verdad → cerrar sesión limpiamente.
            // No redirigimos en medio del fetch para no romper UIs en curso;
            // dejamos que el caller maneje !ok como hoy, pero limpiamos
            // tokens podridos para que el próximo nav vaya a login.
            localStorage.removeItem('sb_token');
            sessionStorage.removeItem('sb_token');
          }
        }
        return r;
      }

      // Helper conveniente para REST: devuelve JSON parseado o lanza con detalle.
      async function sbRest(pathAndQuery, { method = 'GET', body = null, headers = {} } = {}) {
        const init = {
          method,
          headers: { 'Content-Type': 'application/json', Prefer: 'return=representation', ...headers },
        };
        if (body !== null) init.body = typeof body === 'string' ? body : JSON.stringify(body);
        const r = await sbApi('rest/v1/' + pathAndQuery.replace(/^\/+/, ''), init);
        if (!r.ok) {
          const txt = await r.text();
          if (r.status === 401 || r.status === 403) {
            throw new Error('Sesión expirada. Vuelve a iniciar sesión.');
          }
          throw new Error(txt || ('HTTP ' + r.status));
        }
        const txt = await r.text();
        return txt ? JSON.parse(txt) : [];
      }

      window.brokrSb = {
        url: SB_URL,
        key: SB_KEY,
        ensureToken,
        refreshNow,
        fetch: sbApi,   // contactos.html usa esta firma: sb.fetch('rest/v1/...')
        rest: sbRest,   // para módulos nuevos
      };
    })();

    // Wake word: wait for first user gesture before starting (browser policy)
    _updateWakeUI();
    if (_wakeEnabled) {
      const initWake = () => {
        document.removeEventListener('touchstart', initWake);
        document.removeEventListener('click', initWake);
        ensureMicPermission().then(ok => { if (ok) startWakeWordListener(); });
      };
      document.addEventListener('touchstart', initWake, { once: true });
      document.addEventListener('click', initWake, { once: true });
    }

    // ─── Frases motivacionales rotativas (cada hora) ───────────────
    const QUOTES = [
      { t: 'El éxito no es definitivo, el fracaso no es fatal: lo que cuenta es el coraje para continuar.', a: 'Winston Churchill' },
      { t: 'La única forma de hacer un gran trabajo es amar lo que haces.', a: 'Steve Jobs' },
      { t: 'No te preocupes por el fracaso; preocúpate por las oportunidades que pierdes cuando ni siquiera lo intentas.', a: 'Jack Canfield' },
      { t: 'El mercado siempre puede permanecer irracional más tiempo del que tú puedes permanecer solvente.', a: 'John Maynard Keynes' },
      { t: 'La oportunidad no toca: presenta su tarjeta cuando vienes a buscarla.', a: 'Charles Schwab' },
      { t: 'Quien quiere hacer algo encuentra un medio; quien no quiere hacer nada encuentra una excusa.', a: 'Proverbio árabe' },
      { t: 'Café es para closers.', a: 'Glengarry Glen Ross' },
      { t: 'El que no arriesga, no gana.', a: 'Refrán popular' },
      { t: 'Cada batalla se gana antes de pelearla.', a: 'Sun Tzu' },
      { t: 'No vendemos casas. Vendemos sueños, posibilidades, hogares.', a: 'Barbara Corcoran' },
      { t: 'El dinero es como el estiércol: solo sirve si lo esparces.', a: 'J. Paul Getty' },
      { t: 'Lo importante no es lo que te pasa, sino cómo reaccionas a lo que te pasa.', a: 'Epicteto' },
      { t: 'Si no estás dispuesto a arriesgarlo todo, no esperes lograr nada.', a: 'Muhammad Ali' },
      { t: 'En los negocios, lo que es peligroso es no evolucionar.', a: 'Jeff Bezos' },
      { t: 'El precio es lo que pagas. El valor es lo que recibes.', a: 'Warren Buffett' },
      { t: 'No se trata de ideas. Se trata de hacer que las ideas sucedan.', a: 'Scott Belsky' },
      { t: 'Si lo construyes, ellos vendrán.', a: 'Field of Dreams' },
      { t: 'Greed, for lack of a better word, is good.', a: 'Wall Street — Gordon Gekko' },
      { t: 'A.B.C. — Always Be Closing.', a: 'Glengarry Glen Ross' },
      { t: 'La gente no compra productos: compra la versión mejor de sí mismos.', a: 'Don Draper — Mad Men' },
      { t: 'El que tiene un porqué para vivir, puede soportar casi cualquier cómo.', a: 'Friedrich Nietzsche' },
      { t: 'Lo que hagas hoy puede mejorar todos tus mañanas.', a: 'Ralph Marston' },
      { t: 'El verdadero valor de un hombre se determina principalmente examinando en qué medida ha alcanzado la liberación del yo.', a: 'Albert Einstein' },
      { t: 'No persigas el éxito: vuélvete una persona de valor y el éxito te seguirá.', a: 'Albert Einstein' },
    ];
    const quoteEl = document.getElementById('bk-topbar-quote');
    let _quoteIdx = -1;
    function showQuote() {
      if (!quoteEl) return;
      let next;
      // hash de la hora actual para que la frase cambie cada hora de forma determinista
      const hourHash = Math.floor(Date.now() / (1000 * 60 * 60));
      next = hourHash % QUOTES.length;
      if (next === _quoteIdx) next = (next + 1) % QUOTES.length;
      _quoteIdx = next;
      const q = QUOTES[next];
      quoteEl.classList.remove('is-visible');
      setTimeout(() => {
        quoteEl.innerHTML = `${q.t}<span class="quote-author">— ${q.a}</span>`;
        quoteEl.classList.add('is-visible');
      }, 250);
    }
    showQuote();
    // verificación cada minuto: si cambió la hora, rotar
    let _lastHour = new Date().getHours();
    setInterval(() => {
      const h = new Date().getHours();
      if (h !== _lastHour) {
        _lastHour = h;
        showQuote();
      }
    }, 60 * 1000);

    // ─── Búsqueda expandible (lupa en topbar) ──────────────────────
    const searchToggleBtn = document.getElementById('bk-search-toggle');
    const searchExpand    = document.getElementById('bk-search-expand');
    const searchCloseBtn  = document.getElementById('bk-search-close');
    const searchInput     = document.getElementById('bk-search');
    function openSearch() {
      if (!searchExpand) return;
      searchExpand.classList.add('is-open');
      setTimeout(() => searchInput?.focus(), 50);
    }
    function closeSearch() {
      if (!searchExpand) return;
      searchExpand.classList.remove('is-open');
      if (searchInput) searchInput.value = '';
    }
    searchToggleBtn?.addEventListener('click', openSearch);
    searchCloseBtn?.addEventListener('click', closeSearch);
    searchInput?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') closeSearch();
    });

    // Notify module that shell is ready (so modules can run code that depends
    // on the .bk-page wrapper or the avatar, e.g. read sessionStorage payloads).
    // Personalizar saludo con nombre del usuario
    const _welcomeMsg = document.getElementById('bk-welcome-msg');
    if (_welcomeMsg && profile?.fullName) {
      const _firstName = profile.fullName.trim().split(' ')[0];
      _welcomeMsg.textContent = `¡Hola, ${_firstName}! Soy Broq, tu asistente inteligente. ¿En qué te ayudo?`;
    }

    // ─── "Mi sitio" en móvil / iOS ────────────────────────────────
    // En web abre la pantalla de configuración (mi-sitio.html).
    // En celular y en la app de iOS NO: abre directo el sitio público
    // del agente (broquer.app/su-link) en el navegador del teléfono.
    // Si todavía no tiene link configurado, cae a la configuración,
    // porque si no, no habría manera de crearlo desde el celular.
    setupMiSitio(profile);

    // ─── Mensajes de WhatsApp sin leer: globito + notificación ────
    // WhatsApp ya está abierto para todos: todo agente sondea sus no leídos.
    setupChatsBadge(profile);

    // ─── Cita nueva agendada por la IA de WhatsApp: aviso inmediato (web) ──
    setupCitasNotify(profile);

    window.dispatchEvent(new CustomEvent('brokr-shell-ready', { detail: { profile, activeKey } }));
  }

  /* ════════════════════════════════════════════════════════════════
     MI SITIO — comportamiento distinto en móvil/iOS que en web
     ════════════════════════════════════════════════════════════════ */
  let _miSitioCache = null;

  function esMovil() {
    return IS_IOS_NATIVE || window.matchMedia('(max-width: 880px)').matches;
  }

  async function _miSitioDatos(profile) {
    if (_miSitioCache) return _miSitioCache;
    const uid = profile?.user?.id;
    if (!uid) return null;
    try {
      const rows = await sbFetch('usuarios?id=eq.' + encodeURIComponent(uid) + '&select=slug,sitio_activo');
      _miSitioCache = rows[0] || {};
      return _miSitioCache;
    } catch (e) { return null; }
  }

  /* Global: lo usan la hoja de módulos, el drawer de perfil y el dashboard. */
  window.bkOpenMiSitio = async function () {
    if (!esMovil()) { location.href = 'mi-sitio.html'; return; }
    const d = await _miSitioDatos(window.__brokrProfile);
    const slug = d && d.slug;
    if (!slug) { location.href = 'mi-sitio.html'; return; }   // aún no lo configura
    const url = 'https://broquer.app/' + slug;
    // En el WebView de iOS, target=_blank sale a Safari (no atrapa la app).
    try { window.open(url, '_blank', 'noopener'); }
    catch (e) { location.href = url; }
  };

  function setupMiSitio(profile) {
    window.__brokrProfile = profile;
    if (!esMovil()) return;
    // Cualquier link a mi-sitio.html dentro de la app (dashboard, sidebar,
    // atajos de Broq) se reencamina al sitio público cuando es celular.
    document.addEventListener('click', (ev) => {
      const a = ev.target.closest && ev.target.closest('a[href$="mi-sitio.html"]');
      if (!a) return;
      ev.preventDefault();
      window.bkOpenMiSitio();
    }, true);
    // Precarga el slug para que el primer toque sea instantáneo.
    _miSitioDatos(profile);
  }

  /* ════════════════════════════════════════════════════════════════
     CHATS — globito de mensajes sin leer + notificación
     El conteo vive en wa2_conversaciones.unread_count: el webhook lo sube
     cuando entra un mensaje del prospecto y la pestaña de chats lo baja
     a 0 solo cuando el agente abre el chat (o lo vuelve a subir si lo marca
     como no leído). Aquí solo lo leemos cada 20 s.
     En iOS la notificación real la manda APNs (ver capacitor-bridge.js);
     esto es el respaldo para web y PWA.
     ════════════════════════════════════════════════════════════════ */
  let _unreadPrev = null;

  async function _leerNoLeidos() {
    try {
      const rows = await sbFetch('wa2_conversaciones?select=unread_count,no_leida');
      if (!Array.isArray(rows)) return 0;
      // Una conversación que el agente marcó como no leída a mano cuenta como
      // pendiente aunque su contador vaya en cero.
      return rows.reduce((a, c) => a + (Number(c.unread_count) || (c.no_leida ? 1 : 0)), 0);
    } catch (e) { return 0; }
  }

  function _pintarBadge(n) {
    const txt = n > 99 ? '99+' : String(n);
    ['bk-bnav-badge', 'bk-sheet-badge'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = txt;
      el.classList.toggle('is-on', n > 0);
    });
    // Globito en el ícono de la app (iOS / Android / algunos navegadores)
    try {
      if (navigator.setAppBadge) { n > 0 ? navigator.setAppBadge(n) : navigator.clearAppBadge(); }
    } catch (e) {}
    window.__brokrUnread = n;
  }

  function setupChatsBadge(profile) {
    if (!profile?.user?.id) return;

    async function tick() {
      const n = await _leerNoLeidos();
      _pintarBadge(n);
      // Notificación de escritorio/PWA solo cuando SUBE el número y no
      // estamos ya viendo los chats. Ojo: ahora WhatsApp es un módulo con
      // pestañas, así que estar en whatsapp.html no basta para callar el
      // aviso —en Ajustes o Entrenamiento el agente sí quiere enterarse—.
      // La clase .wa-chats en <body> es la que dice si el hilo está a la
      // vista. En iOS nativo no entra aquí: allá manda APNs, y duplicar
      // avisos sería molesto.
      const viendoChats = activeKey === 'whatsapp' && document.body.classList.contains('wa-chats');
      if (_unreadPrev !== null && n > _unreadPrev && !viendoChats && !IS_IOS_NATIVE) {
        _avisoWeb(n - _unreadPrev);
      }
      _unreadPrev = n;
    }

    tick();
    setInterval(() => { if (!document.hidden) tick(); }, 20000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
    // La pestaña de chats avisa al shell cuando el agente lee un chat.
    window.addEventListener('brokr-chats-leidos', tick);
  }

  function _avisoWeb(nuevos) {
    try {
      if (!('Notification' in window) || Notification.permission !== 'granted') return;
      const n = new Notification('Broquer · WhatsApp', {
        body: nuevos === 1 ? 'Tienes un mensaje nuevo de un prospecto.'
                           : `Tienes ${nuevos} mensajes nuevos de prospectos.`,
        icon: 'icon-192.png',
        tag: 'broquer-wa',
      });
      n.onclick = () => { window.focus(); location.href = 'whatsapp.html#chats'; };
    } catch (e) {}
  }

  /* ─── Cita nueva agendada por la IA de WhatsApp: aviso inmediato (web) ───
     En iOS la notificación real la manda APNs (ya se manda desde el backend
     en cuanto se crea la tarea); esto es el aviso equivalente para web/PWA,
     revisando cada 20s. Se guarda en localStorage cuál fue la última cita
     que este dispositivo ya vio, para no re-avisar de todo el historial ni
     duplicar avisos entre pestañas/dispositivos del mismo agente. */
  function setupCitasNotify(profile) {
    if (!profile?.user?.id) return;
    const storageKey = 'bk_ultima_cita_vista_' + profile.user.id;

    async function tick() {
      try {
        const rows = await sbFetch(
          'tareas?select=id,titulo,fecha_entrega,created_at&titulo=ilike.*(WhatsApp)*' +
          '&order=created_at.desc&limit=5'
        );
        if (!Array.isArray(rows) || !rows.length) return;
        const ultimaVista = localStorage.getItem(storageKey);
        if (!ultimaVista) {
          // Primera vez en este dispositivo: solo marca desde dónde avisar
          // de aquí en adelante, no avisa de todo lo que ya existía.
          localStorage.setItem(storageKey, rows[0].created_at);
          return;
        }
        const nuevas = rows.filter(t => t.created_at > ultimaVista);
        if (!nuevas.length) return;
        localStorage.setItem(storageKey, rows[0].created_at);
        if (!IS_IOS_NATIVE) nuevas.reverse().forEach(_avisoCita);
      } catch (e) {}
    }

    tick();
    setInterval(() => { if (!document.hidden) tick(); }, 20000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  }

  function _avisoCita(t) {
    try {
      if (!('Notification' in window) || Notification.permission !== 'granted') return;
      const cuando = t.fecha_entrega
        ? new Date(t.fecha_entrega).toLocaleString('es-MX', { day:'2-digit', month:'short', hour:'numeric', minute:'2-digit' })
        : '';
      const n = new Notification('Broquer · Nueva cita agendada', {
        body: t.titulo + (cuando ? ' — ' + cuando : ''),
        icon: 'icon-192.png',
        tag: 'broquer-cita-' + t.id,
      });
      n.onclick = () => { window.focus(); location.href = 'tareas.html'; };
    } catch (e) {}
  }

  /* Pedir permiso de notificaciones en web/PWA: solo desde los chats y
     solo una vez (pedirlo al entrar a la app se siente invasivo y el
     navegador lo bloquea si no hay gesto del usuario). */
  window.bkPedirNotificaciones = async function () {
    try {
      if (!('Notification' in window)) return 'unsupported';
      if (Notification.permission !== 'default') return Notification.permission;
      return await Notification.requestPermission();
    } catch (e) { return 'error'; }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

/* ── Guarda de escala en iOS ─────────────────────────────────
   Un pellizco sobre el visor PDF de firma, sobre una grafica o sobre
   una tabla amplia deja la vista ampliada y en la app no hay barra de
   navegador para restaurarla. Se bloquea el gesto de escala y, si el
   sistema alcanzo a cambiarla, se devuelve a 1 al soltar. */
(function () {
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(function (t) {
    document.addEventListener(t, function (ev) { ev.preventDefault(); }, { passive: false });
  });
  document.addEventListener('touchend', function () {
    if (window.visualViewport && window.visualViewport.scale > 1.01) {
      document.body.style.zoom = '';
      window.scrollTo(window.scrollX, window.scrollY);
    }
  }, { passive: true });
})();
