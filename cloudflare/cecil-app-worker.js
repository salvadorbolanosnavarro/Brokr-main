/* cecilapp.co → Cecil.
 *
 * Cecil is published once, with the rest of the site, at broquer.app/cecil/
 * (GitHub Pages, main). This Worker serves that same build at the root of
 * Cecil's own domain, so every published correction appears on both at once.
 *
 *   cecilapp.co/              → broquer.app/cecil/index.html
 *   cecilapp.co/tareas.html   → broquer.app/cecil/tareas.html
 *   cecilapp.co/cecil/ui/x    → broquer.app/cecil/ui/x   (absolute asset paths in the build)
 *   cecilapp.co/ui/cecil-*.js → broquer.app/ui/cecil-*.js (pilot controller lives at the root)
 *   www.cecilapp.co/*         → 301 to cecilapp.co/*
 *
 * Static files only: no cookies, sessions or API calls pass through here
 * (the app talks to api.broquer.app and Supabase directly).
 */
const ORIGIN = 'https://broquer.app';
const CANONICAL = 'cecilapp.co';
const ROOT_FILES = new Set(['/ui/cecil-rollout.js', '/ui/cecil-error-probe.js']);

export function upstreamPath(pathname) {
  if (pathname === '/' || pathname === '') return '/cecil/index.html';
  if (pathname === '/cecil' || pathname.startsWith('/cecil/') || ROOT_FILES.has(pathname)) return pathname;
  return '/cecil' + pathname;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname !== CANONICAL) {
      url.hostname = CANONICAL;
      return Response.redirect(url.toString(), 301);
    }
    if (!['GET', 'HEAD'].includes(request.method)) {
      return new Response('Método no permitido', { status: 405, headers: { Allow: 'GET, HEAD' } });
    }
    const target = ORIGIN + upstreamPath(url.pathname) + url.search;
    const upstream = await fetch(target, {
      method: request.method,
      headers: { 'Accept': request.headers.get('Accept') || '*/*', 'Accept-Encoding': request.headers.get('Accept-Encoding') || '' },
      redirect: 'manual',
      cf: { cacheTtl: 60, cacheEverything: true },
    });
    const headers = new Headers(upstream.headers);
    // Redirects from the origin (e.g. /cecil → /cecil/) stay on Cecil's domain.
    const location = headers.get('Location');
    if (location) {
      const to = new URL(location, target);
      if (to.origin === ORIGIN) {
        const path = to.pathname.startsWith('/cecil/') ? to.pathname.slice('/cecil'.length) : to.pathname;
        headers.set('Location', 'https://' + CANONICAL + path + to.search + to.hash);
      }
    }
    headers.set('X-Robots-Tag', 'noindex, nofollow'); // private pilot
    headers.set('Strict-Transport-Security', 'max-age=31536000');
    headers.delete('Set-Cookie');
    return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers });
  },
};
