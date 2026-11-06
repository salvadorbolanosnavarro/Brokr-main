"""Isolated frontend gateway for the real Broquer application.

Run: python scripts/serve_staging.py --port 8080
Requires distinct BROQUER_STAGING_API_URL, BROQUER_STAGING_SUPABASE_URL,
and BROQUER_STAGING_SUPABASE_KEY to enable authenticated operations.
No service-role key is accepted or sent to the browser.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import argparse
import json
import mimetypes
import os

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_API = 'https://api.broquer.app'
PRODUCTION_DB = 'https://urtgysmtnvoqaljuhntz.supabase.co'
PRODUCTION_KEY = 'sb_publishable_EVGLfmHVorBpQQWAh-vypA_hANNk_-i'
ALLOWED_EXTENSIONS = {'.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico', '.ttf', '.woff', '.woff2', '.gif', '.mp4', '.webmanifest'}

def settings():
    api = os.getenv('BROQUER_STAGING_API_URL', '').rstrip('/')
    db = os.getenv('BROQUER_STAGING_SUPABASE_URL', '').rstrip('/')
    key = os.getenv('BROQUER_STAGING_SUPABASE_KEY', '')
    for value in (api, db):
        if not value:
            continue
        u = urlsplit(value)
        if u.hostname in {'api.broquer.app', 'broquer.app', 'urtgysmtnvoqaljuhntz.supabase.co', 'app.navarroai.com.mx'}:
            raise ValueError('Use a separate staging API and Supabase project, never production.')
        if u.scheme not in {'https', 'http'} or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('Invalid staging service URL.')
        if u.scheme == 'http' and u.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('Remote staging services require HTTPS.')
    if key.startswith('sb_secret_') or key == PRODUCTION_KEY:
        raise ValueError('Use the publishable key of the staging project.')
    if key.count('.') == 2:
        import base64
        try:
            claims = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '==='))
        except Exception as exc:
            raise ValueError('Invalid Supabase publishable key.') from exc
        if claims.get('role') != 'anon':
            raise ValueError('Only an anonymous/public key may reach the browser.')
    return api, db, key

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # No URLs/query strings: auth callbacks can contain sensitive tokens.
        pass

    def reply(self, status, body, content_type='application/json', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; worker-src 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def dispatch(self):
        path = urlsplit(self.path).path
        api, db, key = self.server.staging_settings
        if path == '/__stage/status':
            return self.reply(200, json.dumps({'configured': bool(api and db and key), 'environment': 'staging'}).encode())
        for prefix, upstream in (('/__stage/api/', api), ('/__stage/supabase/', db)):
            if path.startswith(prefix):
                if not (api and db and key):
                    return self.reply(503, json.dumps({'error': 'staging_not_configured', 'message': 'Falta conectar el servidor y la base de pruebas. Tus datos de producción están aislados.'}).encode())
                if self.command not in {'GET', 'HEAD'} and self.headers.get('Origin') != self.server.public_origin:
                    return self.reply(403, b'{"error":"invalid_origin"}')
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > 32 * 1024 * 1024:
                    return self.reply(413, b'{"error":"payload_too_large"}')
                body = self.rfile.read(size) if size else None
                headers = {k:v for k,v in self.headers.items() if k.lower() in {'authorization', 'apikey', 'content-type', 'prefer', 'range', 'accept', 'x-brokr-module'}}
                if prefix.endswith('supabase/'):
                    headers['apikey'] = key
                headers['Origin'] = self.server.public_origin
                target = upstream + '/' + self.path[len(prefix):]
                try:
                    response = build_opener(NoRedirect()).open(Request(target, data=body, headers=headers, method=self.command), timeout=30)
                except HTTPError as exc:
                    response = exc
                except (URLError, TimeoutError):
                    return self.reply(502, b'{"error":"staging_unavailable"}')
                with response:
                    if 300 <= response.code < 400:
                        return self.reply(502, b'{"error":"upstream_redirect_rejected"}')
                    extra = {k:v for k,v in response.headers.items() if k.lower() in {'content-range', 'retry-after'}}
                    return self.reply(response.code, response.read(), response.headers.get('Content-Type', 'application/json'), extra)
        if self.command not in {'GET', 'HEAD'}:
            return self.reply(405, b'{"error":"method_not_allowed"}')
        from urllib.parse import unquote
        relative = unquote(path).lstrip('/') or 'index.html'
        file = (ROOT / relative).resolve()
        if not file.is_relative_to(ROOT) or any(p.startswith('.') for p in Path(relative).parts) or file.suffix not in ALLOWED_EXTENSIONS or not file.is_file() or relative.startswith(('ios-app/', 'tests/', 'scripts/')):
            return self.reply(404, b'{"error":"not_found"}')
        if file.name == 'sw.js':
            return self.reply(404, b'')
        data = file.read_bytes()
        if file.suffix in {'.html', '.js', '.json'}:
            content = data.decode('utf-8')
            content = content.replace(PRODUCTION_API, self.server.public_origin + '/__stage/api').replace(PRODUCTION_DB, self.server.public_origin + '/__stage/supabase').replace(PRODUCTION_KEY, key or 'staging-not-configured')
            data = content.encode('utf-8')
        return self.reply(200, data, mimetypes.guess_type(file.name)[0] or 'application/octet-stream')

    do_GET = do_HEAD = do_POST = do_PATCH = do_PUT = do_DELETE = dispatch

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--origin', help='Explicit frontend origin if behind a reverse proxy')
    args = parser.parse_args()
    config = settings()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.staging_settings = config
    server.public_origin = args.origin or f'http://{args.host}:{args.port}'
    print(f'Broquer staging: {server.public_origin}/login.html', flush=True)
    print('Backend configured.' if all(config) else 'Waiting for separate staging API and Supabase configuration.', flush=True)
    server.serve_forever()
