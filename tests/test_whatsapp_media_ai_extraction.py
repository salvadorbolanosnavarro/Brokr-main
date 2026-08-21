from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_media_ai_core import transform_source
from scripts.refactor_whatsapp_media_ai_usage_core import transform_source as usage_transform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_media_ai.py"


class WhatsAppMediaAiExtractionTests(unittest.TestCase):
    def test_media_ai_preserves_limits_and_tracks_real_pricing_units(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            '"whisper-large-v3"',
            '"language": "es"',
            '"response_format": "verbose_json"',
            '"timestamp_granularities[]": "segment"',
            "track_audio_usage(",
            'modulo="whatsapp"',
            'herramienta="nota-voz-transcripcion"',
            "_track_anthropic(user_id, \"whatsapp\", \"foto-descripcion\"",
            "timeout=60",
            "len(contenido) > 4_500_000",
            "max_tokens\": 300",
            "timeout=40",
            'mime not in ("image/jpeg", "image/png", "image/gif", "image/webp")',
        ):
            self.assertIn(required, source)

    def test_extraction_then_usage_attribution_keeps_callers(self):
        extracted = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("async def _transcribir_audio", extracted)
        self.assertNotIn("async def _describir_imagen", extracted)
        self.assertIn("await _transcribir_audio(media_bytes, media_mime)", extracted)
        self.assertIn("await _describir_imagen(media_bytes, media_mime)", extracted)
        attributed = usage_transform(extracted)
        self.assertIn('await _transcribir_audio(media_bytes, media_mime, numero["user_id"])', attributed)
        self.assertIn('await _describir_imagen(media_bytes, media_mime, numero["user_id"])', attributed)
        compile(attributed, "whatsapp.py", "exec")

    def test_transforms_are_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))
        attributed = usage_transform(once)
        self.assertEqual(attributed, usage_transform(attributed))


if __name__ == "__main__":
    unittest.main()
