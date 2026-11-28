"""Guards for "Eliminar mi cuenta": cancel billing first, then delete atomically.

Behavioural tests with Stripe, the database RPC and email stubbed:

* an active Stripe subscription is cancelled (at period end) BEFORE anything
  is deleted; if cancelling fails nothing is deleted and the user is told;
* an active Apple subscription stops the deletion (Apple can't be cancelled
  server-side) and nothing is deleted;
* if the atomic delete fails, the Stripe cancellation is reverted;
* Stripe subscriptions are found by customer email even with no
  ``suscripciones`` row (a real case: a live charge with no DB record);
* the pre-check returns the exact warning shown before confirming.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

import core.suscripcion_baja as sb
import routers.account_delete as ad

UID = "00000000-0000-4000-8000-000000000001"
AVISO = "Tienes una suscripción activa. Al eliminar tu cuenta la cancelamos y ya no se te cobrará."


def run(coro):
    return asyncio.run(coro)


class _Base(unittest.TestCase):
    def setUp(self):
        self.calls: list = []
        patches = [
            mock.patch.object(ad, "get_user_id_from_token", mock.AsyncMock(return_value=UID)),
            mock.patch.object(ad, "SUPABASE_URL", "https://x.supabase.co"),
            mock.patch.object(ad, "SUPABASE_SERVICE_KEY", "service"),
            mock.patch.object(ad, "_storage_rutas_fotos_de_usuario", mock.AsyncMock(return_value={})),
            mock.patch.object(ad, "_storage_borrar_carpeta_usuario", mock.AsyncMock(return_value=0)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def estado(self, stripe=None, apple=False):
        return {"email": "a@b.co", "nombre": "Ana", "stripe": stripe or [], "apple": apple}

    def patch(self, name, value):
        p = mock.patch.object(ad, name, value)
        p.start()
        self.addCleanup(p.stop)
        return value


class DeleteOrderTests(_Base):
    def test_stripe_cancelled_before_delete_and_email_sent(self):
        sub = {"id": "sub_1", "status": "active", "cancel_at_period_end": False, "current_period_end": 1800000000}
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado([sub])))
        cancel = self.patch("cancelar_stripe", mock.AsyncMock(side_effect=lambda s: self.calls.append("cancel") or ["sub_1"]))
        rpc = self.patch("call_service_rpc", mock.AsyncMock(side_effect=lambda *a, **k: self.calls.append("rpc") or {"ok": True, "borrado": {}}))
        mail = self.patch("_correo_confirmacion", mock.AsyncMock(return_value=(True, "")))
        out = run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(self.calls, ["cancel", "rpc"])
        self.assertTrue(out["borrados"]["auth"])
        self.assertEqual(out["borrados"]["stripe"], ["sub_1"])
        mail.assert_awaited_once()
        self.assertTrue(mail.await_args.args[2])  # cancelo=True
        rpc.assert_awaited_once()
        cancel.assert_awaited_once()

    def test_stripe_cancel_failure_deletes_nothing(self):
        sub = {"id": "sub_1", "status": "active", "cancel_at_period_end": False}
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado([sub])))
        self.patch("cancelar_stripe", mock.AsyncMock(side_effect=sb.CancelacionFallida(sb.MENSAJE_STRIPE_FALLO, "x")))
        rpc = self.patch("call_service_rpc", mock.AsyncMock())
        mail = self.patch("_correo_confirmacion", mock.AsyncMock())
        with self.assertRaises(HTTPException) as cm:
            run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(cm.exception.status_code, 502)
        self.assertIn("no eliminamos tu cuenta", cm.exception.detail)
        rpc.assert_not_awaited()
        mail.assert_not_awaited()

    def test_cannot_check_billing_deletes_nothing(self):
        self.patch("suscripciones_cobrables", mock.AsyncMock(side_effect=sb.CancelacionFallida(sb.MENSAJE_STRIPE_FALLO, "down")))
        rpc = self.patch("call_service_rpc", mock.AsyncMock())
        with self.assertRaises(HTTPException) as cm:
            run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(cm.exception.status_code, 502)
        rpc.assert_not_awaited()

    def test_apple_subscription_blocks_delete(self):
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado(apple=True)))
        cancel = self.patch("cancelar_stripe", mock.AsyncMock())
        rpc = self.patch("call_service_rpc", mock.AsyncMock())
        with self.assertRaises(HTTPException) as cm:
            run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("Apple", cm.exception.detail)
        cancel.assert_not_awaited()
        rpc.assert_not_awaited()

    def test_failed_delete_reverts_cancellation(self):
        sub = {"id": "sub_1", "status": "active", "cancel_at_period_end": False}
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado([sub])))
        self.patch("cancelar_stripe", mock.AsyncMock(return_value=["sub_1"]))
        self.patch("call_service_rpc", mock.AsyncMock(return_value={"ok": False, "error": "boom"}))
        revert = self.patch("revertir_stripe", mock.AsyncMock())
        mail = self.patch("_correo_confirmacion", mock.AsyncMock())
        with self.assertRaises(HTTPException) as cm:
            run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(cm.exception.status_code, 500)
        revert.assert_awaited_once_with(["sub_1"])
        mail.assert_not_awaited()

    def test_no_subscription_deletes_and_emails(self):
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado()))
        self.patch("cancelar_stripe", mock.AsyncMock(return_value=[]))
        self.patch("call_service_rpc", mock.AsyncMock(return_value={"ok": True, "borrado": {}}))
        mail = self.patch("_correo_confirmacion", mock.AsyncMock(return_value=(True, "")))
        out = run(ad.eliminar_cuenta_y_datos(mock.Mock()))
        self.assertEqual(out["borrados"]["stripe"], "sin_suscripcion")
        self.assertFalse(mail.await_args.args[2])  # cancelo=False


class PrecheckTests(_Base):
    def test_active_stripe_returns_exact_warning(self):
        sub = {"id": "sub_1", "status": "active", "cancel_at_period_end": False}
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado([sub])))
        out = run(ad.eliminar_cuenta_suscripcion(mock.Mock()))
        self.assertEqual(out, {"activa": True, "proveedor": "stripe", "mensaje": AVISO})

    def test_already_cancelled_is_not_active(self):
        sub = {"id": "sub_1", "status": "active", "cancel_at_period_end": True}
        self.patch("suscripciones_cobrables", mock.AsyncMock(return_value=self.estado([sub])))
        out = run(ad.eliminar_cuenta_suscripcion(mock.Mock()))
        self.assertFalse(out["activa"])
        self.assertIsNone(out["mensaje"])


class DetectionTests(unittest.TestCase):
    def test_finds_stripe_subscription_by_email_without_db_row(self):
        async def fake_get(client, ruta, params):
            if ruta == "/customers":
                self.assertEqual(params["email"], "a@b.co")
                return {"data": [{"id": "cus_1"}]}
            if ruta == "/subscriptions":
                return {"data": [
                    {"id": "sub_live", "status": "active", "cancel_at_period_end": False},
                    {"id": "sub_old", "status": "canceled"},
                ]}
            raise AssertionError(ruta)

        with mock.patch.object(sb, "STRIPE_SECRET_KEY", "sk_test"), \
             mock.patch.object(sb, "_perfil", mock.AsyncMock(return_value={"email": "a@b.co"})), \
             mock.patch.object(sb, "_filas_suscripcion", mock.AsyncMock(return_value=[])), \
             mock.patch.object(sb, "_stripe_get", fake_get):
            estado = run(sb.suscripciones_cobrables(UID))
        self.assertEqual([s["id"] for s in estado["stripe"]], ["sub_live"])
        self.assertTrue(sb.hay_cobro_vivo(estado))

    def test_apple_row_detected(self):
        filas = [{"status": "active", "stripe_subscription_id": None}]
        with mock.patch.object(sb, "STRIPE_SECRET_KEY", ""), \
             mock.patch.object(sb, "_perfil", mock.AsyncMock(return_value={"email": "a@b.co"})), \
             mock.patch.object(sb, "_filas_suscripcion", mock.AsyncMock(return_value=filas)):
            estado = run(sb.suscripciones_cobrables(UID))
        self.assertTrue(estado["apple"])

    def test_trial_row_is_not_apple(self):
        filas = [{"status": "trialing", "stripe_subscription_id": None}]
        with mock.patch.object(sb, "STRIPE_SECRET_KEY", ""), \
             mock.patch.object(sb, "_perfil", mock.AsyncMock(return_value={"email": "a@b.co"})), \
             mock.patch.object(sb, "_filas_suscripcion", mock.AsyncMock(return_value=filas)):
            estado = run(sb.suscripciones_cobrables(UID))
        self.assertFalse(sb.hay_cobro_vivo(estado))

    def test_registered_subscription_without_stripe_key_fails_closed(self):
        filas = [{"status": "active", "stripe_subscription_id": "sub_1"}]
        with mock.patch.object(sb, "STRIPE_SECRET_KEY", ""), \
             mock.patch.object(sb, "_perfil", mock.AsyncMock(return_value={"email": "a@b.co"})), \
             mock.patch.object(sb, "_filas_suscripcion", mock.AsyncMock(return_value=filas)):
            with self.assertRaises(sb.CancelacionFallida):
                run(sb.suscripciones_cobrables(UID))

    def test_partial_cancel_failure_reverts_the_ones_done(self):
        subs = [{"id": "a", "cancel_at_period_end": False}, {"id": "b", "cancel_at_period_end": False}]
        respuestas = iter([mock.Mock(status_code=200), mock.Mock(status_code=500, text="err")])

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, data=None):
                return next(respuestas)

        revert = mock.AsyncMock()
        with mock.patch.object(sb.httpx, "AsyncClient", lambda **k: FakeClient()), \
             mock.patch.object(sb, "revertir_stripe", revert):
            with self.assertRaises(sb.CancelacionFallida):
                run(sb.cancelar_stripe(subs))
        revert.assert_awaited_once_with(["a"])


class SourceGuards(unittest.TestCase):
    def test_atomic_rpc_and_no_piecemeal_deletes(self):
        src = (ad.__file__ and open(ad.__file__, encoding="utf-8").read())
        self.assertIn('"admin_eliminar_usuario_total"', src)
        self.assertNotIn("delete_rows(", src)
        self.assertNotIn("/auth/v1/admin/users/", src)
        self.assertEqual(sb.MENSAJE_AVISO, AVISO)


if __name__ == "__main__":
    unittest.main()
