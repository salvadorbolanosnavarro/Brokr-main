// Brokr Service Worker — auto-update on every deploy
const CACHE_VERSION = 'brokr-' + Date.now(); // changes on every deploy = always fresh
const OFFLINE_URLS = ['/index.html', '/login.html'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(OFFLINE_URLS))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network first — always try fresh, fallback to cache when offline
self.addEventListener('fetch', e => {
  if(e.request.method !== 'GET') return;
  const url = e.request.url;
  if(url.includes('railway.app') || url.includes('supabase.co') || url.includes('groq.com')) return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if(res.ok){
          const clone = res.clone();
          caches.open(CACHE_VERSION).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── PUSH NOTIFICATIONS ──
self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(data.title || 'Brokr', {
    body: data.body || 'Tu tarea está lista.',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [200, 100, 200],
    data: { url: data.url || '/' }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
      const w = cs.find(c => c.url.includes(self.location.origin));
      if(w){ w.focus(); w.navigate(url); } else clients.openWindow(url);
    })
  );
});
