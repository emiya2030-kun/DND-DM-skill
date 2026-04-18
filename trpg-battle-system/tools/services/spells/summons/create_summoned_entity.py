from __future__ import annotations

from typing import Any

from tools.models import Encounter, EncounterEntity
from tools.services.shared_turns import get_shared_turn_owner_id


def create_summoned_entity(
    *,
    encounter: Encounter,
    summon: EncounterEntity,
    insert_after_entity_id: str,
) -> dict[str, Any]:
    encounter.entities[summon.entity_id] = summon
    shared_turn_owner_id = get_shared_turn_owner_id(encounter, summon)
    if shared_turn_owner_id is not None:
        return {
            "entity_id": summon.entity_id,
            "shared_turn_owner_id": shared_turn_owner_id,
            "inserted_into_turn_order": False,
        }

    if insert_after_entity_id not in encounter.turn_order:
        raise ValueError("insert_after_entity_not_in_turn_order")
    insert_index = encounter.turn_order.index(insert_after_entity_id) + 1
    encounter.turn_order.insert(insert_index, summon.entity_id)

    return {
        "entity_id": summon.entity_id,
        "inserted_after": insert_after_entity_id,
        "shared_turn_owner_id": None,
        "inserted_into_turn_order": True,
    }


def create_summoned_entity_by_initiative(
    *,
    encounter: Encounter,
    summon: EncounterEntity,
) -> dict[str, Any]:
    encounter.entities[summon.entity_id] = summon
    shared_turn_owner_id = get_shared_turn_owner_id(encounter, summon)
    if shared_turn_owner_id is not None:
        return {
            "entity_id": summon.entity_id,
            "shared_turn_owner_id": shared_turn_owner_id,
            "inserted_into_turn_order": False,
        }

    insert_index = len(encounter.turn_order)
    for index, entity_id in enumerate(encounter.turn_order):
        current = encounter.entities.get(entity_id)
        current_initiative = int(current.initiative or 0) if current is not None else 0
        if current_initiative < int(summon.initiative or 0):
            insert_index = index
            break

    encounter.turn_order.insert(insert_index, summon.entity_id)
    inserted_before = encounter.turn_order[insert_index + 1] if insert_index + 1 < len(encounter.turn_order) else None
    inserted_after = encounter.turn_order[insert_index - 1] if insert_index - 1 >= 0 else None
    return {
        "entity_id": summon.entity_id,
        "insert_index": insert_index,
        "inserted_before": inserted_before,
        "inserted_after": inserted_after,
        "shared_turn_owner_id": None,
        "inserted_into_turn_order": True,
    }
