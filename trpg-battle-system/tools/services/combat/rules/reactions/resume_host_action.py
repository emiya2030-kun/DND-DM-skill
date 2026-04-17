from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from tools.services.combat.attack.execute_attack import ExecuteAttack
    from tools.services.spells.encounter_cast_spell import EncounterCastSpell


class ResumeHostAction:
    """Placeholder for host action resume logic (Task 4 minimal stub)."""

    def __init__(
        self,
        execute_attack: "ExecuteAttack",
        encounter_cast_spell: "EncounterCastSpell",
    ) -> None:
        self.execute_attack = execute_attack
        self.encounter_cast_spell = encounter_cast_spell

    def execute(self, *, encounter_id: str, pending_window: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(pending_window, dict):
            raise ValueError("pending_reaction_window_not_found")
        host_action_type = pending_window.get("host_action_type")
        snapshot = pending_window.get("host_action_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("host_action_snapshot_missing")

        if host_action_type == "attack":
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": self.execute_attack.execute(
                    encounter_id=encounter_id,
                    actor_id=snapshot.get("actor_id"),
                    target_id=snapshot.get("target_id"),
                    weapon_id=snapshot.get("weapon_id"),
                    final_total=snapshot.get("final_total"),
                    dice_rolls=snapshot.get("dice_rolls"),
                    damage_rolls=snapshot.get("damage_rolls"),
                    vantage=snapshot.get("vantage", "normal") or "normal",
                    description=snapshot.get("description"),
                    attack_mode=snapshot.get("attack_mode"),
                    grip_mode=snapshot.get("grip_mode"),
                    allow_out_of_turn_actor=bool(snapshot.get("allow_out_of_turn_actor", False)),
                    consume_action=bool(snapshot.get("consume_action", True)),
                    consume_reaction=bool(snapshot.get("consume_reaction", False)),
                    pending_damage_multiplier=snapshot.get("pending_damage_multiplier"),
                    host_action_id=snapshot.get("attack_id"),
                    skip_reaction_window=True,
                ),
                "pending_window": pending_window,
            }

        if host_action_type == "spell_cast":
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": self.encounter_cast_spell.execute(
                    encounter_id=encounter_id,
                    actor_id=snapshot.get("actor_id"),
                    spell_id=snapshot.get("spell_id"),
                    target_ids=snapshot.get("target_ids"),
                    target_point=snapshot.get("target_point"),
                    cast_level=snapshot.get("cast_level"),
                    allow_out_of_turn_actor=bool(snapshot.get("allow_out_of_turn_actor", False)),
                    skip_reaction_window=True,
                ),
                "pending_window": pending_window,
            }

        raise ValueError("unsupported_host_action_type")
