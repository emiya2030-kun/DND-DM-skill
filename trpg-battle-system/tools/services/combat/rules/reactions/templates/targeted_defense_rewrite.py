from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import consume_lowest_available_spell_slot


class TargetedDefenseRewrite:
    """Resolve Shield by adding a temporary AC bonus and replaying the host attack."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_entity_id)
        resolved_target_id = target_entity_id or actor_entity_id
        if resolved_target_id != actor_entity_id:
            raise ValueError("shield_must_target_self")

        slot_consumed = self._consume_shield_resources(actor)
        actor.ac += 5
        actor.turn_effects.append(
            {
                "effect_id": f"effect_shield_{actor.entity_id}",
                "effect_type": "shield_ac_bonus",
                "name": "Shield",
                "source_entity_id": actor.entity_id,
                "target_entity_id": actor.entity_id,
                "trigger": "start_of_turn",
                "ac_bonus": 5,
                "save": None,
                "on_trigger": {},
                "on_save_success": {},
                "on_save_failure": {},
                "remove_after_trigger": True,
            }
        )
        self.encounter_repository.save(encounter)
        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "shield_applied",
                "actor_entity_id": actor_entity_id,
                "target_entity_id": resolved_target_id,
                "payload": payload or {},
                "slot_consumed": slot_consumed,
                "ac_bonus": 5,
                "new_ac": actor.ac,
            },
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str):
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _consume_shield_resources(self, actor: Any) -> dict[str, Any]:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        actor.action_economy["reaction_used"] = True

        try:
            return consume_lowest_available_spell_slot(actor, minimum_level=1)
        except ValueError as exc:
            raise ValueError("shield_requires_level_1_or_higher_slot")
