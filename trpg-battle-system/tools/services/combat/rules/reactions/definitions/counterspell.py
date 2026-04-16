from __future__ import annotations

from typing import Any

from tools.services.combat.rules.reactions.templates.cast_interrupt_contest import CastInterruptContest


class ResolveCounterspellReaction:
    """Resolver placeholder for Counterspell."""

    def __init__(self, template: CastInterruptContest) -> None:
        self.template = template

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        final_total: int | None = None,
        dice_rolls: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        actor_entity_id = str(request.get("actor_entity_id"))
        target_entity_id = request.get("target_entity_id")
        payload = request.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        return self.template.execute(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=str(target_entity_id) if target_entity_id is not None else None,
            payload=payload_data,
        )
