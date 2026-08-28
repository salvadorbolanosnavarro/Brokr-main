"""Extract the bounded WhatsApp training GET/PUT API into its prepared router.

Removes exactly TrainingReq plus wa2_training_get/wa2_training_put from the root
router and mounts routers.whatsapp_training_api at the same router position.
The transform is AST-bounded and verifies the legacy decorator contract before
editing.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
IMPORT = "from routers.whatsapp_training_api import router as whatsapp_training_api_router\n"
MOUNT = "router.include_router(whatsapp_training_api_router)\n"
TARGET_FUNCS = {"wa2_training_get": "get", "wa2_training_put": "put"}


def _route_contract(node: ast.AsyncFunctionDef, method: str) -> bool:
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        if not isinstance(dec.func.value, ast.Name) or dec.func.value.id != "router":
            continue
        if dec.func.attr != method or not dec.args:
            continue
        arg = dec.args[0]
        return isinstance(arg, ast.Constant) and arg.value == "/entrenamiento"
    return False


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise SystemExit("WhatsApp training API is already extracted")

    tree = ast.parse(source)
    training_cls: ast.ClassDef | None = None
    funcs: dict[str, ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TrainingReq":
            if training_cls is not None:
                raise SystemExit("duplicate TrainingReq")
            training_cls = node
        elif isinstance(node, ast.AsyncFunctionDef) and node.name in TARGET_FUNCS:
            if node.name in funcs:
                raise SystemExit(f"duplicate target route: {node.name}")
            funcs[node.name] = node

    if training_cls is None:
        raise SystemExit("training source contract changed; TrainingReq missing")
    missing = sorted(set(TARGET_FUNCS) - set(funcs))
    if missing:
        raise SystemExit(f"training source contract changed; missing routes: {missing}")
    for name, method in TARGET_FUNCS.items():
        if not _route_contract(funcs[name], method):
            raise SystemExit(f"route decorator contract changed for {name}")

    targets: list[ast.AST] = [training_cls, *funcs.values()]
    spans: list[tuple[int, int]] = []
    for node in targets:
        end = getattr(node, "end_lineno", None)
        if end is None:
            raise SystemExit("training AST source span unavailable")
        start = min(
            [node.lineno]
            + [dec.lineno for dec in getattr(node, "decorator_list", [])]
        )
        spans.append((start, end))

    insert_line = min(start for start, _ in spans)
    lines = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        replacement = [IMPORT, MOUNT, "\n"] if start == insert_line else []
        lines[start - 1:end] = replacement
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    leftovers = {
        node.name
        for node in final_tree.body
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
        and node.name in {"TrainingReq", *TARGET_FUNCS}
    }
    if leftovers:
        raise SystemExit(f"legacy training API survived: {sorted(leftovers)}")
    if updated.count(IMPORT.strip()) != 1 or updated.count(MOUNT.strip()) != 1:
        raise SystemExit("training router mount contract changed")
    if "class ProbarReq(BaseModel):" not in updated or "async def wa2_probar(" not in updated:
        raise SystemExit("training extraction crossed /probar boundary")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp training API: GET/PUT /entrenamiento")


if __name__ == "__main__":
    main()
