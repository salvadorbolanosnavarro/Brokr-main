"""Process-wide outbound kill switch, independent of configured credentials.

No fabricated provider IDs or success responses: abort the attempted operation,
log only provider/method, and report an explicit simulation at the API boundary.
Supabase, AI and market-data traffic are not simulated by this switch.
"""
from __future__ import annotations

import base64
from contextvars import ContextVar
import logging
import os
import smtplib

import httpx
from fastapi import HTTPException
from starlette.responses import JSONResponse

log = logging.getLogger('broquer.side_effects')
_events: ContextVar[list | None] = ContextVar('side_effect_events', default=None)
_installed = False
_DOMAINS = {
    'stripe': ('stripe.com',),
    'meta': ('facebook.com', 'facebook.net', 'fb.com', 'fbcdn.net', 'fbsbx.com', 'whatsapp.com', 'whatsapp.net'),
    'instagram': ('instagram.com', 'cdninstagram.com'),
    'resend': ('resend.com',),
    'apns': ('push.apple.com',),
    'easybroker': ('easybroker.com',),
}

# Text generation and market-data queries are allowed, including POST queries.
# This is not an exemption for payment, messaging or integration hosts above.
READ_QUERY_SERVICES = {
    'api.firecrawl.dev': ('firecrawl', {'POST': ('/v1/scrape', '/v2/scrape', '/v2/search')}),
    'serpapi.com': ('serpapi', {'GET': ('/search', '/search.json')}),
    'maps.googleapis.com': ('google_places', {'GET': ('/maps/api/place/', '/maps/api/geocode/')}),
    'www.googleapis.com': ('google_search', {'GET': ('/customsearch/v1',)}),
    'www.banxico.org.mx': ('banxico', {'GET': ('/SieAPIRest/service/v1/series/',)}),
    'api.groq.com': ('groq', {'POST': ('/openai/v1/chat/completions',)}),
    'api.anthropic.com': ('anthropic', {'POST': ('/v1/messages',)}),
    'generativelanguage.googleapis.com': ('gemini', {'POST': ('/v1beta/models/', '/v1/models/')}),
}


def read_query_allowed(request) -> bool:
    entry = READ_QUERY_SERVICES.get((request.url.host or '').lower().rstrip('.'))
    if not entry:
        return False
    path = request.url.path
    paths = entry[1].get(request.method, ())
    matches = any(path.startswith(p) if p.endswith('/') else path == p for p in paths)
    if entry[0] == 'gemini':
        matches = matches and path.endswith((':generateContent', ':streamGenerateContent'))
    return matches


def market_read_blocked(url: str) -> bool:
    """Omit forbidden portal candidates before any direct/indirect fetch.

    Omitting a source is not an attempted message/payment and must not poison
    the AVM's entire successful response with a simulated integration result.
    """
    return disabled() and provider_for(httpx.URL(url).host or '') is not None


def disabled() -> bool:
    value = os.getenv('SIDE_EFFECTS_DISABLED', '').strip().lower()
    if is_staging():
        # Fail closed: only an explicit false can opt staging out.
        return value != 'false'
    return value in {'1', 'true', 'yes', 'on'}


def is_staging() -> bool:
    return os.getenv('BROQUER_ENV', '').strip().lower() == 'staging'


def provider_for(host: str) -> str | None:
    host = host.lower().rstrip('.')
    for provider, domains in _DOMAINS.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return provider
    return None


def _record(provider, method, kind):
    event = {'provider': provider, 'method': method, 'kind': kind}
    events = _events.get()
    if events is not None:
        events.append(event)
    # Do not log URL/query, payload, credentials, recipients or device tokens.
    log.warning('outbound_blocked provider=%s method=%s kind=%s', provider, method, kind)


