from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_spell_slots_runtime, ensure_warlock_runtime
from tools.services.combat.shared.grant_temporary_hp import GrantTemporaryHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseFiendishVigor:
    _FALSE_LIFE_MAX_TEMP_HP = 12

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)
        self.grant_temporary_hp = GrantTemporaryHp(encounter_repository, append_event)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_invocation_selected(actor)

        ensure_spell_slots_runtime(actor)
        previous_temp_hp = int(actor.hp.get("temp", 0) or 0)
        actor.action_economy["action_used"] = True
        self.encounter_repository.save(encounter)

        temp_hp_result = self.grant_temporary_hp.execute(
            encounter_id=encounter_id,
            target_id=actor.entity_id,
            temp_hp_amount=self._FALSE_LIFE_MAX_TEMP_HP,
            reason="warlock_fiendish_vigor_false_life",
            source_entity_id=actor.entity_id,
            mode="auto_higher",
        )

        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="class_feature_fiendish_vigor_used",
            actor_entity_id=actor.entity_id,
            target_entity_id=actor.entity_id,
            payload={
                "class_feature_id": "warlock.fiendish_vigor",
                "spell_id": "false_life",
                "temp_hp_amount": self._FALSE_LIFE_MAX_TEMP_HP,
                "temp_hp_before": previous_temp_hp,
                "temp_hp_after": temp_hp_result["temp_hp_after"],
                "temp_hp_decision": temp_hp_result["decision"],
            },
        )

        return {
            "encounter_id": encounter.encounter_id,
            "actor_id": actor.entity_id,
            "class_feature_result": {
                "fiendish_vigor": {
                    "spell_id": "false_life",
                    "temp_hp_amount": self._FALSE_LIFE_MAX_TEMP_HP,
                    "temp_hp_before": previous_temp_hp,
                    "temp_hp_after": temp_hp_result["temp_hp_after"],
                    "temp_hp_decision": temp_hp_result["decision"],
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

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_invocation_selected(self, actor: EncounterEntity) -> None:
        warlock = ensure_warlock_runtime(actor)
        fiendish_vigor = warlock.get("fiendish_vigor")
        if not isinstance(fiendish_vigor, dict) or not bool(fiendish_vigor.get("enabled")):
            raise ValueError("fiendish_vigor_not_available")
