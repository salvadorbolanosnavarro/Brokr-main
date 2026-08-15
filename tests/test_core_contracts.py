"""Regression tests for Broquer's shared platform contracts."""
import os
import unittest
from unittest.mock import patch

from core.config import Settings
from core.modules import ModuleDefinition, ModuleRegistry


class SettingsTests(unittest.TestCase):
    def test_service_key_never_falls_back_to_anon_key(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.supabase_anon_key, "anon")
        self.assertEqual(settings.supabase_service_key, "")
        with self.assertRaises(RuntimeError):
            settings.require_supabase_service()

    def test_public_key_accepts_legacy_environment_name(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "legacy-anon",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.supabase_anon_key, "legacy-anon")


class ModuleContractTests(unittest.TestCase):
    def test_valid_module_definition(self):
        definition = ModuleDefinition(
            key="referidos",
            name="Referidos",
            description="Gestión de referidos inmobiliarios.",
            route_prefix="/referidos",
            navigation_path="/referidos.html",
            permissions=("referidos.ver",),
        )
        self.assertEqual(definition.key, "referidos")

    def test_module_key_rejects_spaces_and_uppercase(self):
        for key in ("Mi Modulo", "mi modulo", "Mi-modulo", ""):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    ModuleDefinition(
                        key=key,
                        name="Módulo",
                        description="Descripción",
                    )

    def test_duplicate_module_keys_are_rejected(self):
        registry = ModuleRegistry()
        definition = ModuleDefinition(
            key="bolsa",
            name="Bolsa",
            description="Bolsa inmobiliaria.",
        )
        registry.register(definition)
        with self.assertRaises(ValueError):
            registry.register(definition)

    def test_duplicate_permissions_are_rejected(self):
        with self.assertRaises(ValueError):
            ModuleDefinition(
                key="equipos",
                name="Equipos",
                description="Equipos de trabajo.",
                permissions=("equipo.ver", "equipo.ver"),
            )


if __name__ == "__main__":
    unittest.main()
