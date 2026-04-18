from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_warlock_runtime, has_selected_warlock_invocation
from tools.services.class_features.shared.warlock_invocations import resolve_gaze_of_two_minds_origin
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import get_center_position
from tools.services.events.append_event import AppendEvent


class UseGazeOfTwoMinds:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_id: str,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        target = self._get_actor_or_raise(encounter, target_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)
        self._ensure_invocation_selected(actor)
        self._ensure_touch_range(encounter=encounter, actor=actor, target=target)

        warlock = ensure_warlock_runtime(actor)
        gaze = warlock.get("gaze_of_two_minds")
        if not isinstance(gaze, dict):
            raise ValueError("gaze_of_two_minds_not_available")

        gaze["linked_entity_id"] = target.entity_id
        gaze["linked_entity_name"] = target.name
        gaze["remaining_source_turn_ends"] = 2
        gaze["special_senses"] = self._extract_special_senses(target)
        actor.action_economy["bonus_action_used"] = True
        self.encounter_repository.save(encounter)

        origin = resolve_gaze_of_two_minds_origin(encounter, actor)
        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_gaze_of_two_minds_used",
            actor_entity_id=actor_id,
            target_entity_id=target_id,
            payload={
                "class_feature_id": "warlock.gaze_of_two_minds",
                "linked_entity_id": gaze["linked_entity_id"],
                "linked_entity_name": gaze["linked_entity_name"],
                "remaining_source_turn_ends": gaze["remaining_source_turn_ends"],
                "special_senses": gaze["special_senses"],
                "can_cast_via_link": origin.get("can_cast_via_link", False),
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "gaze_of_two_minds": {
                    "linked_entity_id": gaze["linked_entity_id"],
                    "linked_entity_name": gaze["linked_entity_name"],
                    "remaining_source_turn_ends": gaze["remaining_source_turn_ends"],
                    "special_senses": gaze["special_senses"],
                    "can_cast_via_link": bool(origin.get("can_cast_via_link")),
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"actor '{entity_id}' not found in encounter")
        return entity

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_invocation_selected(self, actor: EncounterEntity) -> None:
        if not has_selected_warlock_invocation(actor, "gaze_of_two_minds"):
            raise ValueError("gaze_of_two_minds_not_available")

    def _ensure_touch_range(self, *, encounter: Encounter, actor: EncounterEntity, target: EncounterEntity) -> None:
        actor_center = get_center_position(actor)
        target_center = get_center_position(target)
        distance_feet = max(abs(actor_center["x"] - target_center["x"]), abs(actor_center["y"] - target_center["y"])) * encounter.map.grid_size_feet
        if distance_feet > 5:
            raise ValueError("gaze_of_two_minds_target_out_of_touch_range")

    def _extract_special_senses(self, target: EncounterEntity) -> dict[str, object]:
        senses = getattr(target, "senses", None)
        if isinstance(senses, dict):
            return dict(senses)
        source_ref = target.source_ref if isinstance(target.source_ref, dict) else {}
        for key in ("special_senses", "senses"):
            value = source_ref.get(key)
            if isinstance(value, dict):
                return dict(value)
        return {}
