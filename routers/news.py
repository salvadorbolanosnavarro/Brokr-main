"""Real-estate news RSS endpoint."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter

from core.cache import cache_get, cache_set


router = APIRouter()


@router.get("/noticias")
async def get_noticias():
    """Fetch real estate news from Google News RSS — parsed server-side to avoid CORS."""
    FEEDS = [
        "https://news.google.com/rss/search?q=bienes+raices+Mexico&hl=es-419&gl=MX&ceid=MX:es-419",
        "https://news.google.com/rss/search?q=mercado+inmobiliario+Mexico&hl=es-419&gl=MX&ceid=MX:es-419",
    ]

    cached = cache_get("noticias_rss")
    if cached is not None:
        return cached

    items = []
    seen = set()

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for feed_url in FEEDS:
            try:
                r = await client.get(feed_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.text)
                channel = root.find("channel")
                if channel is None:
                    continue
                for item in channel.findall("item")[:8]:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    source_el = item.find("source")
                    if title_el is None or link_el is None:
                        continue
                    title = title_el.text or ""
                    title = re.sub(r"\s*[-–]\s*[^-–]+$", "", title).strip()
                    link = link_el.text or ""
                    source = source_el.text if source_el is not None else "Google News"
                    if title in seen or not title or not link:
                        continue
                    seen.add(title)
                    items.append({"title": title, "url": link, "source": source})
                    if len(items) >= 12:
                        break
            except Exception:
                continue
            if len(items) >= 12:
                break

    if not items:
        return {"items": []}

    result = {"items": items}
    cache_set("noticias_rss", result, ttl=1800)
    return result
