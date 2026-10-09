"""Bandeja de correo: lectura en lote y errores traducidos (sin 502 genéricos
para fallas que la persona puede resolver)."""
from __future__ import annotations

import imaplib
import socket
import unittest
from unittest import mock

from cryptography.fernet import InvalidToken
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.correo as C

CHICO = b"From: Ana <ana@x.mx>\r\nTo: yo@x.mx\r\nSubject: Hola\r\nDate: Fri, 02 Oct 2026 10:00:00 -0600\r\n\r\nQuiero ver la casa."
GRANDE_HDR = b"From: Banco <b@x.mx>\r\nSubject: Estado de cuenta\r\nDate: Fri, 02 Oct 2026 09:00:00 -0600\r\n\r\n"


class FakeIMAP:
    def __init__(self):
        self.fetches = []

    def select(self, carpeta, readonly=False):
        return ("OK", [b"2"]) if carpeta == "INBOX" else ("NO", [b"no existe"])

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b"7 8"]
        uids, partes = args
        self.fetches.append((uids, partes))
        if "HEADER" in partes:
            return "OK", [(b"1 (UID 7 FLAGS (\\Seen) RFC822.SIZE 120 BODY[HEADER] {80}", CHICO.split(b"\r\n\r\n")[0] + b"\r\n\r\n"), b")",
                          (b"2 (UID 8 RFC822.SIZE 9000000 BODY[HEADER] {60}", GRANDE_HDR), b" FLAGS ())"]
        return "OK", [(b"1 (UID 7 BODY[] {120}", CHICO), b")"]

    def logout(self):
        pass


class ListarTests(unittest.TestCase):
    def test_lote_visto_y_adjuntos(self):
        fake = FakeIMAP()
        with mock.patch.object(C, "_imap_conectar", return_value=fake):
            msgs = C._listar_bandeja({}, 30, "INBOX")
        self.assertEqual([m["uid"] for m in msgs], ["8", "7"])
        self.assertEqual(len(fake.fetches), 2)                    # 2 peticiones, no una por correo
        self.assertEqual(fake.fetches[1][0], b"7")                # el grande no se descarga completo
        nuevo, viejo = msgs
        self.assertFalse(nuevo["visto"]); self.assertTrue(viejo["visto"])
        self.assertEqual(viejo["snippet"], "Quiero ver la casa.")
        self.assertIn("adjuntos", nuevo["snippet"])
        self.assertEqual(nuevo["asunto"], "Estado de cuenta")

    def test_carpeta_inexistente(self):
        with mock.patch.object(C, "_imap_conectar", return_value=FakeIMAP()):
            with self.assertRaises(C._ErrorCorreo) as cm:
                C._listar_bandeja({}, 30, "Spam")
        self.assertEqual(cm.exception.status, 404)


class TraducirTests(unittest.TestCase):
    def test_casos(self):
        casos = [
            (InvalidToken(), 409, "reconectar"),
            (imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)"), 409, "reconectar"),
            (ValueError("Servidor IMAP no permitido."), 409, "reconectar"),
            (socket.timeout("timed out"), 504, "proveedor_lento"),
            (ConnectionRefusedError(111, "refused"), 503, "sin_conexion"),
            (RuntimeError("raro"), 502, "error"),
        ]
        for exc, status, codigo in casos:
            e = C._traducir_error(exc, "leer tu bandeja")
            self.assertEqual((e.status, e.codigo), (status, codigo), repr(exc))
            self.assertTrue(e.mensaje)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(C.router)
        self.c = TestClient(app)
        self.p = [mock.patch.object(C, "_uid", mock.AsyncMock(return_value="u1"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_sin_cuenta_es_404(self):
        with mock.patch.object(C, "_cuenta_de", mock.AsyncMock(return_value=None)):
            r = self.c.get("/correo/bandeja")
        self.assertEqual(r.status_code, 404)

    def test_contrasena_revocada_pide_reconectar(self):
        cta = {"email": "yo@x.mx"}
        with mock.patch.object(C, "_cuenta_de", mock.AsyncMock(return_value=cta)), \
             mock.patch.object(C, "_listar_bandeja", side_effect=imaplib.IMAP4.error("b'[AUTHENTICATIONFAILED] Invalid credentials'")):
            r = self.c.get("/correo/bandeja")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["codigo"], "reconectar")

    def test_ok(self):
        with mock.patch.object(C, "_cuenta_de", mock.AsyncMock(return_value={"email": "yo@x.mx"})), \
             mock.patch.object(C, "_listar_bandeja", return_value=[]):
            r = self.c.get("/correo/bandeja")
        self.assertEqual((r.status_code, r.json()["mensajes"]), (200, []))


if __name__ == "__main__":
    unittest.main()
