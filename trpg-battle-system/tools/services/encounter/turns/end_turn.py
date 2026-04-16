from __future__ import annotations

from tools.models.encounter import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.weapon_mastery_effects import remove_expired_weapon_mastery_effects
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.turn_effects import resolve_turn_effects
from tools.services.encounter.turns.turn_engine import end_turn
from tools.services.encounter.zones import resolve_zone_effects
from tools.services.events.append_event import AppendEvent


class EndTurn:
    """遭遇战回合结束入口。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event

    def execute(self, encounter_id: str) -> Encounter:
        saved, _ = self._execute_internal(encounter_id)
        return saved

    def execute_with_state(self, encounter_id: str) -> dict[str, object]:
        saved, resolutions = self._execute_internal(encounter_id)
        return {
            "encounter_id": saved.encounter_id,
            "turn_effect_resolutions": resolutions,
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }

    def _execute_internal(self, encounter_id: str) -> tuple[Encounter, list[dict[str, object]]]:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        if encounter.current_entity_id is None:
            raise ValueError("cannot end turn without current_entity_id")

        updated = end_turn(encounter)
        remove_expired_weapon_mastery_effects(
            encounter=updated,
            source_entity_id=updated.current_entity_id,
            timing="end_of_source_turn",
        )
        resolutions = resolve_turn_effects(
            encounter=updated,
            entity_id=updated.current_entity_id,
            trigger="end_of_turn",
        )
        zone_resolutions = resolve_zone_effects(
            encounter=updated,
            entity_id=updated.current_entity_id,
            trigger="end_of_turn_inside",
        )
        saved = self.repository.save(updated)
        self._append_turn_effect_events(saved, resolutions)
        self._append_zone_effect_events(saved, zone_resolutions)
        self._append_turn_ended_event(saved)
        return saved, resolutions + zone_resolutions

    def _append_turn_effect_events(self, encounter: Encounter, resolutions: list[dict[str, object]]) -> None:
        if self.append_event is None:
            return
        for resolution in resolutions:
            if not isinstance(resolution, dict):
                continue
            trigger = resolution.get("trigger")
            effect_id = resolution.get("effect_id")
            if not isinstance(trigger, str) or not isinstance(effect_id, str):
                continue
            self.append_event.execute(
                encounter_id=encounter.encounter_id,
                round=encounter.round,
                event_type="turn_effect_resolved",
                actor_entity_id=resolution.get("source_entity_id"),
                target_entity_id=resolution.get("target_entity_id"),
                payload=dict(resolution),
            )

    def _append_zone_effect_events(self, encounter: Encounter, resolutions: list[dict[str, object]]) -> None:
        if self.append_event is None:
            return
        for resolution in resolutions:
            if not isinstance(resolution, dict):
                continue
            zone_id = resolution.get("zone_id")
            trigger = resolution.get("trigger")
            if not isinstance(zone_id, str) or not isinstance(trigger, str):
                continue
            self.append_event.execute(
                encounter_id=encounter.encounter_id,
                round=encounter.round,
                event_type="zone_effect_resolved",
                actor_entity_id=resolution.get("source_entity_id"),
                target_entity_id=resolution.get("target_entity_id"),
                payload=dict(resolution),
            )

    def _append_turn_ended_event(self, encounter: Encounter) -> None:
        if self.append_event is None or encounter.current_entity_id is None:
            return

        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="turn_ended",
            actor_entity_id=encounter.current_entity_id,
        )
