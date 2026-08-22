"""Freeze the effective HTTP contract of the FastAPI app.

An extraction may move a handler to any module; what it must never do is change
the URL a client calls, the parameters it sends, the body it posts or the status
codes it gets back.  This test compares the *effective* contract -- taken from
``app.openapi()``, so ``APIRouter``/``include_router`` prefixes are already
resolved -- against a committed snapshot.

Regenerate deliberately, never to make a red test go green:

    python -m tests.test_http_contract_golden --update
"""
from __future__ import annotations

import json
import pathlib
import unittest

GOLDEN = pathlib.Path(__file__).parent / "golden" / "http_contract_effective.json"
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")


def effective_contract() -> dict:
    from main import app  # imported lazily so collection errors stay readable

    operations = []
    for path, item in (app.openapi().get("paths") or {}).items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "params": sorted(
                        "{}:{}{}".format(
                            p.get("in"), p.get("name"), "!" if p.get("required") else ""
                        )
                        for p in (operation.get("parameters") or [])
                    ),
                    "body": bool(operation.get("requestBody")),
                    "responses": sorted((operation.get("responses") or {}).keys()),
                }
            )
    operations.sort(key=lambda o: (o["path"], o["method"]))
    return {"count": len(operations), "operations": operations}


def _describe(expected: dict, actual: dict) -> str:
    key = lambda o: (o["path"], o["method"])  # noqa: E731
    old = {key(o): o for o in expected["operations"]}
    new = {key(o): o for o in actual["operations"]}
    lines = []
    for k in sorted(set(old) - set(new)):
        lines.append("  DESAPARECIÓ  {1} {0}".format(*k))
    for k in sorted(set(new) - set(old)):
        lines.append("  APARECIÓ     {1} {0}".format(*k))
    for k in sorted(set(old) & set(new)):
        if old[k] == new[k]:
            continue
        lines.append("  CAMBIÓ       {1} {0}".format(*k))
        for field in ("params", "body", "responses"):
            if old[k][field] != new[k][field]:
                lines.append(
                    "      {}: {!r} -> {!r}".format(field, old[k][field], new[k][field])
                )
    return "\n".join(lines)


class HTTPContractGoldenTests(unittest.TestCase):
    def test_effective_contract_is_unchanged(self):
        self.assertTrue(
            GOLDEN.exists(),
            "Falta {}. Genéralo con: python -m tests.test_http_contract_golden --update".format(
                GOLDEN.name
            ),
        )
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        actual = effective_contract()
        if expected != actual:
            self.fail(
                "El contrato HTTP efectivo cambió respecto al golden:\n"
                + _describe(expected, actual)
                + "\n\nUna extracción no debe mover ninguna de estas líneas. "
                "Si el cambio es intencional, regenera el golden a propósito."
            )


def _update() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(
        json.dumps(effective_contract(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("golden actualizado:", GOLDEN)


if __name__ == "__main__":
    import sys

    if "--update" in sys.argv:
        _update()
    else:
        unittest.main()
