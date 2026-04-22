from __future__ import annotations

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import consume_lowest_available_spell_slot, ensure_bard_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseFontOfInspiration:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
    ) -> dict[str, object]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")

        bard = ensure_bard_runtime(actor)
        font = bard.get("font_of_inspiration")
        if not isinstance(font, dict) or not bool(font.get("spell_slot_restore_enabled")):
            raise ValueError("font_of_inspiration_not_available")

        inspiration = bard.get("bardic_inspiration")
        if not isinstance(inspiration, dict):
            raise ValueError("bardic_inspiration_not_available")

        uses_current = inspiration.get("uses_current")
        uses_max = inspiration.get("uses_max")
        if not isinstance(uses_current, int) or not isinstance(uses_max, int):
            raise ValueError("bardic_inspiration_state_invalid")
        if uses_current >= uses_max:
            raise ValueError("bardic_inspiration_already_full")

        slot_consumed = consume_lowest_available_spell_slot(actor, minimum_level=1)
        inspiration["uses_current"] = min(uses_max, uses_current + 1)
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_font_of_inspiration_used",
            actor_entity_id=actor_id,
            payload={
                "class_feature_id": "bard.font_of_inspiration",
                "slot_level": slot_consumed["slot_level"],
                "resource_pool": slot_consumed["resource_pool"],
                "uses_current": inspiration["uses_current"],
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "font_of_inspiration": {
                    "slot_level": slot_consumed["slot_level"],
                    "resource_pool": slot_consumed["resource_pool"],
                    "uses_current": inspiration["uses_current"],
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }
