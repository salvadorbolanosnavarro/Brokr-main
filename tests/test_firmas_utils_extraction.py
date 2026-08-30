"""Permanent behavior guards for pure electronic-signature utilities."""
from __future__ import annotations

import hashlib
import re
import unittest
from unittest.mock import patch

from core.firmas_utils import (
    _email_ok,
    _fecha_larga,
    _folio,
    _limpio,
    _mask_email,
    _mask_tel,
    _sha256,
    _tel,
)


class FirmasUtilsExtractionTests(unittest.TestCase):
    def test_filename_cleanup_contract(self):
        self.assertEqual(_limpio(" Contrato final (1).pdf "), "Contrato_final_1_.pdf")
        self.assertEqual(_limpio(""), "documento")
        self.assertEqual(len(_limpio("a" * 120)), 80)

    def test_folio_shape_and_alphabet_contract(self):
        with patch("core.firmas_utils.secrets.choice", return_value="B"):
            self.assertEqual(_folio(), "BRQ-BBBBBBBB")
        self.assertRegex(_folio(), re.compile(r"^BRQ-[23456789BCDFGHJKMNPQRSTVWXYZ]{8}$"))

    def test_sha256_contract(self):
        payload = b"Broquer firma"
        self.assertEqual(_sha256(payload), hashlib.sha256(payload).hexdigest())

    def test_long_date_contract(self):
        self.assertEqual(_fecha_larga(None), "—")
        self.assertEqual(
            _fecha_larga("2026-08-31T06:30:45+00:00"),
            "31 de agosto de 2026, 00:30:45 (UTC-6)",
        )
        self.assertEqual(_fecha_larga("valor-invalido"), "valor-invalido")

    def test_mexican_phone_normalization_contract(self):
        self.assertEqual(_tel("443 123 4567"), "+524431234567")
        self.assertEqual(_tel("+52 443 123 4567"), "+524431234567")
        self.assertEqual(_tel("5214431234567"), "+521443123456")
        self.assertEqual(_tel(""), "")
        self.assertEqual(_tel("123"), "+123")

    def test_email_validation_contract(self):
        self.assertTrue(_email_ok(" agente@example.com "))
        self.assertFalse(_email_ok("agente@example"))
        self.assertFalse(_email_ok(""))

    def test_masking_contract(self):
        self.assertEqual(_mask_tel("+524431234567"), "•••••••••4567")
        self.assertEqual(_mask_tel("1234"), "••••")
        self.assertEqual(_mask_email("salvador@example.com"), "s•••••••@example.com")
        self.assertEqual(_mask_email("invalido"), "••••")


if __name__ == "__main__":
    unittest.main()
