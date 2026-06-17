/* ════════════════════════════════════════════════════════════════════
   BROQUER — App Shell compartido
   Inyecta: sidebar desktop, topbar, mobile header, bottom nav, Shaark.
   Conserva 1:1 el flujo de Supabase / OpenAI / Railway del repo original.

   Uso en cada módulo:
     <body data-app="isr">         ← clave del módulo activo
        … contenido del módulo …
     <script src="app-shell.js" defer></script>
   Claves válidas: home, props, contactos, contratos, avm, valor, ficha,
                   ficha-manual, isr, image-cleaner, facebook-ads, whatsapp, guia, admin
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

  /* ── Configuración de módulos ── */
  const MODS = [
    { key:'props',        href:'propiedades.html',   label:'Tus Inmuebles',       group:'main', icon:'building' },
    { key:'contactos',    href:'contactos.html',     label:'Contactos',       group:'main', icon:'users' },
    { key:'contratos',    href:'contratos.html',     label:'Contratos',       group:'main', icon:'document' },
    { key:'avm',          href:'avm.html',           label:'Estimación de valor', group:'main', icon:'peso' },
    { key:'ficha-manual', href:'ficha-manual.html',  label:'Ficha técnica',   group:'main', icon:'landscape' },
    { key:'isr',          href:'isr.html',           label:'ISR',             group:'main', icon:'calculator' },
    { key:'image-cleaner',href:'image-cleaner.html', label:'Editor imágenes', group:'main', icon:'image' },
    { key:'facebook-ads', href:'facebook-ads.html',  label:'Facebook Ads', group:'main', icon:'facebook' },
    { key:'whatsapp',     href:'whatsapp.html',       label:'WhatsApp',     group:'main', icon:'whatsapp' },
    { key:'guia',         href:'guia-agente.html',   label:'Ayuda', group:'main', icon:'question' },
    { key:'admin',        href:'admin.html',         label:'Admin',           group:'main', icon:'cog', adminOnly:true },
  ];

  const CONTEXT_LABELS = {
    'home':         'Dashboard principal — menú de módulos',
    'props':        'Tus Inmuebles — catálogo de propiedades',
    'contactos':    'Contactos — CRM de prospectos',
    'contratos':    'Contratos — arrendamiento y promesa de compraventa',
    'avm':          'Estimación de valor AVM — avalúo de mercado automatizado',
    'valor':        'Valor web — estimación de valor con investigación controlada de comparables públicos',
    'ficha':        'Ficha EasyBroker — generar ficha técnica desde ID de EasyBroker',
    'ficha-manual': 'Ficha Técnica Manual — crear ficha sin EasyBroker',
    'isr':          'Calculadora ISR por enajenación de inmuebles',
    'image-cleaner':'Editor de imágenes — limpieza con IA',
    'admin':        'Panel administrativo',
    'facebook-ads': 'Meta Ads Express — crear, activar y medir anuncios de Facebook e Instagram',
  };

  /* ── Iconos (heroicons outline 1.6) ── */
  const ICONS = {
    home:       '<path stroke-linecap="round" stroke-linejoin="round" d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h4v-6h4v6h4a1 1 0 001-1V10"/>',
    building:   '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955a1.5 1.5 0 012.121 0L22.28 12M4.5 9.75v10.125a1.125 1.125 0 001.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125a1.125 1.125 0 001.125-1.125V9.75"/>',
    users:      '<path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>',
    document:   '<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>',
    chart:      '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941"/>',
    tag:        '<path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/>',
    pencil:     '<path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125"/>',
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
    handshake:  '<path stroke-linecap="round" stroke-linejoin="round" d="M3 12l3-3 3 3 4-4 5 5-3 3-2-2-4 4-2-2-2 2-2-2 0-4z"/>',
    question:   '<path stroke-linecap="round" stroke-linejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"/>',
    facebook:   '<path fill="currentColor" stroke="none" d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.886v2.269h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>',
    whatsapp:   '<path fill="currentColor" stroke="none" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347zM12 0C5.373 0 0 5.373 0 12c0 2.127.558 4.126 1.533 5.857L.057 23.882a.5.5 0 00.614.612l6.115-1.598A11.947 11.947 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.967 0-3.805-.538-5.378-1.47l-.385-.23-3.993 1.044 1.012-3.9-.252-.403A9.96 9.96 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/>',
  };
  const svg = (name, size = 18, sw = 1.6) =>
    `<svg width="${size}" height="${size}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="${sw}">${ICONS[name] || ''}</svg>`;

  /* Helper local para SVGs dentro de chips de Shaark (14×14, stroke 1.7) */
  const _CICO = (name) =>
    `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7" style="flex-shrink:0;vertical-align:-2px;margin-right:6px">${ICONS[name] || ''}</svg>`;

  const SHAARK_CHIPS_MAP = {
    home:         [{l:_CICO('document')+'Contratos', m:'Generar un contrato'}, {l:_CICO('calculator')+'Calc. ISR', m:'Calcular ISR'}, {l:_CICO('tag')+'Fichas téc.', m:'Crear ficha técnica'}, {l:_CICO('building')+'Tus Inmuebles', m:'Ver tus inmuebles'}],
    contratos:    [{l:_CICO('pencil')+'Arrendamiento', m:'Genera un contrato de arrendamiento'}, {l:_CICO('handshake')+'Promesa', m:'Genera una promesa de compraventa'}, {l:_CICO('question')+'¿Cómo funciona?', m:'¿Qué tipos de contrato puedo generar?'}],
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
.bk-shell-root { display: flex; height: 100vh; min-height: 100vh; background: var(--paper); }
.bk-shell-root.bk-narrow .bk-sidebar { display: none; }

/* Sidebar (drawer) — fondo negro para distinguirlo del panel principal */
.bk-sidebar {
  width: 260px; flex-shrink: 0;
  background: #0A0A0A;
  border-right: none;
  padding: 22px 14px;
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.bk-sidebar::-webkit-scrollbar { width: 0; }
@media (max-width: 880px) { .bk-sidebar { display: none; } }
.bk-sidebar__brand {
  padding: 6px 10px 22px;
  border-bottom: none;
  margin-bottom: 14px;
  display: flex; align-items: center;
}
.bk-sidebar__brand a { display: flex; align-items: center; gap: 8px; text-decoration: none; }
.bk-sidebar__brand img { height: 84px; width: auto; display: block; filter: brightness(0) invert(1); }
.bk-sb-section {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: 0.18em;
  text-transform: uppercase; color: rgba(247,245,238,0.4);
  padding: 16px 10px 8px; font-weight: 500;
}
.bk-sb-link {
  display: flex !important; align-items: center; gap: 10px;
  padding: 10px 12px;
  border-radius: var(--r);
  font-size: 14px; color: rgba(247,245,238,0.78) !important;
  cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
  font-weight: 500; letter-spacing: -0.005em;
  text-decoration: none !important;
  visibility: visible !important;
  opacity: 1 !important;
}
.bk-sidebar .bk-sb-link,
.bk-sidebar a.bk-sb-link {
  color: rgba(247,245,238,0.78) !important;
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  background: transparent;
}
.bk-sb-link:hover,
.bk-sidebar .bk-sb-link:hover,
.bk-sidebar a.bk-sb-link:hover { background: rgba(247,245,238,0.06) !important; color: var(--paper) !important; }
.bk-sb-link.is-active,
.bk-sidebar .bk-sb-link.is-active,
.bk-sidebar a.bk-sb-link.is-active { background: var(--paper) !important; color: var(--ink) !important; }
.bk-sb-link svg,
.bk-sidebar .bk-sb-link svg { flex-shrink: 0; opacity: .82; }
.bk-sb-foot {
  margin-top: auto;
  display: flex; align-items: center; gap: 10px;
  padding: 12px;
  border-top: 1px solid rgba(247,245,238,0.08);
}
.bk-sb-foot__avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--paper); color: var(--ink);
  display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 13px; letter-spacing: -0.02em;
}
.bk-sb-foot__name { font-size: 13px; font-weight: 500; line-height: 1.2; flex: 1; min-width: 0; color: var(--paper) !important; }
.bk-sb-foot__name .role { color: rgba(247,245,238,0.5) !important; font-size: 11px; font-weight: 400; }
.bk-sb-foot__logout {
  background: transparent; border: none; cursor: pointer;
  color: rgba(247,245,238,0.5) !important; padding: 6px;
}
.bk-sb-foot__logout:hover { color: var(--paper) !important; }

