from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path("main.py")
PREFIX = "core.facebook_"
PROTECTED_BINDINGS = {
    # Permanent architecture seams required by extraction guards even when
    # main.py has no runtime AST load after the consumer moved to its router.
    "_fb_estado_token",
    "FACEBOOK_REQUIRED_SCOPES",
    "descifrar_secreto",
    "cifrar_secreto",
    "facebook_secret_encryption_available",
    "_fb_get_meta_row",
    "FB_API_VERSION",
    "FB_GRAPH",
    "_FB_CODIGOS_REINTENTABLES",
    "_FB_CODIGOS_TOKEN",
    "_FB_ERRORES_COMUNES",
    "_FB_ESPERA_BASE",
    "_FB_ESPERA_MAX",
    "_FB_REINTENTOS",
    "_FB_USAR_PROOF",
    "_fb_appsecret_proof",
    "_fb_debe_reintentar",
    "_fb_espera_por_uso",
    "_fb_exigir_ok",
    "_fb_friendly_error",
    "_fb_get_json",
    "_fb_parse_error",
    "_fb_batch",
    "_fb_patch_meta",
    "_FB_TOKEN_VIDA_DEFECTO",
    "_fb_debug_token",
    "_FB_BREAKDOWNS",
    "_FB_DATE_PRESETS",
    "_FB_INSIGHTS_FIELDS",
    "_FB_ACCIONES_CLAVE",
    "_fb_normaliza_insights",
    "FB_VERIFY_TOKEN",
    "_FB_WEBHOOK_SECRET",
    "_FB_TABLA_ENTIDADES",
    "_fb_tabla_falta",
    "_fb_avisa_migracion",
    "_FB_CAMPOS_LEAD",
    "_fb_buscar_dueno_de_pagina",
    "_fb_procesar_lead",
    "_fb_buscar_por_idempotencia",
    "_fb_reservar_creacion",
    "_fb_actualizar_entidad",
}


def _bound_names(node: ast.ImportFrom) -> list[str]:
    return [alias.asname or alias.name for alias in node.names]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    loaded = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    candidates: list[ast.ImportFrom] = []
    removed_names: list[str] = []
    protected_seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith(PREFIX):
            continue
        names = _bound_names(node)
        protected_seen.update(PROTECTED_BINDINGS & set(names))
        if PROTECTED_BINDINGS & set(names):
            continue
        if names and all(name not in loaded for name in names):
            candidates.append(node)
            removed_names.extend(names)

    missing_protected = sorted(PROTECTED_BINDINGS - protected_seen)
    if missing_protected:
        raise SystemExit(f"protected Facebook seams missing: {missing_protected}")

    if not candidates:
        raise SystemExit("no fully dead unguarded core.facebook_* imports found")

    # Keep the cut bounded: whole import declarations only, never partial edits.
    if len(candidates) > 12:
        raise SystemExit(f"unexpectedly broad facebook import cleanup: {len(candidates)} declarations")

    spans = sorted(
        ((node.lineno, node.end_lineno) for node in candidates),
        reverse=True,
    )
    lines = source.splitlines(keepends=True)
    for start, end in spans:
        del lines[start - 1 : end]

    updated = "".join(lines)
    ast.parse(updated)

    # Prove every removed binding had zero reads in the original AST and no
    # architecture-protected seam entered the cut.
    leaked = sorted(set(removed_names) & loaded)
    if leaked:
        raise SystemExit(f"refusing to remove live facebook bindings: {leaked}")
    protected_removed = sorted(set(removed_names) & PROTECTED_BINDINGS)
    if protected_removed:
        raise SystemExit(f"refusing to remove protected Facebook seams: {protected_removed}")

    MAIN.write_text(updated, encoding="utf-8")
    print(f"removed {len(candidates)} fully dead core.facebook_* import declarations")
    print("bindings:", ", ".join(sorted(removed_names)))


if __name__ == "__main__":
    main()
