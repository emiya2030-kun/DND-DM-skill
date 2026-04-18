from __future__ import annotations

from typing import Any

from tools.models import Encounter, EncounterEntity


def create_summoned_entity(
    *,
    encounter: Encounter,
    summon: EncounterEntity,
    insert_after_entity_id: str,
) -> dict[str, Any]:
    if insert_after_entity_id not in encounter.turn_order:
        raise ValueError("insert_after_entity_not_in_turn_order")

    encounter.entities[summon.entity_id] = summon
    insert_index = encounter.turn_order.index(insert_after_entity_id) + 1
    encounter.turn_order.insert(insert_index, summon.entity_id)

    return {
        "entity_id": summon.entity_id,
        "inserted_after": insert_after_entity_id,
    }
