"""Server-side Lead Ads verification and webhook secret policy."""
from __future__ import annotations

from core.config import settings
from core.legacy_main_config import legacy_main_settings


FB_VERIFY_TOKEN = legacy_main_settings.fb_verify_token
FB_WEBHOOK_SECRET = (
    legacy_main_settings.fb_webhook_secret
    or settings.legacy_main_fb_app_secret
)
