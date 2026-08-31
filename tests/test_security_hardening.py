"""Focused regression tests for the security audit remediations."""
from __future__ import annotations

import hashlib
import hmac
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from core.redirects import checkout_redirect
from routers.correo import _validar_destino_publico
from routers.stripe_webhook import _verify_stripe_signature


class StripeReplayTests(unittest.TestCase):
    def _header(self, payload: bytes, secret: str, timestamp: int) -> str:
        signed = f"{timestamp}.{payload.decode()}".encode()
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={signature}"

    def test_accepts_current_valid_signature(self):
        payload = b'{"id":"evt_test"}'
        secret = "whsec_test"
        now = int(time.time())
        _verify_stripe_signature(payload, self._header(payload, secret, now), secret, now=now)

    def test_rejects_valid_but_stale_signature(self):
        payload = b'{"id":"evt_test"}'
        secret = "whsec_test"
        now = 2_000_000_000
        with self.assertRaises(HTTPException) as cm:
            _verify_stripe_signature(
                payload,
                self._header(payload, secret, now - 301),
                secret,
                now=now,
            )
        self.assertEqual(cm.exception.status_code, 400)

    def test_accepts_any_valid_v1_during_rotation(self):
        payload = b'{"id":"evt_test"}'
        secret = "whsec_test"
        now = 2_000_000_000
        good = self._header(payload, secret, now).split("v1=", 1)[1]
        header = f"t={now},v1=bad,v1={good}"
        _verify_stripe_signature(payload, header, secret, now=now)


class MailSsrfTests(unittest.TestCase):
    def test_rejects_loopback_imap(self):
        with self.assertRaises(ValueError):
            _validar_destino_publico("127.0.0.1", 993, servicio="IMAP")

    def test_rejects_private_smtp(self):
        with self.assertRaises(ValueError):
            _validar_destino_publico("10.0.0.8", 587, servicio="SMTP")

    def test_rejects_arbitrary_mail_port_before_dns(self):
        with self.assertRaises(ValueError):
            _validar_destino_publico("mail.example.com", 22, servicio="SMTP")

    @patch("routers.correo.socket.getaddrinfo")
    def test_rejects_hostname_resolving_to_link_local(self, mocked):
        mocked.return_value = [(2, 1, 6, "", ("169.254.169.254", 993))]
        with self.assertRaises(ValueError):
            _validar_destino_publico("mail.attacker.test", 993, servicio="IMAP")


class CheckoutRedirectTests(unittest.TestCase):
    def test_rejects_external_redirect(self):
        with self.assertRaises(HTTPException):
            checkout_redirect(
                "https://evil.example/phish",
                default_base="https://broquer.app",
                default_path="index.html",
            )

    def test_default_redirect_uses_server_base(self):
        self.assertEqual(
            checkout_redirect(
                "",
                default_base="https://broquer.app",
                default_path="index.html?suscripcion=ok",
            ),
            "https://broquer.app/index.html?suscripcion=ok",
        )


if __name__ == "__main__":
    unittest.main()
