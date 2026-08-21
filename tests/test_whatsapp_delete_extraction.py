from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_delete_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
DELETE_ROUTER = ROOT / "routers" / "whatsapp_delete.py"


class WhatsAppDeleteStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DELETE_ROUTER.read_text(encoding="utf-8")

    def test_router_contains_exact_destructive_surface(self):
        self.assertEqual(self.source.count("@router.delete("), 3)
        for route in (
            '@router.delete("/numeros/{numero_id}")',
            '@router.delete("/mensajes/{mensaje_id}")',
            '@router.delete("/conversaciones/{conversacion_id}")',
        ):
            self.assertIn(route, self.source)

    def test_each_handler_authorizes_before_destructive_database_work(self):
        blocks = [
            ("async def wa2_numero_delete", "@router.delete(\"/mensajes/{mensaje_id}\")"),
            ("async def wa2_borrar_mensaje", "@router.delete(\"/conversaciones/{conversacion_id}\")"),
            ("async def wa2_borrar_conversacion", None),
        ]
        for start_marker, end_marker in blocks:
            start = self.source.index(start_marker)
            end = self.source.index(end_marker, start) if end_marker else len(self.source)
            block = self.source[start:end]
            self.assertIn("user_id = await _require_user(request)", block)
            self.assertIn("ids = await _ids_visibles(user_id)", block)
            first_delete = block.find("await sb_delete(")
            self.assertGreater(first_delete, block.find("_ids_visibles(user_id)"))

    def test_media_is_removed_before_message_rows(self):
        message = self.source[self.source.index("async def wa2_borrar_mensaje"):]
        self.assertLess(
            message.index("await _borrar_archivos"),
            message.index('await sb_delete("wa2_mensajes"'),
        )
        conv_start = self.source.index("async def wa2_borrar_conversacion")
        conv = self.source[conv_start:]
        self.assertLess(
            conv.index("await _borrar_archivos"),
            conv.index('await sb_delete("wa2_mensajes"'),
        )

    def test_crm_contacts_are_never_deleted(self):
        self.assertNotIn('sb_delete("contactos"', self.source)
        self.assertIn('sb_delete("wa2_contactos"', self.source)

    def test_number_delete_preserves_bounded_pagination_and_scope(self):
        block = self.source[
            self.source.index("async def wa2_numero_delete"):
            self.source.index('@router.delete("/mensajes/{mensaje_id}")')
        ]
        self.assertIn("while pagina < 20:", block)
        self.assertIn("while pag < 40:", block)
        self.assertIn("range(0, len(conv_ids), 50)", block)
        self.assertIn("range(0, len(conv_ids), 60)", block)
        self.assertIn('"user_id": _in_filter(ids)', block)


class WhatsAppDeleteExtractionTests(unittest.TestCase):
    def test_transform_moves_only_three_destructive_handlers(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_delete import router as whatsapp_delete_router", transformed)
        self.assertIn("router.include_router(whatsapp_delete_router)", transformed)
        for handler in (
            "async def wa2_numero_delete",
            "async def wa2_borrar_mensaje",
            "async def wa2_borrar_conversacion",
        ):
            self.assertNotIn(handler, transformed)
        self.assertIn("async def wa2_automatizacion_delete", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
