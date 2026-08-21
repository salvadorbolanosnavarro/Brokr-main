from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_media_ai_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_media_ai.py"


class WhatsAppMediaAiExtractionTests(unittest.TestCase):
    def test_media_ai_preserves_models_limits_and_fallbacks(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            '"whisper-large-v3"',
            '"language": "es"',
            '"response_format": "json"',
            "timeout=60",
            "len(contenido) > 4_500_000",
            "max_tokens\": 300",
            "timeout=40",
            'mime not in ("image/jpeg", "image/png", "image/gif", "image/webp")',
        ):
            self.assertIn(required, source)

    def test_transform_reuses_media_ai_callers(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("async def _transcribir_audio", transformed)
        self.assertNotIn("async def _describir_imagen", transformed)
        self.assertIn("await _transcribir_audio(media_bytes, media_mime)", transformed)
        self.assertIn("await _describir_imagen(media_bytes, media_mime)", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
