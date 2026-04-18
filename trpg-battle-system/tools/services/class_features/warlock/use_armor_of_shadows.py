from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_spell_slots_runtime, ensure_warlock_runtime
from tools.services.combat.defense.armor_profile_resolver import refresh_entity_armor_class
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseArmorOfShadows:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

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
        self._ensure_unarmored(actor)

        ensure_spell_slots_runtime(actor)
        effect = self._build_mage_armor_effect(actor)
        self._upsert_mage_armor_effect(actor, effect)
        profile = refresh_entity_armor_class(actor)
        actor.action_economy["action_used"] = True
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_armor_of_shadows_used",
            actor_entity_id=actor_id,
            target_entity_id=actor_id,
            payload={
                "class_feature_id": "warlock.armor_of_shadows",
                "spell_id": "mage_armor",
                "effect_type": "mage_armor",
                "ac_after": profile["current_ac"],
                "duration_model": "until_long_rest_or_armor_equipped",
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "armor_of_shadows": {
                    "effect_type": "mage_armor",
                    "ac_after": profile["current_ac"],
                    "duration_model": "until_long_rest_or_armor_equipped",
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
        armor_of_shadows = warlock.get("armor_of_shadows")
        if not isinstance(armor_of_shadows, dict) or not bool(armor_of_shadows.get("enabled")):
            raise ValueError("armor_of_shadows_not_available")

    def _ensure_unarmored(self, actor: EncounterEntity) -> None:
        if actor.equipped_armor is not None:
            raise ValueError("mage_armor_requires_unarmored_target")

    def _build_mage_armor_effect(self, actor: EncounterEntity) -> dict[str, Any]:
        return {
            "effect_type": "mage_armor",
            "source_type": "class_feature",
            "source_entity_id": actor.entity_id,
            "source_name": actor.name,
            "source_ref": "armor_of_shadows",
            "duration_model": "until_long_rest_or_armor_equipped",
            "ends_when_equips_armor": True,
        }

    def _upsert_mage_armor_effect(self, actor: EncounterEntity, effect: dict[str, Any]) -> None:
        filtered_effects: list[dict[str, Any]] = []
        for existing in actor.turn_effects:
            if not isinstance(existing, dict):
                filtered_effects.append(existing)
                continue
            if str(existing.get("effect_type") or "").strip().lower() == "mage_armor":
                continue
            filtered_effects.append(existing)
        filtered_effects.append(effect)
        actor.turn_effects = filtered_effects
