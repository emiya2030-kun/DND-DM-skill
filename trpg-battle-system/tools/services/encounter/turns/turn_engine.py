from __future__ import annotations

from tools.models import Encounter, EncounterEntity
from tools.services.combat.attack.weapon_mastery_effects import get_weapon_mastery_speed_penalty


def reset_turn_resources(entity: EncounterEntity) -> None:
    entity.action_economy = {
        "action_used": False,
        "bonus_action_used": False,
        "reaction_used": False,
        "free_interaction_used": False,
    }
    speed_penalty = get_weapon_mastery_speed_penalty(entity)
    entity.speed["remaining"] = max(0, entity.speed["walk"] - speed_penalty)
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    combat_flags["movement_spent_feet"] = 0
    combat_flags.pop("light_bonus_trigger", None)
    entity.combat_flags = combat_flags


def start_turn(encounter: Encounter) -> Encounter:
    if not encounter.turn_order:
        raise ValueError("cannot advance turn without turn_order")

    if encounter.current_entity_id is None:
        encounter.current_entity_id = encounter.turn_order[0]
    reset_turn_resources(encounter.entities[encounter.current_entity_id])
    return encounter


def end_turn(encounter: Encounter) -> Encounter:
    if encounter.current_entity_id is None:
        raise ValueError("cannot end turn without current_entity_id")
    if encounter.current_entity_id not in encounter.entities:
        raise ValueError("current_entity_id must exist in entities")
    return encounter


def advance_turn(encounter: Encounter) -> Encounter:
    if not encounter.turn_order:
        raise ValueError("cannot advance turn without turn_order")

    if encounter.current_entity_id is None:
        encounter.current_entity_id = encounter.turn_order[0]
        return encounter

    current_index = encounter.turn_order.index(encounter.current_entity_id)
    next_index = current_index + 1

    if next_index >= len(encounter.turn_order):
        encounter.current_entity_id = encounter.turn_order[0]
        encounter.round += 1
    else:
        encounter.current_entity_id = encounter.turn_order[next_index]
    return encounter
