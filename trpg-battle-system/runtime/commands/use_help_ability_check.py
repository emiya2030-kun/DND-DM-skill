from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_help_ability_check import UseHelpAbilityCheck


def use_help_ability_check(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = UseHelpAbilityCheck(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
        ally_id=str(args["ally_id"]),
        check_type=str(args["check_type"]),
        check_key=str(args["check_key"]),
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
