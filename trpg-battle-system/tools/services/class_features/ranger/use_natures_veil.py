from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_ranger_runtime
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseNaturesVeil:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        ranger = ensure_ranger_runtime(actor)
        natures_veil = ranger.get("natures_veil")
        if not isinstance(natures_veil, dict) or not bool(natures_veil.get("enabled")):
            raise ValueError("natures_veil_not_available")

        remaining_uses = natures_veil.get("uses_remaining")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("natures_veil_no_remaining_uses")

        if "invisible" not in actor.conditions:
            actor.conditions.append("invisible")
        actor.action_economy["bonus_action_used"] = True
        natures_veil["uses_remaining"] = remaining_uses - 1

        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_natures_veil_{uuid4().hex[:12]}",
                "effect_type": "ranger_natures_veil",
                "name": "Nature's Veil",
                "trigger": "end_of_turn",
                "source_entity_id": actor.entity_id,
                "source_ref": "ranger:natures_veil",
                "expires_at": "end_of_next_turn",
                "remaining_end_triggers": 2,
            },
        )

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter.encounter_id,
            "actor_id": actor.entity_id,
            "class_feature_result": {
                "natures_veil": {
                    "condition_applied": "invisible",
                    "uses_remaining": natures_veil["uses_remaining"],
                    "duration": "until_end_of_next_turn",
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
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

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")
