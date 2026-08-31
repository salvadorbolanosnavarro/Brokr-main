"""Permanent regression guard for WhatsApp 2 database migration."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhatsAppDatabaseRegressionTests(unittest.TestCase):
    def test_router_routes_table_access_through_core(self):
        source = (ROOT / "whatsapp.py").read_text(encoding="utf-8")
        data = (ROOT / "routers" / "whatsapp_data.py").read_text(encoding="utf-8")
        stats_io = (ROOT / "routers" / "whatsapp_stats_io.py").read_text(encoding="utf-8")

        self.assertIn(
            "from core.database import delete_rows, get_rows, patch_rows, post_rows",
            data,
        )
        self.assertIn("return await get_rows(table, params, timeout=15)", data)
        self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", data)
        self.assertIn("return await patch_rows(", data)
        self.assertIn("await delete_rows(table, params, timeout=15)", data)

        # During the prepared->applied transition the wrappers may still live in
        # whatsapp.py. Once extracted, the router must import the canonical
        # domain adapter module instead. Both states preserve the same behavior.
        if "async def sb_get(" in source:
            self.assertIn("return await get_rows(table, params, timeout=15)", source)
            self.assertIn("return await post_rows(table, body, prefer=prefer, timeout=15)", source)
            self.assertIn("await delete_rows(table, params, timeout=15)", source)
        else:
            self.assertIn(
                "from routers.whatsapp_data import sb_delete, sb_get, sb_patch, sb_post",
                source,
            )

        # Diagnostic statistics reads intentionally bypass the fail-soft sb_get
        # adapter so the database error text remains visible. During extraction
        # that implementation moves to whatsapp_stats_io, while whatsapp.py keeps
        # bounded wrappers with the original names for exact call-site behavior.
        stats_extracted = "from routers.whatsapp_stats_io import (" in source
        if stats_extracted:
            self.assertIn("data = await get_rows(table, params, timeout=25)", stats_io)
            self.assertIn("resultados = await asyncio.gather(*tareas, return_exceptions=True)", stats_io)
            self.assertIn("return salida[:tope], error", stats_io)
            self.assertIn("return await _sb_diag_core(table, params, get_rows=get_rows, httpx=httpx)", source)
            self.assertIn("return await _sb_get_paginado_core(", source)
            self.assertIn("_sb_diag=_sb_diag, asyncio=asyncio", source)
        else:
            self.assertIn("data = await get_rows(table, params, timeout=25)", source)

        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/{table}"', source)
        self.assertNotIn("service_headers", source)
        self.assertNotIn("def _sb_headers()", source)
        self.assertIn("GRAPH_API", source)
        compile(source, "whatsapp.py", "exec")
        compile(data, "routers/whatsapp_data.py", "exec")
        compile(stats_io, "routers/whatsapp_stats_io.py", "exec")


if __name__ == "__main__":
    unittest.main()
