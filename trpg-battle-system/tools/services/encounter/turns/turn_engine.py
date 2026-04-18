from __future__ import annotations

from tools.models import Encounter, EncounterEntity
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.combat.actions import clear_turn_effect_type
from tools.services.combat.attack.weapon_mastery_effects import get_weapon_mastery_speed_penalty
from tools.services.combat.defense.armor_profile_resolver import get_armor_speed_penalty
from tools.services.class_features.shared import (
    ensure_monk_runtime,
    ensure_rogue_runtime,
    ensure_ranger_runtime,
    ensure_warlock_runtime,
    get_class_runtime,
    get_monk_runtime,
)


def reset_turn_resources(entity: EncounterEntity) -> None:
    entity.action_economy = {
        "action_used": False,
        "bonus_action_used": False,
        "reaction_used": False,
        "free_interaction_used": False,
    }
    clear_turn_effect_type(entity, "disengage")
    clear_turn_effect_type(entity, "dodge")
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    base_walk_speed = _resolve_base_walk_speed(entity=entity, combat_flags=combat_flags)
    current_walk_speed = max(
        0,
        base_walk_speed
        + _get_monk_unarmored_movement_bonus(entity)
        + _get_barbarian_fast_movement_bonus(entity)
        + _get_ranger_roving_bonus(entity),
    )
    entity.speed["walk"] = current_walk_speed
    speed_penalty = get_weapon_mastery_speed_penalty(entity) + get_armor_speed_penalty(entity)
    entity.speed["remaining"] = max(0, current_walk_speed - speed_penalty)
    if _get_ranger_roving_bonus(entity) > 0:
        entity.speed["climb"] = current_walk_speed
        entity.speed["swim"] = current_walk_speed
    else:
        entity.speed.pop("climb", None)
        entity.speed.pop("swim", None)
    combat_flags["base_walk_speed"] = base_walk_speed
    combat_flags["movement_spent_feet"] = 0
    combat_flags.pop("light_bonus_trigger", None)
    entity.combat_flags = combat_flags

    class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
    fighter = class_features.get("fighter")
    if isinstance(fighter, dict):
        turn_counters = fighter.get("turn_counters")
        action_surge = fighter.get("action_surge")
        temporary_bonuses = fighter.get("temporary_bonuses")
        if isinstance(turn_counters, dict):
            turn_counters["attack_action_attacks_used"] = 0
        if isinstance(action_surge, dict):
            action_surge["used_this_turn"] = False
        if isinstance(temporary_bonuses, dict):
            temporary_bonuses["extra_non_magic_action_available"] = 0
    rogue = class_features.get("rogue")
    if isinstance(rogue, dict):
        rogue = ensure_rogue_runtime(entity)
        sneak_attack = rogue.get("sneak_attack")
        if isinstance(sneak_attack, dict):
            sneak_attack["used_this_turn"] = False
    monk = class_features.get("monk")
    if isinstance(monk, dict):
        monk = ensure_monk_runtime(entity)
        stunning_strike = monk.get("stunning_strike")
        if isinstance(stunning_strike, dict):
            stunning_strike["uses_this_turn"] = 0
    warlock = class_features.get("warlock")
    if isinstance(warlock, dict):
        warlock = ensure_warlock_runtime(entity)
        turn_counters = warlock.get("turn_counters")
        if isinstance(turn_counters, dict):
            turn_counters["attack_action_attacks_used"] = 0
        lifedrinker = warlock.get("lifedrinker")
        if isinstance(lifedrinker, dict):
            lifedrinker["used_this_turn"] = False


def _resolve_base_walk_speed(*, entity: EncounterEntity, combat_flags: dict[str, object]) -> int:
    tracked = combat_flags.get("base_walk_speed")
    if isinstance(tracked, int) and tracked >= 0:
        return tracked
    current = entity.speed.get("walk", 0)
    return current if isinstance(current, int) and current >= 0 else 0


