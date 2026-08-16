#!/usr/bin/env python3
"""Route /profile/status's organization subscription read through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

NEW_BRANCH = '''        else:
            # La suscripción cuelga de la ORG: en una empresa la paga el
            # titular y la heredan todos sus agentes.
            _oid = await get_org_id_for_user(user_id)
            sub_rows = await get_rows(
                "suscripciones",
                {"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"},
                timeout=6,
            )
            if sub_rows:
                row = sub_rows[0]
                _st = row.get("status")
                _act = _st in ("active", "trialing")
                if _st == "trialing" and row.get("trial_hasta") and _trial_ya_vencio(row.get("trial_hasta")):
                    _act = False
                    _st = "trial_vencido"
                    asyncio.create_task(_expirar_trial_suscripcion(row.get("id")))
                sub_state = {
                    "active": _act,
                    "plan": row.get("plan_nombre"),
                    "status": _st,
                }
'''


def transform_source(source: str) -> str:
    fn_start = source.index('@app.get("/profile/status")')
    branch_marker = '        else:\n            async with httpx.AsyncClient(timeout=6) as client:\n'
    core_marker = '        else:\n            # La suscripción cuelga de la ORG: en una empresa la paga el\n'
    old_start = source.find(branch_marker, fn_start)
    if old_start == -1:
        core_start = source.find(core_marker, fn_start)
        if core_start != -1:
            outer_except = source.find('    except Exception:\n', core_start)
            if outer_except != -1 and 'sub_rows = await get_rows(' in source[core_start:outer_except]:
                return source
        raise RuntimeError("Could not find legacy or Core profile subscription branch")

    outer_except = source.find('    except Exception:\n', old_start)
    if outer_except == -1:
        raise RuntimeError("Could not find profile subscription fail-soft boundary")
    old = source[old_start:outer_except]
    required = (
        '/rest/v1/suscripciones',
        'rs.status_code == 200',
        'rs.json()',
        '_trial_ya_vencio',
        '_expirar_trial_suscripcion',
        'row.get("plan_nombre")',
    )
    for token in required:
        if token not in old:
            raise RuntimeError(f"Profile subscription legacy branch missing {token!r}")
    if old.count('/rest/v1/suscripciones') != 1:
        raise RuntimeError("Expected exactly one direct subscription read in profile branch")
    return source[:old_start] + NEW_BRANCH + source[outer_except:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
