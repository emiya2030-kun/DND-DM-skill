from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import (
    AttackRollRequest,
    AttackRollResult,
    BeginMoveEncounterEntity,
    ExecuteAttack,
    UpdateHp,
)
from tools.services.events.append_event import AppendEvent


def _require_arg(args: dict[str, object], key: str) -> object:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return value


def move_and_attack(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(_require_arg(args, "encounter_id"))
    actor_id = str(_require_arg(args, "actor_id"))
    target_position = _require_arg(args, "target_position")
    target_id = str(_require_arg(args, "target_id"))
    weapon_id = str(_require_arg(args, "weapon_id"))

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

    if movement_result["movement_status"] == "waiting_reaction":
        return {
            "encounter_id": encounter_id,
            "result": {
                "movement_result": movement_result,
                "attack_result": None,
            },
            "encounter_state": movement_result["encounter_state"],
        }

    execute_attack = ExecuteAttack(
        AttackRollRequest(context.encounter_repository),
        AttackRollResult(
            encounter_repository=context.encounter_repository,
            update_hp=UpdateHp(
                context.encounter_repository,
                append_event,
            ),
            append_event=append_event,
        ),
    )
    execute_kwargs = {
        "encounter_id": encounter_id,
        "actor_id": actor_id,
        "target_id": target_id,
        "weapon_id": weapon_id,
        "include_encounter_state": True,
    }
    if "damage_rolls" in args and args.get("damage_rolls") is not None:
        execute_kwargs["damage_rolls"] = list(args.get("damage_rolls"))
    attack_result = execute_attack.execute(**execute_kwargs)

    if attack_result.get("status") == "invalid_attack":
        return {
            "encounter_id": encounter_id,
            "error_code": "attack_invalid_after_movement",
            "result": {
                "movement_result": movement_result,
                "attack_result": attack_result,
            },
            "encounter_state": attack_result["encounter_state"],
        }

    return {
        "encounter_id": encounter_id,
        "result": {
            "movement_result": movement_result,
            "attack_result": attack_result,
        },
        "encounter_state": attack_result["encounter_state"],
    }
