from __future__ import annotations

import random
import re
from typing import Any

from tools.services.class_features.shared import ensure_sorcerer_runtime
from tools.services.shared.rule_validation_error import RuleValidationError

_FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
_FLAT_RE = re.compile(r"^[+]?(\d+)$")

TRANSMUTED_DAMAGE_TYPES = {"acid", "cold", "fire", "lightning", "poison", "thunder"}
METAMAGIC_SORCERY_POINT_COSTS = {
    "careful_spell": 1,
    "distant_spell": 1,
    "empowered_spell": 1,
    "extended_spell": 1,
    "heightened_spell": 2,
    "quickened_spell": 2,
    "seeking_spell": 1,
    "subtle_spell": 1,
    "transmuted_spell": 1,
    "twinned_spell": 1,
}
_METAMAGIC_COMBO_EXCEPTIONS = {"empowered_spell", "seeking_spell"}


def build_default_metamagic() -> dict[str, Any]:
    return {
        "selected": [],
        "subtle_spell": False,
        "quickened_spell": False,
        "distant_spell": False,
        "heightened_spell": False,
        "careful_spell": False,
        "empowered_spell": False,
        "extended_spell": False,
        "seeking_spell": False,
        "transmuted_spell": False,
        "twinned_spell": False,
        "sorcery_point_cost": 0,
        "heightened_target_id": None,
        "careful_target_ids": [],
        "effective_range_override_feet": None,
        "transmuted_damage_type": None,
        "effective_target_scaling_bonus_levels": 0,
    }


def build_default_noticeability() -> dict[str, Any]:
    return {
        "casting_is_perceptible": True,
        "verbal_visible": True,
        "somatic_visible": True,
        "material_visible": True,
        "spell_effect_visible": True,
    }


