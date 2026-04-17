from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_help_attack import UseHelpAttack


def use_help_attack(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = UseHelpAttack(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
        target_id=str(args["target_id"]),
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
