from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.grapple.escape_grapple import EscapeGrapple


def escape_grapple(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = EscapeGrapple(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
