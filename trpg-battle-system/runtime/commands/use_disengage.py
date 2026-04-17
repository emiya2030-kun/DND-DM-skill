from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_disengage import UseDisengage


def use_disengage(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(args["encounter_id"])
    actor_id = str(args["actor_id"])
    result = UseDisengage(context.encounter_repository).execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
