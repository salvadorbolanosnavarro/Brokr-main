"""Permanent guards for static extraction of POST /easybroker/import-all."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "easybroker_migration.py"
TRANSFORM = ROOT / "scripts" / "refactor_main_extract_easybroker_import_all_core.py"


class EasyBrokerImportAllExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.transform = TRANSFORM.read_text(encoding="utf-8")

    def test_route_has_exactly_one_owner_in_prepared_or_certified_state(self):
        route_in_main = '@app.post("/easybroker/import-all")' in self.main
        factory_imported = (
            "from routers.easybroker_migration import create_import_all_router"
            in self.main
        )
        factory_included = "app.include_router(create_import_all_router(" in self.main
        self.assertEqual(factory_imported, factory_included)
        self.assertNotEqual(route_in_main, factory_imported)
        self.assertIn('@import_all_router.post("/easybroker/import-all")', self.router)
        # Prepared state must not expose the factory route through the already-mounted router.
        self.assertNotIn('@router.post("/easybroker/import-all")', self.router)

    def test_auth_configuration_and_status_contract_are_preserved(self):
        router = self.router
        self.assertIn('status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión."', router)
        self.assertIn('status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker antes de importar."', router)
        self.assertIn('status_code=500, detail="Supabase no está configurado en el servidor."', router)
        self.assertIn('pedidos = (body_imp or {}).get("statuses")', router)
        self.assertIn('statuses_elegidos = list(eb_status_default)', router)
        self.assertIn('fotos_diferidas = bool((body_imp or {}).get("fotos_diferidas"))', router)

    def test_current_user_org_ownership_semantics_are_frozen_for_extraction(self):
        router = self.router
        # This mixed legacy behavior is intentional for the extraction only:
        # existing rows are looked up by user_id, while writes conflict org-wide.
        self.assertIn('{"user_id": f"eq.{user_id}"', router)
        self.assertIn('org_id_import = await get_org_id_for_user_dep(user_id)', router)
        self.assertIn('status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte."', router)
        self.assertIn('inmueble["org_id"] = org_id_import', router)
        self.assertIn('conflict="org_id,eb_public_id"', router)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', router)

    def test_easybroker_pagination_rate_limit_and_retry_contract_are_preserved(self):
        router = self.router
        self.assertIn('while pagina <= 400:', router)
        self.assertIn('[("limit", 50), ("page", pagina),', router)
        self.assertIn('("search[statuses][]", eb_status)]', router)
        self.assertIn('if len(ids_published) >= eb_limite_propiedades:', router)
        self.assertIn('batch = eb_lote', router)
        self.assertIn('resto = eb_pausa_lote - (time_dep.monotonic() - inicio_lote)', router)
        self.assertIn('if lotes_fallidos_seguidos >= 4:', router)
        self.assertIn('status_code=429, detail="EasyBroker está limitando las peticiones de tu cuenta (429 sostenido).', router)
        self.assertIn('for intento in range(3):', router)
        self.assertIn('await asyncio_dep.sleep(1.5 * (2 ** intento))', router)

    def test_mapping_preservation_progress_and_photos_contract_are_preserved(self):
        router = self.router
        self.assertIn('inmueble = eb_to_brokr(prop_full, user_id)', router)
        self.assertIn('inmueble["notas"] = prev["notas"]', router)
        self.assertIn('inmueble["estatus"] = prev["estatus"]', router)
        self.assertIn('prog(user_id, f"propiedades {min(i + batch, len(ids_published))} de {len(ids_published)}")', router)
        self.assertIn('asyncio_dep.create_task(migrar_fotos_org(org_id_import))', router)

    def test_response_schema_is_preserved(self):
        router = self.router
        for key in (
            "total_easybroker", "importadas", "actualizadas", "ya_existian",
            "por_estatus", "statuses", "descartadas", "limite",
            "limite_alcanzado", "fotos_en_proceso", "errores",
        ):
            self.assertIn(f'"{key}":', router)

    def test_transform_is_ast_bounded(self):
        self.assertIn("import ast", self.transform)
        self.assertIn('TARGET_FUNCTION = "easybroker_import_all"', self.transform)
        self.assertNotIn("anchor", self.transform.lower())
        self.assertIn("ast.parse(updated)", self.transform)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/easybroker_migration.py", "exec")
        compile(self.transform, "scripts/refactor_main_extract_easybroker_import_all_core.py", "exec")


if __name__ == "__main__":
    unittest.main()
