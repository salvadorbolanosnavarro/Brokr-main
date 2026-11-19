"""Transport spies prove that disabled integrations never reach the network."""
import asyncio
from contextlib import contextmanager
import os
import smtplib
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core import side_effects as safety
from core import staging_safety


@contextmanager
def installed(env):
    with patch.dict(os.environ, env, clear=True), patch.object(safety, '_installed', False), \
         patch.object(httpx.AsyncClient, 'send', httpx.AsyncClient.send), \
         patch.object(httpx.Client, 'send', httpx.Client.send), \
         patch.object(smtplib.SMTP, 'connect', smtplib.SMTP.connect):
        safety.install_side_effects_safety()
        yield


class SideEffectsTests(unittest.TestCase):
    def test_sync_and_async_all_methods_block_even_with_real_keys(self):
        hosts=['api.stripe.com','graph.facebook.com','graph.instagram.com','api.resend.com',
               'api.push.apple.com','api.sandbox.push.apple.com','api.easybroker.com',
               'graph.whatsapp.com','GRAPH.FACEBOOK.COM.']
        calls=[]
        def transport(r):
            calls.append(str(r.url));return httpx.Response(200,json={})
        env={'SIDE_EFFECTS_DISABLED':'true','STRIPE_SECRET_KEY':'sk_live_secret',
             'WHATSAPP_TOKEN':'real','RESEND_API_KEY':'real','EB_API_KEY':'real'}
        with installed(env):
            for host in hosts:
                for method in ['GET','POST','PUT','PATCH','DELETE']:
                    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
                        with self.assertRaises(safety.SideEffectBlocked):c.request(method,'https://'+host+'/private?token=secret')
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:
                    for host in hosts:
                        with self.assertRaises(safety.SideEffectBlocked):await c.post('https://'+host+'/private')
            asyncio.run(run())
        self.assertEqual(calls,[])

    def test_no_credentials_in_log_and_no_false_host_match(self):
        with installed({'SIDE_EFFECTS_DISABLED':'true'}),self.assertLogs('broquer.side_effects',level='WARNING') as logs:
            with httpx.Client() as c:
                with self.assertRaises(safety.SideEffectBlocked):c.post('https://graph.facebook.com/phone-123/messages?access_token=SECRET',json={'to':'5551234567','text':'PRIVATE'},headers={'Authorization':'Bearer HIDDEN'})
        text=' '.join(logs.output)
        self.assertIn('provider=meta',text)
        for sensitive in ['SECRET','HIDDEN','5551234567','PRIVATE','phone-123']:self.assertNotIn(sensitive,text)
        self.assertIsNone(safety.provider_for('api.stripe.com.example.org'))

    def test_smtp_and_ssl_block_before_socket_connection(self):
        with installed({'SIDE_EFFECTS_DISABLED':'true'}),patch.object(smtplib.SMTP,'_get_socket') as plain,patch.object(smtplib.SMTP_SSL,'_get_socket') as tls:
            for cls in [smtplib.SMTP,smtplib.SMTP_SSL]:
                with self.assertRaises(safety.SideEffectBlocked):cls('smtp.example.test',587)
            plain.assert_not_called();tls.assert_not_called()

    def test_database_and_ai_still_work_and_redirects_cannot_bypass(self):
        seen=[]
        def transport(r):
            seen.append(r.url.host)
            if r.url.host=='allowed.example':return httpx.Response(302,headers={'location':'https://api.stripe.com/v1/customers'})
            return httpx.Response(200,json={'ok':True})
        with installed({'SIDE_EFFECTS_DISABLED':'true'}),httpx.Client(transport=httpx.MockTransport(transport),follow_redirects=True) as c:
            self.assertEqual(c.get('https://tymhlvawnqadqgwnpruk.supabase.co/rest/v1/contactos').status_code,200)
            self.assertEqual(c.post('https://api.anthropic.com/v1/messages').status_code,200)
            self.assertEqual(c.get('https://allowed.example').status_code,302)
        self.assertNotIn('api.stripe.com',seen)

    def test_flag_off_preserves_production_transport_and_smtp(self):
        seen=[]
        def transport(r):seen.append(r.url.host);return httpx.Response(200,json={})
        with patch.object(smtplib.SMTP,'connect',return_value=(220,b'OK')) as original:
            with installed({}):
                with httpx.Client(transport=httpx.MockTransport(transport)) as c:self.assertEqual(c.get('https://api.stripe.com').status_code,200)
                smtplib.SMTP().connect('smtp.example.test')
            original.assert_called_once()
        self.assertEqual(seen,['api.stripe.com'])

    def test_staging_stripe_invalid_keys_are_controlled_503_with_zero_network(self):
        for key in ['', 'sk_live_private', 'rk_test_private','sk_test_']:
            for flag in ['false','true']:
                env={'BROQUER_ENV':'staging','SIDE_EFFECTS_DISABLED':flag,'STRIPE_SECRET_KEY':key}
                with installed(env):
                    app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
                    @app.post('/operation')
                    async def operation():
                        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:self.fail('NETWORK'))) as c:
                            await c.post('https://api.stripe.com/v1/customers',headers={'Authorization':'Bearer sk_test_override'})
                    r=TestClient(app).post('/operation')
                    self.assertEqual(r.status_code,503);self.assertEqual(r.json()['code'],'STAGING_STRIPE_TEST_KEY_REQUIRED')
                    self.assertFalse(r.json()['external_call_performed'])

    def test_staging_actual_auth_cannot_bypass_configured_test_key(self):
        with installed({'BROQUER_ENV':'staging','STRIPE_SECRET_KEY':'sk_test_configured','SIDE_EFFECTS_DISABLED':'false'}):
            for auth in ['Bearer sk_live_bad','Bearer xxsk_test_fake','Basic !!!','', 'Bearer rk_test_bad']:
                with httpx.Client(transport=httpx.MockTransport(lambda r:self.fail('NETWORK'))) as c:
                    with self.assertRaises(Exception) as raised:c.get('https://api.stripe.com',headers={'Authorization':auth})
                    self.assertEqual(raised.exception.status_code,503)
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={}))) as c:
                for auth in ['Bearer sk_test_override','Basic c2tfdGVzdF9jb25maWd1cmVkOg==']:
                    self.assertEqual(c.post('https://api.stripe.com',headers={'Authorization':auth}).status_code,200)

    def test_simulation_is_explicit_even_when_route_swallows_exception(self):
        with installed({'SIDE_EFFECTS_DISABLED':'true'}):
            app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
            @app.post('/send')
            async def send_message():
                try:
                    async with httpx.AsyncClient() as c:await c.post('https://graph.facebook.com/v25.0/messages')
                except Exception:pass
                return {'ok':True,'sent':True}
            r=TestClient(app).post('/send');self.assertEqual(r.status_code,409)
            self.assertTrue(r.json()['simulated']);self.assertFalse(r.json()['external_call_performed'])
            self.assertNotIn('sent',r.json());self.assertIn('no-store',r.headers['cache-control'])

    def test_unhandled_block_does_not_become_500(self):
        with installed({'SIDE_EFFECTS_DISABLED':'true','BROQUER_ENV':'staging','STRIPE_SECRET_KEY':'sk_test_good'}):
            app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
            @app.get('/send')
            async def send_message():
                async with httpx.AsyncClient() as c:await c.get('https://api.stripe.com/v1/customers',headers={'Authorization':'Bearer sk_test_good'})
            r=TestClient(app).get('/send');self.assertEqual(r.status_code,409);self.assertTrue(r.json()['simulated'])

    def test_non_provider_error_still_propagates(self):
        app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
        @app.get('/error')
        async def error():raise ValueError('real defect')
        with self.assertRaises(ValueError):TestClient(app).get('/error')

    def test_legacy_easybroker_config_is_ignored_even_if_written_at_runtime(self):
        import tempfile
        from pathlib import Path
        from core import easybroker
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.json';path.write_text('{"eb_api_key":"live-legacy-key"}')
            with patch.object(easybroker,'_CONFIG_FILE',path):
                with patch.dict(os.environ,{'BROQUER_ENV':'staging'}):self.assertEqual(easybroker._load_legacy_config(),{})
                with patch.dict(os.environ,{'BROQUER_ENV':'production'}):self.assertEqual(easybroker._load_legacy_config()['eb_api_key'],'live-legacy-key')

    def test_startup_db_validation_no_longer_crashes_for_stripe_key(self):
        env={'SUPABASE_URL':'https://separate.supabase.co','BROQUER_STAGING_DB_REF':'separate',
             'BROQUER_STAGING_PROJECT_NAME':'broquer-redesign-staging','RECORDATORIOS_ACTIVOS':'false',
             'BUSCADOR_PROPIEDADES_ACTIVO':'false','APP_URL':'https://staging.broquer.app',
             'FRONTEND_URL':'https://staging.broquer.app','API_BASE_URL':'https://brokr-main-staging.up.railway.app',
             'BROQUER_API_BASE':'https://brokr-main-staging.up.railway.app'}
        for key in ['', 'sk_live_no_startup_crash','rk_test_disallowed']:
            self.assertEqual(staging_safety.validate(dict(env,STRIPE_SECRET_KEY=key)),'separate')
        with self.assertRaises(RuntimeError):staging_safety.validate(dict(env,SUPABASE_URL='https://urtgysmtnvoqaljuhntz.supabase.co'))

    def test_real_checkout_and_cancel_endpoints_return_clear_503(self):
        from routers import subscription_checkout, subscription_cancel, subscription_enterprise
        cases=[('/subscription/checkout',{'plan_id':'max'}),('/subscription/cancel',{}),
               ('/subscription/empresa/checkout',{}),('/subscription/empresa/asientos',{'asientos':6})]
        for key in ['', 'sk_live_bad']:
            with installed({'BROQUER_ENV':'staging','STRIPE_SECRET_KEY':key}):
                app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
                for router in [subscription_checkout.router,subscription_cancel.router,subscription_enterprise.router]:app.include_router(router)
                for path,body in cases:
                    with self.subTest(key_type='empty' if not key else 'live',path=path):
                        r=TestClient(app).post(path,json=body)
                        self.assertEqual(r.status_code,503,r.text)
                        self.assertEqual(r.json()['code'],'STAGING_STRIPE_TEST_KEY_REQUIRED')

    def test_webhook_never_activates_live_or_disabled_stripe_events(self):
        import hashlib,hmac,json,time
        from routers import stripe_webhook
        for live,flag,status in [(True,'false',400),(False,'true',409)]:
            payload=json.dumps({'livemode':live,'type':'checkout.session.completed','data':{'object':{'metadata':{'user_id':'fake'},'subscription':'fake'}}}).encode()
            timestamp=str(int(time.time()));sig=hmac.new(b'whsec_fake',timestamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
            with installed({'BROQUER_ENV':'staging','STRIPE_SECRET_KEY':'sk_test_fake','SIDE_EFFECTS_DISABLED':flag}),patch.object(stripe_webhook,'STRIPE_WEBHOOK_SECRET','whsec_fake'),patch.object(stripe_webhook,'post_rows') as write:
                app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware);app.include_router(stripe_webhook.router)
                r=TestClient(app).post('/subscription/webhook',content=payload,headers={'stripe-signature':f't={timestamp},v1={sig}'})
                self.assertEqual(r.status_code,status,r.text);write.assert_not_called()

    def test_concurrent_requests_and_background_calls_have_no_shared_simulation_state(self):
        with installed({'SIDE_EFFECTS_DISABLED':'true'}):
            app=FastAPI();app.add_middleware(safety.SideEffectsMiddleware)
            @app.get('/blocked')
            async def blocked():
                async with httpx.AsyncClient() as c:await c.post('https://api.resend.com/emails')
            @app.get('/normal')
            async def normal():return {'ok':True}
            async def run():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                    import asyncio
                    responses=await asyncio.gather(c.get('/blocked'),c.get('/normal'))
                    self.assertEqual([r.status_code for r in responses],[409,200])
                    self.assertEqual(responses[1].json(),{'ok':True})
                # No HTTP request context, as in cron/background tasks: still blocked.
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:self.fail('NETWORK'))) as c:
                    with self.assertRaises(safety.SideEffectBlocked):await c.post('https://api.resend.com/emails')
            asyncio.run(run())

    def test_real_startup_layer_order_blocks_allowlisted_providers_too(self):
        env={'BROQUER_ENV':'staging','SIDE_EFFECTS_DISABLED':'true','STRIPE_SECRET_KEY':'sk_live_bad',
             'SUPABASE_URL':'https://separate.supabase.co','BROQUER_STAGING_DB_REF':'separate',
             'BROQUER_STAGING_PROJECT_NAME':'broquer-redesign-staging','RECORDATORIOS_ACTIVOS':'false',
             'BUSCADOR_PROPIEDADES_ACTIVO':'false','APP_URL':'https://staging.broquer.app',
             'FRONTEND_URL':'https://staging.broquer.app','API_BASE_URL':'https://brokr-main-staging.up.railway.app',
             'BROQUER_API_BASE':'https://brokr-main-staging.up.railway.app',
             'BROQUER_STAGING_TEST_EMAILS':'owner@example.test','BROQUER_STAGING_TEST_PHONES':'5551234567'}
        with patch.dict(os.environ,env,clear=True),patch.object(staging_safety,'_installed',False),patch.object(safety,'_installed',False),patch.object(httpx.Client,'send',httpx.Client.send),patch.object(httpx.AsyncClient,'send',httpx.AsyncClient.send),patch.object(smtplib.SMTP,'sendmail',smtplib.SMTP.sendmail),patch.object(smtplib.SMTP,'connect',smtplib.SMTP.connect):
            staging_safety.install_staging_safety()  # A live key no longer kills startup.
            safety.install_side_effects_safety()
            with httpx.Client(transport=httpx.MockTransport(lambda r:self.fail('NETWORK'))) as c:
                for url,body in [('https://graph.facebook.com/v25/messages',{'to':'5551234567'}),('https://api.resend.com/emails',{'to':['owner@example.test']}),('https://api.sandbox.push.apple.com/3/device/fake',{})]:
                    with self.assertRaises(safety.SideEffectBlocked):c.post(url,json=body)


    def test_staging_defaults_to_blocked_and_only_explicit_false_disables(self):
        for value in [None, '', 'true', '0', 'off', 'unexpected']:
            env={'BROQUER_ENV':'staging','STRIPE_SECRET_KEY':'sk_live_exists'}
            if value is not None:env['SIDE_EFFECTS_DISABLED']=value
            with self.subTest(value=value),installed(env):
                self.assertTrue(safety.disabled())
                with httpx.Client(transport=httpx.MockTransport(lambda r:self.fail('NETWORK'))) as c:
                    with self.assertRaises(safety.SideEffectBlocked):c.post('https://graph.facebook.com/v25/messages')
                    with self.assertRaises(HTTPException) as error:c.post('https://api.stripe.com/v1/checkout/sessions')
                    self.assertEqual(error.exception.status_code,503)
        for value in ['false',' FALSE ']:
            with installed({'BROQUER_ENV':'staging','SIDE_EFFECTS_DISABLED':value}):self.assertFalse(safety.disabled())
        with installed({}):self.assertFalse(safety.disabled())
