from __future__ import annotations

import math
import re
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared.warlock_invocations import resolve_gaze_of_two_minds_origin
from tools.services.combat.shared.turn_actor_guard import resolve_current_turn_actor_or_raise
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells


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
        actor_level = self._resolve_actor_level(actor=actor)
        scaling_mode, resolved_scaling = self._resolve_scaling(
            spell_definition=spell_definition,
            base_level=base_level,
            cast_level=cast_level,
            is_cantrip=is_cantrip,
            actor_level=actor_level,
        )
        target_point_error = self._validate_target_point(
            encounter=encounter,
            actor=origin_actor,
            spell_definition=spell_definition,
            target_point=target_point,
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
        )
        if single_target_error is not None:
            return single_target_error

        upcast_delta = 0 if is_cantrip else max(cast_level - base_level, 0)
        requires_concentration = bool(spell_definition.get("base", {}).get("concentration", False))

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
    ) -> bool:
        if not isinstance(targeting, dict):
            return True
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
