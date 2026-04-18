from __future__ import annotations

import re
from typing import Any

from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import get_monk_runtime
from tools.services.combat.rules.conditions import INCAPACITATING_CONDITIONS
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.shared.update_conditions import UpdateConditions
from tools.services.combat.shared.update_encounter_notes import UpdateEncounterNotes
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.events.append_event import AppendEvent
from tools.services.spells.build_spell_instance import build_spell_instance
from tools.services.spells.build_turn_effect_instance import build_turn_effect_instance


class SavingThrowResult:
    """处理一次豁免结果，并按结果触发后续效果。"""
    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        update_hp: UpdateHp | None = None,
        update_conditions: UpdateConditions | None = None,
        update_encounter_notes: UpdateEncounterNotes | None = None,
        resolve_damage_parts: ResolveDamageParts | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.update_hp = update_hp
        self.update_conditions = update_conditions
        self.update_encounter_notes = update_encounter_notes
        self.resolve_damage_parts = resolve_damage_parts or ResolveDamageParts()

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        roll_result: RollResult,
        spell_definition: dict[str, Any] | None = None,
        damage_rolls: list[dict[str, Any]] | None = None,
        cast_level: int | None = None,
        hp_change_on_failed_save: int | None = None,
        hp_change_on_success: int | None = None,
        damage_reason: str | None = None,
        damage_type: str | None = None,
        concentration_vantage: str = "normal",
        conditions_on_failed_save: list[str] | None = None,
        conditions_on_success: list[str] | None = None,
        note_on_failed_save: str | None = None,
        note_on_success: str | None = None,
    ) -> dict[str, Any]:
        """结算一次豁免。

        这层的职责是：
        1. 判断豁免成功还是失败
        2. 记录 `saving_throw_resolved`
        3. 视情况自动串上 HP、condition、note 的后续更新
        """
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        self._validate_request_and_result(encounter_id, roll_request, roll_result)

        target_id = roll_request.target_entity_id or roll_result.target_entity_id or roll_result.actor_entity_id
        target = encounter.entities.get(target_id)
        if target is None:
            raise ValueError(f"target '{target_id}' not found in encounter")
        caster_entity_id = roll_request.context.get("caster_entity_id")
        save_dc = roll_request.context.get("save_dc")
        save_ability = roll_request.context.get("save_ability")
        if not isinstance(save_dc, int):
            raise ValueError("roll_request.context.save_dc must be an integer")

        success = roll_result.final_total >= save_dc
        result = {
            "encounter_id": encounter_id,
            "spell_id": roll_request.context.get("spell_id"),
            "spell_name": roll_request.context.get("spell_name"),
            "caster_entity_id": caster_entity_id,
            "target_entity_id": target_id,
            "save_ability": save_ability,
            "save_dc": save_dc,
            "final_total": roll_result.final_total,
            "vantage": roll_result.metadata.get("vantage"),
            "chosen_roll": roll_result.metadata.get("chosen_roll"),
            "save_bonus": roll_result.metadata.get("save_bonus"),
            "save_bonus_breakdown": roll_result.metadata.get("save_bonus_breakdown"),
            "success": success,
            "failed": not success,
            "comparison": {
                "left_label": "saving_throw_total",
                "left_value": roll_result.final_total,
                "operator": ">=",
                "right_label": "save_dc",
                "right_value": save_dc,
                "passed": success,
            },
        }

        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="saving_throw_resolved",
            actor_entity_id=caster_entity_id,
            target_entity_id=target_id,
            request_id=roll_request.request_id,
            payload=result,
        )
        result["event_id"] = event.event_id

        self._validate_effect_input_mode(
            spell_definition=spell_definition,
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        )
        use_outcome_path = isinstance(spell_definition, dict)
        if use_outcome_path:
            selected_outcome, outcome = self._select_outcome(success=success, spell_definition=spell_definition)
            result["selected_outcome"] = selected_outcome

            damage_resolution = self._maybe_resolve_outcome_damage(
                roll_request=roll_request,
                roll_result=roll_result,
                outcome=outcome,
                spell_definition=spell_definition,
                damage_rolls=damage_rolls,
                cast_level=cast_level,
                caster_level=self._resolve_caster_level(encounter=encounter, caster_entity_id=caster_entity_id),
                target=target,
            )
            if damage_resolution is not None:
                damage_resolution = self._maybe_apply_evasion(
                    target=target,
                    roll_request=roll_request,
                    success=success,
                    spell_definition=spell_definition,
                    outcome=outcome,
                    damage_resolution=damage_resolution,
                )
                damage_resolution = self._maybe_apply_careful_spell_protection(
                    roll_request=roll_request,
                    success=success,
                    spell_definition=spell_definition,
                    outcome=outcome,
                    damage_resolution=damage_resolution,
                )
                result["damage_resolution"] = damage_resolution
                if self.update_hp is None:
                    raise ValueError("update_hp service is required when resolving spell outcome damage")
                result["hp_update"] = self.update_hp.execute(
                    encounter_id=encounter_id,
                    target_id=target_id,
                    hp_change=damage_resolution["total_damage"],
                    reason=damage_reason or str(spell_definition.get("name") or roll_request.reason),
                    damage_type=None,
                    source_entity_id=caster_entity_id,
                    concentration_vantage=concentration_vantage,
                )

            outcome_conditions = outcome.get("apply_conditions")
            if outcome_conditions is None:
                outcome_conditions = outcome.get("conditions", [])
            if not isinstance(outcome_conditions, list):
                raise ValueError("outcome.apply_conditions must be a list")
            result["condition_updates"] = self._maybe_apply_conditions(
                encounter_id=encounter_id,
                target_id=target_id,
                caster_entity_id=caster_entity_id,
                success=success,
                conditions_on_failed_save=outcome_conditions if not success else [],
                conditions_on_success=outcome_conditions if success else [],
            )

            result["turn_effect_updates"] = self._maybe_apply_turn_effects(
                encounter_id=encounter_id,
                caster_entity_id=caster_entity_id,
                target_id=target_id,
                spell_definition=spell_definition,
                outcome=outcome,
                save_dc=save_dc,
            )
            result["spell_instance"] = self._maybe_record_spell_instance(
                encounter_id=encounter_id,
                spell_definition=spell_definition,
                caster_entity_id=caster_entity_id,
                cast_level=cast_level,
                target_id=target_id,
                applied_conditions=outcome_conditions,
                turn_effect_updates=result["turn_effect_updates"],
            )

            outcome_note = outcome.get("note")
            if outcome_note is not None and not isinstance(outcome_note, str):
                raise ValueError("outcome.note must be a string or null")
            result["note_update"] = self._maybe_apply_note(
                encounter_id=encounter_id,
                target_id=target_id,
                caster_entity_id=caster_entity_id,
                success=success,
                note_on_failed_save=outcome_note if not success else None,
                note_on_success=outcome_note if success else None,
            )
            return result

        result["hp_update"] = self._maybe_apply_hp(
            encounter_id=encounter_id,
            target_id=target_id,
            success=success,
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            damage_reason=damage_reason or str(roll_request.reason),
            damage_type=damage_type,
            concentration_vantage=concentration_vantage,
            source_entity_id=caster_entity_id,
        )
        result["condition_updates"] = self._maybe_apply_conditions(
            encounter_id=encounter_id,
            target_id=target_id,
            caster_entity_id=caster_entity_id,
            success=success,
            conditions_on_failed_save=conditions_on_failed_save or [],
            conditions_on_success=conditions_on_success or [],
        )
        result["note_update"] = self._maybe_apply_note(
            encounter_id=encounter_id,
            target_id=target_id,
            caster_entity_id=caster_entity_id,
            success=success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        )
        return result

    def _validate_request_and_result(
        self,
        encounter_id: str,
        roll_request: RollRequest,
        roll_result: RollResult,
    ) -> None:
        if roll_request.encounter_id != encounter_id:
            raise ValueError("roll_request.encounter_id does not match encounter_id")
        if roll_result.encounter_id != encounter_id:
            raise ValueError("roll_result.encounter_id does not match encounter_id")
        if roll_request.roll_type != "saving_throw":
            raise ValueError("roll_request must use saving_throw")
        if roll_result.roll_type != "saving_throw":
            raise ValueError("roll_result must use saving_throw")
        if roll_request.request_id != roll_result.request_id:
            raise ValueError("roll_request.request_id does not match roll_result.request_id")
        if roll_request.actor_entity_id != roll_result.actor_entity_id:
            raise ValueError("roll_request.actor_entity_id does not match roll_result.actor_entity_id")

    def _has_legacy_effect_inputs(
        self,
        *,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        conditions_on_failed_save: list[str] | None,
        conditions_on_success: list[str] | None,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> bool:
        return any(
            [
                hp_change_on_failed_save is not None,
                hp_change_on_success is not None,
                bool(conditions_on_failed_save),
                bool(conditions_on_success),
                note_on_failed_save is not None,
                note_on_success is not None,
            ]
        )

    def _validate_effect_input_mode(
        self,
        *,
        spell_definition: dict[str, Any] | None,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        conditions_on_failed_save: list[str] | None,
        conditions_on_success: list[str] | None,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> None:
        if not isinstance(spell_definition, dict):
            return
        if not self._has_legacy_effect_inputs(
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        ):
            return
        raise ValueError("spell_definition cannot be combined with legacy save spell effect inputs")

    def _select_outcome(
        self,
        *,
        success: bool,
        spell_definition: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        on_cast = spell_definition.get("on_cast")
        if isinstance(on_cast, dict):
            key = "on_successful_save" if success else "on_failed_save"
            outcome = on_cast.get(key, {})
            if not isinstance(outcome, dict):
                raise ValueError(f"on_cast.{key} must be a dict")
            return ("successful_save" if success else "failed_save"), outcome

        key = "successful_save_outcome" if success else "failed_save_outcome"
        outcome = spell_definition.get(key, {})
        if not isinstance(outcome, dict):
            raise ValueError(f"{key} must be a dict")
        return ("successful_save" if success else "failed_save"), outcome

    def _maybe_resolve_outcome_damage(
        self,
        *,
        roll_request: RollRequest,
        roll_result: RollResult,
        outcome: dict[str, Any],
        spell_definition: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None,
        cast_level: int | None,
        caster_level: int | None,
        target: Any,
    ) -> dict[str, Any] | None:
        damage_parts = self._build_outcome_damage_parts(outcome=outcome, spell_definition=spell_definition)
        scaling = spell_definition.get("scaling")
        damage_parts = self._apply_cantrip_scaling(damage_parts=damage_parts, scaling=scaling, caster_level=caster_level)
        damage_parts = self._apply_slot_level_scaling(damage_parts=damage_parts, scaling=scaling, cast_level=cast_level)

        # outcome 不造成伤害时直接返回，避免对外部传入的 damage_rolls 做无意义校验。
        if not damage_parts:
            return None

        indexed_rolls = self._index_damage_rolls(damage_rolls)
        expected_sources = [part["source"] for part in damage_parts]
        self._validate_damage_roll_sources(expected_sources=expected_sources, actual_sources=list(indexed_rolls.keys()))

        resolved = self.resolve_damage_parts.execute(
            damage_parts=damage_parts,
            is_critical_hit=False,
            rolled_values=[indexed_rolls[source] for source in expected_sources],
            resistances=getattr(target, "resistances", []),
            immunities=getattr(target, "immunities", []),
            vulnerabilities=getattr(target, "vulnerabilities", []),
        )
        return self._apply_damage_multiplier(resolved=resolved, damage_multiplier=outcome.get("damage_multiplier"))

    def _build_outcome_damage_parts(
        self,
        *,
        outcome: dict[str, Any],
        spell_definition: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_damage_parts: Any
        damage_parts_mode = outcome.get("damage_parts_mode")
        if damage_parts_mode is None:
            raw_damage_parts = outcome.get("damage_parts", [])
        elif damage_parts_mode == "same_as_failed":
            on_cast = spell_definition.get("on_cast")
            if isinstance(on_cast, dict):
                failed_outcome = on_cast.get("on_failed_save", {})
            else:
                failed_outcome = spell_definition.get("failed_save_outcome", {})
            if not isinstance(failed_outcome, dict):
                raise ValueError("failed_save_outcome must be a dict")
            raw_damage_parts = failed_outcome.get("damage_parts", [])
        else:
            raise ValueError("outcome.damage_parts_mode must be 'same_as_failed' when provided")

        if not isinstance(raw_damage_parts, list):
            raise ValueError("outcome.damage_parts must be a list")

        normalized: list[dict[str, Any]] = []
        for index, part in enumerate(raw_damage_parts):
            if not isinstance(part, dict):
                raise ValueError(f"outcome.damage_parts[{index}] must be a dict")
            source = part.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"outcome.damage_parts[{index}].source must be a non-empty string")
            formula = part.get("formula")
            if not isinstance(formula, str) or not formula.strip():
                raise ValueError(f"outcome.damage_parts[{index}].formula must be a non-empty string")
            normalized.append(
                {
                    "source": source.strip(),
                    "formula": formula.strip(),
                    "damage_type": part.get("damage_type"),
                }
            )
        return normalized

    def _apply_cantrip_scaling(
        self,
        *,
        damage_parts: list[dict[str, Any]],
        scaling: Any,
        caster_level: int | None,
    ) -> list[dict[str, Any]]:
        scaled_parts = [dict(part) for part in damage_parts]
        if not scaled_parts:
            return scaled_parts
        if not isinstance(scaling, dict):
            return scaled_parts
        if not isinstance(caster_level, int):
            return scaled_parts

        cantrip_by_level = scaling.get("cantrip_by_level")
        if not isinstance(cantrip_by_level, list):
            return scaled_parts

        selected_formula: str | None = None
        selected_threshold = -1
        for rule in cantrip_by_level:
            if not isinstance(rule, dict):
                continue
            threshold = rule.get("caster_level")
            replace_formula = rule.get("replace_formula")
            if not isinstance(threshold, int):
                continue
            if not isinstance(replace_formula, str) or not replace_formula.strip():
                continue
            if caster_level >= threshold and threshold >= selected_threshold:
                selected_formula = replace_formula.strip()
                selected_threshold = threshold

        if selected_formula is not None:
            scaled_parts[0]["formula"] = selected_formula
        return scaled_parts

    def _apply_slot_level_scaling(
        self,
        *,
        damage_parts: list[dict[str, Any]],
        scaling: Any,
        cast_level: int | None,
    ) -> list[dict[str, Any]]:
        scaled_parts = [dict(part) for part in damage_parts]
        if not isinstance(scaling, dict):
            return scaled_parts

        slot_level_bonus = scaling.get("slot_level_bonus")
        if not isinstance(slot_level_bonus, dict):
            return scaled_parts
        if not isinstance(cast_level, int):
            return scaled_parts

        base_slot_level = slot_level_bonus.get("base_slot_level")
        if not isinstance(base_slot_level, int):
            return scaled_parts
        if cast_level <= base_slot_level:
            return scaled_parts

        additional_damage_parts = slot_level_bonus.get("additional_damage_parts")
        if not isinstance(additional_damage_parts, list):
            return scaled_parts

        extra_levels = cast_level - base_slot_level
        for index, part in enumerate(additional_damage_parts):
            if not isinstance(part, dict):
                raise ValueError(f"slot_level_bonus.additional_damage_parts[{index}] must be a dict")
            source = part.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(
                    f"slot_level_bonus.additional_damage_parts[{index}].source must be a non-empty string"
                )
            formula_per_extra_level = part.get("formula_per_extra_level")
            if not isinstance(formula_per_extra_level, str) or not formula_per_extra_level.strip():
                raise ValueError(
                    "slot_level_bonus.additional_damage_parts"
                    f"[{index}].formula_per_extra_level must be a non-empty string"
                )
            scaled_parts.append(
                {
                    "source": source.strip(),
                    "formula": self._multiply_formula(formula_per_extra_level.strip(), extra_levels),
                    "damage_type": part.get("damage_type"),
                }
            )
        return scaled_parts

    def _multiply_formula(self, formula: str, times: int) -> str:
        if times <= 0:
            raise ValueError("formula multiplier must be positive")
        match = self._FORMULA_RE.match(formula)
        if match is None:
            raise ValueError("invalid_damage_formula")

        dice_count = int(match.group(1)) * times
        die_size = int(match.group(2))
        flat_bonus = int(match.group(3) or 0) * times

        if flat_bonus > 0:
            bonus_text = f"+{flat_bonus}"
        elif flat_bonus < 0:
            bonus_text = str(flat_bonus)
        else:
            bonus_text = ""
        return f"{dice_count}d{die_size}{bonus_text}"

    def _apply_damage_multiplier(
        self,
        *,
        resolved: dict[str, Any],
        damage_multiplier: Any,
    ) -> dict[str, Any]:
        if damage_multiplier is None:
            return resolved
        if not isinstance(damage_multiplier, (int, float)):
            raise ValueError("outcome.damage_multiplier must be a number")
        if damage_multiplier < 0:
            raise ValueError("outcome.damage_multiplier must be >= 0")
        if damage_multiplier == 1:
            return resolved

        parts = resolved.get("parts", [])
        if not isinstance(parts, list):
            raise ValueError("damage_resolution.parts must be a list")

        total_damage = 0
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError("damage_resolution.parts must contain dict items")
            adjusted_total = part.get("adjusted_total")
            if not isinstance(adjusted_total, int):
                raise ValueError("damage_resolution.parts[].adjusted_total must be an integer")
            multiplied = int(adjusted_total * damage_multiplier)
            if multiplied < 0:
                multiplied = 0
            part["adjusted_total"] = multiplied
            total_damage += multiplied

        resolved["total_damage"] = total_damage
        return resolved

    def _maybe_apply_evasion(
        self,
        *,
        target: Any,
        roll_request: RollRequest,
        success: bool,
        spell_definition: dict[str, Any],
        outcome: dict[str, Any],
        damage_resolution: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._is_evasion_eligible(
            target=target,
            save_ability=roll_request.context.get("save_ability"),
            spell_definition=spell_definition,
            outcome=outcome,
        ):
            return damage_resolution

        adjusted = {
            **damage_resolution,
            "parts": [dict(part) for part in damage_resolution.get("parts", [])],
        }
        for part in adjusted["parts"]:
            adjusted_total = part.get("adjusted_total")
            if not isinstance(adjusted_total, int):
                raise ValueError("damage_resolution.parts[].adjusted_total must be an integer")
            part["adjusted_total"] = 0 if success else adjusted_total // 2

        adjusted["total_damage"] = sum(part["adjusted_total"] for part in adjusted["parts"])
        adjusted["feature_adjustment"] = {
            "feature_id": "monk.evasion",
            "rule": "success_zero_failure_half",
            "applied": True,
        }
        return adjusted

    def _is_evasion_eligible(
        self,
        *,
        target: Any,
        save_ability: Any,
        spell_definition: dict[str, Any],
        outcome: dict[str, Any],
    ) -> bool:
        if str(save_ability).strip().lower() != "dex":
            return False
        monk_runtime = get_monk_runtime(target)
        if not isinstance(monk_runtime, dict):
            return False
        evasion_runtime = monk_runtime.get("evasion")
        if not isinstance(evasion_runtime, dict) or not bool(evasion_runtime.get("enabled")):
            return False
        if any(condition in INCAPACITATING_CONDITIONS for condition in getattr(target, "conditions", [])):
            return False
        if self._is_success_half_damage_spell(spell_definition=spell_definition):
            return True
        damage_multiplier = outcome.get("damage_multiplier")
        return damage_multiplier == 0.5

    def _is_success_half_damage_spell(self, *, spell_definition: dict[str, Any]) -> bool:
        selected_outcome: dict[str, Any] | None = None
        on_cast = spell_definition.get("on_cast")
        if isinstance(on_cast, dict):
            maybe_outcome = on_cast.get("on_successful_save")
            if isinstance(maybe_outcome, dict):
                selected_outcome = maybe_outcome
        if selected_outcome is None:
            maybe_outcome = spell_definition.get("successful_save_outcome")
            if isinstance(maybe_outcome, dict):
                selected_outcome = maybe_outcome
        if selected_outcome is None:
            return False
        return selected_outcome.get("damage_multiplier") == 0.5

    def _maybe_apply_careful_spell_protection(
        self,
        *,
        roll_request: RollRequest,
        success: bool,
        spell_definition: dict[str, Any],
        outcome: dict[str, Any],
        damage_resolution: dict[str, Any],
    ) -> dict[str, Any]:
        if not success:
            return damage_resolution
        if not bool(roll_request.context.get("auto_success")):
            return damage_resolution
        if not self._is_success_half_damage_spell(spell_definition=spell_definition) and outcome.get("damage_multiplier") != 0.5:
            return damage_resolution

        adjusted = {
            **damage_resolution,
            "parts": [dict(part) for part in damage_resolution.get("parts", [])],
        }
        for part in adjusted["parts"]:
            adjusted_total = part.get("adjusted_total")
            if not isinstance(adjusted_total, int):
                raise ValueError("damage_resolution.parts[].adjusted_total must be an integer")
            part["adjusted_total"] = 0

        adjusted["total_damage"] = 0
        adjusted["metamagic_adjustment"] = {
            "metamagic_id": "careful_spell",
            "rule": "successful_half_damage_becomes_zero",
            "applied": True,
        }
        return adjusted

    def _maybe_apply_turn_effects(
        self,
        *,
        encounter_id: str,
        target_id: str,
        spell_definition: dict[str, Any],
        outcome: dict[str, Any],
        caster_entity_id: Any,
        save_dc: int,
    ) -> list[dict[str, Any]]:
        raw_effects = outcome.get("apply_turn_effects", [])
        if not isinstance(raw_effects, list) or not raw_effects:
            return []

        if not isinstance(caster_entity_id, str):
            raise ValueError("caster entity is required when applying turn effects")

        current_encounter = self.encounter_repository.get(encounter_id)
        if current_encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        caster = current_encounter.entities.get(caster_entity_id)
        if caster is None:
            raise ValueError("caster entity is required when applying turn effects")
        target = current_encounter.entities.get(target_id)
        if target is None:
            raise ValueError("target entity is required when applying turn effects")

        updates: list[dict[str, Any]] = []
        for index, item in enumerate(raw_effects):
            if not isinstance(item, dict):
                raise ValueError(f"apply_turn_effects[{index}] must be a dict")
            effect_template_id = item.get("effect_template_id")
            if not isinstance(effect_template_id, str) or not effect_template_id.strip():
                raise ValueError(f"apply_turn_effects[{index}].effect_template_id must be a non-empty string")
            instance = build_turn_effect_instance(
                spell_definition=spell_definition,
                effect_template_id=effect_template_id.strip(),
                caster=caster,
                save_dc=save_dc,
            )
            target.turn_effects.append(instance)
            updates.append(
                {
                    "effect_id": instance["effect_id"],
                    "effect_template_id": effect_template_id.strip(),
                    "trigger": instance.get("trigger"),
                }
            )
        self.encounter_repository.save(current_encounter)
        return updates

    def _maybe_record_spell_instance(
        self,
        *,
        encounter_id: str,
        spell_definition: dict[str, Any],
        caster_entity_id: Any,
        cast_level: int | None,
        target_id: str,
        applied_conditions: list[str],
        turn_effect_updates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not isinstance(caster_entity_id, str):
            return None
        if not isinstance(cast_level, int):
            spell_level = spell_definition.get("level")
            cast_level = spell_level if isinstance(spell_level, int) else 0

        current_encounter = self.encounter_repository.get(encounter_id)
        if current_encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        caster = current_encounter.entities.get(caster_entity_id)
        if caster is None:
            raise ValueError("caster entity is required when creating spell instance")

        turn_effect_ids = [
            update["effect_id"]
            for update in turn_effect_updates
            if isinstance(update, dict) and isinstance(update.get("effect_id"), str)
        ]
        if not applied_conditions and not turn_effect_ids:
            return None

        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=caster,
            cast_level=cast_level,
            targets=[
                {
                    "entity_id": target_id,
                    "applied_conditions": list(applied_conditions),
                    "turn_effect_ids": turn_effect_ids,
                }
            ],
            started_round=current_encounter.round,
        )
        current_encounter.spell_instances.append(instance)
        self.encounter_repository.save(current_encounter)
        return instance

    def _index_damage_rolls(self, damage_rolls: list[dict[str, Any]] | None) -> dict[str, list[int]]:
        indexed: dict[str, list[int]] = {}
        for item in damage_rolls or []:
            if not isinstance(item, dict):
                raise ValueError("damage_rolls must contain dict items")
            source = item.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("damage_roll_source must be a non-empty string")
            if source in indexed:
                raise ValueError(f"duplicate_damage_roll_source: {source}")
            rolls = item.get("rolls", [])
            if not isinstance(rolls, list):
                raise ValueError(f"damage_rolls[{source}] rolls must be a list")
            indexed[source] = rolls
        return indexed

    def _validate_damage_roll_sources(
        self,
        *,
        expected_sources: list[str],
        actual_sources: list[str],
    ) -> None:
        actual_source_set = set(actual_sources)

        missing = sorted(source for source in expected_sources if source not in actual_source_set)
        unknown = sorted(source for source in actual_sources if source not in expected_sources)
        if unknown:
            raise ValueError(f"unknown_damage_roll_sources: {', '.join(unknown)}")
        if missing:
            raise ValueError(f"missing_damage_roll_sources: {', '.join(missing)}")

    def _resolve_caster_level(self, *, encounter: Any, caster_entity_id: Any) -> int | None:
        if not isinstance(caster_entity_id, str) or not caster_entity_id:
            return None
        caster = encounter.entities.get(caster_entity_id)
        if caster is None:
            return None
        caster_level = caster.source_ref.get("caster_level")
        if isinstance(caster_level, int):
            return caster_level
        return None

    def _maybe_apply_hp(
        self,
        *,
        encounter_id: str,
        target_id: str,
        success: bool,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        damage_reason: str,
        damage_type: str | None,
        concentration_vantage: str,
        source_entity_id: str | None,
    ) -> dict[str, Any] | None:
        hp_change = hp_change_on_success if success else hp_change_on_failed_save
        if hp_change is None:
            return None
        if self.update_hp is None:
            raise ValueError("update_hp service is required when hp change is provided")

        return self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            hp_change=hp_change,
            reason=damage_reason,
            damage_type=damage_type,
            source_entity_id=source_entity_id,
            concentration_vantage=concentration_vantage,
        )

    def _maybe_apply_conditions(
        self,
        *,
        encounter_id: str,
        target_id: str,
        caster_entity_id: str | None,
        success: bool,
        conditions_on_failed_save: list[str],
        conditions_on_success: list[str],
    ) -> list[dict[str, Any]]:
        conditions = conditions_on_success if success else conditions_on_failed_save
        if not conditions:
            return []
        if self.update_conditions is None:
            raise ValueError("update_conditions service is required when conditions are provided")

        results: list[dict[str, Any]] = []
        for condition in conditions:
            results.append(
                self.update_conditions.execute(
                    encounter_id=encounter_id,
                    target_id=target_id,
                    condition=condition,
                    operation="apply",
                    source_entity_id=caster_entity_id,
                    reason="saving throw result",
                )
            )
        return results

    def _maybe_apply_note(
        self,
        *,
        encounter_id: str,
        target_id: str,
        caster_entity_id: str | None,
        success: bool,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> dict[str, Any] | None:
        note = note_on_success if success else note_on_failed_save
        if note is None:
            return None
        if self.update_encounter_notes is None:
            raise ValueError("update_encounter_notes service is required when note is provided")

        return self.update_encounter_notes.execute(
            encounter_id=encounter_id,
            action="add",
            note=note,
            entity_id=target_id,
            actor_entity_id=caster_entity_id,
        )
