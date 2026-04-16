from __future__ import annotations

from typing import Any

from tools.services.combat.attack.execute_attack import ExecuteAttack


class LeaveReachInterrupt:
    """Template for reactions that interrupt leaving reach (e.g. opportunity attack)."""

    def __init__(self, execute_attack: ExecuteAttack) -> None:
        self.execute_attack = execute_attack

    def execute(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        weapon_id: str,
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        return self.execute_attack.execute(
            encounter_id=encounter_id,
            actor_id=actor_entity_id,
            target_id=target_entity_id,
            weapon_id=weapon_id,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
            consume_action=False,
            consume_reaction=True,
            allow_out_of_turn_actor=True,
        )
