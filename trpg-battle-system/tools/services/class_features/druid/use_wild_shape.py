from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_druid_runtime
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseWildShape:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        form_name: str,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        normalized_form_name = self._normalize_form_name(form_name)
        druid = ensure_druid_runtime(actor)
        wild_shape = druid.get("wild_shape")
        if not isinstance(wild_shape, dict) or not bool(wild_shape.get("enabled")):
            raise ValueError("wild_shape_not_available")

        remaining_uses = wild_shape.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("wild_shape_no_remaining_uses")
        if bool(wild_shape.get("active")):
            raise ValueError("wild_shape_already_active")

        active_temp_hp = int(actor.source_ref.get("level", 0) or druid.get("level", 0) or 0)
        actor.action_economy["bonus_action_used"] = True
        wild_shape["remaining_uses"] = remaining_uses - 1
        wild_shape["active"] = True
        wild_shape["active_form_name"] = normalized_form_name
        wild_shape["active_temp_hp"] = active_temp_hp
        wild_shape["activated_round"] = encounter.round
        wild_shape["activated_turn_entity_id"] = actor_id
        actor.hp["temp"] = max(int(actor.hp.get("temp", 0) or 0), active_temp_hp)

        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_wild_shape_{uuid4().hex[:12]}",
                "effect_type": "wild_shape_active",
                "name": f"Wild Shape: {normalized_form_name}",
                "trigger": "class_feature",
                "source_entity_id": actor.entity_id,
                "source_ref": "druid:wild_shape",
                "expires_at": None,
            },
        )

        self.encounter_repository.save(encounter)
        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_wild_shape_used",
            actor_entity_id=actor_id,
            payload={
                "class_feature_id": "druid.wild_shape",
                "active_form_name": normalized_form_name,
                "remaining_uses": wild_shape["remaining_uses"],
                "active_temp_hp": active_temp_hp,
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "wild_shape": {
                    "active_form_name": normalized_form_name,
                    "remaining_uses": wild_shape["remaining_uses"],
                    "active_temp_hp": active_temp_hp,
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

    def _normalize_form_name(self, form_name: str) -> str:
        normalized = str(form_name or "").strip()
        if not normalized:
            raise ValueError("wild_shape_form_invalid")
        return normalized
