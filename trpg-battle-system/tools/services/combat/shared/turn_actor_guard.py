from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity


def get_current_turn_entity_or_raise(encounter: Encounter) -> EncounterEntity:
    if encounter.current_entity_id is None:
        raise ValueError("encounter has no current_entity_id")
    entity = encounter.entities.get(encounter.current_entity_id)
    if entity is None:
        raise ValueError("current_entity_id not found in entities")
    return entity


def get_entity_or_raise(
    encounter: Encounter,
    entity_id: str,
    *,
    entity_label: str = "entity",
) -> EncounterEntity:
    entity = encounter.entities.get(entity_id)
    if entity is None:
        raise ValueError(f"{entity_label} '{entity_id}' not found in encounter")
    return entity


def resolve_current_turn_actor_or_raise(
    encounter: Encounter,
    *,
    actor_id: str | None,
    allow_out_of_turn_actor: bool = False,
    entity_label: str = "actor",
) -> EncounterEntity:
    current_entity = get_current_turn_entity_or_raise(encounter)
    if actor_id is None:
        return current_entity

    actor = get_entity_or_raise(encounter, actor_id, entity_label=entity_label)
    if not allow_out_of_turn_actor and actor.entity_id != current_entity.entity_id:
        raise ValueError("actor_not_current_turn_entity")
    return actor
