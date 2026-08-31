"""Regression tests for validated multi-object Storage deletion."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from core.storage import delete_objects


def _fake_settings():
    return SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_service_key="service",
        require_supabase_service=lambda: None,
    )


class StorageBatchDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_traversal_before_network_access(self):
        with patch("core.storage.settings", _fake_settings()):
            with self.assertRaises(ValueError):
                await delete_objects("wa-media", ["user/ok.jpg", "../secret"])

    async def test_empty_batch_does_not_open_http_client(self):
        with (
            patch("core.storage.settings", _fake_settings()),
            patch("core.storage.httpx.AsyncClient") as client,
        ):
            await delete_objects("wa-media", [])
        client.assert_not_called()

    async def test_sends_normalized_prefixes_in_one_request(self):
        response = AsyncMock()
        response.raise_for_status = lambda: None
        client = AsyncMock()
        client.request.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client
        context.__aexit__.return_value = False

        with (
            patch("core.storage.settings", _fake_settings()),
            patch("core.storage.httpx.AsyncClient", return_value=context),
        ):
            await delete_objects("wa-media", ["user/a.jpg", "/user/b.pdf"])

        client.request.assert_awaited_once_with(
            "DELETE",
            "https://example.supabase.co/storage/v1/object/wa-media",
            headers={
                "apikey": "service",
                "Authorization": "Bearer service",
                "Content-Type": "application/json",
            },
            json={"prefixes": ["user/a.jpg", "user/b.pdf"]},
        )


if __name__ == "__main__":
    unittest.main()