def require_staging_stripe_key(key: str | None = None):
    if not is_staging():
        return
    configured = os.getenv('STRIPE_SECRET_KEY', '')
    if not configured.startswith('sk_test_') or len(configured) <= len('sk_test_') or (
        key is not None and (not key.startswith('sk_test_') or len(key) <= len('sk_test_'))
    ):
        _record('stripe', 'CONFIG', 'stripe_configuration')
        raise HTTPException(status_code=503, detail={
            'code': 'STAGING_STRIPE_TEST_KEY_REQUIRED',
            'message': 'Stripe bloqueado en staging: STRIPE_SECRET_KEY debe ser una llave sk_test_ válida. No se contactó a Stripe.'
        })


class SideEffectBlocked(httpx.RequestError):
    pass


def _block(provider, method, request=None):
    _record(provider, method, 'simulation')
    raise SideEffectBlocked('SIDE_EFFECTS_DISABLED: operación externa simulada; no se contactó al proveedor.', request=request)


def _guard(request):
    provider = provider_for(request.url.host or '')
    if provider == 'stripe':
        auth = request.headers.get('authorization', '')
        key = ''
        if auth.lower().startswith('bearer '):
            key = auth[7:].strip()
        elif auth.lower().startswith('basic '):
            try:
                key = base64.b64decode(auth[6:], validate=True).decode().split(':', 1)[0]
            except (ValueError, UnicodeError):
                pass
        require_staging_stripe_key(key)
    if provider and disabled():
        _block(provider, request.method, request)
    read_service = READ_QUERY_SERVICES.get((request.url.host or '').lower().rstrip('.'))
    if read_service and disabled() and not read_query_allowed(request):
        _block(read_service[0], request.method, request)


def install_side_effects_safety():
    """Install once before importing routes/clients, even when the flag is off."""
    global _installed
    if _installed:
        return
    original_async = httpx.AsyncClient.send
    original_sync = httpx.Client.send
    original_connect = smtplib.SMTP.connect

    async def send_async(self, request, *args, **kwargs):
        _guard(request)
        if disabled():
            # A permitted host cannot redirect into a blocked integration.
            kwargs['follow_redirects'] = False
        return await original_async(self, request, *args, **kwargs)

    def send_sync(self, request, *args, **kwargs):
        _guard(request)
        if disabled():
            kwargs['follow_redirects'] = False
        return original_sync(self, request, *args, **kwargs)

    def connect(self, *args, **kwargs):
        if disabled():
            _block('smtp', 'CONNECT')
        return original_connect(self, *args, **kwargs)

    httpx.AsyncClient.send = send_async
    httpx.Client.send = send_sync
    smtplib.SMTP.connect = connect  # Also used by SMTP_SSL before TLS/login.
    _installed = True


class SideEffectsMiddleware:
    """Preserve explicit simulation even when a legacy route catches HTTP errors."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        events = []
        context = _events.set(events)
        replaced = False
        started = False

        async def replacement():
            nonlocal replaced
            replaced = True
            config_error = any(e['kind'] == 'stripe_configuration' for e in events)
            body = {'ok': False, 'simulated': not config_error, 'external_call_performed': False,
                    'code': 'STAGING_STRIPE_TEST_KEY_REQUIRED' if config_error else 'SIDE_EFFECTS_DISABLED',
                    'message': 'Stripe requiere una llave sk_test_ en staging.' if config_error else 'Simulación: no se enviaron mensajes, cobros ni solicitudes al proveedor bloqueado.',
                    'blocked_operations': events}
            await JSONResponse(body, status_code=503 if config_error else 409,
                               headers={'Cache-Control': 'no-store', 'X-Broquer-Simulated': 'false' if config_error else 'true'})(scope, receive, send)

        async def guarded_send(message):
            nonlocal started
            if replaced:
                return
            if message['type'] == 'http.response.start':
                if events:
                    await replacement()
                    return
                started = True
            await send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except Exception:
            if events and not started:
                if not replaced:
                    await replacement()
            else:
                raise
        finally:
            _events.reset(context)
