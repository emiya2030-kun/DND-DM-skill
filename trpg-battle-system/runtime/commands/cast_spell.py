from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AppendEvent, ExecuteSpell, SpellRequest
from tools.services.shared.rule_validation_error import RuleValidationError


def _require_arg(args: dict[str, object], key: str) -> object:
    value = args.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{key} is required")
    return value


def cast_spell(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(_require_arg(args, "encounter_id"))
    actor_id = str(_require_arg(args, "actor_id"))
    spell_id = str(_require_arg(args, "spell_id"))

    cast_level = args.get("cast_level")
    if isinstance(cast_level, bool) or not isinstance(cast_level, int):
        raise ValueError("cast_level is required and must be an integer")

    execute_spell = ExecuteSpell(
        encounter_repository=context.encounter_repository,
        append_event=AppendEvent(context.event_repository),
        spell_request=SpellRequest(
            context.encounter_repository,
            context.spell_definition_repository,
        ),
    )
    result = execute_spell.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        spell_id=spell_id,
        cast_level=cast_level,
        target_entity_ids=args.get("target_entity_ids"),
        target_point=args.get("target_point"),
        save_rolls=args.get("save_rolls"),
        damage_rolls=args.get("damage_rolls"),
        attack_rolls=args.get("attack_rolls"),
        declared_action_cost=args.get("declared_action_cost"),
        context=args.get("context"),
        allow_out_of_turn_actor=bool(args.get("allow_out_of_turn_actor", False)),
    )

    if not bool(result.get("ok", True)):
        raise RuleValidationError(
            str(result.get("error_code") or "cast_spell_failed"),
            str(result.get("message") or result.get("error_code") or "cast_spell_failed"),
            rule_context=result.get("rule_context") if isinstance(result.get("rule_context"), dict) else None,
        )

    return {
        "encounter_id": encounter_id,
        "result": result,
        "encounter_state": context.get_encounter_state(encounter_id),
    }
