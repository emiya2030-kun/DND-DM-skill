from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity


def get_shared_turn_owner_id(encounter: Encounter, entity: EncounterEntity | None) -> str | None:
    if entity is None:
        return None
    if entity.category != "summon":
        return None
    if entity.controller != "player":
        return None
    source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
    owner_id = source_ref.get("summoner_entity_id")
    if not isinstance(owner_id, str) or not owner_id:
        return None
    owner = encounter.entities.get(owner_id)
    if owner is None or owner.controller != "player":
        return None
    return owner_id


def is_shared_turn_summon(encounter: Encounter, entity: EncounterEntity | None) -> bool:
    return get_shared_turn_owner_id(encounter, entity) is not None


def is_entity_in_current_turn_group(encounter: Encounter, actor_id: str) -> bool:
    current_entity_id = encounter.current_entity_id
    if current_entity_id is None:
        return False
    if actor_id == current_entity_id:
        return True
    actor = encounter.entities.get(actor_id)
    return get_shared_turn_owner_id(encounter, actor) == current_entity_id


def list_current_turn_group_members(encounter: Encounter) -> list[EncounterEntity]:
    current_entity_id = encounter.current_entity_id
    if current_entity_id is None:
        return []
    owner = encounter.entities.get(current_entity_id)
    if owner is None:
        return []
    members = [owner]
    for entity in encounter.entities.values():
        if entity.entity_id == owner.entity_id:
            continue
        if get_shared_turn_owner_id(encounter, entity) == owner.entity_id:
            members.append(entity)
    return members


def normalize_shared_turn_state(encounter: Encounter) -> Encounter:
    shared_summon_ids = {
        entity.entity_id
        for entity in encounter.entities.values()
        if get_shared_turn_owner_id(encounter, entity) is not None
    }
    if not shared_summon_ids:
        return encounter

    encounter.turn_order = [entity_id for entity_id in encounter.turn_order if entity_id not in shared_summon_ids]
    current_entity_id = encounter.current_entity_id
    if isinstance(current_entity_id, str) and current_entity_id in shared_summon_ids:
        shared_entity = encounter.entities.get(current_entity_id)
        owner_id = get_shared_turn_owner_id(encounter, shared_entity)
        if owner_id in encounter.turn_order:
            encounter.current_entity_id = owner_id
        else:
            encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
    elif current_entity_id is not None and current_entity_id not in encounter.turn_order:
        encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
    return encounter
