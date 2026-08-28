from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "contact_file_import.py"


class ContactFileImportExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.legacy_owned = '@app.post("/contactos/importar-archivo")' in cls.main
        cls.owner = cls.main if cls.legacy_owned else cls.router

    def test_auth_file_and_parser_contract_is_preserved(self):
        o = self.owner
        self.assertIn('user_id = await get_user_id_from_token(request)', o)
        self.assertIn('status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión."', o)
        self.assertIn('status_code=500, detail="Supabase no está configurado en el servidor."', o)
        self.assertIn('status_code=400, detail="El archivo llegó vacío."', o)
        self.assertIn('if len(contenido) > 15 * 1024 * 1024:', o)
        self.assertIn('nombre_archivo.endswith((".xlsx", ".xls"))', o)
        self.assertIn('openpyxl.load_workbook(BytesIO(contenido), read_only=True, data_only=True)', o)
        self.assertIn('for enc in ("utf-8-sig", "utf-8", "latin-1"):', o)
        self.assertIn('delim = ";" if primera.count(";") > primera.count(",") else ","', o)

    def test_mapping_dedupe_and_legacy_tenant_contract_are_frozen(self):
        o = self.owner
        self.assertIn('_RE_EB = re.compile(r"EB-[A-Za-z0-9]{4,10}")', o)
        self.assertIn('org_id_import = await get_org_id_for_user(user_id)', o)
        self.assertIn('{"org_id": f"eq.{org_id_import}"} if org_id_import', o)
        self.assertIn('else {"user_id": f"eq.{user_id}"}', o)
        self.assertIn('"contactos_propiedades",', o)
        self.assertIn('{"select": "contacto_id,propiedad_id", "limit": "20000"}', o)
        self.assertIn('mapa_ag = await _mapa_agentes_org(org_id_import, user_id)', o)
        self.assertIn('existente = (por_tel.get(tel) if tel else None) or (por_email.get(email) if email else None)', o)
        self.assertIn('"org_id": org_id_import', o)
        self.assertIn('{"user_id": user_id, "contacto_id": contacto_id,', o)

    def test_write_semantics_and_response_shape_are_preserved(self):
        o = self.owner
        self.assertIn('await patch_rows(', o)
        self.assertIn('accepted_statuses=(200, 204)', o)
        self.assertIn('await post_rows(', o)
        self.assertIn('prefer="return=minimal"', o)
        self.assertIn('accepted_statuses=(200, 201, 204)', o)
        for key in ('"ok": True', '"filas":', '"importados":', '"actualizados":', '"omitidos":', '"vinculos":', '"sin_propiedad":', '"errores":', '"columnas":'):
            self.assertIn(key, o)

    def test_ownership_is_transitional_and_factory_wiring_is_exact(self):
        self.assertIn('@router.post("/contactos/importar-archivo")', self.router)
        self.assertIn('def create_router(get_context):', self.router)
        if self.legacy_owned:
            self.assertNotIn('create_contact_file_import_router', self.main)
        else:
            self.assertNotIn('@app.post("/contactos/importar-archivo")', self.main)
            self.assertIn('from routers.contact_file_import import create_router as create_contact_file_import_router', self.main)
            self.assertIn('app.include_router(create_contact_file_import_router(lambda: {', self.main)
            for seam in (
                '"get_user_id_from_token": get_user_id_from_token',
                '"HTTPException": HTTPException',
                '"SUPABASE_URL": SUPABASE_URL',
                '"SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY',
                '"re": re',
                '"datetime": datetime',
                '"get_org_id_for_user": get_org_id_for_user',
                '"httpx": httpx',
                '"get_rows": get_rows',
                '"_mapa_agentes_org": _mapa_agentes_org',
                '"patch_rows": patch_rows',
                '"post_rows": post_rows',
                '"_uuid": _uuid',
            ):
                self.assertIn(seam, self.main)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/contact_file_import.py", "exec")


if __name__ == "__main__":
    unittest.main()
