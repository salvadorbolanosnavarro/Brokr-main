import importlib
import io
import os
import unittest
import zipfile
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request


class _FakeLoop:
    def __init__(self, addresses):
        self.addresses = addresses

    async def getaddrinfo(self, host, port, family=0, type=0):
        return [(2, 1, 6, "", (address, port)) for address in self.addresses]


def _request(query: bytes = b"") -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/webhook",
        "raw_path": b"/webhook",
        "query_string": query,
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    })


def _docx_bytes(document_xml: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/document.xml", document_xml)
    return out.getvalue()


class SecurityHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_ssrf_rejects_private_literal_and_pins_validated_dns_result(self):
        from core.http import UnsafePublicURL, _resolve_public_http_url

        with self.assertRaises(UnsafePublicURL):
            await _resolve_public_http_url("http://127.0.0.1/private")

        fake_loop = _FakeLoop(["93.184.216.34"])
        with patch("core.http.asyncio.get_running_loop", return_value=fake_loop):
            resolved = await _resolve_public_http_url("https://example.com/path?q=1")
        self.assertEqual(resolved.request_url, "https://93.184.216.34/path?q=1")
        self.assertEqual(resolved.host_header, "example.com")
        self.assertEqual(resolved.sni_hostname, "example.com")

    async def test_ssrf_does_not_swallow_unsafe_resolved_address(self):
        from core.http import UnsafePublicURL, assert_public_http_url

        fake_loop = _FakeLoop(["10.0.0.9"])
        with patch("core.http.asyncio.get_running_loop", return_value=fake_loop):
            with self.assertRaises(UnsafePublicURL):
                await assert_public_http_url("https://attacker.example/resource")

    async def test_docx_validator_bounds_real_decompression(self):
        from core.documents import UnsafeDocument, validate_docx_archive

        safe = _docx_bytes(b"<w:document/>" * 10)
        validate_docx_archive(safe, max_single_entry_bytes=4096, max_uncompressed_bytes=8192)

        bomb = _docx_bytes(b"A" * 16384)
        with self.assertRaises(UnsafeDocument):
            validate_docx_archive(
                bomb,
                max_single_entry_bytes=1024,
                max_uncompressed_bytes=2048,
            )

    async def test_meta_token_write_fails_closed_without_fernet(self):
        main = importlib.import_module("main")
        with patch.object(main, "_FERNET", None):
            with self.assertRaises(RuntimeError):
                main.cifrar_secreto("EA-test-token")
        self.assertEqual(main.cifrar_secreto(""), "")

    async def test_whatsapp_webhook_fails_closed_when_verify_secret_missing(self):
        whatsapp = importlib.import_module("whatsapp")
        query = b"hub.mode=subscribe&hub.verify_token=&hub.challenge=123"
        with patch.object(whatsapp, "WA2_VERIFY_TOKEN", ""):
            response = whatsapp.wa2_verify_webhook(_request(query))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.body, b"forbidden")

    async def test_registration_pin_configuration_has_no_public_fallback(self):
        with patch.dict(os.environ, {"WA_REGISTER_PIN": ""}, clear=False):
            chatgpt = importlib.import_module("routers.whatsapp_chatgpt")
            chatgpt = importlib.reload(chatgpt)
            whatsapp = importlib.import_module("whatsapp")
            whatsapp = importlib.reload(whatsapp)
        self.assertEqual(chatgpt.WA_REGISTER_PIN, "")
        self.assertEqual(whatsapp.WA2_REGISTER_PIN, "")


if __name__ == "__main__":
    unittest.main()
