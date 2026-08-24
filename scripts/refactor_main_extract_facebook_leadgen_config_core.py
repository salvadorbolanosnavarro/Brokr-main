"""Deterministically move Facebook Lead Ads secret policy out of main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT_BLOCK = (
    "from core.facebook_leadgen_config import (\n"
    "    FB_VERIFY_TOKEN,\n"
    "    FB_WEBHOOK_SECRET as _FB_WEBHOOK_SECRET,\n"
    ")\n"
)
TARGETS = {"FB_VERIFY_TOKEN", "_FB_WEBHOOK_SECRET"}


def assignment_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = {name: [] for name in TARGETS}
    for node in tree.body:
        name = assignment_name(node)
        if name in found:
            found[name].append(node)
    for name, nodes in found.items():
        if len(nodes) != 1:
            raise SystemExit(f"expected exactly one {name} assignment, found {len(nodes)}")

    verify_block = ast.get_source_segment(source, found["FB_VERIFY_TOKEN"][0]) or ""
    webhook_block = ast.get_source_segment(source, found["_FB_WEBHOOK_SECRET"][0]) or ""
    if "legacy_main_settings.fb_verify_token" not in verify_block:
        raise SystemExit("FB_VERIFY_TOKEN source changed")
    if "legacy_main_settings.fb_webhook_secret or FB_APP_SECRET" not in webhook_block:
        raise SystemExit("Facebook webhook secret fallback changed")

    required_consumers = (
        "if not FB_VERIFY_TOKEN:",
        "if not _FB_WEBHOOK_SECRET:",
        "hmac.compare_digest(firma, esperada)",
        'status_code=503',
    )
    missing = [frag for frag in required_consumers if frag not in source]
    if missing:
        raise SystemExit(f"Lead Ads fail-closed consumers changed: {missing}")
    if "from core.facebook_leadgen_config import" in source:
        raise SystemExit("Lead Ads config already imported")

    lines = source.splitlines(keepends=True)
    spans = [(nodes[0].lineno - 1, nodes[0].end_lineno) for nodes in found.values()]
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_assignments = [
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assignments) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_assignments)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_assignments[0].lineno - 1, "\n" + IMPORT_BLOCK)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    leftovers = [assignment_name(n) for n in check.body if assignment_name(n) in TARGETS]
    if leftovers:
        raise SystemExit(f"Lead Ads config assignments still in main.py: {leftovers}")
    if transformed.count("from core.facebook_leadgen_config import (") != 1:
        raise SystemExit("unexpected Lead Ads config import count")
    for frag in required_consumers:
        if frag not in transformed:
            raise SystemExit(f"Lead Ads fail-closed consumer lost: {frag}")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook Lead Ads config core")


if __name__ == "__main__":
    main()
