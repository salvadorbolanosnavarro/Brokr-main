// capacitor-bridge.js — puente nativo iOS para Broquer.
// No-op cuando se carga desde un navegador web normal.
// Solo se activa cuando window.Capacitor.isNativePlatform() === true (iOS app).
//
// NOTA (App Store review): en iOS NO se inyecta "Iniciar sesión con Apple"
// ni se muestran botones de OAuth de Google ni botones de pago/checkout.
// El login en iOS es exclusivamente correo + contraseña, y la suscripción
// se gestiona únicamente vía web (broquer.app). Esto se controla marcando
// <html class="is-ios-native"> lo antes posible para que el CSS y app-shell.js
// oculten esos elementos solo dentro del WebView nativo.
(function () {
  const isNative = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  if (!isNative) return;

  // ─── 0. Marca el contexto nativo iOS cuanto antes ───────────────────
  // El CSS (.is-ios-native ...) y app-shell.js dependen de esta clase/flag
  // para ocultar OAuth de Google y cualquier botón de pago dentro de la app.
  try {
    document.documentElement.classList.add('is-ios-native');
    window.__BROQUER_IOS_NATIVE__ = true;
  } catch (_) {}

  const SB_URL = 'https://urtgysmtnvoqaljuhntz.supabase.co';
  const SB_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i';

  // ─── 1. Desregistrar service worker (rompe caching en WebView) ───
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then(rs => rs.forEach(r => r.unregister()))
      .catch(() => {});
  }

  // ─── 2. Notificaciones push (APNs) ────────────────────────────────
  // El backend (push.py) manda el aviso cuando un prospecto escribe por
  // WhatsApp. Aquí: pedimos permiso, guardamos el token del iPhone en
  // usuarios.apns_token, y decidimos qué hacer cuando llega o la tocan.

  function usuarioActual() {
    try {
      return JSON.parse(localStorage.getItem('sb_user') || sessionStorage.getItem('sb_user') || 'null');
    } catch (_) { return null; }
  }

  // Guarda el token del dispositivo en la fila del agente.
  // OJO: el PATCH va filtrado por id. Sin filtro, PostgREST intentaría tocar
  // toda la tabla (RLS lo frena, pero es una llamada que no queremos hacer).
  function guardarToken(valor) {
    const tok = localStorage.getItem('sb_token') || sessionStorage.getItem('sb_token');
    const u = usuarioActual();
    if (!tok || !u || !u.id) return;
    // Si ya está guardado el mismo, no gastamos la llamada.
    if (localStorage.getItem('apns_token_guardado') === valor) return;

    fetch(SB_URL + '/rest/v1/usuarios?id=eq.' + encodeURIComponent(u.id), {
      method: 'PATCH',
      headers: {
        'apikey': SB_KEY,
        'Authorization': 'Bearer ' + tok,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
      },
      body: JSON.stringify({ apns_token: valor }),
    })
      .then(r => { if (r.ok) localStorage.setItem('apns_token_guardado', valor); })
      .catch(() => {});
  }

  let _listenersListos = false;

  async function registerPush() {
    try {
      const { PushNotifications } = window.Capacitor.Plugins;
      if (!PushNotifications) return;

      if (!_listenersListos) {
        _listenersListos = true;

        // Apple nos da el token del iPhone.
        PushNotifications.addListener('registration', t => guardarToken(t.value));
        PushNotifications.addListener('registrationError', e => console.error('[push] regError', e));

        // Llega un aviso con la app ABIERTA. iOS no lo muestra encima de la
        // app; lo aprovechamos para refrescar el globito y, si el agente ya
        // está en la bandeja, recargar la lista sin que tenga que hacer nada.
        PushNotifications.addListener('pushNotificationReceived', () => {
          try { window.dispatchEvent(new CustomEvent('brokr-chats-leidos')); } catch (_) {}
        });

        // El agente TOCÓ la notificación: lo llevamos al chat exacto.
        PushNotifications.addListener('pushNotificationActionPerformed', ev => {
          try {
            const d = (ev && ev.notification && ev.notification.data) || {};
            if (d.tipo === 'whatsapp' && d.conversation_id) {
              location.href = 'bandeja.html?c=' + encodeURIComponent(d.conversation_id);
            } else {
              location.href = 'bandeja.html';
            }
          } catch (_) { location.href = 'bandeja.html'; }
        });
      }

      // El permiso se pide una sola vez. Si el agente dijo que no, iOS ya no
      // vuelve a preguntar: tiene que ir a Ajustes > Broquer > Notificaciones.
      let perm = await PushNotifications.checkPermissions();
      if (perm.receive === 'prompt' || perm.receive === 'prompt-with-rationale') {
        perm = await PushNotifications.requestPermissions();
      }
      if (perm.receive !== 'granted') return;

      await PushNotifications.register();
    } catch (e) {
      console.error('[push] init', e);
    }
  }

  // ─── 3. Limpiar el globito del ícono al abrir la app ───────────────
  function limpiarBadgeSiCorresponde() {
    try {
      const { PushNotifications } = window.Capacitor.Plugins;
      if (PushNotifications && PushNotifications.removeAllDeliveredNotifications) {
        // Solo cuando el agente entra a la bandeja: si borramos los avisos
        // nada más por abrir la app, perdería los que no ha visto.
        const enBandeja = (location.pathname.split('/').pop() || '').indexOf('bandeja') === 0;
        if (enBandeja) PushNotifications.removeAllDeliveredNotifications();
      }
    } catch (_) {}
  }

  // ─── Lifecycle ────────────────────────────────────────────────────
  // Después de que el shell autentica y carga, registramos APNs.
  window.addEventListener('brokr-shell-ready', () => {
    registerPush();
    limpiarBadgeSiCorresponde();
  });

  // Al volver a la app desde segundo plano, revisamos mensajes nuevos.
  try {
    const { App } = window.Capacitor.Plugins;
    if (App) {
      App.addListener('appStateChange', ({ isActive }) => {
        if (!isActive) return;
        try { window.dispatchEvent(new CustomEvent('brokr-chats-leidos')); } catch (_) {}
        limpiarBadgeSiCorresponde();
      });
    }
  } catch (_) {}

  // Exponer para debug
  window.brokrCapacitor = { registerPush };
})();
