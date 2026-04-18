from __future__ import annotations

import math
import re
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import ensure_sorcerer_runtime
from tools.services.class_features.shared.warlock_invocations import resolve_gaze_of_two_minds_origin
from tools.services.combat.shared.turn_actor_guard import resolve_current_turn_actor_or_raise
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells
from tools.services.spells.metamagic_support import (
    normalize_transmuted_damage_type,
    spell_supports_extended_spell,
    spell_supports_transmuted_spell,
    spell_supports_twinned_spell,
)


class SpellRequest:
    """法术声明请求：校验施法者是否掌握法术并返回模板。"""
    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        spell_definition_repository: SpellDefinitionRepository | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_id: str,
        # 以下参数在 Task 1 暂未使用，预留给 Task 2 的施法流程扩展。
        cast_level: int,
        target_entity_ids: list[str] | None = None,
        target_point: dict[str, Any] | None = None,
        declared_action_cost: str | None = None,
        context: dict[str, Any] | None = None,
        metamagic_options: dict[str, Any] | None = None,
        allow_out_of_turn_actor: bool = False,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        current_entity_id = encounter.current_entity_id
        actor = resolve_current_turn_actor_or_raise(
            encounter,
            actor_id=actor_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            entity_label="actor",
        )
        spell_origin = resolve_gaze_of_two_minds_origin(encounter, actor)
        origin_actor = spell_origin.get("origin_entity") or actor

        known_spell = self._find_actor_spell_definition(actor=actor, spell_id=spell_id)
        if known_spell is None:
            return {
                "ok": False,
                "error_code": "spell_not_known",
                "message": f"施法者未掌握 {spell_id}",
            }

        repository_spell_definition = self.spell_definition_repository.get(spell_id)
        if isinstance(repository_spell_definition, dict):
            spell_definition = repository_spell_definition
        else:
            spell_definition = self._normalize_fallback_spell_definition(known_spell=known_spell, spell_id=spell_id)

        barbarian_error = self._validate_barbarian_rage_spell_restriction(actor=actor)
        if barbarian_error is not None:
            return barbarian_error

        base_level = self._resolve_base_level(spell_definition=spell_definition, known_spell=known_spell)
        is_cantrip = base_level == 0

        if is_cantrip and cast_level != 0:
            return {
                "ok": False,
                "error_code": "invalid_cantrip_cast_level",
                "message": f"{spell_id} 是戏法，cast_level 必须为 0",
            }

        if not is_cantrip and cast_level < base_level:
            return {
                "ok": False,
                "error_code": "invalid_cast_level",
                "message": f"{spell_id} 的施法环位不能低于基础环位 {base_level}",
            }

        action_cost = self._resolve_action_cost(spell_definition=spell_definition)
        normalized_declared_action = self._normalize_action_cost(declared_action_cost)
        if (
            isinstance(normalized_declared_action, str)
            and isinstance(action_cost, str)
            and normalized_declared_action != action_cost
        ):
            return {
                "ok": False,
                "error_code": "invalid_action_cost",
                "message": f"声明动作为 {normalized_declared_action}，但法术要求 {action_cost}",
            }
        effective_action_cost = action_cost or normalized_declared_action
        is_out_of_turn = isinstance(current_entity_id, str) and actor.entity_id != current_entity_id
        if allow_out_of_turn_actor and is_out_of_turn and effective_action_cost != "reaction":
            raise ValueError("out_of_turn_cast_requires_reaction")
        availability_error = self._validate_action_cost_available(
            actor=actor,
            action_cost=effective_action_cost,
        )
        if availability_error is not None:
            return availability_error

        normalized_target_ids = list(target_entity_ids or [])
        metamagic = self._resolve_metamagic(
            encounter=encounter,
            actor=actor,
            known_spell=known_spell,
            spell_definition=spell_definition,
            action_cost=effective_action_cost,
            target_entity_ids=normalized_target_ids,
            metamagic_options=metamagic_options,
        )
        if metamagic.get("ok") is False:
            return metamagic
        metamagic_summary = metamagic["metamagic"]
        noticeability = metamagic["noticeability"]
        actor_level = self._resolve_actor_level(actor=actor)
        scaling_mode, resolved_scaling = self._resolve_scaling(
            spell_definition=spell_definition,
            base_level=base_level,
            cast_level=cast_level,
            is_cantrip=is_cantrip,
            actor_level=actor_level,
            metamagic=metamagic_summary,
        )
        target_point_error = self._validate_target_point(
            encounter=encounter,
            actor=origin_actor,
            spell_definition=spell_definition,
            target_point=target_point,
            metamagic=metamagic_summary,
        )
        if target_point_error is not None:
            return target_point_error
        normalized_target_point = self._normalize_target_point(target_point)
        target_count_error = self._validate_target_count(
            spell_definition=spell_definition,
            target_entity_ids=normalized_target_ids,
            resolved_scaling=resolved_scaling,
        )
        if target_count_error is not None:
            return target_count_error
        target_validation_error = self._validate_target_types(
            encounter=encounter,
            spell_definition=spell_definition,
            target_entity_ids=normalized_target_ids,
        )
        if target_validation_error is not None:
            return target_validation_error
        single_target_error = self._validate_single_target_rules(
            encounter=encounter,
            actor=origin_actor,
            spell_definition=spell_definition,
            target_entity_ids=normalized_target_ids,
            metamagic=metamagic_summary,
        )
        if single_target_error is not None:
            return single_target_error

        upcast_delta = 0 if is_cantrip else max(cast_level - base_level, 0)
        requires_concentration = bool(spell_definition.get("base", {}).get("concentration", False))
        sorcerer_modifiers = self._resolve_sorcerer_spell_modifiers(actor=actor, known_spell=known_spell)

        return {
            "ok": True,
            "actor_id": actor_id,
            "spell_id": spell_id,
            "base_level": base_level,
            "cast_level": cast_level,
            "upcast_delta": upcast_delta,
            "is_cantrip": is_cantrip,
            "action_cost": effective_action_cost,
            "target_entity_ids": normalized_target_ids,
            "target_point": normalized_target_point,
            "requires_concentration": requires_concentration,
            "will_replace_concentration": False,
            "scaling_mode": scaling_mode,
            "resolved_scaling": resolved_scaling,
            "spell_definition": spell_definition,
            "area_template": spell_definition.get("area_template"),
            "spell_origin_entity_id": spell_origin.get("origin_entity_id"),
            "spell_origin_via_gaze_of_two_minds": bool(spell_origin.get("via_link")),
            "spell_attack_advantage": bool(sorcerer_modifiers["spell_attack_advantage"]),
            "spell_save_dc_bonus": int(sorcerer_modifiers["spell_save_dc_bonus"]),
            "metamagic": metamagic_summary,
            "noticeability": noticeability,
        }

    def _find_actor_spell_definition(self, *, actor: Any, spell_id: str) -> dict[str, Any] | None:
        for spell in actor.spells:
            if spell.get("spell_id") == spell_id:
                return spell
        return None

    def _normalize_fallback_spell_definition(
        self, *, known_spell: dict[str, Any], spell_id: str
    ) -> dict[str, Any]:
        normalized = dict(known_spell)

        known_level = known_spell.get("level")
        safe_level = known_level if isinstance(known_level, int) and known_level >= 0 else 0

        spell_name = known_spell.get("name")
        if not isinstance(spell_name, str) or not spell_name.strip():
            spell_name = spell_id

        normalized["id"] = str(known_spell.get("id") or known_spell.get("spell_id") or spell_id)
        normalized["name"] = spell_name
        normalized["level"] = safe_level

        base = normalized.get("base")
        if not isinstance(base, dict):
            base = {}
        if not isinstance(base.get("level"), int):
            base["level"] = safe_level
        normalized["base"] = base

        if not isinstance(normalized.get("resolution"), dict):
            normalized["resolution"] = {}
        if not isinstance(normalized.get("targeting"), dict):
            normalized["targeting"] = {}
        if not isinstance(normalized.get("on_cast"), dict):
            normalized["on_cast"] = {}
        if not isinstance(normalized.get("scaling"), dict):
            normalized["scaling"] = {}
        if not isinstance(normalized.get("effect_templates"), dict):
            normalized["effect_templates"] = {}
        if not isinstance(normalized.get("localization"), dict):
            normalized["localization"] = {}
        if not isinstance(normalized.get("runtime_support"), dict):
            normalized["runtime_support"] = {}
        if not isinstance(normalized.get("special_rules"), dict):
            normalized["special_rules"] = {}
        if not isinstance(normalized.get("usage_contexts"), list):
            normalized["usage_contexts"] = []
        if not isinstance(normalized.get("requires_attack_roll"), bool):
            normalized["requires_attack_roll"] = False
        save_ability = normalized.get("save_ability")
        if not isinstance(save_ability, str) or not save_ability.strip():
            normalized["save_ability"] = None
        return normalized

    def _resolve_base_level(self, *, spell_definition: dict[str, Any], known_spell: dict[str, Any]) -> int:
        base = spell_definition.get("base")
        if isinstance(base, dict):
            level = base.get("level")
            if isinstance(level, int) and level >= 0:
                return level

        level = spell_definition.get("level")
        if isinstance(level, int) and level >= 0:
            return level

        known_level = known_spell.get("level")
        if isinstance(known_level, int) and known_level >= 0:
            return known_level
        return 0

    def _normalize_action_cost(self, action_cost: str | None) -> str | None:
        if not isinstance(action_cost, str):
            return None
        normalized = action_cost.strip().lower()
        if not normalized:
            return None
        if normalized in {"bonus action", "bonus_action"}:
            return "bonus_action"
        return normalized.replace(" ", "_")

    def _resolve_spellcasting_class(self, *, known_spell: dict[str, Any]) -> str | None:
        casting_class = known_spell.get("casting_class")
        if isinstance(casting_class, str) and casting_class.strip():
            return casting_class.strip().lower()
        classes = known_spell.get("classes")
        if isinstance(classes, list) and len(classes) == 1:
            current_class = classes[0]
            if isinstance(current_class, str) and current_class.strip():
                return current_class.strip().lower()
        return None

    def _resolve_sorcerer_spell_modifiers(self, *, actor: Any, known_spell: dict[str, Any]) -> dict[str, Any]:
        if self._resolve_spellcasting_class(known_spell=known_spell) != "sorcerer":
            return {"spell_attack_advantage": False, "spell_save_dc_bonus": 0}
        sorcerer = ensure_sorcerer_runtime(actor)
        innate_sorcery = sorcerer.get("innate_sorcery")
        if not isinstance(innate_sorcery, dict) or not bool(innate_sorcery.get("active")):
            return {"spell_attack_advantage": False, "spell_save_dc_bonus": 0}
        return {"spell_attack_advantage": True, "spell_save_dc_bonus": 1}

    def _resolve_metamagic(
        self,
        *,
        encounter: Any,
        actor: Any,
        known_spell: dict[str, Any],
        spell_definition: dict[str, Any],
        action_cost: str | None,
        target_entity_ids: list[str],
        metamagic_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        default_result = {
            "ok": True,
            "metamagic": self._build_default_metamagic(),
            "noticeability": self._build_default_noticeability(),
        }
        if not isinstance(metamagic_options, dict):
            return default_result

        selected = metamagic_options.get("selected")
        if not isinstance(selected, list):
            return default_result

        normalized_selected = [str(item).strip().lower() for item in selected if str(item).strip()]
        if not normalized_selected:
            return default_result
        if len(normalized_selected) > 1:
            return {
                "ok": False,
                "error_code": "multiple_metamagic_not_supported",
                "message": "当前一次施法只支持声明一种超魔法",
            }

        if self._resolve_spellcasting_class(known_spell=known_spell) != "sorcerer":
            return {
                "ok": False,
                "error_code": "metamagic_requires_sorcerer_spell",
                "message": "只有术士法术可以使用超魔法",
            }

        sorcerer = ensure_sorcerer_runtime(actor)
        level = int(sorcerer.get("level", 0) or 0)
        if level < 2:
            return {
                "ok": False,
                "error_code": "subtle_spell_requires_sorcerer_level_2",
                "message": "精妙法术需要至少 2 级术士",
            }

        sorcery_points = sorcerer.get("sorcery_points")
        current_points = int(sorcery_points.get("current", 0) or 0) if isinstance(sorcery_points, dict) else 0
        if current_points < 1:
            return {
                "ok": False,
                "error_code": "insufficient_sorcery_points",
                "message": "术法点不足，无法使用精妙法术",
            }

        selected_metamagic = normalized_selected[0]
        supported_costs = {
            "subtle_spell": 1,
            "quickened_spell": 2,
            "distant_spell": 1,
            "heightened_spell": 2,
            "careful_spell": 1,
            "empowered_spell": 1,
            "extended_spell": 1,
            "seeking_spell": 1,
            "transmuted_spell": 1,
            "twinned_spell": 1,
        }
        if selected_metamagic not in supported_costs:
            return {
                "ok": False,
                "error_code": "unknown_metamagic_option",
                "message": f"未知超魔法选项：{selected_metamagic}",
            }

        metamagic = self._build_default_metamagic()
        metamagic["selected"] = [selected_metamagic]
        metamagic[selected_metamagic] = True
        metamagic["sorcery_point_cost"] = supported_costs[selected_metamagic]

        if selected_metamagic == "quickened_spell" and action_cost != "action":
            return {
                "ok": False,
                "error_code": "quickened_spell_requires_action_cast_time",
                "message": "瞬发法术只能作用于施法时间为动作的法术",
            }

        if selected_metamagic == "distant_spell":
            if not self._spell_can_use_distant_spell(spell_definition=spell_definition):
                return {
                    "ok": False,
                    "error_code": "distant_spell_requires_range_or_touch_spell",
                    "message": "远程法术只能用于具有射程或触碰距离的法术",
                }
            metamagic["effective_range_override_feet"] = self._resolve_distant_spell_range_override_feet(
                spell_definition=spell_definition
            )

        if selected_metamagic == "heightened_spell":
            if not self._spell_requires_saving_throw(spell_definition=spell_definition):
                return {
                    "ok": False,
                    "error_code": "heightened_spell_requires_saving_throw_spell",
                    "message": "升阶法术只能用于要求目标进行豁免的法术",
                }
            heightened_target_id = metamagic_options.get("heightened_target_id")
            if not isinstance(heightened_target_id, str) or not heightened_target_id.strip():
                return {
                    "ok": False,
                    "error_code": "heightened_spell_requires_target",
                    "message": "升阶法术需要指定一个吃劣势的目标",
                }
            if heightened_target_id not in target_entity_ids:
                return {
                    "ok": False,
                    "error_code": "heightened_target_not_in_spell_targets",
                    "message": "升阶法术指定的目标必须属于本次法术目标",
                }
            metamagic["heightened_target_id"] = heightened_target_id

        if selected_metamagic == "careful_spell":
            if not self._spell_requires_saving_throw(spell_definition=spell_definition):
                return {
                    "ok": False,
                    "error_code": "careful_spell_requires_saving_throw_spell",
                    "message": "谨慎法术只能用于要求目标进行豁免的法术",
                }
            careful_target_ids = metamagic_options.get("careful_target_ids")
            if not isinstance(careful_target_ids, list) or not careful_target_ids:
                return {
                    "ok": False,
                    "error_code": "careful_spell_requires_targets",
                    "message": "谨慎法术需要提供被保护目标列表",
                }
            normalized_careful_target_ids = [str(item).strip() for item in careful_target_ids if str(item).strip()]
            max_protected_targets = max(1, int(actor.ability_mods.get("cha", 0) or 0))
            if len(normalized_careful_target_ids) > max_protected_targets:
                return {
                    "ok": False,
                    "error_code": "careful_spell_too_many_targets",
                    "message": "谨慎法术指定的被保护目标数量超过了魅力调整值上限",
                }
            for entity_id in normalized_careful_target_ids:
                if entity_id not in encounter.entities:
                    return {
                        "ok": False,
                        "error_code": "careful_target_not_in_spell_targets",
                        "message": "谨慎法术指定的目标必须存在于当前遭遇战中",
                    }
            metamagic["careful_target_ids"] = normalized_careful_target_ids

        if selected_metamagic == "empowered_spell":
            if not self._spell_has_damage_resolution(spell_definition=spell_definition):
                return {
                    "ok": False,
                    "error_code": "empowered_spell_requires_damage_spell",
                    "message": "强效法术只能用于造成伤害的法术",
                }

        if selected_metamagic == "extended_spell":
            if not spell_supports_extended_spell(spell_definition):
                return {
                    "ok": False,
                    "error_code": "extended_spell_requires_duration_spell",
                    "message": "延效法术只能用于持续时间至少 1 分钟的法术",
                }

        if selected_metamagic == "seeking_spell":
            if not bool(spell_definition.get("requires_attack_roll")):
                return {
                    "ok": False,
                    "error_code": "seeking_spell_requires_attack_roll_spell",
                    "message": "追踪法术只能用于需要攻击检定的法术",
                }

        if selected_metamagic == "transmuted_spell":
            if not spell_supports_transmuted_spell(spell_definition):
                return {
                    "ok": False,
                    "error_code": "transmuted_spell_requires_eligible_damage_type",
                    "message": "转化法术只能用于造成可转化元素伤害的法术",
                }
            transmuted_damage_type = normalize_transmuted_damage_type(metamagic_options.get("transmuted_damage_type"))
            if transmuted_damage_type is None:
                return {
                    "ok": False,
                    "error_code": "invalid_transmuted_damage_type",
                    "message": "转化法术需要指定 acid/cold/fire/lightning/poison/thunder 之一",
                }
            metamagic["transmuted_damage_type"] = transmuted_damage_type

        if selected_metamagic == "twinned_spell":
            if not spell_supports_twinned_spell(spell_definition):
                return {
                    "ok": False,
                    "error_code": "twinned_spell_requires_scaling_target_spell",
                    "message": "孪生法术只能用于可通过升环增加目标的单体法术",
                }
            metamagic["effective_target_scaling_bonus_levels"] = 1

        noticeability = self._build_default_noticeability()
        if selected_metamagic == "subtle_spell":
            noticeability = {
                "casting_is_perceptible": False,
                "verbal_visible": False,
                "somatic_visible": False,
                "material_visible": False,
                "spell_effect_visible": True,
            }

        return {
            "ok": True,
            "metamagic": metamagic,
            "noticeability": noticeability,
        }

    def _build_default_metamagic(self) -> dict[str, Any]:
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

    def _build_default_noticeability(self) -> dict[str, Any]:
        return {
            "casting_is_perceptible": True,
            "verbal_visible": True,
            "somatic_visible": True,
            "material_visible": True,
            "spell_effect_visible": True,
        }

    def _spell_can_use_distant_spell(self, *, spell_definition: dict[str, Any]) -> bool:
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

    def _resolve_distant_spell_range_override_feet(self, *, spell_definition: dict[str, Any]) -> int | None:
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

    def _spell_requires_saving_throw(self, *, spell_definition: dict[str, Any]) -> bool:
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

    def _resolve_action_cost(self, *, spell_definition: dict[str, Any]) -> str | None:
        resolution = spell_definition.get("resolution")
        if isinstance(resolution, dict):
            activation = self._normalize_action_cost(resolution.get("activation"))
            if activation is not None:
                return activation

        base = spell_definition.get("base")
        if isinstance(base, dict):
            casting_time = base.get("casting_time")
            if isinstance(casting_time, str):
                casting_time_lower = casting_time.strip().lower()
                if "bonus" in casting_time_lower:
                    return "bonus_action"
                if "reaction" in casting_time_lower:
                    return "reaction"
                if "action" in casting_time_lower:
                    return "action"
        return None

    def _validate_action_cost_available(
        self,
        *,
        actor: Any,
        action_cost: str | None,
    ) -> dict[str, Any] | None:
        if not isinstance(action_cost, str):
            return None
        action_economy = actor.action_economy if isinstance(actor.action_economy, dict) else {}
        if action_cost == "action" and bool(action_economy.get("action_used")):
            return {
                "ok": False,
                "error_code": "action_already_used",
                "message": "该施法者本回合动作已用完",
            }
        if action_cost == "bonus_action" and bool(action_economy.get("bonus_action_used")):
            return {
                "ok": False,
                "error_code": "bonus_action_already_used",
                "message": "该施法者本回合附赠动作已用完",
            }
        if action_cost == "reaction" and bool(action_economy.get("reaction_used")):
            return {
                "ok": False,
                "error_code": "reaction_already_used",
                "message": "该施法者本轮反应已用完",
            }
        return None

    def _validate_barbarian_rage_spell_restriction(self, *, actor: Any) -> dict[str, Any] | None:
        if not actor.class_features.get("barbarian"):
            return None
        barbarian = ensure_barbarian_runtime(actor)
        rage = barbarian.get("rage")
        if isinstance(rage, dict) and bool(rage.get("active")):
            return {
                "ok": False,
                "error_code": "cannot_cast_spells_while_raging",
                "message": "狂暴期间不能施法",
            }
        return None

    def _resolve_scaling(
        self,
        *,
        spell_definition: dict[str, Any],
        base_level: int,
        cast_level: int,
        is_cantrip: bool,
        actor_level: int,
        metamagic: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        scaling = spell_definition.get("scaling")
        if not isinstance(scaling, dict):
            return ("cantrip", {"beam_count": 1}) if is_cantrip else ("none", {})

        if is_cantrip:
            return ("cantrip", self._resolve_cantrip_scaling(scaling=scaling, actor_level=actor_level))

        resolved: dict[str, Any] = {"upcast_delta": max(cast_level - base_level, 0)}
        slot_level_bonus = scaling.get("slot_level_bonus")
        if isinstance(slot_level_bonus, dict):
            base_slot_level = slot_level_bonus.get("base_slot_level")
            if not isinstance(base_slot_level, int):
                base_slot_level = base_level
            upcast_delta = max(cast_level - base_slot_level, 0)
            resolved["upcast_delta"] = upcast_delta

            additional_damage_parts = slot_level_bonus.get("additional_damage_parts")
            if isinstance(additional_damage_parts, list):
                resolved_extra_damage_parts: list[dict[str, Any]] = []
                for part in additional_damage_parts:
                    if not isinstance(part, dict):
                        continue
                    formula_per_extra_level = part.get("formula_per_extra_level")
                    if not isinstance(formula_per_extra_level, str) or not formula_per_extra_level.strip():
                        continue
                    if upcast_delta <= 0:
                        continue
                    resolved_extra_damage_parts.append(
                        {
                            "formula": self._multiply_formula(formula_per_extra_level.strip(), upcast_delta),
                            "damage_type": part.get("damage_type"),
                        }
                    )
                resolved["extra_damage_parts"] = resolved_extra_damage_parts

            additional_targets_per_extra_level = slot_level_bonus.get("additional_targets_per_extra_level")
            if isinstance(additional_targets_per_extra_level, int):
                resolved["additional_targets"] = max(upcast_delta, 0) * additional_targets_per_extra_level
                if isinstance(metamagic, dict):
                    effective_bonus_levels = metamagic.get("effective_target_scaling_bonus_levels")
                    if isinstance(effective_bonus_levels, int) and effective_bonus_levels > 0:
                        resolved["additional_targets"] += effective_bonus_levels * additional_targets_per_extra_level

        slot_duration_bonus = self._resolve_slot_duration_bonus(
            slot_duration_rules=scaling.get("slot_duration_bonus"),
            cast_level=cast_level,
        )
        if slot_duration_bonus is not None:
            resolved["slot_duration_bonus"] = slot_duration_bonus

        if not isinstance(slot_level_bonus, dict) and slot_duration_bonus is None:
            return ("none", {})

        return ("slot", resolved)

    def _resolve_slot_duration_bonus(
        self, *, slot_duration_rules: Any, cast_level: int
    ) -> dict[str, Any] | None:
        if not isinstance(slot_duration_rules, list):
            return None

        matched_rule: dict[str, Any] | None = None
        matched_slot_level = -1
        for rule in slot_duration_rules:
            if not isinstance(rule, dict):
                continue
            slot_level = rule.get("slot_level")
            if not isinstance(slot_level, int):
                continue
            if slot_level > cast_level or slot_level < matched_slot_level:
                continue

            duration = rule.get("duration")
            duration_zh = rule.get("duration_zh")
            has_duration = isinstance(duration, str) and bool(duration.strip())
            has_duration_zh = isinstance(duration_zh, str) and bool(duration_zh.strip())
            if not has_duration and not has_duration_zh:
                continue

            matched_rule = {"slot_level": slot_level}
            if has_duration:
                matched_rule["duration"] = duration.strip()
            if has_duration_zh:
                matched_rule["duration_zh"] = duration_zh.strip()
            matched_slot_level = slot_level
        return matched_rule

    def _resolve_cantrip_scaling(self, *, scaling: dict[str, Any], actor_level: int) -> dict[str, Any]:
        cantrip_by_level = scaling.get("cantrip_by_level")
        if not isinstance(cantrip_by_level, list):
            return {"beam_count": 1}

        resolved = {"beam_count": 1}
        selected_threshold = -1
        for rule in cantrip_by_level:
            if not isinstance(rule, dict):
                continue
            threshold = rule.get("caster_level")
            if not isinstance(threshold, int):
                continue
            if actor_level < threshold or threshold < selected_threshold:
                continue
            selected_threshold = threshold
            replace_formula = rule.get("replace_formula")
            if isinstance(replace_formula, str) and replace_formula.strip():
                resolved["replace_formula"] = replace_formula.strip()
            beam_count = rule.get("beam_count")
            if isinstance(beam_count, int) and beam_count > 0:
                resolved["beam_count"] = beam_count
        return resolved

    def _resolve_actor_level(self, *, actor: Any) -> int:
        source_ref = getattr(actor, "source_ref", None)
        if isinstance(source_ref, dict):
            caster_level = source_ref.get("caster_level")
            if isinstance(caster_level, int) and caster_level > 0:
                return caster_level
        return 1

    def _validate_target_count(
        self,
        *,
        spell_definition: dict[str, Any],
        target_entity_ids: list[str],
        resolved_scaling: dict[str, Any],
    ) -> dict[str, Any] | None:
        targeting = spell_definition.get("targeting")
        if not isinstance(targeting, dict):
            return None
        if targeting.get("type") != "single_target":
            return None

        max_targets = 1
        beam_count = resolved_scaling.get("beam_count")
        if isinstance(beam_count, int) and beam_count > max_targets:
            max_targets = beam_count
        additional_targets = resolved_scaling.get("additional_targets")
        if isinstance(additional_targets, int) and additional_targets > 0:
            max_targets += additional_targets

        target_count = len(target_entity_ids)
        if 1 <= target_count <= max_targets:
            return None

        if max_targets == 1:
            message = "该法术必须指定 1 个目标"
        else:
            message = f"该法术必须指定 1 到 {max_targets} 个目标"
        return {
            "ok": False,
            "error_code": "invalid_target_count",
            "message": message,
        }

    def _spell_has_damage_resolution(self, *, spell_definition: dict[str, Any]) -> bool:
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

    def _validate_target_types(
        self,
        *,
        encounter: Any,
        spell_definition: dict[str, Any],
        target_entity_ids: list[str],
    ) -> dict[str, Any] | None:
        if not target_entity_ids:
            return None

        targeting = spell_definition.get("targeting")
        allowed_target_types: Any = None
        if isinstance(targeting, dict):
            allowed_target_types = targeting.get("allowed_target_types")
        normalized_allowed = (
            {str(item).strip().lower() for item in allowed_target_types if isinstance(item, str)}
            if isinstance(allowed_target_types, list)
            else set()
        )

        for entity_id in target_entity_ids:
            target = encounter.entities.get(entity_id)
            if target is None:
                return {
                    "ok": False,
                    "error_code": "invalid_target",
                    "message": f"目标 {entity_id} 不存在",
                }
            if not normalized_allowed or "creature" in normalized_allowed:
                continue

            target_type = self._resolve_entity_type(target=target)
            if isinstance(target_type, str) and target_type in normalized_allowed:
                continue
            if "humanoid" in normalized_allowed:
                return {
                    "ok": False,
                    "error_code": "invalid_target_type",
                    "message": f"目标 {entity_id} 不是 humanoid",
                }
            return {
                "ok": False,
                "error_code": "invalid_target_type",
                "message": f"目标 {entity_id} 类型不合法",
            }
        return None

    def _validate_single_target_rules(
        self,
        *,
        encounter: Any,
        actor: Any,
        spell_definition: dict[str, Any],
        target_entity_ids: list[str],
        metamagic: dict[str, Any],
    ) -> dict[str, Any] | None:
        if len(target_entity_ids) != 1:
            return None

        targeting = spell_definition.get("targeting")
        if not isinstance(targeting, dict):
            return None
        if targeting.get("type") != "single_target":
            return None

        target = encounter.entities.get(target_entity_ids[0])
        if target is None:
            return None

        range_feet = metamagic.get("effective_range_override_feet")
        if not isinstance(range_feet, int):
            range_feet = targeting.get("range_feet")
        if isinstance(range_feet, int) and range_feet > 0:
            distance_feet = self._distance_feet(actor, target, encounter)
            if distance_feet > range_feet:
                return {
                    "ok": False,
                    "error_code": "target_out_of_range",
                    "message": "该目标超出法术施法距离。",
                }

        if bool(targeting.get("requires_line_of_sight")) and not self._has_line_of_sight(
            encounter=encounter,
            actor=actor,
            target=target,
        ):
            return {
                "ok": False,
                "error_code": "blocked_by_line_of_sight",
                "message": "当前无法指定该目标，因为视线被阻挡。",
            }

        return None

    def _validate_target_point(
        self,
        *,
        encounter: Any,
        actor: Any,
        spell_definition: dict[str, Any],
        target_point: dict[str, Any] | None,
        metamagic: dict[str, Any],
    ) -> dict[str, Any] | None:
        area_template = spell_definition.get("area_template")
        targeting = spell_definition.get("targeting")
        if not isinstance(area_template, dict) and not isinstance(targeting, dict):
            return None

        targeting_type = targeting.get("type") if isinstance(targeting, dict) else None
        if not isinstance(targeting_type, str):
            return None
        if not targeting_type.strip().lower().startswith("area_"):
            return None

        if not isinstance(target_point, dict):
            return {
                "ok": False,
                "error_code": "missing_target_point",
                "message": "该法术需要指定落点坐标。",
            }
        if not self._is_valid_target_point(target_point):
            return {
                "ok": False,
                "error_code": "invalid_target_point",
                "message": "area 法术必须提供包含 int x/y 的 target_point",
            }
        normalized_target_point = self._normalize_target_point(target_point)
        if normalized_target_point is None:
            return {
                "ok": False,
                "error_code": "invalid_target_point",
                "message": "当前只支持以格子中心为法术落点。",
            }
        if not self._is_target_point_in_spell_range(
            actor=actor,
            target_point=normalized_target_point,
            targeting=targeting,
            encounter=encounter,
            metamagic=metamagic,
        ):
            return {
                "ok": False,
                "error_code": "target_point_out_of_range",
                "message": "该落点超出法术施法距离。",
            }
        return None

    def _normalize_target_point(self, target_point: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(target_point, dict):
            return None
        x = target_point.get("x")
        y = target_point.get("y")
        if not self._is_int_coordinate(x) or not self._is_int_coordinate(y):
            return None
        anchor = target_point.get("anchor", "cell_center")
        if anchor != "cell_center":
            return None
        return {
            "x": int(x),
            "y": int(y),
            "anchor": "cell_center",
        }

    def _is_valid_target_point(self, target_point: dict[str, Any] | None) -> bool:
        if not isinstance(target_point, dict):
            return False
        x = target_point.get("x")
        y = target_point.get("y")
        return self._is_int_coordinate(x) and self._is_int_coordinate(y)

    def _is_target_point_in_spell_range(
        self,
        *,
        actor: Any,
        target_point: dict[str, Any],
        targeting: Any,
        encounter: Any,
        metamagic: dict[str, Any],
    ) -> bool:
        if not isinstance(targeting, dict):
            return True
        range_feet = metamagic.get("effective_range_override_feet")
        if not isinstance(range_feet, int):
            range_feet = targeting.get("range_feet")
        if not isinstance(range_feet, int) or range_feet <= 0:
            return True
        actor_center = get_center_position(actor)
        dx = abs(actor_center["x"] - target_point["x"])
        dy = abs(actor_center["y"] - target_point["y"])
        distance_feet = math.ceil(max(dx, dy)) * encounter.map.grid_size_feet
        return distance_feet <= range_feet

    def _distance_feet(self, source: Any, target: Any, encounter: Any) -> int:
        source_center = get_center_position(source)
        target_center = get_center_position(target)
        dx = abs(source_center["x"] - target_center["x"])
        dy = abs(source_center["y"] - target_center["y"])
        return math.ceil(max(dx, dy)) * encounter.map.grid_size_feet

    def _has_line_of_sight(self, *, encounter: Any, actor: Any, target: Any) -> bool:
        blocking_cells = {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
            and (terrain.get("blocks_los") or terrain.get("type") == "wall")
        }
        if not blocking_cells:
            return True

        actor_cells = get_occupied_cells(actor)
        target_cells = get_occupied_cells(target)
        source = get_center_position(actor)
        destination = get_center_position(target)
        steps = max(int(math.ceil(max(abs(destination["x"] - source["x"]), abs(destination["y"] - source["y"])) * 4)), 1)

        for index in range(1, steps):
            ratio = index / steps
            sample_x = source["x"] + (destination["x"] - source["x"]) * ratio
            sample_y = source["y"] + (destination["y"] - source["y"]) * ratio
            cell = (math.floor(sample_x + 0.5), math.floor(sample_y + 0.5))
            if cell in actor_cells or cell in target_cells:
                continue
            if cell in blocking_cells:
                return False
        return True

    def _is_int_coordinate(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def _resolve_entity_type(self, *, target: Any) -> str | None:
        source_ref = getattr(target, "source_ref", None)
        if isinstance(source_ref, dict):
            for key in ("entity_type", "creature_type", "monster_type", "target_type"):
                value = source_ref.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()

        category = getattr(target, "category", None)
        if isinstance(category, str):
            category_lower = category.strip().lower()
            if category_lower in {"pc", "npc"}:
                return "humanoid"
        return None

    def _multiply_formula(self, formula: str, multiplier: int) -> str:
        if multiplier <= 0:
            return "0d0"
        match = self._FORMULA_RE.match(formula)
        if match is None:
            return formula

        dice_count = int(match.group(1)) * multiplier
        die_size = int(match.group(2))
        flat_bonus = int(match.group(3) or 0) * multiplier
        if flat_bonus > 0:
            return f"{dice_count}d{die_size}+{flat_bonus}"
        if flat_bonus < 0:
            return f"{dice_count}d{die_size}{flat_bonus}"
        return f"{dice_count}d{die_size}"
