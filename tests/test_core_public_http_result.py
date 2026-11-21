from pathlib import Path
import unittest

from core.http import PublicHTTPResult

ROOT = Path(__file__).resolve().parents[1]
CORE_HTTP = ROOT / "core" / "http.py"


class PublicHTTPResultTests(unittest.TestCase):
    def test_text_uses_httpx_decoding_semantics(self):
        result = PublicHTTPResult(
            status_code=403,
            headers={"content-type": "text/html; charset=iso-8859-1"},
            content="Información".encode("iso-8859-1"),
            url="https://example.com/",
        )
        self.assertEqual(result.text, "Información")

    def test_status_preserving_fetch_reuses_public_url_validation_for_redirects(self):
        source = CORE_HTTP.read_text(encoding="utf-8")
        self.assertIn("async def fetch_public_http_result(", source)
        self.assertIn("await assert_public_http_url(current)", source)
        self.assertIn("follow_redirects=False", source)
        self.assertIn("current = urljoin(current, location)", source)
        self.assertIn("if len(chunks) > max_bytes:", source)
        self.assertIn("status_code=response.status_code", source)


if __name__ == "__main__":
    unittest.main()

class StagingRedirectSafetyTests(unittest.TestCase):
    def test_blocked_redirect_is_omitted_before_transport_without_side_effect_event(self):
        import asyncio, os, httpx
        from unittest.mock import patch, AsyncMock
        from core.http import fetch_public_http_result, UnsafePublicURL
        from core import side_effects
        seen=[]
        def transport(r):
            seen.append(r.url.host)
            return httpx.Response(302,headers={'location':'https://www.easybroker.com/property/test'})
        original=httpx.AsyncClient
        token=side_effects._events.set([])
        try:
            with patch.dict(os.environ,{'BROQUER_ENV':'staging'},clear=True), patch('core.http.assert_public_http_url',AsyncMock()), patch('core.http.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(transport),**kw)):
                with self.assertRaises(UnsafePublicURL):asyncio.run(fetch_public_http_result('https://www.lamudi.com.mx/test'))
            self.assertEqual(seen,['www.lamudi.com.mx'])
            self.assertEqual(side_effects._events.get(),[])
        finally:side_effects._events.reset(token)