/* Content area */
.bk-content { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }

/* Mobile head */
.bk-mobile-head {
  display: none;
  padding: 14px 16px 12px;
  background: var(--paper);
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
  background: var(--paper);
  flex-shrink: 0;
  position: relative;
}
@media (max-width: 880px) { .bk-topbar { display: none; } }

/* Quote rotativo (ocupa el espacio donde antes iban título + búsqueda) */
.bk-topbar__quote {
  flex: 1;
  min-width: 0;
  font-family: var(--font-display, 'Inter'), -apple-system, BlinkMacSystemFont, sans-serif;
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

/* Bottom nav (mobile) */
.bk-bnav {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0;
  background: var(--bone);
  border-top: none;
  padding: 6px 8px calc(6px + env(safe-area-inset-bottom, 0px));
  z-index: 60;
  justify-content: space-around;
}
@media (max-width: 880px) { .bk-bnav { display: flex; } }
.bk-bnav__item {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 8px 4px;
  font-size: 10px;
  color: var(--mute);
  text-decoration: none;
  font-weight: 500;
  cursor: pointer;
  border: none; background: transparent;
  font-family: inherit;
  transition: color var(--dur) var(--ease);
}
.bk-bnav__item.is-active { color: var(--ink); }
.bk-bnav__item svg { opacity: .9; }
.bk-bnav__item.is-active svg { opacity: 1; }

/* Broquer FAB (desktop only — mobile uses bottom-nav center) */
.bk-shaark-fab {
  position: fixed; right: 28px; bottom: 28px; z-index: 80;
  width: 60px; height: 60px; border-radius: 50%;
  background: var(--bone); color: var(--ink);
  border: 1px solid var(--line);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 14px 32px rgba(31,28,22,.18), 0 4px 10px rgba(31,28,22,.08);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
  padding: 0; overflow: hidden;
}
.bk-shaark-fab:hover { transform: translateY(-2px); box-shadow: 0 18px 36px rgba(31,28,22,.22), 0 6px 12px rgba(31,28,22,.12); }
.bk-shaark-fab img { width: 70%; height: 70%; object-fit: contain; }
.bk-shaark-fab__pulse {
  position: absolute; inset: -4px; border-radius: 50%;
  border: 1.5px solid var(--ink); opacity: 0;
  animation: bkPulse 2.4s ease-out infinite;
  pointer-events: none;
}
@keyframes bkPulse { 0% { transform: scale(.95); opacity: .35; } 100% { transform: scale(1.25); opacity: 0; } }
.bk-wake-dot {
  position: absolute; top: 6px; right: 6px;
  width: 10px; height: 10px; background: #4ade80;
  border-radius: 50%; border: 2px solid var(--bone);
  display: none;
}
.bk-shaark-fab.wake-on .bk-wake-dot { display: block; }
@media (max-width: 880px) { .bk-shaark-fab { display: none; } }

/* Shaark popup */
.bk-shaark-popup {
  display: none;
  position: fixed; right: 28px; bottom: 100px; z-index: 90;
  width: min(420px, calc(100vw - 32px));
  max-height: min(600px, calc(100dvh - 140px));
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: 0 24px 64px rgba(31,28,22,.18), 0 8px 16px rgba(31,28,22,.08);
  flex-direction: column; overflow: hidden;
  animation: bkShkIn .26s cubic-bezier(.16,1,.3,1);
}
.bk-shaark-popup.is-open { display: flex; }
@keyframes bkShkIn { from { opacity: 0; transform: translateY(12px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@media (max-width: 880px) {
  .bk-shaark-popup { right: 12px; left: 12px; bottom: 84px; width: auto; }
}
.bk-shk-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--line);
}
.bk-shk-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--bone); border: 1px solid var(--line);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  overflow: hidden;
}
.bk-shk-avatar img { width: 70%; height: 70%; object-fit: contain; }
.bk-shk-name { font-family: var(--font-display); font-size: 14px; font-weight: 600; letter-spacing: -0.01em; color: var(--ink); }
.bk-shk-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--mute); font-family: var(--font-mono); letter-spacing: .04em; }
.bk-shk-status::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--forest); }
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
  width: 28px; height: 28px;
  background: transparent; border: none; cursor: pointer;
  border-radius: 8px; color: var(--mute);
  display: flex; align-items: center; justify-content: center;
}
.bk-shk-close:hover { background: var(--paper-2); color: var(--ink); }
.bk-shk-msgs { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.bk-shk-msgs::-webkit-scrollbar { width: 4px; } .bk-shk-msgs::-webkit-scrollbar-thumb { background: var(--line-2); border-radius: 4px; }
.bk-shk-bubble { max-width: 88%; padding: 10px 13px; border-radius: 14px; font-size: 13.5px; line-height: 1.5; letter-spacing: -0.005em; white-space: pre-wrap; }
.bk-shk-bubble.bot { background: var(--bone); color: var(--ink); border: 1px solid var(--line); border-bottom-left-radius: 5px; align-self: flex-start; }
.bk-shk-bubble.user { background: var(--ink); color: var(--paper); border-bottom-right-radius: 5px; align-self: flex-end; }
.bk-shk-bubble.toast { background: transparent; border: none; color: var(--mute); font-size: 12px; padding: 4px 10px; align-self: center; }
.bk-shk-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 10px; }
.bk-shk-chip {
  background: var(--paper); border: 1px solid var(--line-2);
  border-radius: var(--r-pill); padding: 7px 12px;
  font-size: 12px; color: var(--ink-2); cursor: pointer; font-weight: 500;
  font-family: inherit;
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.bk-shk-chip:hover { background: var(--paper-2); border-color: var(--ink); }
.bk-shk-input-row { display: flex; gap: 8px; padding: 12px 14px; border-top: 1px solid var(--line); align-items: center; }
.bk-shk-input { flex: 1; min-width: 0; background: var(--bone); border: 1px solid var(--line-2); border-radius: var(--r-pill); padding: 10px 14px; font-size: 14px; outline: none; font-family: inherit; color: var(--ink); }
.bk-shk-input:focus { border-color: var(--ink); background: var(--paper); }
.bk-shk-mic, .bk-shk-send {
  width: 40px; height: 40px; border-radius: 50%;
  border: none; cursor: pointer; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.bk-shk-mic { background: var(--paper-2); color: var(--ink-2); border: 1px solid var(--line); }
.bk-shk-mic:hover { background: var(--ink); color: var(--paper); }
.bk-shk-mic.listening { background: var(--danger); color: white; border-color: var(--danger); animation: bkMicPulse 1.2s ease-in-out infinite; }
@keyframes bkMicPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(184,75,63,.5); } 50% { box-shadow: 0 0 0 8px rgba(184,75,63,0); } }
.bk-shk-send { background: var(--ink); color: var(--paper); }
.bk-shk-send:hover { opacity: .9; }
@media (hover: hover) and (pointer: fine) { .bk-shk-mic { display: none; } }

