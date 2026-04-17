from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.grapple.use_grapple import UseGrapple


def use_grapple(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = UseGrapple(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
        target_id=str(args["target_id"]),
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
