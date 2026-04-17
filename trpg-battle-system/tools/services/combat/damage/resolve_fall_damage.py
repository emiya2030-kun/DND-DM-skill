from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import get_monk_runtime
from tools.services.combat.shared.update_hp import UpdateHp


class ResolveFallDamage:
    """最小坠落伤害入口，允许武僧用 Slow Fall 减伤。"""

    def __init__(self, *, encounter_repository: EncounterRepository, update_hp: UpdateHp):
        self.encounter_repository = encounter_repository
        self.update_hp = update_hp

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        damage: int,
        use_slow_fall: bool = False,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(damage, int) or damage < 0:
            raise ValueError("damage must be a non-negative integer")

        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        reduction = 0
        if use_slow_fall:
            if bool(actor.action_economy.get("reaction_used")):
                raise ValueError("reaction_already_used")
            monk = get_monk_runtime(actor)
            if not monk:
                raise ValueError("slow_fall_not_available")
            level = monk.get("level")
            if not isinstance(level, int) or level <= 0:
                raise ValueError("slow_fall_not_available")
            reduction = level * 5
            actor.action_economy["reaction_used"] = True
            self.encounter_repository.save(encounter)

        final_damage = max(0, damage - reduction)
        hp_update = self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=actor_id,
            hp_change=final_damage,
            reason="fall_damage",
            damage_type="bludgeoning",
            source_entity_id=None,
            include_encounter_state=include_encounter_state,
        )
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "fall_resolution": {
                "base_damage": damage,
                "reduction": reduction,
                "final_damage": final_damage,
                "used_slow_fall": use_slow_fall,
            },
            "hp_update": hp_update,
            **({"encounter_state": hp_update["encounter_state"]} if include_encounter_state else {}),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor
