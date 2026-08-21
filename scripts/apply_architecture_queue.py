#!/usr/bin/env python3
"""Apply the prepared Broquer architecture transforms in a deterministic order.

This script is intentionally fail-fast. Every individual transform owns its
anchors, compile guard and idempotence rules; this runner merely sequences
those already-reviewed cuts so an executable checkout can advance the branch
without hand-editing the monoliths.

Destructive *routes* may be moved by static source transforms, but this script
never invokes HTTP endpoints or application data operations.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass


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
    Step("whatsapp-property-view", "scripts.refactor_whatsapp_extract_property_view_core"),
    Step("whatsapp-stats", "scripts.refactor_whatsapp_extract_stats_core"),
    Step("whatsapp-stats-api", "scripts.refactor_whatsapp_extract_stats_api_core"),
    Step("whatsapp-cloud-api", "scripts.refactor_whatsapp_extract_cloud_api_core"),
    Step("whatsapp-appointments", "scripts.refactor_whatsapp_extract_appointments_core"),
    Step("whatsapp-media-storage", "scripts.refactor_whatsapp_extract_media_storage_core"),
    Step("whatsapp-webhook-auth", "scripts.refactor_whatsapp_extract_webhook_verify_core"),
    Step("whatsapp-connection", "scripts.refactor_whatsapp_extract_connection_core"),
    Step("whatsapp-team-number-verify", "scripts.refactor_whatsapp_connection_team_verify_core"),
    Step("whatsapp-training-api", "scripts.refactor_whatsapp_extract_training_api_core"),
    Step("whatsapp-templates", "scripts.refactor_whatsapp_extract_templates_core"),
    Step("whatsapp-inbox-read", "scripts.refactor_whatsapp_extract_inbox_read_core"),
    Step("whatsapp-inbox-send", "scripts.refactor_whatsapp_extract_inbox_send_core"),
    Step("whatsapp-inbox-read-state", "scripts.refactor_whatsapp_extract_inbox_read_state_core"),
    Step("whatsapp-conversation-settings", "scripts.refactor_whatsapp_extract_conversation_settings_core"),
    Step("whatsapp-contact-notes", "scripts.refactor_whatsapp_extract_contact_notes_core"),
    Step("whatsapp-contact-settings", "scripts.refactor_whatsapp_extract_contact_settings_core"),
    Step("whatsapp-automations-api", "scripts.refactor_whatsapp_extract_automations_api_core"),
    Step("whatsapp-campaigns-read", "scripts.refactor_whatsapp_extract_campaigns_read_core"),
    Step("whatsapp-delete-static", "scripts.refactor_whatsapp_extract_delete_core"),
]


def _run_step(step: Step) -> None:
    mod = importlib.import_module(step.module)
    main = getattr(mod, "main", None)
    if not callable(main):
        raise RuntimeError(f"{step.module} does not expose main()")
    print(f"[architecture] APPLY {step.name}")
    main()


def main() -> None:
    for step in STEPS:
        _run_step(step)
    print(f"[architecture] OK: {len(STEPS)} transforms applied")


if __name__ == "__main__":
    main()