/* ── Profile Drawer ─────────────────────────────────────────── */
.bk-profile-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(10,10,10,0.28);
  opacity: 0; visibility: hidden; pointer-events: none;
  transition: opacity .18s ease, visibility .18s ease;
}
.bk-profile-overlay.is-open { opacity: 1; visibility: visible; pointer-events: auto; }
.bk-profile-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 201;
  width: 360px; max-width: 100vw;
  background: var(--paper); border-left: 1px solid var(--line);
  display: flex; flex-direction: column;
  transform: translate3d(100%,0,0);
  transition: transform .22s cubic-bezier(.16,1,.3,1);
  overflow: hidden;
  contain: layout paint style;
  will-change: transform;
}
.bk-profile-drawer.is-open { transform: translate3d(0,0,0); }
.bk-pd-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 20px 16px; border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.bk-pd-head h2 { font-family: var(--font-display); font-size: 16px; font-weight: 600; letter-spacing: -0.01em; color: var(--ink); }
.bk-pd-close {
  width: 30px; height: 30px; border-radius: 8px;
  background: none; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--mute);
}
.bk-pd-close:hover { background: var(--paper-2); color: var(--ink); }
.bk-pd-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 20px; }
.bk-pd-body::-webkit-scrollbar { width: 0; }
.bk-pd-avatar-row {
  display: flex; align-items: center; gap: 14px;
}
.bk-pd-avatar {
  width: 52px; height: 52px; border-radius: 50%;
  background: var(--ink); color: var(--paper);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 18px; letter-spacing: -0.02em;
  flex-shrink: 0;
}
.bk-pd-avatar-info { flex: 1; min-width: 0; }
.bk-pd-name { font-size: 15px; font-weight: 600; color: var(--ink); letter-spacing: -0.01em; }
.bk-pd-email { font-size: 12px; color: var(--mute); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bk-pd-role-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 8px; border-radius: var(--r-pill); margin-top: 4px;
  background: var(--forest-soft); color: var(--forest);
}
.bk-pd-role-badge.admin { background: rgba(184,75,63,0.1); color: var(--danger); }
.bk-pd-section-label {
  font-family: var(--font-mono); font-size: 9px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.14em; color: var(--mute-2);
  margin-bottom: 8px;
}
.bk-pd-card {
  background: var(--bone); border: 1px solid var(--line);
  border-radius: var(--r); padding: 16px;
}
.bk-pd-field { margin-bottom: 12px; }
.bk-pd-field:last-child { margin-bottom: 0; }
.bk-pd-field label { display: block; font-size: 11px; font-weight: 600; color: var(--mute); margin-bottom: 5px; letter-spacing: 0.02em; }
.bk-pd-field input {
  width: 100%; background: var(--paper-2); border: 1px solid var(--line-2);
  border-radius: var(--r-sm); padding: 9px 12px;
  font-size: 13px; font-family: inherit; color: var(--ink); outline: none;
}
.bk-pd-field input:focus { border-color: var(--ink); background: var(--bone); }
.bk-pd-field input[readonly] { color: var(--mute); cursor: default; }
.bk-pd-btn {
  width: 100%; padding: 10px; border-radius: var(--r-sm);
  font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; border: none; transition: opacity .2s;
  display: flex; align-items: center; justify-content: center; gap: 7px;
}
.bk-pd-btn:hover { opacity: .88; }
.bk-pd-btn-primary { background: var(--ink); color: var(--paper); }
.bk-pd-btn-outline { background: none; border: 1px solid var(--line-2); color: var(--ink-2); margin-top: 8px; }
.bk-pd-btn-danger  { background: none; border: 1px solid rgba(184,75,63,.3); color: var(--danger); margin-top: 8px; }
.bk-pd-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--mute); margin-top: 8px;
}
.bk-pd-status .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--mute-3); flex-shrink: 0; }
.bk-pd-status .dot.ok { background: var(--success); }
.bk-pd-status .dot.warn { background: var(--warn); }
.bk-pd-toast {
  padding: 8px 12px; border-radius: var(--r-sm); font-size: 12px; font-weight: 500;
  margin-top: 8px; display: none;
}
.bk-pd-toast.ok   { background: var(--success-soft); color: var(--success); display: block; }
.bk-pd-toast.err  { background: var(--danger-soft);  color: var(--danger);  display: block; }
.bk-pd-foot {
  padding: 16px 20px; border-top: 1px solid var(--line); flex-shrink: 0;
}
/* Accordion menu */
.bk-pd-menu { display: flex; flex-direction: column; gap: 0; }
.bk-pd-menu-item { border-bottom: 1px solid var(--line); }
.bk-pd-menu-item:first-child { border-top: 1px solid var(--line); }
.bk-pd-menu-trigger {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0; background: none; border: none; cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 600; color: var(--ink);
  text-align: left;
}
.bk-pd-menu-trigger:hover { color: var(--navy, #1a2e6e); }
.bk-pd-menu-trigger-left { display: flex; align-items: center; gap: 10px; }
.bk-pd-menu-trigger-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--mute-3); flex-shrink: 0; }
.bk-pd-menu-trigger-dot.ok { background: var(--success); }
.bk-pd-menu-trigger-dot.warn { background: var(--warn); }
.bk-pd-menu-chevron {
  width: 16px; height: 16px; color: var(--mute); flex-shrink: 0;
  transition: transform .22s cubic-bezier(.16,1,.3,1);
}
.bk-pd-menu-item.is-open .bk-pd-menu-chevron { transform: rotate(180deg); }
.bk-pd-menu-panel {
  overflow: hidden; display: none;
}
.bk-pd-menu-item.is-open .bk-pd-menu-panel { display: block; }
.bk-pd-menu-panel-inner { padding-bottom: 16px; }
/* Suscripcion */
.bk-pd-sub-badge {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 10px; border-radius: var(--r-pill);
  background: var(--forest-soft); color: var(--forest);
}
.bk-pd-sub-badge.inactive { background: var(--bone); color: var(--mute); }
.bk-pd-sub-info { font-size: 12px; color: var(--mute); margin: 8px 0 14px; line-height: 1.5; }

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

  async function authInit() {
    let tok = getToken();

    // Si no hay token, intentar renovar con refresh token antes de redirigir
    if (!tok) {
      tok = await tryRefreshToken();
      if (!tok) { location.href = 'login.html'; return null; }
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
          if (!tok) { location.href = 'login.html'; return null; }
          const r2 = await fetch(SB_URL + '/auth/v1/user', { headers: { apikey: SB_KEY, Authorization: 'Bearer ' + tok } });
          user = await r2.json();
        } else {
          user = await r.json();
        }
        if (user?.id) sessionStorage.setItem('sb_user', JSON.stringify(user));
      } catch (e) {}
    }

    if (!user?.id) { location.href = 'login.html'; return null; }
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
  function buildBnavItem(m, active) {
    return `<a href="${m.href}" class="bk-bnav__item${m.key === active ? ' is-active' : ''}">${svg(m.icon, 22)} <span>${m.label.split(' ')[0]}</span></a>`;
  }

  function injectShell(profile) {
    // Wrap existing body content into .bk-page
    const pageWrap = document.createElement('div');
    pageWrap.className = 'bk-page';
    pageWrap.id = 'bk-page';
    while (document.body.firstChild) pageWrap.appendChild(document.body.firstChild);

    const main = MODS.filter(m => m.group === 'main' && (!m.adminOnly || profile?.isAdmin));

    const ini = initials(profile?.fullName || '');
    const shell = document.createElement('div');
    shell.className = 'bk-shell-root';
    shell.innerHTML = `
      <aside class="bk-sidebar" id="bk-sidebar">
        <div class="bk-sidebar__brand">
          <a href="index.html" aria-label="Ir al inicio Broquer">
            <img src="logo-broquer.png" alt="Broquer"/>
          </a>
        </div>
        ${main.map(m => buildSidebarLink(m, activeKey)).join('')}
        <div class="bk-sb-foot">
          <div class="bk-sb-foot__avatar" id="bk-sb-avatar" onclick="openProfileDrawer()" style="cursor:pointer" title="Mi perfil">${ini}</div>
          <div class="bk-sb-foot__name">
            <div id="bk-sb-name">${profile?.fullName || ''}</div>
            <div class="role">${profile?.isAdmin ? 'Admin' : 'Agente'}</div>
          </div>
          <button class="bk-sb-foot__logout" onclick="doLogout()" title="Cerrar sesión" aria-label="Cerrar sesión">${svg('arrowOut', 16)}</button>
        </div>
      </aside>

      <main class="bk-content">
        <div class="bk-mobile-head">
          <a href="index.html" aria-label="Ir al inicio Broquer"><img src="logo-broquer.png" alt="Broquer"/></a>
          <div class="bk-mobile-head__avatar" id="bk-mob-avatar" onclick="openProfileDrawer()" style="cursor:pointer" title="Mi perfil">${ini}</div>
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

    // ── Diagnóstico de cascada CSS del sidebar ──
    // Si algún módulo override el color de los links del drawer, lo detectamos
    // y forzamos un re-anclaje del style del shell al final del head.
    setTimeout(() => {
      try {
        const link = document.querySelector('.bk-sidebar .bk-sb-link:not(.is-active)');
        if (!link) return;
        const cs = getComputedStyle(link);
        const c = cs.color;
        // El color esperado es rgba(247,245,238,0.78) ≈ rgb(247, 245, 238) con alpha
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
              el.style.setProperty('color', 'rgba(247,245,238,0.78)', 'important');
            });
          }
        }
      } catch(e){}
    }, 300);

    // Place page wrap inside content
    shell.querySelector('.bk-content').appendChild(pageWrap);

    // Bottom nav
    // PWA bottom nav: Inmuebles · Contratos · [Broquer] · Estimación · ISR
    const bnavFixed = [
      MODS.find(m => m.key === 'props'),
      MODS.find(m => m.key === 'contratos'),
    ].filter(Boolean);
    const bnavFixed2 = [
      MODS.find(m => m.key === 'avm'),
      MODS.find(m => m.key === 'isr'),
    ].filter(Boolean);

    function buildBnavItemLabel(m, active, overrideLabel) {
      const label = overrideLabel || m.label.split(' ')[0];
      return `<a href="${m.href}" class="bk-bnav__item${m.key === active ? ' is-active' : ''}">${svg(m.icon, 22)} <span>${label}</span></a>`;
    }

    const bnav = document.createElement('nav');
    bnav.className = 'bk-bnav';
    bnav.innerHTML =
      bnavFixed.map(m => buildBnavItemLabel(m, activeKey)).join('') +
      `<button class="bk-bnav__item bk-bnav__broquer" id="bk-bnav-shaark" type="button" aria-label="Abrir Broquer">
         <img src="icon-192.png" alt="" style="width:26px;height:26px;object-fit:contain;"/>
         <span>Broquer</span>
       </button>` +
      buildBnavItemLabel(bnavFixed2[0], activeKey, 'Estimación') +
      buildBnavItemLabel(bnavFixed2[1], activeKey, 'ISR');
    document.body.appendChild(bnav);

    // Shaark FAB + popup
    const fab = document.createElement('button');
    fab.className = 'bk-shaark-fab';
    fab.id = 'bk-shaark-fab';
    fab.setAttribute('aria-label', 'Abrir Broquer');
    fab.innerHTML = `<span class="bk-shaark-fab__pulse"></span><span class="bk-wake-dot" id="bk-wake-dot"></span><img src="isotipo-broquer.png" alt="Broquer"/>`;
    fab.addEventListener('click', () => toggleShaarkPopup());
    document.body.appendChild(fab);

    document.getElementById('bk-bnav-shaark').addEventListener('click', () => toggleShaarkPopup());

    const pop = document.createElement('div');
    pop.className = 'bk-shaark-popup';
    pop.id = 'bk-shaark-popup';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Broquer — asistente');
    pop.innerHTML = `
      <div class="bk-shk-head">
        <div class="bk-shk-avatar"><img src="isotipo-broquer.png" alt=""/></div>
        <div style="flex:1;min-width:0">
          <div class="bk-shk-name">Broquer</div>
          <div class="bk-shk-status">En línea</div>
        </div>
        <button class="bk-shk-close" type="button" aria-label="Cerrar">${svg('close', 14, 2)}</button>
      </div>
      <div class="bk-shk-msgs" id="bk-shk-msgs">
        <div class="bk-shk-bubble bot" id="bk-welcome-msg">¡Hola! Soy Broquer, tu asistente inteligente. ¿Qué puedo hacer por ti?</div>
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
     Shaark — popup, fetch, voice, wake word
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
    addBubble(text, 'user');
    shaarkMsgs.push({ role: 'user', content: text });
    shaarkFabFetch(text);
  }
  window.shaarkChip = shaarkChip;

  async function shaarkFabFetch(text) {
    const wrap = document.getElementById('bk-shk-msgs');
    const typing = addBubble('…', 'bot');
    try {
      const r = await fetch(API_BASE + '/chat-claude', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_tokens: 1200, messages: shaarkMsgs, context: getCurrentContext() }),
      });
      const data = await r.json();
      if (!r.ok) {
        typing.textContent = (data.detail || 'Error del servidor.');
        return;
      }
      const reply = data.choices?.[0]?.message?.content;
      if (!reply) { typing.textContent = 'Respuesta vacía. Intenta de nuevo.'; return; }
      // Parse [ACCION]…[/ACCION] payloads
      const accionRe = /\[ACCION\](.*?)\[\/ACCION\]/gs;
      let m;
      while ((m = accionRe.exec(reply)) !== null) {
        try {
          const ac = JSON.parse(m[1].trim());
          handleAccion(ac);
        } catch (e) { /* malformed payload */ }
      }
      const clean = reply.replace(/\[ACCION\].*?\[\/ACCION\]/gs, '').trim();
      shaarkMsgs.push({ role: 'assistant', content: clean });
      typing.textContent = clean;
      if (window._scwLastWasVoice) { speak(clean); window._scwLastWasVoice = false; }
    } catch (e) {
      typing.textContent = 'Sin conexión. Revisa tu internet.';
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
      case 'crear_ficha':        stash('ficha', ac);        location.href = 'ficha.html'; break;
      case 'crear_ficha_manual': stash('ficha_manual', ac); location.href = 'ficha-manual.html'; break;
      case 'buscar_propiedad':   stash('buscar_props', ac); location.href = 'propiedades.html'; break;
      case 'confirmar_campana':  stash('fb_ads', ac);       location.href = 'facebook-ads.html'; break;

      // ── ACCIONES DIRECTAS — ejecutan en la ventana del asistente ──
      case 'agregar_contacto':         agregarContactoDirecto(ac); break;
      case 'generar_contrato_directo': generarContratoDirecto(ac); break;
      case 'calcular_isr_directo':     calcularISRDirecto(ac); break;
      case 'estimar_valor_directo':    estimarValorDirecto(ac); break;
    }
  }

  /* ── Acciones directas: ejecutan API y muestran resultado en chat ── */
  function _addAssistantBubble(html) {
    const wrap = document.getElementById('bk-shk-msgs');
    if (!wrap) return;
    const b = document.createElement('div');
    b.className = 'bk-shk-bubble bot';
    b.innerHTML = html;
    wrap.appendChild(b);
    wrap.scrollTop = wrap.scrollHeight;
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

  async function generarContratoDirecto(ac) {
    try {
      const API = window.API_BASE || 'https://api.broquer.app';
      const tipo = ac.subtipo === 'promesa' ? 'promesa' : 'arrendamiento';
      _addAssistantBubble(`Generando contrato de ${tipo === 'promesa' ? 'promesa de compraventa' : 'arrendamiento'}…`);
      const r = await fetch(API + '/contrato', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo, datos: ac.datos || ac, clausulas_especiales: ac.clausulas_especiales || [] })
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        _addAssistantBubble('No pude generar el contrato: ' + (j.detail || ('error ' + r.status)));
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = tipo === 'promesa' ? 'Promesa_Compraventa.docx' : 'Contrato_Arrendamiento.docx';
      document.body.appendChild(a); a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 800);
      _addAssistantBubble(`✓ Contrato listo. Se descargó en tu dispositivo.`);
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
      const r1 = await fetch(API + '/api/avm-websearch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = tokData.filename || ('Estimacion_Valor_' + (body.colonia || 'inmueble') + '.pdf');
      a.rel = 'noopener';
      document.body.appendChild(a); a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);
      bubble.innerHTML += '<br>✓ <strong>PDF descargado.</strong>';
    } catch (e) {
      bubble.textContent = 'No pude completar la estimación: ' + (e.message || e);
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
    t = t.replace(/\bbroker\b/gi, 'Broquer');
    t = t.replace(/\bbroquer\b/gi, 'Broquer');
    t = t.replace(/\bshaark\b/gi, 'Broquer');
    t = t.replace(/\bshark\b/gi, 'Broquer');
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

  function toggleScwVoice() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      showShaarkToast('Tu navegador no soporta voz. Usa Chrome o Safari.'); return;
    }
    if (scwListening) { stopScwVoice(); return; }
    startScwVoice();
  }
  window.toggleScwVoice = toggleScwVoice;

  async function startScwVoice() {
    if (scwListening) return;
    _wakePaused = true; stopWakeWordListener();
    const ok = await ensureMicPermission();
    if (!ok) { _wakePaused = false; _resumeWake(); showShaarkToast('Sin permiso de micrófono'); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    try { scwRec = new SR(); } catch (e) { _wakePaused = false; _resumeWake(); return; }
    scwRec.lang = 'es-MX'; scwRec.continuous = false; scwRec.interimResults = true;
    const btn = document.getElementById('bk-shk-mic');
    const inp = document.getElementById('bk-shk-input');
    scwListening = true;
    btn?.classList.add('listening');
    if (inp) { inp.placeholder = 'Escuchando…'; inp.value = ''; }
    scwTimer = setTimeout(() => stopScwVoice(), 12000);
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
        showShaarkToast('Sin permiso de micrófono. Activa el micrófono en la configuración del navegador.');
      }
      stopScwVoice(); _wakePaused = false; _resumeWake();
    };
    scwRec.onend = () => {
      clearTimeout(scwTimer);
      const txt = inp ? inp.value.trim() : '';
      const wasListening = scwListening;
      stopScwVoice();
      if (wasListening && txt) {
        window._scwLastWasVoice = true;
        setTimeout(() => shaarkFabSend(), 100);
      }
      _wakePaused = false; _resumeWake();
    };
    try { scwRec.start(); } catch (e) { stopScwVoice(); _wakePaused = false; _resumeWake(); }
  }

  function stopScwVoice() {
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
  const WAKE = ['oye broquer','oye broker','broquer','broker','oye shaark','oye shark','shaark','oie shaark','hey shaark','hey shark'];

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
      btn.title = _wakeEnabled ? 'Siempre escuchando: ON — toca para desactivar' : 'Activar "Oye Broquer"';
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
        panel.style.cssText = "position:fixed;top:64px;right:16px;z-index:300;width:min(340px, calc(100vw - 32px));background:var(--paper);border:1px solid var(--line-2);border-radius:16px;box-shadow:0 12px 40px rgba(31,28,22,.14),0 3px 8px rgba(31,28,22,.08);animation:bkNotifIn .18s var(--ease) both;";
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
                <span class="bk-pd-menu-trigger-dot" id="pdot-datos"></span>
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

          <!-- EasyBroker -->
          <div class="bk-pd-menu-item" id="pdsec-eb">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('eb')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-trigger-dot" id="pdot-eb"></span>
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
                <span class="bk-pd-menu-trigger-dot" id="pdot-fb"></span>
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
                <span class="bk-pd-menu-trigger-dot" id="pdot-sub"></span>
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
                  <div class="bk-pd-toast" id="pd-toast-sub"></div>
                </div>
              </div>
            </div>
          </div>`}

          <!-- Legal -->
          <div class="bk-pd-menu-item" id="pdsec-legal">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('legal')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-trigger-dot" id="pdot-legal"></span>
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
                <span class="bk-pd-menu-trigger-dot" style="background:var(--danger)"></span>
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

          <!-- Admin (solo admin) -->
          <div class="bk-pd-menu-item" id="pdsec-admin" style="display:none">
            <button class="bk-pd-menu-trigger" onclick="togglePdSection('admin')">
              <span class="bk-pd-menu-trigger-left">
                <span class="bk-pd-menu-trigger-dot ok"></span>
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
      // Actualizar nombre en sidebar
      document.getElementById('bk-sb-name').textContent = nombre;
      document.getElementById('pd-name').textContent = nombre;
      const ini2 = initials(nombre);
      document.getElementById('bk-sb-avatar').textContent = ini2;
      document.getElementById('bk-mob-avatar').textContent = ini2;
      document.getElementById('pd-avatar').textContent = ini2;
    } catch(e) {
      toast.textContent = 'Error al guardar. Intenta de nuevo.';
      toast.className = 'bk-pd-toast err';
    }
    setTimeout(() => { toast.className = 'bk-pd-toast'; }, 3500);
  }
  window.saveProfileData = saveProfileData;

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
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(10,10,10,.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
        const modal = document.createElement('div');
        modal.style.cssText = 'background:var(--bone);border:1px solid var(--line-2);border-radius:16px;padding:28px 24px;max-width:360px;width:100%;box-shadow:0 8px 32px rgba(10,10,10,.18)';
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
    if (msg) { msg.style.color = 'var(--mute)'; msg.textContent = 'Activando tu cuenta…'; }
    const delay = ms => new Promise(r => setTimeout(r, ms));
    for (let i = 0; i < 12; i++) {
      try {
        const r = await fetch(API_BASE + '/subscription/status', { headers: { Authorization: 'Bearer ' + getToken() } });
        if (r.ok) { const d = await r.json().catch(() => ({})); if (d.active) { location.reload(); return; } }
      } catch (_) {}
      await delay(2500);
    }
    if (msg) { msg.style.color = 'var(--ink)'; msg.textContent = 'Tu pago se procesó. Dale unos segundos y recarga la app.'; }
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

  function renderSubscriptionGate(message) {
    if (IS_IOS_NATIVE) {
      // App nativa iOS: compra dentro de la app vía App Store (RevenueCat).
      document.body.innerHTML = `
        <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--paper);padding:24px;font-family:var(--font-sans);">
          <div style="width:100%;max-width:440px;background:var(--bone);border:1px solid var(--line);border-radius:24px;padding:30px;box-shadow:0 10px 40px rgba(10,10,10,.08);text-align:center;">
            <img src="isotipo-black.png" alt="Broquer" style="width:58px;height:58px;object-fit:contain;margin-bottom:18px;"/>
            <h1 style="font-family:var(--font-display);font-size:30px;line-height:1.05;margin:0 0 10px;color:var(--ink);letter-spacing:-.03em;">Activa Broquer Max</h1>
            <p style="color:var(--mute);font-size:13px;line-height:1.5;margin:0 0 20px;">Suscríbete para usar todas tus herramientas. Broquer Max es una suscripción mensual: el pago se cobra a tu cuenta de Apple al confirmar y se renueva automáticamente cada mes, salvo que la canceles desde Ajustes de iOS al menos 24 h antes del fin del periodo.</p>
            <button id="bk-iap-buy" onclick="rcBuy()" disabled style="width:100%;height:48px;border:none;border-radius:999px;background:var(--ink);color:var(--paper);font-weight:700;font-size:14px;cursor:pointer;">Cargando…</button>
            <button id="bk-iap-restore" onclick="rcRestore()" style="width:100%;height:42px;border:1px solid var(--line-2);border-radius:999px;background:transparent;color:var(--ink);font-weight:600;font-size:13px;cursor:pointer;margin-top:10px;">Restaurar compras</button>
            <button onclick="doLogout()" style="width:100%;height:40px;border:none;background:transparent;color:var(--mute);font-weight:500;font-size:13px;cursor:pointer;margin-top:4px;">Cerrar sesión</button>
            <div id="bk-gate-msg" style="margin-top:10px;font-size:12px;color:var(--danger);min-height:18px;">${message || ''}</div>
            <div style="margin-top:14px;font-size:11px;color:var(--mute);line-height:1.5;">Al continuar aceptas los <a href="legal.html" style="color:var(--mute);text-decoration:underline;">Términos de uso</a> y el <a href="legal.html" style="color:var(--mute);text-decoration:underline;">Aviso de Privacidad</a>.</div>
          </div>
        </div>`;
      rcRenderPrice();
      return;
    }
    document.body.innerHTML = `
      <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--paper);padding:24px;font-family:var(--font-sans);">
        <div style="width:100%;max-width:440px;background:var(--bone);border:1px solid var(--line);border-radius:24px;padding:30px;box-shadow:0 10px 40px rgba(10,10,10,.08);text-align:center;">
          <img src="isotipo-black.png" alt="Broquer" style="width:58px;height:58px;object-fit:contain;margin-bottom:18px;"/>
          <h1 style="font-family:var(--font-display);font-size:30px;line-height:1.05;margin:0 0 10px;color:var(--ink);letter-spacing:-.03em;">Actualmente no cuentas con un plan de suscripción</h1>
          <p style="color:var(--mute);font-size:14px;line-height:1.5;margin:0 0 22px;">Activa tu plan para ingresar a Broquer y usar tus herramientas inmobiliarias.</p>
          <button id="bk-gate-sub-btn" onclick="startSubscriptionCheckoutFromGate()" style="width:100%;height:48px;border:none;border-radius:999px;background:var(--ink);color:var(--paper);font-weight:700;font-size:14px;cursor:pointer;">Suscribirme ahora</button>
          <button onclick="doLogout()" style="width:100%;height:42px;border:1px solid var(--line-2);border-radius:999px;background:transparent;color:var(--ink);font-weight:600;font-size:13px;cursor:pointer;margin-top:10px;">Cerrar sesión</button>
          <div id="bk-gate-msg" style="margin-top:12px;font-size:12px;color:var(--danger);min-height:18px;">${message || ''}</div>
        </div>
      </div>`;
  }

  async function ensureSubscriptionOrGate(profile) {
    if (profile?.isAdmin || profile?.profile?.plan === 'admin' || profile?.profile?.rol === 'equipo' || profile?.profile?.plan === 'equipo') return true;

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

    if (authExpired) { location.href = 'login.html'; return false; }

    if (confirmedInactive) {
      renderSubscriptionGate(justPaid ? 'Tu pago fue recibido. Si esto tarda más de un minuto, recarga la página.' : '');
      return false;
    }

    // Nunca pudimos confirmar inactividad → fail-open. El backend ya valida la
    // suscripción en cada endpoint real, así que esto no abre acceso indebido.
    return true;
  }

  async function boot() {
    const profile = await authInit();
    if (!profile) return; // redirected to login
    if (!(await ensureSubscriptionOrGate(profile))) return;
    injectShell(profile);

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
      _welcomeMsg.textContent = `¡Hola, ${_firstName}! Soy Broquer, tu asistente inteligente. ¿En qué te ayudo?`;
    }

    window.dispatchEvent(new CustomEvent('brokr-shell-ready', { detail: { profile, activeKey } }));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
