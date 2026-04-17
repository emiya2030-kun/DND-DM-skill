from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AppendEvent, ExecuteAbilityCheck


def _require_arg(args: dict[str, object], key: str) -> object:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return value


def execute_ability_check(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(_require_arg(args, "encounter_id"))
    actor_id = str(_require_arg(args, "actor_id"))
    check_type = str(_require_arg(args, "check_type"))
    check = str(_require_arg(args, "check"))
    dc = _require_arg(args, "dc")
    if isinstance(dc, bool) or not isinstance(dc, int):
        raise ValueError("dc must be an integer")

    service = ExecuteAbilityCheck(
        encounter_repository=context.encounter_repository,
        append_event=AppendEvent(context.event_repository),
    )
    result = service.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        check_type=check_type,
        check=check,
        dc=dc,
        vantage=str(args.get("vantage") or "normal"),
        additional_bonus=int(args.get("additional_bonus") or 0),
        reason=args.get("reason"),
        include_encounter_state=True,
    )
    return {
        "encounter_id": encounter_id,
        "result": result,
        "encounter_state": result["encounter_state"],
    }
