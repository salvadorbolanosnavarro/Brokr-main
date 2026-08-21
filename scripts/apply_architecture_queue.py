#!/usr/bin/env python3
"""Preflight and apply the prepared Broquer architecture transforms as one batch.

Every transform is first simulated in memory, in dependency order, against the
output of previous transforms for the same target file. Nothing is written
until *all* transforms have found their exact anchors and passed their compile
checks. This prevents a late transform failure from leaving ``main.py`` or
``whatsapp.py`` half-refactored.

Destructive *routes* may be moved by static source transforms, but this runner
never invokes HTTP endpoints or application data operations.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Step:
    name: str
    module: str


STEPS = [
    Step("admin-usage", "scripts.refactor_main_extract_admin_usage_core"),
    Step("self-account-delete-static", "scripts.refactor_main_extract_account_delete_core"),
    Step("avm-legacy", "scripts.refactor_main_extract_avm_legacy_core"),
    Step("avm-claude", "scripts.refactor_main_extract_avm_claude_core"),
    Step("avm-websearch-ssrf", "scripts.refactor_main_avm_websearch_ssrf_core"),
    Step("facebook-token-encryption", "scripts.refactor_main_facebook_token_encryption_fail_closed_core"),
    Step("whatsapp-secret-defaults", "scripts.refactor_whatsapp_security_defaults_core"),
    Step("whatsapp-chatgpt-register-pin", "scripts.refactor_whatsapp_chatgpt_register_pin_guard_core"),
    Step("whatsapp-data", "scripts.refactor_whatsapp_extract_data_core"),
    Step("whatsapp-policy", "scripts.refactor_whatsapp_extract_policy_core"),
    Step("whatsapp-utils", "scripts.refactor_whatsapp_extract_utils_core"),
    Step("whatsapp-time", "scripts.refactor_whatsapp_extract_time_core"),
    Step("whatsapp-access", "scripts.refactor_whatsapp_extract_access_core"),
    Step("whatsapp-identity", "scripts.refactor_whatsapp_extract_identity_core"),
    Step("whatsapp-training-policy", "scripts.refactor_whatsapp_extract_training_core"),
    Step("whatsapp-handoff", "scripts.refactor_whatsapp_extract_handoff_core"),
    Step("whatsapp-messages", "scripts.refactor_whatsapp_extract_messages_core"),
    Step("whatsapp-crm-bridge", "scripts.refactor_whatsapp_extract_crm_bridge_core"),
    Step("whatsapp-contacts", "scripts.refactor_whatsapp_extract_contacts_core"),
    Step("whatsapp-property-view", "scripts.refactor_whatsapp_extract_property_view_core"),
    Step("whatsapp-stats", "scripts.refactor_whatsapp_extract_stats_core"),
    Step("whatsapp-stats-api", "scripts.refactor_whatsapp_extract_stats_api_core"),
    Step("whatsapp-cloud-api", "scripts.refactor_whatsapp_extract_cloud_api_core"),
    Step("whatsapp-media-ai", "scripts.refactor_whatsapp_extract_media_ai_core"),
    Step("whatsapp-media-ai-usage", "scripts.refactor_whatsapp_media_ai_usage_core"),
    Step("whatsapp-webhook-messages", "scripts.refactor_whatsapp_extract_webhook_messages_core"),
    Step("whatsapp-appointments", "scripts.refactor_whatsapp_extract_appointments_core"),
    Step("whatsapp-media-storage", "scripts.refactor_whatsapp_extract_media_storage_core"),
    Step("whatsapp-webhook-auth", "scripts.refactor_whatsapp_extract_webhook_verify_core"),
    Step("whatsapp-webhook-post-auth", "scripts.refactor_whatsapp_webhook_post_auth_core"),
    Step("whatsapp-connection", "scripts.refactor_whatsapp_extract_connection_core"),
    Step("whatsapp-team-number-verify", "scripts.refactor_whatsapp_connection_team_verify_core"),
    Step("whatsapp-training-api", "scripts.refactor_whatsapp_extract_training_api_core"),
    Step("whatsapp-templates", "scripts.refactor_whatsapp_extract_templates_core"),
    Step("whatsapp-template-send", "scripts.refactor_whatsapp_extract_template_send_core"),
    Step("whatsapp-inbox-read", "scripts.refactor_whatsapp_extract_inbox_read_core"),
    Step("whatsapp-inbox-send", "scripts.refactor_whatsapp_extract_inbox_send_core"),
    Step("whatsapp-inbox-read-state", "scripts.refactor_whatsapp_extract_inbox_read_state_core"),
    Step("whatsapp-conversation-settings", "scripts.refactor_whatsapp_extract_conversation_settings_core"),
    Step("whatsapp-contact-notes", "scripts.refactor_whatsapp_extract_contact_notes_core"),
    Step("whatsapp-contact-settings", "scripts.refactor_whatsapp_extract_contact_settings_core"),
    Step("whatsapp-automations-api", "scripts.refactor_whatsapp_extract_automations_api_core"),
    Step("whatsapp-campaigns-read", "scripts.refactor_whatsapp_extract_campaigns_read_core"),
    Step("whatsapp-campaigns-send", "scripts.refactor_whatsapp_extract_campaigns_send_core"),
    Step("whatsapp-delete-static", "scripts.refactor_whatsapp_extract_delete_core"),
]

_TARGET_ATTRS = ("TARGET", "MAIN", "CONFIG")


def _load_step(step: Step):
    mod = importlib.import_module(step.module)
    transform = getattr(mod, "transform_source", None)
    if not callable(transform):
        raise RuntimeError(f"{step.module} does not expose transform_source()")
    targets = []
    for attr in _TARGET_ATTRS:
        value = getattr(mod, attr, None)
        if isinstance(value, Path):
            targets.append(value.resolve())
    targets = list(dict.fromkeys(targets))
    if len(targets) != 1:
        raise RuntimeError(
            f"{step.module} must expose exactly one source target through "
            f"{', '.join(_TARGET_ATTRS)}; found {targets!r}"
        )
    return transform, targets[0]


def preflight() -> dict[Path, str]:
    """Return final in-memory contents after every transform validates."""
    staged: dict[Path, str] = {}
    for index, step in enumerate(STEPS, start=1):
        transform, target = _load_step(step)
        if not target.exists():
            raise RuntimeError(f"target for {step.name} does not exist: {target}")
        source = staged.get(target)
        if source is None:
            source = target.read_text(encoding="utf-8")
        print(f"[architecture] CHECK {index:02d}/{len(STEPS)} {step.name}")
        staged[target] = transform(source)
    return staged


def apply(staged: dict[Path, str]) -> None:
    """Write only after the complete queue has passed preflight."""
    for target, content in staged.items():
        current = target.read_text(encoding="utf-8")
        if current == content:
            continue
        tmp = target.with_name(target.name + ".architecture-next")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
        print(f"[architecture] WRITE {target.name}")


def main() -> None:
    staged = preflight()
    print(f"[architecture] PREFLIGHT OK: {len(STEPS)} transforms")
    apply(staged)
    print(f"[architecture] APPLY OK: {len(STEPS)} transforms")


if __name__ == "__main__":
    main()
