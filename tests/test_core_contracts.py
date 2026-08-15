"""Regression tests for Broquer's shared platform contracts."""
import os
import unittest
from unittest.mock import patch

from core.config import Settings
from core.http import UnsafePublicURL, assert_public_http_url
from core.modules import ModuleDefinition, ModuleRegistry
from core.permissions import (
    ROLE_ADMIN,
    ROLE_AGENT,
    ROLE_OWNER,
    VALID_PERMISSIONS,
    default_permission,
    effective_permission,
)


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


class OrganizationPermissionTests(unittest.TestCase):
    def test_owner_and_admin_defaults_are_allowed(self):
        for role in (ROLE_OWNER, ROLE_ADMIN):
            for permission in VALID_PERMISSIONS:
                with self.subTest(role=role, permission=permission):
                    self.assertTrue(default_permission(role, permission))

    def test_agent_sensitive_defaults_are_denied(self):
        for permission in (
            "ver_telefonos",
            "gestionar_integraciones",
            "ver_comisiones",
            "ver_estadisticas_equipo",
        ):
            with self.subTest(permission=permission):
                self.assertFalse(default_permission(ROLE_AGENT, permission))

    def test_explicit_boolean_override_wins(self):
        self.assertTrue(
            effective_permission(
                ROLE_AGENT,
                "gestionar_integraciones",
                {"gestionar_integraciones": True},
            )
        )
        self.assertFalse(
            effective_permission(
                ROLE_OWNER,
                "ver_telefonos",
                {"ver_telefonos": False},
            )
        )

    def test_unknown_role_or_permission_fails_closed(self):
        with self.assertRaises(ValueError):
            default_permission("superadmin", "ver_telefonos")
        with self.assertRaises(ValueError):
            default_permission(ROLE_AGENT, "permiso_inventado")


class PublicURLSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_loopback_is_rejected(self):
        for url in ("http://127.0.0.1/admin", "http://[::1]/admin"):
            with self.subTest(url=url):
                with self.assertRaises(UnsafePublicURL):
                    await assert_public_http_url(url)

    async def test_private_networks_are_rejected(self):
        for url in (
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(UnsafePublicURL):
                    await assert_public_http_url(url)

    async def test_localhost_and_non_http_schemes_are_rejected(self):
        for url in (
            "http://localhost/internal",
            "http://service.local/internal",
            "file:///etc/passwd",
            "ftp://example.com/file",
        ):
            with self.subTest(url=url):
                with self.assertRaises(UnsafePublicURL):
                    await assert_public_http_url(url)


if __name__ == "__main__":
    unittest.main()
