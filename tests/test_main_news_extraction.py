"""Permanent guard for real-estate RSS news extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainNewsExtractionTests(unittest.TestCase):
    def test_news_route_preserves_feed_cache_and_failsoft_contract(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "news.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/noticias")', router)
        self.assertIn('cache_get("noticias_rss")', router)
        self.assertIn('httpx.AsyncClient(timeout=10, follow_redirects=True)', router)
        self.assertIn('headers={"User-Agent": "Mozilla/5.0"}', router)
        self.assertIn('channel.findall("item")[:8]', router)
        self.assertIn('if len(items) >= 12:', router)
        self.assertIn('except Exception:\n                continue', router)
        self.assertIn('return {"items": []}', router)
        self.assertIn('cache_set("noticias_rss", result, ttl=1800)', router)
        self.assertIn('from routers.news import router as news_router', main)
        self.assertNotIn('@app.get("/noticias")', main)
        compile(router, "routers/news.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