def resolve_declared_metamagic(
    *,
    actor: Any,
    spellcasting_class: str | None,
    spell_definition: dict[str, Any],
    action_cost: str | None,
    spell_target_ids: list[str] | None,
    encounter_entity_ids: list[str] | None,
    metamagic_options: dict[str, Any] | None,
) -> dict[str, Any]:
    default_result = {
        "metamagic": build_default_metamagic(),
        "noticeability": build_default_noticeability(),
    }
    if not isinstance(metamagic_options, dict):
        return default_result

    normalized_selected = _normalize_selected_metamagic(metamagic_options.get("selected"))
    if not normalized_selected:
        return default_result
    if len(normalized_selected) > 2:
        raise RuleValidationError(
            "too_many_metamagic_options",
            "一次施法最多只能应用两个超魔法选项。",
        )

    if spellcasting_class != "sorcerer":
        raise RuleValidationError(
            "metamagic_requires_sorcerer_spell",
            "只有术士法术可以使用超魔法。",
        )

    sorcerer = ensure_sorcerer_runtime(actor)
    level = int(sorcerer.get("level", 0) or 0)
    if level < 2:
        raise RuleValidationError(
            "metamagic_requires_sorcerer_level_2",
            "超魔法需要至少 2 级术士。",
        )

    known_options = _normalize_selected_metamagic(
        sorcerer.get("metamagic", {}).get("known_options") if isinstance(sorcerer.get("metamagic"), dict) else []
    )
    for selected_option in normalized_selected:
        if selected_option not in METAMAGIC_SORCERY_POINT_COSTS:
            raise RuleValidationError(
                "unknown_metamagic_option",
                f"未知超魔法选项：{selected_option}",
            )
        if selected_option not in known_options:
            raise RuleValidationError(
                "metamagic_option_not_known",
                f"术士未习得超魔法选项：{selected_option}",
            )

    if len(normalized_selected) > 1 and not _can_combine_metamagic(
        sorcerer=sorcerer,
        selected_options=normalized_selected,
    ):
        raise RuleValidationError(
            "metamagic_combination_not_allowed",
            "当前状态下不能组合这些超魔法；通常只能叠加强效法术或追踪法术，术法化身激活时除外。",
        )

    total_cost = sum(METAMAGIC_SORCERY_POINT_COSTS[option] for option in normalized_selected)
    sorcery_points = sorcerer.get("sorcery_points")
    current_points = int(sorcery_points.get("current", 0) or 0) if isinstance(sorcery_points, dict) else 0
    if current_points < total_cost:
        raise RuleValidationError(
            "insufficient_sorcery_points",
            "术法点不足，无法使用所选超魔法。",
        )

    metamagic = build_default_metamagic()
    metamagic["selected"] = list(normalized_selected)
    metamagic["sorcery_point_cost"] = total_cost
    for option in normalized_selected:
        metamagic[option] = True

    spell_target_ids = list(spell_target_ids or [])
    known_entity_ids = {entity_id for entity_id in list(encounter_entity_ids or []) if isinstance(entity_id, str)}

    if "quickened_spell" in normalized_selected and action_cost != "action":
        raise RuleValidationError(
            "quickened_spell_requires_action_cast_time",
            "瞬发法术只能作用于施法时间为动作的法术。",
        )

    if "distant_spell" in normalized_selected:
        if not spell_can_use_distant_spell(spell_definition=spell_definition):
            raise RuleValidationError(
                "distant_spell_requires_range_or_touch_spell",
                "远程法术只能用于具有射程或触碰距离的法术。",
            )
        metamagic["effective_range_override_feet"] = resolve_distant_spell_range_override_feet(
            spell_definition=spell_definition
        )

    if "heightened_spell" in normalized_selected:
        if not spell_requires_saving_throw(spell_definition=spell_definition):
            raise RuleValidationError(
                "heightened_spell_requires_saving_throw_spell",
                "升阶法术只能用于要求目标进行豁免的法术。",
            )
        heightened_target_id = metamagic_options.get("heightened_target_id")
        if not isinstance(heightened_target_id, str) or not heightened_target_id.strip():
            raise RuleValidationError(
                "heightened_spell_requires_target",
                "升阶法术需要指定一个吃劣势的目标。",
            )
        if heightened_target_id not in spell_target_ids:
            raise RuleValidationError(
                "heightened_target_not_in_spell_targets",
                "升阶法术指定的目标必须属于本次法术目标。",
            )
        metamagic["heightened_target_id"] = heightened_target_id

    if "careful_spell" in normalized_selected:
        if not spell_requires_saving_throw(spell_definition=spell_definition):
            raise RuleValidationError(
                "careful_spell_requires_saving_throw_spell",
                "谨慎法术只能用于要求目标进行豁免的法术。",
            )
        careful_target_ids = metamagic_options.get("careful_target_ids")
        if not isinstance(careful_target_ids, list) or not careful_target_ids:
            raise RuleValidationError(
                "careful_spell_requires_targets",
                "谨慎法术需要提供被保护目标列表。",
            )
        normalized_careful_target_ids: list[str] = []
        for item in careful_target_ids:
            normalized_target_id = str(item).strip()
            if normalized_target_id and normalized_target_id not in normalized_careful_target_ids:
                normalized_careful_target_ids.append(normalized_target_id)
        max_protected_targets = max(1, int(getattr(actor, "ability_mods", {}).get("cha", 0) or 0))
        if len(normalized_careful_target_ids) > max_protected_targets:
            raise RuleValidationError(
                "careful_spell_too_many_targets",
                "谨慎法术指定的被保护目标数量超过了魅力调整值上限。",
            )
        for entity_id in normalized_careful_target_ids:
            if entity_id not in known_entity_ids:
                raise RuleValidationError(
                    "careful_target_not_in_spell_targets",
                    "谨慎法术指定的目标必须存在于当前遭遇战中。",
                )
        metamagic["careful_target_ids"] = normalized_careful_target_ids

    if "empowered_spell" in normalized_selected and not spell_has_damage_resolution(spell_definition=spell_definition):
        raise RuleValidationError(
            "empowered_spell_requires_damage_spell",
            "强效法术只能用于造成伤害的法术。",
        )

    if "extended_spell" in normalized_selected and not spell_supports_extended_spell(spell_definition):
        raise RuleValidationError(
            "extended_spell_requires_duration_spell",
            "延效法术只能用于持续时间至少 1 分钟的法术。",
        )

    if "seeking_spell" in normalized_selected and not bool(spell_definition.get("requires_attack_roll")):
        raise RuleValidationError(
            "seeking_spell_requires_attack_roll_spell",
            "追踪法术只能用于需要攻击检定的法术。",
        )

    if "transmuted_spell" in normalized_selected:
        if not spell_supports_transmuted_spell(spell_definition):
            raise RuleValidationError(
                "transmuted_spell_requires_eligible_damage_type",
                "转化法术只能用于造成可转化元素伤害的法术。",
            )
        transmuted_damage_type = normalize_transmuted_damage_type(metamagic_options.get("transmuted_damage_type"))
        if transmuted_damage_type is None:
            raise RuleValidationError(
                "invalid_transmuted_damage_type",
                "转化法术需要指定 acid/cold/fire/lightning/poison/thunder 之一。",
            )
        metamagic["transmuted_damage_type"] = transmuted_damage_type

    if "twinned_spell" in normalized_selected:
        if not spell_supports_twinned_spell(spell_definition):
            raise RuleValidationError(
                "twinned_spell_requires_scaling_target_spell",
                "孪生法术只能用于可通过升环增加目标的单体法术。",
            )
        metamagic["effective_target_scaling_bonus_levels"] = 1

    noticeability = build_default_noticeability()
    if "subtle_spell" in normalized_selected:
        noticeability = {
            "casting_is_perceptible": False,
            "verbal_visible": False,
            "somatic_visible": False,
            "material_visible": False,
            "spell_effect_visible": True,
        }

    return {
        "metamagic": metamagic,
        "noticeability": noticeability,
    }


