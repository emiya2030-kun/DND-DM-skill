from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_dodge import UseDodge


def use_dodge(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(args["encounter_id"])
    actor_id = str(args["actor_id"])
    result = UseDodge(context.encounter_repository).execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
