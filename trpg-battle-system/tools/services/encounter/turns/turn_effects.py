from __future__ import annotations

import random
import re
from typing import Any

from tools.models import Encounter, EncounterEntity
from tools.services.combat.damage import ResolveDamageParts
from tools.services.class_features.shared import resolve_entity_save_proficiencies
from tools.services.spells.end_concentration_spell_instances import end_concentration_spell_instances

_FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


def resolve_turn_effects(
    *,
    encounter: Encounter,
    entity_id: str,
    trigger: str,
    damage_roll_overrides: dict[str, dict[str, object]] | None = None,
    save_roll_overrides: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    if trigger not in {"start_of_turn", "end_of_turn"}:
        raise ValueError("trigger must be 'start_of_turn' or 'end_of_turn'")

    entity = encounter.entities.get(entity_id)
    if entity is None:
        raise ValueError(f"entity '{entity_id}' not found in encounter")

    damage_roll_overrides = damage_roll_overrides or {}
    save_roll_overrides = save_roll_overrides or {}

    resolutions: list[dict[str, object]] = []
    retained_effects: list[dict[str, Any]] = []

    for effect in entity.turn_effects:
        if effect.get("trigger") != trigger:
            retained_effects.append(effect)
            continue

        resolution = {
            "effect_id": effect.get("effect_id"),
            "name": effect.get("name"),
            "trigger": trigger,
            "target_entity_id": entity.entity_id,
            "source_entity_id": effect.get("source_entity_id"),
            "save": None,
            "trigger_damage_resolution": None,
            "success_damage_resolution": None,
            "failure_damage_resolution": None,
            "condition_updates": [],
            "effect_removed": False,
        }

        special_updates = _apply_special_turn_effect(
            target=entity,
            effect=effect,
            trigger=trigger,
        )
        if special_updates:
            resolution["condition_updates"].extend(special_updates)

        trigger_updates, trigger_damage_resolution = _apply_effect_outcome(
            encounter=encounter,
            target=entity,
            outcome=effect.get("on_trigger"),
            damage_roll_overrides=damage_roll_overrides,
        )
        resolution["condition_updates"].extend(trigger_updates)
        resolution["trigger_damage_resolution"] = trigger_damage_resolution

        save_config = effect.get("save")
        save_success: bool | None = None
        if isinstance(save_config, dict):
            save_result = _resolve_effect_save(
                target=entity,
                effect=effect,
                save_config=save_config,
                save_roll_overrides=save_roll_overrides,
            )
            save_success = save_result["success"]
            resolution["save"] = save_result

            outcome_key = "on_save_success" if save_success else "on_save_failure"
            outcome_updates, outcome_damage_resolution = _apply_effect_outcome(
                encounter=encounter,
                target=entity,
                outcome=effect.get(outcome_key),
                damage_roll_overrides=damage_roll_overrides,
            )
            resolution["condition_updates"].extend(outcome_updates)
            if save_success:
                resolution["success_damage_resolution"] = outcome_damage_resolution
            else:
                resolution["failure_damage_resolution"] = outcome_damage_resolution

        remove_effect = bool(effect.get("remove_after_trigger"))
        if save_success and isinstance(save_config, dict) and bool(save_config.get("on_success_remove_effect")):
            remove_effect = True

        if remove_effect:
            resolution["effect_removed"] = True
        else:
            retained_effects.append(effect)

        resolutions.append(resolution)

    entity.turn_effects = _filter_retained_effects_against_current_state(
        current_effects=entity.turn_effects,
        retained_effects=retained_effects,
    )
    return resolutions


def _apply_effect_outcome(
    *,
    encounter: Encounter,
    target: EncounterEntity,
    outcome: Any,
    damage_roll_overrides: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    if not isinstance(outcome, dict):
        return [], None

    condition_updates = _apply_condition_changes(
        target,
        apply_conditions=outcome.get("apply_conditions"),
        remove_conditions=outcome.get("remove_conditions"),
    )
    damage_resolution = _resolve_effect_damage(
        encounter=encounter,
        target=target,
        damage_parts=outcome.get("damage_parts"),
        damage_roll_overrides=damage_roll_overrides,
    )
    return condition_updates, damage_resolution


def _apply_special_turn_effect(
    *,
    target: EncounterEntity,
    effect: dict[str, Any],
    trigger: str,
) -> list[dict[str, object]]:
    effect_type = effect.get("effect_type")
    if effect_type != "shield_ac_bonus" or trigger != "start_of_turn":
        return []

    ac_bonus = effect.get("ac_bonus", 0)
    if not isinstance(ac_bonus, int):
        raise ValueError("shield_ac_bonus.ac_bonus must be an integer")
    if ac_bonus == 0:
        return [{"operation": "shield_ac_bonus_removed", "changed": False, "ac_bonus": 0}]

    target.ac = max(0, target.ac - ac_bonus)
    return [
        {
            "operation": "shield_ac_bonus_removed",
            "changed": True,
            "ac_bonus": ac_bonus,
            "new_ac": target.ac,
        }
    ]


def _apply_condition_changes(
    target: EncounterEntity,
    *,
    apply_conditions: Any,
    remove_conditions: Any,
) -> list[dict[str, object]]:
    updates: list[dict[str, object]] = []

    if isinstance(remove_conditions, list):
        for condition in remove_conditions:
            if not isinstance(condition, str):
                continue
            if condition in target.conditions:
                target.conditions.remove(condition)
                updates.append({"operation": "remove", "condition": condition, "changed": True})
            else:
                updates.append({"operation": "remove", "condition": condition, "changed": False})

    if isinstance(apply_conditions, list):
        for condition in apply_conditions:
            if not isinstance(condition, str):
                continue
            if condition not in target.conditions:
                target.conditions.append(condition)
                updates.append({"operation": "apply", "condition": condition, "changed": True})
            else:
                updates.append({"operation": "apply", "condition": condition, "changed": False})

    return updates


def _resolve_effect_damage(
    *,
    encounter: Encounter,
    target: EncounterEntity,
    damage_parts: Any,
    damage_roll_overrides: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    if not isinstance(damage_parts, list) or not damage_parts:
        return None

    rolled_values: list[list[int]] = []
    for index, part in enumerate(damage_parts):
        if not isinstance(part, dict):
            raise ValueError("damage_parts items must be dict")
        source = str(part.get("source") or f"part_{index}")
        override = damage_roll_overrides.get(source, {})
        rolls = override.get("rolls")
        if rolls is None:
            rolls = _default_rolls_for_formula(str(part.get("formula")))
        if not isinstance(rolls, list):
            raise ValueError("damage_roll_overrides[source].rolls must be a list")
        rolled_values.append(list(rolls))

    resolution = ResolveDamageParts().execute(
        damage_parts=damage_parts,
        is_critical_hit=False,
        rolled_values=rolled_values,
        resistances=target.resistances,
        immunities=target.immunities,
        vulnerabilities=target.vulnerabilities,
    )
    _apply_damage_to_target(
        encounter=encounter,
        target=target,
        damage=int(resolution["total_damage"]),
    )
    return resolution


def _apply_damage_to_target(*, encounter: Encounter, target: EncounterEntity, damage: int) -> None:
    if damage <= 0:
        return

    hp_before = int(target.hp["current"])
    temp_hp_absorbed = min(target.hp["temp"], damage)
    remaining_damage = damage - temp_hp_absorbed
    target.hp["temp"] -= temp_hp_absorbed
    target.hp["current"] = max(0, target.hp["current"] - remaining_damage)

    _apply_zero_hp_rules(
        encounter=encounter,
        target=target,
        hp_before=hp_before,
        hp_after=int(target.hp["current"]),
        adjusted_damage=damage,
    )


def _apply_zero_hp_rules(
    *,
    encounter: Encounter,
    target: EncounterEntity,
    hp_before: int,
    hp_after: int,
    adjusted_damage: int,
) -> None:
    if hp_after != 0 or adjusted_damage <= 0:
        return

    if hp_before > 0:
        if target.category in {"pc", "npc"}:
            if "unconscious" not in target.conditions:
                target.conditions.append("unconscious")
            target.combat_flags["is_defeated"] = False
            target.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
            target.combat_flags["is_dead"] = False
            _end_concentration_if_needed(encounter=encounter, target=target)
            return
        if target.category == "monster":
            remains = {
                "remains_id": f"remains_{target.entity_id}",
                "icon": "💀",
                "label": f"{target.name}尸骸",
                "position": dict(target.position),
                "source_entity_id": target.entity_id,
            }
            encounter.map.remains.append(remains)
            _remove_entity_from_encounter(encounter=encounter, entity_id=target.entity_id)
            return
        if target.category == "summon":
            _remove_entity_from_encounter(encounter=encounter, entity_id=target.entity_id)
            return
        target.combat_flags["is_defeated"] = True
        return

    if target.category not in {"pc", "npc"}:
        return
    if "unconscious" not in target.conditions:
        return

    death_saves = target.combat_flags.get("death_saves")
    if not isinstance(death_saves, dict):
        death_saves = {"successes": 0, "failures": 0}
        target.combat_flags["death_saves"] = death_saves

    successes = death_saves.get("successes", 0)
    failures = death_saves.get("failures", 0)
    if not isinstance(successes, int):
        successes = 0
    if not isinstance(failures, int):
        failures = 0
    death_saves["successes"] = successes
    death_saves["failures"] = failures + 1

    if death_saves["failures"] >= 3:
        target.combat_flags["is_dead"] = True
        _end_concentration_if_needed(encounter=encounter, target=target)


def _end_concentration_if_needed(*, encounter: Encounter, target: EncounterEntity) -> None:
    if not bool(target.combat_flags.get("is_concentrating")):
        return
    target.combat_flags["is_concentrating"] = False
    end_concentration_spell_instances(
        encounter=encounter,
        caster_entity_id=target.entity_id,
        reason="concentration_broken",
    )


def _remove_entity_from_encounter(*, encounter: Encounter, entity_id: str) -> None:
    if entity_id in encounter.entities:
        del encounter.entities[entity_id]
    encounter.turn_order = [item for item in encounter.turn_order if item != entity_id]
    if encounter.current_entity_id == entity_id:
        encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
    pending = encounter.pending_movement
    if isinstance(pending, dict) and pending.get("entity_id") == entity_id:
        pending["status"] = "interrupted"


def _resolve_effect_save(
    *,
    target: EncounterEntity,
    effect: dict[str, Any],
    save_config: dict[str, Any],
    save_roll_overrides: dict[str, int],
) -> dict[str, object]:
    ability = str(save_config.get("ability") or "").strip().lower()
    dc = save_config.get("dc")
    if ability not in {"str", "dex", "con", "int", "wis", "cha"}:
        raise ValueError("save.ability must be a valid ability")
    if not isinstance(dc, int):
        raise ValueError("save.dc must be an integer")

    effect_id = str(effect.get("effect_id") or "")
    base_roll = save_roll_overrides.get(effect_id)
    if base_roll is None:
        base_roll = random.randint(1, 20)
    if not isinstance(base_roll, int):
        raise ValueError("save roll override must be an integer")

    save_bonus = int(target.ability_mods.get(ability, 0))
    if ability in resolve_entity_save_proficiencies(target):
        save_bonus += int(target.proficiency_bonus)
    total = base_roll + save_bonus

    return {
        "ability": ability,
        "dc": dc,
        "base_roll": base_roll,
        "bonus": save_bonus,
        "total": total,
        "success": total >= dc,
    }


def _default_rolls_for_formula(formula: str) -> list[int]:
    match = _FORMULA_RE.match(formula)
    if not match:
        raise ValueError("invalid_damage_formula")
    dice_count = int(match.group(1))
    die_size = int(match.group(2))
    if dice_count <= 0 or die_size <= 0:
        raise ValueError("invalid_damage_formula")
    return [random.randint(1, die_size) for _ in range(dice_count)]


def _filter_retained_effects_against_current_state(
    *,
    current_effects: list[Any],
    retained_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for effect in retained_effects:
        if not isinstance(effect, dict):
            continue
        effect_id = effect.get("effect_id")
        if isinstance(effect_id, str):
            if any(
                isinstance(current, dict) and current.get("effect_id") == effect_id
                for current in current_effects
            ):
                filtered.append(effect)
            continue
        if effect in current_effects:
            filtered.append(effect)
    return filtered
