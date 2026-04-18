from __future__ import annotations

import random
from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.rules.concentration.request_concentration_check import RequestConcentrationCheck
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared.proficiency_resolver import resolve_entity_save_proficiencies
from tools.services.events.append_event import AppendEvent
from tools.services.spells.end_concentration_spell_instances import end_concentration_spell_instances


class UpdateHp:
    """处理伤害或治疗，并把结果写回 encounter 快照和事件日志。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        request_concentration_check: RequestConcentrationCheck | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.request_concentration_check = request_concentration_check

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        hp_change: int,
        reason: str,
        damage_type: str | None = None,
        from_critical_hit: bool = False,
        source_entity_id: str | None = None,
        attack_kind: str | None = None,
        zero_hp_intent: str | None = None,
        concentration_vantage: str = "normal",
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        """更新目标 HP。

        约定：
        - `hp_change > 0` 表示受到伤害
        - `hp_change < 0` 表示受到治疗
        - `hp_change == 0` 表示无变化
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        target = self._get_entity_or_raise(encounter, target_id)

        if not isinstance(hp_change, int):
            raise ValueError("hp_change must be an integer")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")

        hp_before = target.hp["current"]
        temp_hp_before = target.hp["temp"]
        normalized_damage_type = self._normalize_damage_type(damage_type)
        class_feature_resolution: dict[str, Any] = {}

        if hp_change > 0:
            adjusted_damage, damage_adjustment = self._adjust_damage_by_traits(
                target,
                hp_change,
                normalized_damage_type,
            )
            result = self._apply_damage(target, adjusted_damage)
            result["original_hp_change"] = hp_change
            result["adjusted_hp_change"] = adjusted_damage
            result["damage_adjustment"] = damage_adjustment
            relentless_rage = self._maybe_apply_relentless_rage(
                target=target,
                adjusted_damage=adjusted_damage,
            )
            if relentless_rage is not None:
                class_feature_resolution["relentless_rage"] = relentless_rage
                result["hp_after"] = target.hp["current"]
            abjure_foes_cleanup = self._clear_abjure_foes_on_damage(target)
            if abjure_foes_cleanup is not None:
                class_feature_resolution["abjure_foes"] = abjure_foes_cleanup
            event_type = "damage_applied"
        elif hp_change < 0:
            if bool(target.combat_flags.get("is_dead")):
                result = {
                    "hp_before": hp_before,
                    "hp_after": hp_before,
                    "temp_hp_before": temp_hp_before,
                    "temp_hp_after": temp_hp_before,
                    "applied_change": 0,
                    "temp_hp_absorbed": 0,
                    "original_hp_change": hp_change,
                    "adjusted_hp_change": 0,
                    "damage_adjustment": None,
                    "healing_blocked": True,
                    "healing_blocked_reason": "target_is_dead",
                }
                event_type = "hp_unchanged"
            else:
                result = self._apply_healing(target, abs(hp_change))
                result["original_hp_change"] = hp_change
                result["adjusted_hp_change"] = hp_change
                result["damage_adjustment"] = None
                event_type = "healing_applied"
        else:
            result = {
                "hp_before": hp_before,
                "hp_after": hp_before,
                "temp_hp_before": temp_hp_before,
                "temp_hp_after": temp_hp_before,
                "applied_change": 0,
                "temp_hp_absorbed": 0,
                "original_hp_change": 0,
                "adjusted_hp_change": 0,
                "damage_adjustment": None,
            }
            event_type = "hp_unchanged"

        zero_hp_outcome = self._resolve_zero_hp_outcome(
            encounter=encounter,
            target=target,
            hp_before=hp_before,
            hp_after=result["hp_after"],
            attack_kind=attack_kind,
            zero_hp_intent=zero_hp_intent,
        )
        zero_hp_followup = self._resolve_zero_hp_followup(
            encounter=encounter,
            target=target,
            hp_before=hp_before,
            hp_after=result["hp_after"],
            adjusted_damage=result["adjusted_hp_change"],
            from_critical_hit=from_critical_hit,
        )
        if zero_hp_followup is not None and zero_hp_followup.get("outcome") == "entity_dead":
            self._remove_summons_for_dead_summoner(
                encounter=encounter,
                summoner_entity_id=target.entity_id,
            )
        retarget_updates = self._maybe_enable_retarget_marked_spells(
            encounter=encounter,
            target=target,
            hp_before=hp_before,
            hp_after=result["hp_after"],
        )

        self.encounter_repository.save(encounter)

        payload = {
            "target_id": target_id,
            "hp_change": hp_change,
            "reason": reason,
            "damage_type": normalized_damage_type,
            "from_critical_hit": from_critical_hit,
            "source_entity_id": source_entity_id,
            **result,
        }
        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type=event_type,
            actor_entity_id=source_entity_id,
            target_entity_id=target_id,
            payload=payload,
        )

        response = {
            "encounter_id": encounter_id,
            "target_id": target_id,
            "event_id": event.event_id,
            "event_type": event_type,
            **payload,
        }
        if zero_hp_outcome is not None:
            response["zero_hp_outcome"] = zero_hp_outcome
        if zero_hp_followup is not None:
            response["zero_hp_followup"] = zero_hp_followup
        if retarget_updates:
            response["retarget_updates"] = retarget_updates
        if class_feature_resolution:
            response["class_feature_resolution"] = class_feature_resolution
        concentration_check_request = self._maybe_request_concentration_check(
            encounter_id=encounter_id,
            target=target,
            adjusted_damage=result["adjusted_hp_change"],
            source_entity_id=source_entity_id,
            concentration_vantage=concentration_vantage,
        )
        if concentration_check_request is not None:
            response["concentration_check_request"] = concentration_check_request.to_dict()
        if include_encounter_state:
            from tools.services.encounter.get_encounter_state import GetEncounterState

            response["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return response

    def _clear_abjure_foes_on_damage(self, target: EncounterEntity) -> dict[str, Any] | None:
        turn_effects = target.turn_effects if isinstance(target.turn_effects, list) else []
        remaining_effects: list[Any] = []
        removed_source_ids: set[str] = set()
        removed_effects = 0
        for effect in turn_effects:
            if (
                isinstance(effect, dict)
                and effect.get("effect_type") == "abjure_foes_restriction"
                and bool(effect.get("ends_on_damage"))
            ):
                source_entity_id = effect.get("source_entity_id")
                if isinstance(source_entity_id, str) and source_entity_id.strip():
                    removed_source_ids.add(source_entity_id)
                removed_effects += 1
                continue
            remaining_effects.append(effect)

        if removed_effects == 0:
            return None

        target.turn_effects = remaining_effects
        if isinstance(target.conditions, list) and removed_source_ids:
            target.conditions = [
                condition
                for condition in target.conditions
                if not (
                    isinstance(condition, str)
                    and any(condition == f"frightened:{source_id}" for source_id in removed_source_ids)
                )
            ]
        return {
            "removed_effects": removed_effects,
            "removed_sources": sorted(removed_source_ids),
        }

    def _maybe_apply_relentless_rage(
        self,
        *,
        target: EncounterEntity,
        adjusted_damage: int,
    ) -> dict[str, Any] | None:
        if int(target.hp.get("current", 0) or 0) != 0:
            return None

        barbarian = ensure_barbarian_runtime(target)
        rage = barbarian.get("rage")
        relentless_rage = barbarian.get("relentless_rage")
        if not isinstance(rage, dict) or not bool(rage.get("active")):
            return None
        if not isinstance(relentless_rage, dict) or not bool(relentless_rage.get("enabled")):
            return None
        if adjusted_damage >= int(target.hp.get("max", 0) or 0):
            return None

        current_dc = relentless_rage.get("current_dc", 10)
        if isinstance(current_dc, bool) or not isinstance(current_dc, int) or current_dc < 0:
            current_dc = 10

        base_roll = random.randint(1, 20)
        con_modifier = int(target.ability_mods.get("con", 0) or 0)
        is_proficient = "con" in resolve_entity_save_proficiencies(target)
        proficiency_bonus = int(target.proficiency_bonus or 0) if is_proficient else 0
        save_total = base_roll + con_modifier + proficiency_bonus

        relentless_rage["current_dc"] = current_dc + 5
        success = save_total >= current_dc
        if success:
            level = barbarian.get("level", 0)
            if isinstance(level, bool) or not isinstance(level, int) or level < 0:
                level = 0
            restored_hp = level * 2
            target.hp["current"] = restored_hp
            target.combat_flags["is_dead"] = False
            target.combat_flags["is_defeated"] = False

        return {
            "triggered": True,
            "success": success,
            "save_dc": current_dc,
            "base_roll": base_roll,
            "save_total": save_total,
            "save_bonus": con_modifier + proficiency_bonus,
            "next_dc": relentless_rage["current_dc"],
            "hp_after": target.hp["current"],
        }

    def _adjust_damage_by_traits(
        self,
        target: EncounterEntity,
        damage: int,
        damage_type: str | None,
    ) -> tuple[int, dict[str, Any] | None]:
        # 没有伤害类型时，系统无法判断抗性 / 免疫 / 易伤，直接按原值处理。
        if damage_type is None:
            return damage, None

        has_immunity = damage_type in self._normalize_damage_type_list(target.immunities)
        has_resistance = damage_type in self._normalize_damage_type_list(target.resistances)
        has_vulnerability = damage_type in self._normalize_damage_type_list(target.vulnerabilities)

        if has_immunity:
            return (
                0,
                {
                    "rule": "immunity",
                    "damage_type": damage_type,
                    "original_damage": damage,
                    "adjusted_damage": 0,
                },
            )

        if has_resistance and has_vulnerability:
            return (
                damage,
                {
                    "rule": "resistance_and_vulnerability_cancel",
                    "damage_type": damage_type,
                    "original_damage": damage,
                    "adjusted_damage": damage,
                },
            )

        if has_resistance:
            adjusted_damage = damage // 2
            return (
                adjusted_damage,
                {
                    "rule": "resistance",
                    "damage_type": damage_type,
                    "original_damage": damage,
                    "adjusted_damage": adjusted_damage,
                },
            )

        if has_vulnerability:
            adjusted_damage = damage * 2
            return (
                adjusted_damage,
                {
                    "rule": "vulnerability",
                    "damage_type": damage_type,
                    "original_damage": damage,
                    "adjusted_damage": adjusted_damage,
                },
            )

        return (
            damage,
            {
                "rule": "normal",
                "damage_type": damage_type,
                "original_damage": damage,
                "adjusted_damage": damage,
            },
        )

    def _apply_damage(self, target: EncounterEntity, damage: int) -> dict[str, int]:
        hp_before = target.hp["current"]
        temp_hp_before = target.hp["temp"]

        temp_hp_absorbed = min(temp_hp_before, damage)
        remaining_damage = damage - temp_hp_absorbed

        target.hp["temp"] = temp_hp_before - temp_hp_absorbed
        target.hp["current"] = max(0, hp_before - remaining_damage)

        return {
            "hp_before": hp_before,
            "hp_after": target.hp["current"],
            "temp_hp_before": temp_hp_before,
            "temp_hp_after": target.hp["temp"],
            "applied_change": damage,
            "temp_hp_absorbed": temp_hp_absorbed,
        }

    def _resolve_zero_hp_outcome(
        self,
        *,
        encounter: Encounter,
        target: EncounterEntity,
        hp_before: int,
        hp_after: int,
        attack_kind: str | None,
        zero_hp_intent: str | None,
    ) -> dict[str, Any] | None:
        if hp_before <= 0 or hp_after != 0:
            return None

        if target.category == "monster":
            remains = {
                "remains_id": f"remains_{target.entity_id}",
                "icon": "💀",
                "label": f"{target.name}尸骸",
                "position": dict(target.position),
                "source_entity_id": target.entity_id,
            }
            encounter.map.remains.append(remains)
            self._remove_entity_from_encounter(encounter, target.entity_id)
            return {
                "outcome": "monster_removed_with_remains",
                "position": dict(remains["position"]),
                "icon": remains["icon"],
            }

        if target.category == "summon":
            self._clear_summon_runtime_links(encounter=encounter, summon_entity_id=target.entity_id)
            self._remove_entity_from_encounter(encounter, target.entity_id)
            return {
                "outcome": "summon_removed",
                "position": dict(target.position),
            }

        if target.category in {"pc", "npc"}:
            if "unconscious" not in target.conditions:
                target.conditions.append("unconscious")
            target.combat_flags["is_defeated"] = False
            target.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
            target.combat_flags["is_dead"] = False
            self._end_concentration_if_needed(
                encounter=encounter,
                target=target,
                reason="concentration_broken",
            )
            if self._should_apply_knockout_protection(
                target=target,
                attack_kind=attack_kind,
                zero_hp_intent=zero_hp_intent,
            ):
                self._apply_knockout_protection(target)
            return {
                "outcome": "entity_dying",
                "position": dict(target.position),
            }

        target.combat_flags["is_defeated"] = True
        return {
            "outcome": "entity_disabled",
            "position": dict(target.position),
        }

    def _apply_healing(self, target: EncounterEntity, healing: int) -> dict[str, int]:
        hp_before = target.hp["current"]
        temp_hp_before = target.hp["temp"]

        target.hp["current"] = min(target.hp["max"], hp_before + healing)
        actual_healing = target.hp["current"] - hp_before

        return {
            "hp_before": hp_before,
            "hp_after": target.hp["current"],
            "temp_hp_before": temp_hp_before,
            "temp_hp_after": temp_hp_before,
            "applied_change": -actual_healing,
            "temp_hp_absorbed": 0,
        }

    def _resolve_zero_hp_followup(
        self,
        *,
        encounter: Encounter,
        target: EncounterEntity,
        hp_before: int,
        hp_after: int,
        adjusted_damage: int,
        from_critical_hit: bool,
    ) -> dict[str, Any] | None:
        if hp_before > 0 or hp_after != 0 or adjusted_damage <= 0:
            return None
        if target.category not in {"pc", "npc"}:
            return None

        target.combat_flags["is_defeated"] = False
        self._remove_knockout_protection(target)

        if adjusted_damage >= target.hp["max"]:
            target.combat_flags["is_dead"] = True
            self._end_concentration_if_needed(
                encounter=encounter,
                target=target,
                reason="concentration_broken",
            )
            return {
                "outcome": "entity_dead",
                "reason": "massive_damage",
            }

        death_saves = target.combat_flags.get("death_saves")
        if not isinstance(death_saves, dict):
            death_saves = {"successes": 0, "failures": 0}
            target.combat_flags["death_saves"] = death_saves

        failures = death_saves.get("failures", 0)
        if not isinstance(failures, int):
            failures = 0
        failures += 2 if from_critical_hit else 1
        death_saves["failures"] = failures

        if "successes" not in death_saves or not isinstance(death_saves.get("successes"), int):
            death_saves["successes"] = 0

        is_dead = failures >= 3
        target.combat_flags["is_dead"] = is_dead
        if is_dead:
            self._end_concentration_if_needed(
                encounter=encounter,
                target=target,
                reason="concentration_broken",
            )
        return {
            "outcome": "entity_dead" if is_dead else "death_save_failure",
            "death_save_failures": failures,
        }

    def _should_apply_knockout_protection(
        self,
        *,
        target: EncounterEntity,
        attack_kind: str | None,
        zero_hp_intent: str | None,
    ) -> bool:
        return (
            target.category in {"pc", "npc"}
            and attack_kind == "melee_weapon"
            and zero_hp_intent == "knockout"
        )

    def _apply_knockout_protection(self, target: EncounterEntity) -> None:
        self._remove_knockout_protection(target)
        target.turn_effects.append(
            {
                "effect_id": f"effect_knockout_{uuid4().hex[:12]}",
                "effect_type": "knockout_protection",
                "duration_seconds": 3600,
            }
        )

    def _remove_knockout_protection(self, target: EncounterEntity) -> None:
        target.turn_effects = [
            effect
            for effect in target.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "knockout_protection"
            )
        ]

    def _maybe_enable_retarget_marked_spells(
        self,
        *,
        encounter: Encounter,
        target: EncounterEntity,
        hp_before: int,
        hp_after: int,
    ) -> list[dict[str, Any]]:
        if hp_before <= 0 or hp_after != 0:
            return []

        updates: list[dict[str, Any]] = []
        for instance in encounter.spell_instances:
            if not self._is_retargetable_instance_for_target(instance, target.entity_id):
                continue

            target_entry = self._find_spell_instance_target(instance, target.entity_id)
            if target_entry is None:
                continue

            turn_effect_ids = {
                effect_id for effect_id in target_entry.get("turn_effect_ids", []) if isinstance(effect_id, str)
            }
            if turn_effect_ids:
                target.turn_effects = [
                    effect
                    for effect in target.turn_effects
                    if not (
                        isinstance(effect, dict)
                        and isinstance(effect.get("effect_id"), str)
                        and effect.get("effect_id") in turn_effect_ids
                    )
                ]
            target_entry["turn_effect_ids"] = []

            special_runtime = instance.setdefault("special_runtime", {})
            special_runtime["retarget_available"] = True
            special_runtime["current_target_id"] = None
            updates.append(
                {
                    "spell_instance_id": instance.get("instance_id"),
                    "spell_id": instance.get("spell_id"),
                    "spell_name": instance.get("spell_name"),
                    "previous_target_id": target.entity_id,
                    "retarget_available": True,
                    "retarget_activation": special_runtime.get("retarget_activation"),
                }
            )

        return updates

    def _is_retargetable_instance_for_target(self, instance: dict[str, Any], target_id: str) -> bool:
        special_runtime = instance.get("special_runtime")
        if not isinstance(special_runtime, dict):
            return False
        if not bool(special_runtime.get("retargetable")):
            return False
        if special_runtime.get("current_target_id") != target_id:
            return False

        lifecycle = instance.get("lifecycle")
        if not isinstance(lifecycle, dict) or lifecycle.get("status") != "active":
            return False

        concentration = instance.get("concentration")
        if isinstance(concentration, dict) and concentration.get("required") and not concentration.get("active"):
            return False
        return True

    def _find_spell_instance_target(self, instance: dict[str, Any], target_id: str) -> dict[str, Any] | None:
        targets = instance.get("targets")
        if not isinstance(targets, list):
            return None
        for item in targets:
            if isinstance(item, dict) and item.get("entity_id") == target_id:
                return item
        return None

    def _maybe_request_concentration_check(
        self,
        *,
        encounter_id: str,
        target: EncounterEntity,
        adjusted_damage: int,
        source_entity_id: str | None,
        concentration_vantage: str,
    ) -> Any | None:
        # 只有“造成了实际伤害”且“目标当前正在专注”时，才需要创建专注检定请求。
        if adjusted_damage <= 0:
            return None
        if not bool(target.combat_flags.get("is_concentrating")):
            return None
        if self.request_concentration_check is None:
            return None

        return self.request_concentration_check.execute(
            encounter_id=encounter_id,
            target_id=target.entity_id,
            damage_taken=adjusted_damage,
            vantage=concentration_vantage,
            source_entity_id=source_entity_id,
        )

    def _end_concentration_if_needed(
        self,
        *,
        encounter: Encounter,
        target: EncounterEntity,
        reason: str,
    ) -> None:
        if not bool(target.combat_flags.get("is_concentrating")):
            return
        target.combat_flags["is_concentrating"] = False
        end_concentration_spell_instances(
            encounter=encounter,
            caster_entity_id=target.entity_id,
            reason=reason,
        )

    def _remove_entity_from_encounter(self, encounter: Encounter, entity_id: str) -> None:
        if entity_id in encounter.entities:
            del encounter.entities[entity_id]
        encounter.turn_order = [item for item in encounter.turn_order if item != entity_id]
        if encounter.current_entity_id == entity_id:
            encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
        pending = encounter.pending_movement
        if isinstance(pending, dict) and pending.get("entity_id") == entity_id:
            pending["status"] = "interrupted"

    def _clear_summon_runtime_links(self, *, encounter: Encounter, summon_entity_id: str) -> None:
        for instance in encounter.spell_instances:
            special_runtime = instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                continue
            summon_entity_ids = special_runtime.get("summon_entity_ids")
            if not isinstance(summon_entity_ids, list):
                continue
            if summon_entity_id in summon_entity_ids:
                special_runtime["summon_entity_ids"] = [
                    entity_id for entity_id in summon_entity_ids if entity_id != summon_entity_id
                ]

    def _remove_summons_for_dead_summoner(self, *, encounter: Encounter, summoner_entity_id: str) -> None:
        summon_ids = [
            entity_id
            for entity_id, entity in encounter.entities.items()
            if entity.category == "summon"
            and isinstance(entity.source_ref, dict)
            and entity.source_ref.get("summoner_entity_id") == summoner_entity_id
        ]
        for summon_id in summon_ids:
            self._clear_summon_runtime_links(encounter=encounter, summon_entity_id=summon_id)
            self._remove_entity_from_encounter(encounter, summon_id)

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _normalize_damage_type(self, damage_type: str | None) -> str | None:
        if damage_type is None:
            return None
        if not isinstance(damage_type, str) or not damage_type.strip():
            raise ValueError("damage_type must be a non-empty string or None")
        return damage_type.strip().lower()

    def _normalize_damage_type_list(self, values: list[str]) -> set[str]:
        normalized: set[str] = set()
        for value in values:
            if isinstance(value, str) and value.strip():
                normalized.add(value.strip().lower())
        return normalized
