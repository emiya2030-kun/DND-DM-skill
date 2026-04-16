from __future__ import annotations

from typing import Any

from tools.services.combat.rules.reactions.templates.leave_reach_interrupt import LeaveReachInterrupt


class ResolveOpportunityAttackReaction:
    """Resolver for the opportunity attack reaction."""

    def __init__(self, leave_reach_template: LeaveReachInterrupt) -> None:
        self.leave_reach_template = leave_reach_template

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        weapon_id = str(request.get("payload", {}).get("weapon_id", ""))
        if not weapon_id:
            raise ValueError("reaction_weapon_missing")
        actor_entity_id = str(request["actor_entity_id"])
        target_entity_id = str(request["target_entity_id"])
        return self.leave_reach_template.execute(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            weapon_id=weapon_id,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
        )
