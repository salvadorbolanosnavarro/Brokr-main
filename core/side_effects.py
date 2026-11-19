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


def disabled() -> bool:
    return os.getenv('SIDE_EFFECTS_DISABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}


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