def normalize_transmuted_damage_type(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in TRANSMUTED_DAMAGE_TYPES:
        return None
    return normalized


def spell_supports_extended_spell(spell_definition: dict[str, Any]) -> bool:
    base = spell_definition.get("base")
    if not isinstance(base, dict):
        return False
    if bool(base.get("concentration")):
        return True
    duration = base.get("duration")
    if not isinstance(duration, str):
        return False
    lowered = duration.strip().lower()
    return any(token in lowered for token in ("minute", "hour", "day", "month", "year"))


def spell_supports_twinned_spell(spell_definition: dict[str, Any]) -> bool:
    targeting = spell_definition.get("targeting")
    if not isinstance(targeting, dict) or targeting.get("type") != "single_target":
        return False
    scaling = spell_definition.get("scaling")
    if not isinstance(scaling, dict):
        return False
    slot_level_bonus = scaling.get("slot_level_bonus")
    if not isinstance(slot_level_bonus, dict):
        return False
    additional_targets = slot_level_bonus.get("additional_targets_per_extra_level")
    return isinstance(additional_targets, int) and additional_targets > 0


def spell_supports_transmuted_spell(spell_definition: dict[str, Any]) -> bool:
    return bool(_collect_transmutable_damage_sources(spell_definition))


def spell_can_use_distant_spell(*, spell_definition: dict[str, Any]) -> bool:
    targeting = spell_definition.get("targeting")
    if isinstance(targeting, dict):
        range_kind = targeting.get("range_kind")
        if isinstance(range_kind, str) and range_kind.strip().lower() == "touch":
            return True
        range_feet = targeting.get("range_feet")
        if isinstance(range_feet, int) and range_feet >= 5:
            return True
    base = spell_definition.get("base")
    if isinstance(base, dict):
        spell_range = base.get("range")
        if isinstance(spell_range, str) and spell_range.strip().lower() == "touch":
            return True
    return False


def resolve_distant_spell_range_override_feet(*, spell_definition: dict[str, Any]) -> int | None:
    targeting = spell_definition.get("targeting")
    if isinstance(targeting, dict):
        range_kind = targeting.get("range_kind")
        if isinstance(range_kind, str) and range_kind.strip().lower() == "touch":
            return 30
        range_feet = targeting.get("range_feet")
        if isinstance(range_feet, int) and range_feet >= 5:
            return range_feet * 2
    base = spell_definition.get("base")
    if isinstance(base, dict):
        spell_range = base.get("range")
        if isinstance(spell_range, str) and spell_range.strip().lower() == "touch":
            return 30
    return None


def spell_requires_saving_throw(*, spell_definition: dict[str, Any]) -> bool:
    save_ability = spell_definition.get("save_ability")
    if isinstance(save_ability, str) and save_ability.strip():
        return True
    resolution = spell_definition.get("resolution")
    if isinstance(resolution, dict):
        resolution_save_ability = resolution.get("save_ability")
        if isinstance(resolution_save_ability, str) and resolution_save_ability.strip():
            return True
        return resolution.get("mode") == "save"
    return False


def spell_has_damage_resolution(*, spell_definition: dict[str, Any]) -> bool:
    on_cast = spell_definition.get("on_cast")
    if not isinstance(on_cast, dict):
        return False
    for key in ("on_hit", "on_failed_save", "on_successful_save"):
        outcome = on_cast.get(key)
        if not isinstance(outcome, dict):
            continue
        damage_parts = outcome.get("damage_parts")
        if isinstance(damage_parts, list) and damage_parts:
            return True
    return False


def apply_transmuted_damage_parts(
    *,
    damage_parts: list[dict[str, Any]],
    replacement_damage_type: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    normalized_type = normalize_transmuted_damage_type(replacement_damage_type)
    copied_parts = [dict(part) for part in damage_parts]
    if normalized_type is None:
        return copied_parts, None

    changed_sources: list[str] = []
    for part in copied_parts:
        current_type = part.get("damage_type")
        if isinstance(current_type, str) and current_type.strip().lower() in TRANSMUTED_DAMAGE_TYPES:
            part["damage_type"] = normalized_type
            source = part.get("source")
            if isinstance(source, str) and source.strip():
                changed_sources.append(source.strip())

    if not changed_sources:
        return copied_parts, None
    return (
        copied_parts,
        {
            "metamagic_id": "transmuted_spell",
            "applied": True,
            "replacement_damage_type": normalized_type,
            "changed_sources": changed_sources,
        },
    )


def apply_empowered_spell_to_damage_rolls(
    *,
    damage_parts: list[dict[str, Any]],
    indexed_rolls: dict[str, list[int]],
    charisma_modifier: int,
) -> tuple[dict[str, list[int]], dict[str, Any] | None]:
    reroll_limit = max(1, int(charisma_modifier or 0))
    updated_rolls = {source: list(rolls) for source, rolls in indexed_rolls.items()}

    candidates: list[dict[str, Any]] = []
    for part_order, part in enumerate(damage_parts):
        source = part.get("source")
        if not isinstance(source, str) or source not in updated_rolls:
            continue
        parsed = _parse_formula(str(part.get("formula") or ""))
        if parsed is None:
            continue
        dice_count, die_size, _ = parsed
        if dice_count <= 0:
            continue
        average = (die_size + 1) / 2
        rolls = updated_rolls[source]
        for roll_index, roll_value in enumerate(rolls):
            if roll_value >= average:
                continue
            candidates.append(
                {
                    "source": source,
                    "roll_index": roll_index,
                    "old_value": roll_value,
                    "die_size": die_size,
                    "gain": average - roll_value,
                    "part_order": part_order,
                }
            )

    if not candidates:
        return updated_rolls, None

    candidates.sort(key=lambda item: (-item["gain"], item["part_order"], item["roll_index"]))
    rerolls: list[dict[str, Any]] = []
    for candidate in candidates[:reroll_limit]:
        new_value = random.randint(1, candidate["die_size"])
        updated_rolls[candidate["source"]][candidate["roll_index"]] = new_value
        rerolls.append(
            {
                "source": candidate["source"],
                "roll_index": candidate["roll_index"],
                "old_value": candidate["old_value"],
                "new_value": new_value,
            }
        )

    return (
        updated_rolls,
        {
            "metamagic_id": "empowered_spell",
            "applied": True,
            "rerolled_count": len(rerolls),
            "rerolls": rerolls,
        },
    )


def reroll_missed_spell_attack(
    *,
    attack_roll: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    dice_rolls = attack_roll.get("dice_rolls")
    if not isinstance(dice_rolls, dict):
        return attack_roll, None

    chosen_roll = dice_rolls.get("chosen_roll")
    modifier = dice_rolls.get("modifier")
    if not isinstance(chosen_roll, int):
        base_rolls = dice_rolls.get("base_rolls")
        if isinstance(base_rolls, list) and base_rolls and isinstance(base_rolls[0], int):
            chosen_roll = base_rolls[0]
    if not isinstance(chosen_roll, int):
        return attack_roll, None
    if not isinstance(modifier, int):
        final_total = attack_roll.get("final_total")
        if not isinstance(final_total, int):
            return attack_roll, None
        modifier = final_total - chosen_roll

    new_roll = random.randint(1, 20)
    updated = {
        "final_total": new_roll + modifier,
        "dice_rolls": {
            **dice_rolls,
            "base_rolls": [new_roll],
            "chosen_roll": new_roll,
            "modifier": modifier,
            "rerolled_from": chosen_roll,
        },
    }
    return (
        updated,
        {
            "metamagic_id": "seeking_spell",
            "applied": True,
            "old_roll": chosen_roll,
            "new_roll": new_roll,
        },
    )


def _collect_transmutable_damage_sources(spell_definition: dict[str, Any]) -> list[str]:
    on_cast = spell_definition.get("on_cast")
    if not isinstance(on_cast, dict):
        return []

    sources: list[str] = []
    for outcome_key in ("on_hit", "on_failed_save", "on_successful_save"):
        outcome = on_cast.get(outcome_key)
        if not isinstance(outcome, dict):
            continue
        raw_damage_parts = outcome.get("damage_parts")
        if not isinstance(raw_damage_parts, list):
            continue
        for part in raw_damage_parts:
            if not isinstance(part, dict):
                continue
            damage_type = part.get("damage_type")
            if isinstance(damage_type, str) and damage_type.strip().lower() in TRANSMUTED_DAMAGE_TYPES:
                source = part.get("source")
                if isinstance(source, str) and source.strip():
                    sources.append(source.strip())
    return sources


def _parse_formula(formula: str) -> tuple[int, int, int] | None:
    match = _FORMULA_RE.match(formula)
    if match is not None:
        return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    flat_match = _FLAT_RE.match(formula)
    if flat_match is not None:
        return 0, 1, int(flat_match.group(1))
    return None


def _normalize_selected_metamagic(selected: Any) -> list[str]:
    if not isinstance(selected, list):
        return []
    normalized_selected: list[str] = []
    for item in selected:
        normalized = str(item).strip().lower()
        if normalized and normalized not in normalized_selected:
            normalized_selected.append(normalized)
    return normalized_selected


def _can_combine_metamagic(*, sorcerer: dict[str, Any], selected_options: list[str]) -> bool:
    if len(selected_options) <= 1:
        return True
    if _sorcery_incarnate_allows_dual_metamagic(sorcerer=sorcerer):
        return True
    non_exception_count = sum(1 for option in selected_options if option not in _METAMAGIC_COMBO_EXCEPTIONS)
    return non_exception_count <= 1


def _sorcery_incarnate_allows_dual_metamagic(*, sorcerer: dict[str, Any]) -> bool:
    if int(sorcerer.get("level", 0) or 0) < 7:
        return False
    innate_sorcery = sorcerer.get("innate_sorcery")
    return isinstance(innate_sorcery, dict) and bool(innate_sorcery.get("active"))
