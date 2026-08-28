"""Permanent prepared/certified guards for /contactos/importar-archivo."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "contactos_importar_archivo.py"


class ContactosImportarArchivoExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.prepared = '@app.post("/contactos/importar-archivo")' in cls.main
        cls.owner = cls.main if cls.prepared else cls.router

    def test_route_has_exactly_one_owner(self):
        self.assertEqual(
            self.main.count('@app.post("/contactos/importar-archivo")')
            + self.router.count('@router.post("/contactos/importar-archivo")'),
            1,
        )
        if self.prepared:
            self.assertNotIn("create_contactos_importar_archivo_router", self.main)
        else:
            self.assertIn(
                "from routers.contactos_importar_archivo import create_router as create_contactos_importar_archivo_router",
                self.main,
            )
            self.assertEqual(
                self.main.count("app.include_router(create_contactos_importar_archivo_router("),
                1,
            )
            self.assertNotIn("async def importar_contactos_archivo(", self.main)

    def test_auth_file_and_format_contracts_are_preserved(self):
        s = self.owner
        self.assertIn('detail="Tu sesión expiró. Vuelve a iniciar sesión."', s)
        self.assertIn('detail="Supabase no está configurado en el servidor."', s)
        self.assertIn('detail="El archivo llegó vacío."', s)
        self.assertIn("15 * 1024 * 1024", s)
        self.assertIn('nombre_archivo.endswith((".xlsx", ".xls"))', s)
        self.assertIn('openpyxl.load_workbook(BytesIO(contenido), read_only=True, data_only=True)', s)
        self.assertIn('for enc in ("utf-8-sig", "utf-8", "latin-1"):', s)
        self.assertIn('delim = ";" if primera.count(";") > primera.count(",") else ","', s)
        self.assertIn('detail="No se encontraron filas con datos. Revisa que la primera fila tenga los encabezados."', s)

    def test_mapping_dedupe_and_org_contracts_are_preserved(self):
        s = self.owner
        self.assertIn('re.compile(r"EB-[A-Za-z0-9]{4,10}")', s)
        self.assertIn('org_id_import = await get_org_id_for_user', s)
        self.assertIn('{"org_id": f"eq.{org_id_import}"} if org_id_import', s)
        self.assertIn('else {"user_id": f"eq.{user_id}"}', s)
        self.assertIn('"contactos_propiedades"', s)
        self.assertIn('mapa_ag = await _mapa_agentes_org', s)
        self.assertIn('linea = f"Asesor en EasyBroker: {agente}"', s)
        self.assertIn('union = list(dict.fromkeys([*prev, *etiquetas]))', s)
        self.assertIn('now_iso = datetime.utcnow().isoformat()', s)

    def test_core_read_write_and_link_contracts_are_preserved(self):
        s = self.owner
        self.assertIn('existentes = await get_rows(', s)
        self.assertIn('propiedades_existentes = await get_rows(', s)
        self.assertIn('vinculos_existentes = await get_rows(', s)
        self.assertIn('await patch_rows(', s)
        self.assertIn('accepted_statuses=(200, 204)', s)
        self.assertIn('await post_rows(', s)
        self.assertIn('accepted_statuses=(200, 201, 204)', s)
        self.assertIn('"user_id":    agente_uid or user_id' if self.prepared else '"user_id": agente_uid or user_id', s)
        self.assertIn('"org_id":', s)
        self.assertIn('"relacion": "interes"', s)
        self.assertIn('except httpx.HTTPStatusError:', s)

    def test_response_shape_and_sources_compile(self):
        s = self.owner
        for key in (
            '"ok": True', '"filas":', '"importados":', '"actualizados":',
            '"omitidos":', '"vinculos":', '"sin_propiedad":', '"errores":',
            '"columnas":',
        ):
            self.assertIn(key, s)
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/contactos_importar_archivo.py", "exec")


if __name__ == "__main__":
    unittest.main()
