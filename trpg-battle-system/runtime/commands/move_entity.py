from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import BeginMoveEncounterEntity
from tools.services.events.append_event import AppendEvent


def _require_arg(args: dict[str, object], key: str) -> object:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return value


def move_entity(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(_require_arg(args, "encounter_id"))
    actor_id = str(_require_arg(args, "actor_id"))
    target_position = _require_arg(args, "target_position")

    append_event = AppendEvent(context.event_repository)
    movement_result = BeginMoveEncounterEntity(
        context.encounter_repository,
        append_event,
    ).execute_with_state(
        encounter_id=encounter_id,
        entity_id=actor_id,
        target_position=target_position,
        use_dash=bool(args.get("use_dash", False)),
        movement_mode=str(args.get("movement_mode") or "walk"),
    )

    return {
        "encounter_id": encounter_id,
        "result": movement_result,
        "encounter_state": movement_result["encounter_state"],
    }
