from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AttackRollRequest, AttackRollResult, ExecuteAttack, UpdateHp
from tools.services.events.append_event import AppendEvent


def _require_arg(args: dict[str, object], key: str) -> str:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return str(value)


def execute_attack(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = _require_arg(args, "encounter_id")
    actor_id = _require_arg(args, "actor_id")
    target_id = _require_arg(args, "target_id")
    weapon_id = _require_arg(args, "weapon_id")

    append_event = AppendEvent(context.event_repository)
    service = ExecuteAttack(
        AttackRollRequest(context.encounter_repository),
        AttackRollResult(
            encounter_repository=context.encounter_repository,
            append_event=append_event,
            update_hp=UpdateHp(context.encounter_repository, append_event),
        ),
    )

    payload = service.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        target_id=target_id,
        weapon_id=weapon_id,
        attack_mode=args.get("attack_mode"),
        grip_mode=args.get("grip_mode"),
        vantage=str(args.get("vantage") or "normal"),
        description=args.get("description"),
        zero_hp_intent=args.get("zero_hp_intent"),
        allow_out_of_turn_actor=bool(args.get("allow_out_of_turn_actor", False)),
        consume_action=bool(args.get("consume_action", True)),
        consume_reaction=bool(args.get("consume_reaction", False)),
        damage_rolls=list(args["damage_rolls"]) if "damage_rolls" in args and args.get("damage_rolls") is not None else None,
        include_encounter_state=True,
    )
    return {
        "encounter_id": encounter_id,
        "result": {
            "attack_result": payload,
        },
        "encounter_state": payload["encounter_state"],
    }