def _get_monk_unarmored_movement_bonus(entity: EncounterEntity) -> int:
    monk_runtime = get_monk_runtime(entity)
    if not monk_runtime:
        return 0
    if entity.equipped_armor is not None or entity.equipped_shield is not None:
        return 0
    bonus = monk_runtime.get("unarmored_movement_bonus_feet")
    if isinstance(bonus, int) and bonus > 0:
        return bonus
    return 0


def _get_barbarian_fast_movement_bonus(entity: EncounterEntity) -> int:
    barbarian_runtime = get_class_runtime(entity, "barbarian")
    if not barbarian_runtime:
        return 0
    barbarian = ensure_barbarian_runtime(entity)
    if int(barbarian.get("level", 0) or 0) < 5:
        return 0
    armor = entity.equipped_armor
    if isinstance(armor, dict):
        category = armor.get("category")
        if isinstance(category, str) and category.strip().lower() == "heavy":
            return 0
    return 10


def _get_ranger_roving_bonus(entity: EncounterEntity) -> int:
    ranger_runtime = get_class_runtime(entity, "ranger")
    if not ranger_runtime:
        return 0
    ranger = ensure_ranger_runtime(entity)
    roving = ranger.get("roving")
    if not isinstance(roving, dict) or not roving.get("enabled"):
        return 0
    armor = entity.equipped_armor
    if isinstance(armor, dict):
        category = armor.get("category")
        if isinstance(category, str) and category.strip().lower() == "heavy":
            return 0
    bonus = roving.get("speed_bonus_feet")
    if isinstance(bonus, int) and bonus > 0:
        return bonus
    return 0


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
    actor = encounter.entities[encounter.current_entity_id]
    _resolve_barbarian_rage_at_turn_end(actor)
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


def _resolve_barbarian_rage_at_turn_end(entity: EncounterEntity) -> None:
    class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
    if "barbarian" not in class_features:
        return

    barbarian = ensure_barbarian_runtime(entity)
    rage = barbarian.get("rage")
    if not isinstance(rage, dict) or not bool(rage.get("active")):
        _clear_barbarian_rage_extension_flags(entity)
        return

    if _is_wearing_heavy_armor(entity):
        _end_rage(rage)
        _clear_barbarian_rage_extension_flags(entity)
        return

    conditions = {str(condition).strip().lower() for condition in entity.conditions if isinstance(condition, str)}
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    is_unconscious = "unconscious" in conditions
    is_incapacitated = "incapacitated" in conditions or is_unconscious
    is_dead = bool(combat_flags.get("is_dead"))
    is_persistent = bool(rage.get("persistent_rage"))

    if is_persistent:
        if is_unconscious or is_dead:
            _end_rage(rage)
        else:
            rage["ends_at_turn_end_of"] = entity.entity_id
        _clear_barbarian_rage_extension_flags(entity)
        return

    if is_incapacitated or is_dead:
        _end_rage(rage)
        _clear_barbarian_rage_extension_flags(entity)
        return

    if _has_rage_extension_this_turn(combat_flags):
        rage["ends_at_turn_end_of"] = entity.entity_id
    else:
        _end_rage(rage)

    _clear_barbarian_rage_extension_flags(entity)


def _is_wearing_heavy_armor(entity: EncounterEntity) -> bool:
    armor = entity.equipped_armor
    if not isinstance(armor, dict):
        return False
    category = armor.get("category")
    return isinstance(category, str) and category.strip().lower() == "heavy"


def _has_rage_extension_this_turn(combat_flags: dict[str, object]) -> bool:
    return bool(
        combat_flags.get("rage_extended_by_attack_this_turn")
        or combat_flags.get("rage_extended_by_forced_save_this_turn")
        or combat_flags.get("rage_extended_by_bonus_action_this_turn")
    )


def _clear_barbarian_rage_extension_flags(entity: EncounterEntity) -> None:
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    combat_flags.pop("rage_extended_by_attack_this_turn", None)
    combat_flags.pop("rage_extended_by_forced_save_this_turn", None)
    combat_flags.pop("rage_extended_by_bonus_action_this_turn", None)
    entity.combat_flags = combat_flags


def _end_rage(rage: dict[str, object]) -> None:
    rage["active"] = False
    rage["ends_at_turn_end_of"] = None
