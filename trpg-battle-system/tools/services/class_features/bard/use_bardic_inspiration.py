from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_bard_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseBardicInspiration:
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
        allow_out_of_turn_actor: bool = False,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
        target = self._get_entity_or_raise(encounter, target_id, label="target")

        if not allow_out_of_turn_actor:
            self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)
        self._ensure_target_is_other(actor_id, target_id)
        self._ensure_within_range(actor, target, maximum_feet=60)

        bard = ensure_bard_runtime(actor)
        inspiration = bard.get("bardic_inspiration")
        if not isinstance(inspiration, dict):
            raise ValueError("bardic_inspiration_not_available")

        uses_current = inspiration.get("uses_current")
        if isinstance(uses_current, bool) or not isinstance(uses_current, int) or uses_current <= 0:
            raise ValueError("bardic_inspiration_no_remaining_uses")

        die = str(inspiration.get("die") or "").strip().lower()
        if not die:
            raise ValueError("bardic_inspiration_die_missing")

        if not isinstance(target.combat_flags, dict):
            target.combat_flags = {}
        target.combat_flags["bardic_inspiration"] = {
            "die": die,
            "source_entity_id": actor_id,
            "source_name": actor.name,
        }
        actor.action_economy["bonus_action_used"] = True
        inspiration["uses_current"] = uses_current - 1
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_bardic_inspiration_used",
            actor_entity_id=actor_id,
            target_entity_id=target_id,
            payload={
                "class_feature_id": "bard.bardic_inspiration",
                "granted_die": die,
                "uses_remaining": inspiration["uses_current"],
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "class_feature_result": {
                "bardic_inspiration": {
                    "granted_die": die,
                    "uses_remaining": inspiration["uses_current"],
                    "source_entity_id": actor_id,
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str, *, label: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"{label} '{entity_id}' not found in encounter")
        return entity

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_target_is_other(self, actor_id: str, target_id: str) -> None:
        if actor_id == target_id:
            raise ValueError("bardic_inspiration_cannot_target_self")

    def _ensure_within_range(self, actor: EncounterEntity, target: EncounterEntity, *, maximum_feet: int) -> None:
        dx = abs(actor.position["x"] - target.position["x"])
        dy = abs(actor.position["y"] - target.position["y"])
        if max(dx, dy) * 5 > maximum_feet:
            raise ValueError("bardic_inspiration_target_out_of_range")
