"""Deterministically extract POST /facebook/create-ad from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT = "from routers.facebook_create_ad import router as facebook_create_ad_router\n"
MOUNT = "app.include_router(facebook_create_ad_router)\n"


def _is_route(node: ast.AST) -> bool:
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_create_ad":
        return False
    return any(
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and isinstance(dec.func.value, ast.Name)
        and dec.func.value.id == "app"
        and dec.func.attr == "post"
        and dec.args
        and isinstance(dec.args[0], ast.Constant)
        and dec.args[0].value == "/facebook/create-ad"
        for dec in node.decorator_list
    )


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise SystemExit("Facebook create-ad router already connected")

    tree = ast.parse(source)
    models = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FbCreateAdRequest"]
    routes = [node for node in tree.body if _is_route(node)]
    if len(models) != 1 or len(routes) != 1:
        raise SystemExit(f"expected one model/route, found models={len(models)} routes={len(routes)}")
    model, route = models[0], routes[0]
    if [arg.arg for arg in route.args.args] != ["req", "request"]:
        raise SystemExit("facebook_create_ad signature changed")

    model_block = ast.get_source_segment(source, model) or ""
    model_required = (
        "account_id: str",
        "campaign_name: str",
        "daily_budget_mxn: float = 50.0",
        "duration_days: int = 7",
        "age_min: int = 18",
        "age_max: int = 0",
        'country: str = "MX"',
        'city_type: str = "city"',
        'objective: str = "OUTCOME_ENGAGEMENT"',
        "publish_now: bool = False",
        "idempotency_key: str = \"\"",
        "custom_audience_ids: list = []",
        "excluded_audience_ids: list = []",
    )
    missing_model = [fragment for fragment in model_required if fragment not in model_block]
    if missing_model:
        raise SystemExit(f"FbCreateAdRequest contract changed: {missing_model}")

    block = ast.get_source_segment(source, route) or ""
    required = (
        "get_user_id_from_token(request)",
        'detail="No autenticado"',
        "_fb_get_meta_row(user_id)",
        'detail="Facebook no conectado"',
        'meta.get("page_id", "")',
        'meta.get("ad_account_id", "")',
        "req.account_id = server_account_id",
        "req.page_id = page_id",
        'f"{req.account_id}/promote_pages"',
        'params={"fields": "id", "limit": "100"}',
        'if req.post_id:',
        'optimization_goal = "CONVERSATIONS"',
        'billing_event = "IMPRESSIONS"',
        'target_status = "ACTIVE" if req.publish_now else "PAUSED"',
        'daily_budget_cents = int(req.daily_budget_mxn * 100)',
        'idem = (req.idempotency_key or "").strip()[:120]',
        "_fb_reservar_creacion(",
        'if estado_previo == "CREANDO":',
        'if estado_previo == "FALLIDO":',
        '"duplicado": True',
        'if not req.post_id and not images_b64:',
        'if len(images_b64) > 10:',
        'detail="Debes seleccionar una ciudad para el anuncio."',
        'f"{account_id}/adimages"',
        'ad_text = (req.ad_text or "")[:2200]',
        'headline = (req.headline or "")[:40]',
        '"is_adset_budget_sharing_enabled": False',
        '_fb_exigir_ok(r_camp, "Error creando campaña")',
        '"DELETE", str(rid)',
        '"targeting_automation": {"advantage_audience": 0}',
        'targeting["custom_audiences"]',
        'targeting["excluded_custom_audiences"]',
        '"destination_type": "MESSENGER"',
        '"object_story_id": req.post_id',
        '"type": "MESSAGE_PAGE"',
        'for nivel, rid in (("anuncio", ad_id), ("conjunto", adset_id), ("campaña", campaign_id))',
        'json_body={"status": "ACTIVE"}',
        'for rid in reversed(activados):',
        'json_body={"status": "PAUSED"}',
        '_fb_actualizar_entidad(row_id, {',
        '"ads_manager_url": ads_manager_url',
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"facebook_create_ad source contract changed: {missing}")

    lines = source.splitlines(keepends=True)
    ranges = []
    for node in (model, route):
        start = min([node.lineno, *(dec.lineno for dec in getattr(node, "decorator_list", []))]) - 1
        ranges.append((start, node.end_lineno))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        node for node in tree2.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    app_nodes = [
        node for node in tree3.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].end_lineno, MOUNT + "\n")
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(isinstance(node, ast.ClassDef) and node.name == "FbCreateAdRequest" for node in check.body):
        raise SystemExit("FbCreateAdRequest remains in main.py")
    if any(_is_route(node) for node in check.body):
        raise SystemExit("facebook_create_ad remains in main.py")
    if transformed.count(IMPORT.strip()) != 1 or transformed.count(MOUNT.strip()) != 1:
        raise SystemExit("unexpected create-ad import/mount count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/create-ad")


if __name__ == "__main__":
    main()
