from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.weapon_mastery_effects import remove_expired_weapon_mastery_effects
from tools.services.combat.rules.death_saves.resolve_death_save import resolve_death_save
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.turn_effects import resolve_turn_effects
from tools.services.encounter.turns.turn_engine import start_turn
from tools.services.encounter.zones import resolve_zone_effects
from tools.services.events.append_event import AppendEvent


class StartTurn:
    """遭遇战回合开始入口。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event

    def execute(self, encounter_id: str) -> Encounter:
        updated, _ = self._execute_internal(encounter_id)
        return updated

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

        updated = start_turn(encounter)
        _expire_source_turn_help_effects(updated, updated.current_entity_id)
        remove_expired_weapon_mastery_effects(
            encounter=updated,
            source_entity_id=updated.current_entity_id,
            timing="start_of_source_turn",
        )
        resolutions = resolve_turn_effects(
            encounter=updated,
            entity_id=updated.current_entity_id,
            trigger="start_of_turn",
        )
        zone_resolutions = resolve_zone_effects(
            encounter=updated,
            entity_id=updated.current_entity_id,
            trigger="start_of_turn_inside",
        )
        current_entity = updated.entities.get(updated.current_entity_id)
        if current_entity is not None and _should_resolve_death_save(current_entity):
            resolutions.append(resolve_death_save(target=current_entity))
        saved = self.repository.save(updated)
        self._append_turn_effect_events(saved, resolutions)
        self._append_zone_effect_events(saved, zone_resolutions)
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


def _should_resolve_death_save(entity: EncounterEntity) -> bool:
    if entity.category not in {"pc", "npc"}:
        return False
    if entity.hp.get("current") != 0:
        return False
    if "unconscious" not in entity.conditions:
        return False
    if _has_knockout_protection(entity):
        return False
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    if combat_flags.get("is_dead") is True:
        return False
    return True


def _has_knockout_protection(entity: EncounterEntity) -> bool:
    for effect in entity.turn_effects:
        if isinstance(effect, dict) and effect.get("effect_type") == "knockout_protection":
            return True
    return False


def _expire_source_turn_help_effects(encounter: Encounter, source_entity_id: str | None) -> None:
    if not isinstance(source_entity_id, str) or not source_entity_id:
        return
    for entity in encounter.entities.values():
        entity.turn_effects = [
            effect
            for effect in entity.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") in {"help_attack", "help_ability_check"}
                and effect.get("source_entity_id") == source_entity_id
                and effect.get("expires_on") == "source_next_turn_start"
            )
        ]
