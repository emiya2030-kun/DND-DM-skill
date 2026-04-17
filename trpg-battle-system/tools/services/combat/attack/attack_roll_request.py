from __future__ import annotations

import math
import re
from uuid import uuid4


from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.armor_definition_repository import ArmorDefinitionRepository
from tools.repositories.weapon_definition_repository import WeaponDefinitionRepository
from tools.services.combat.defense.armor_profile_resolver import ArmorProfileResolver
from tools.services.combat.rules.conditions import (
    AUTO_CRIT_MELEE_TARGET_CONDITIONS,
    BLOCKED_ATTACK_CONDITIONS,
    ConditionRuntime,
    TARGET_ATTACK_ADVANTAGE_CONDITIONS,
    TARGET_ATTACK_DISADVANTAGE_CONDITIONS,
    ATTACK_ADVANTAGE_CONDITIONS,
    ATTACK_DISADVANTAGE_CONDITIONS,
)
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells
from tools.services.combat.attack.weapon_profile_resolver import WeaponProfileResolver
from tools.services.combat.attack.weapon_mastery_effects import collect_attack_roll_weapon_mastery_modifiers
from tools.services.combat.shared.turn_actor_guard import (
    get_entity_or_raise,
    resolve_current_turn_actor_or_raise,
)
from tools.services.class_features.shared import (
    fighter_has_studied_attacks,
    has_unconsumed_studied_attack_mark,
    resolve_extra_attack_count,
)

class AttackRollRequest:
    """根据当前 encounter 状态生成一次武器攻击的掷骰请求。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        weapon_definition_repository: WeaponDefinitionRepository | None = None,
        armor_definition_repository: ArmorDefinitionRepository | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.weapon_profile_resolver = WeaponProfileResolver(weapon_definition_repository or WeaponDefinitionRepository())
        self.armor_profile_resolver = ArmorProfileResolver(armor_definition_repository or ArmorDefinitionRepository())

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        weapon_id: str,
        actor_id: str | None = None,
        allow_out_of_turn_actor: bool = False,
        require_action_available: bool = True,
        vantage: str = "normal",
        description: str | None = None,
        attack_mode: str | None = None,
        grip_mode: str | None = None,
    ) -> RollRequest:
        """为当前行动者生成一次武器攻击请求。"""
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(
            encounter,
            actor_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
        )
        target = self._get_entity_or_raise(encounter, target_id)
        self.armor_profile_resolver.refresh_entity_armor_class(actor)
        self.armor_profile_resolver.refresh_entity_armor_class(target)
        weapon = self.resolve_weapon_or_raise(actor, weapon_id)
        actor_armor_profile = self.armor_profile_resolver.resolve(actor)

        actor_runtime = ConditionRuntime(actor.conditions)
        target_runtime = ConditionRuntime(target.conditions)
        normalized_attack_mode = self._normalize_attack_mode(attack_mode)
        normalized_grip_mode = self._normalize_grip_mode(grip_mode)

        modifier = self._resolve_modifier_name(actor, weapon, normalized_attack_mode)
        modifier_value = actor.ability_mods.get(modifier, 0)
        proficiency_bonus = actor.proficiency_bonus if bool(weapon.get("is_proficient", True)) else 0
        attack_bonus_override = weapon.get("attack_bonus_override")
        explicit_attack_bonus = weapon.get("attack_bonus")
        if isinstance(attack_bonus_override, int):
            base_attack_bonus = attack_bonus_override
        elif isinstance(explicit_attack_bonus, int):
            base_attack_bonus = explicit_attack_bonus
        else:
            base_attack_bonus = modifier_value + proficiency_bonus
        exhaustion_penalty = actor_runtime.get_d20_penalty()
        attack_bonus = base_attack_bonus - exhaustion_penalty
        distance_to_target_feet = self._distance_feet(actor, target)
        attack_kind = self._resolve_attack_kind(weapon, normalized_attack_mode)
        light_bonus_uses_bonus_action = True
        if normalized_attack_mode == "light_bonus":
            light_bonus_trigger = self._ensure_light_bonus_attack_available(actor, weapon)
            light_bonus_uses_bonus_action = not bool(light_bonus_trigger.get("grants_nick"))
            if light_bonus_uses_bonus_action:
                self._ensure_bonus_action_available(actor)
        elif require_action_available:
            self._ensure_action_available(actor)
        self._ensure_two_handed_hands_available(actor, weapon, normalized_grip_mode)
        self._ensure_actor_can_attack(actor_runtime)
        self._ensure_actor_not_charmed(actor_runtime, target.entity_id)
        self._ensure_target_in_range(distance_to_target_feet, weapon, attack_kind, normalized_attack_mode)
        self._ensure_line_of_sight(encounter, actor, target)
        resolved_vantage, vantage_sources = self._resolve_vantage(
            encounter=encounter,
            requested_vantage=vantage,
            actor=actor,
            target=target,
            attack_kind=attack_kind,
            attack_mode=normalized_attack_mode,
            distance_to_target_feet=distance_to_target_feet,
            weapon=weapon,
            actor_runtime=actor_runtime,
            target_runtime=target_runtime,
        )
        mastery_modifiers = collect_attack_roll_weapon_mastery_modifiers(actor=actor, target=target)
        if mastery_modifiers["advantage_sources"]:
            vantage_sources["advantage"].extend(mastery_modifiers["advantage_sources"])
        if mastery_modifiers["disadvantage_sources"]:
            vantage_sources["disadvantage"].extend(mastery_modifiers["disadvantage_sources"])
        if actor_armor_profile["wearing_untrained_armor"] and modifier in {"str", "dex"}:
            vantage_sources["disadvantage"].append("armor_untrained")
        if (
            fighter_has_studied_attacks(actor.class_features)
            and has_unconsumed_studied_attack_mark(actor.class_features, target.entity_id)
        ):
            vantage_sources["advantage"].append("studied_attacks")
        if vantage_sources["advantage"] and vantage_sources["disadvantage"]:
            resolved_vantage = "normal"
        elif vantage_sources["advantage"]:
            resolved_vantage = "advantage"
        elif vantage_sources["disadvantage"]:
            resolved_vantage = "disadvantage"
        else:
            resolved_vantage = "normal"

        melee_auto_crit = (
            attack_kind == "melee_weapon"
            and distance_to_target_feet <= 5
            and any(
                target_runtime.has(condition)
                for condition in AUTO_CRIT_MELEE_TARGET_CONDITIONS
            )
        )

        return RollRequest(
            request_id=self._generate_request_id(),
            encounter_id=encounter.encounter_id,
            actor_entity_id=actor.entity_id,
            target_entity_id=target.entity_id,
            roll_type="attack_roll",
            formula=self._build_formula(attack_bonus),
            reason=description or f"{weapon.get('name', weapon_id)} attack",
            context={
                "attack_name": weapon.get("name"),
                "attack_kind": attack_kind,
                "attack_mode": normalized_attack_mode,
                "grip_mode": normalized_grip_mode,
                "weapon_slot": weapon.get("slot"),
                "weapon_properties": list(weapon.get("properties", [])),
                "weapon_mastery": weapon.get("mastery"),
                "weapon_mastery_base": weapon.get("mastery"),
                "light_bonus_uses_bonus_action": light_bonus_uses_bonus_action,
                "weapon_category": weapon.get("category"),
                "weapon_is_proficient": bool(weapon.get("is_proficient", True)),
                "primary_damage_type": self._resolve_primary_damage_type(weapon),
                "consumed_mastery_effect_ids": mastery_modifiers["consumed_effect_ids"],
                "modifier": modifier,
                "modifier_value": modifier_value,
                "proficiency_bonus": proficiency_bonus,
                "base_attack_bonus": base_attack_bonus,
                "attack_bonus": attack_bonus,
                "exhaustion_penalty": exhaustion_penalty,
                "vantage": resolved_vantage,
                "vantage_sources": vantage_sources,
                "target_ac": target.ac,
                "distance_to_target": f"{distance_to_target_feet} ft",
                "distance_to_target_feet": distance_to_target_feet,
                "melee_auto_crit": melee_auto_crit,
                "studied_attacks_applied": "studied_attacks" in vantage_sources["advantage"],
            },
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(
        self,
        encounter: Encounter,
        actor_id: str | None,
        *,
        allow_out_of_turn_actor: bool,
    ) -> EncounterEntity:
        return resolve_current_turn_actor_or_raise(
            encounter,
            actor_id=actor_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            entity_label="actor",
        )

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        return get_entity_or_raise(encounter, entity_id, entity_label="entity")

    def _get_weapon_or_raise(self, actor: EncounterEntity, weapon_id: str) -> dict:
        return self.resolve_weapon_or_raise(actor, weapon_id)

    def resolve_weapon_or_raise(self, actor: EncounterEntity, weapon_id: str) -> dict[str, Any]:
        return self.weapon_profile_resolver.resolve(actor, weapon_id)

    def _resolve_modifier_name(self, actor: EncounterEntity, weapon: dict, attack_mode: str) -> str:
        properties = {str(prop).lower() for prop in weapon.get("properties", [])}
        normal_range = weapon.get("range", {}).get("normal", 0)
        kind = str(weapon.get("kind") or "").lower()

        if "finesse" in properties:
            str_mod = actor.ability_mods.get("str", 0)
            dex_mod = actor.ability_mods.get("dex", 0)
            return "dex" if dex_mod >= str_mod else "str"

        if attack_mode == "thrown":
            return "str"

        if kind == "ranged" or (normal_range and normal_range > 10):
            return "dex"

        return "str"

    def _resolve_attack_kind(self, weapon: dict, attack_mode: str) -> str:
        if attack_mode == "thrown":
            return "ranged_weapon"
        kind = str(weapon.get("kind") or "").lower()
        if kind == "ranged":
            return "ranged_weapon"
        if kind == "melee":
            return "melee_weapon"
        normal_range = weapon.get("range", {}).get("normal", 0)
        if normal_range and normal_range > 10:
            return "ranged_weapon"
        return "melee_weapon"

    def _distance_feet(self, source: EncounterEntity, target: EncounterEntity) -> int:
        source_center = get_center_position(source)
        target_center = get_center_position(target)
        dx = abs(source_center["x"] - target_center["x"])
        dy = abs(source_center["y"] - target_center["y"])
        return math.ceil(max(dx, dy)) * 5

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("action_used")) and not self._can_continue_attack_action_sequence(actor):
            raise ValueError("action_already_used")

    def _can_continue_attack_action_sequence(self, actor: EncounterEntity) -> bool:
        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        fighter = class_features.get("fighter")
        if not isinstance(fighter, dict):
            return False

        max_attacks = max(1, resolve_extra_attack_count(class_features))
        if max_attacks <= 1:
            return False

        used_attacks = self._read_attack_action_attacks_used(fighter)
        if used_attacks is None:
            return False

        return used_attacks < max_attacks

    def _read_attack_action_attacks_used(self, fighter: dict[str, Any]) -> int | None:
        turn_counters = fighter.get("turn_counters")
        if not isinstance(turn_counters, dict):
            return None

        used_attacks = turn_counters.get("attack_action_attacks_used")
        if isinstance(used_attacks, bool) or not isinstance(used_attacks, int):
            return 0
        return max(0, used_attacks)

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_actor_can_attack(self, actor_runtime: ConditionRuntime) -> None:
        if any(actor_runtime.has(condition) for condition in BLOCKED_ATTACK_CONDITIONS):
            raise ValueError("actor_cannot_attack")

    def _ensure_actor_not_charmed(self, actor_runtime: ConditionRuntime, target_id: str) -> None:
        if actor_runtime.has_from_source("charmed", target_id):
            raise ValueError("actor_cannot_attack_charmed_target")

    def _ensure_target_in_range(
        self,
        distance_to_target_feet: int,
        weapon: dict,
        attack_kind: str,
        attack_mode: str,
    ) -> None:
        if attack_mode == "thrown":
            weapon_range = weapon.get("thrown_range", {})
            normal_range = int(weapon_range.get("normal", 0) or 0)
            long_range = int(weapon_range.get("long", 0) or 0)
            maximum_range = long_range or normal_range
            if maximum_range <= 0 or distance_to_target_feet > maximum_range:
                raise ValueError("target_out_of_range")
            return

        if attack_kind == "melee_weapon":
            melee_reach = self._resolve_melee_reach(weapon)
            if distance_to_target_feet > melee_reach:
                raise ValueError("target_out_of_range")
            return

        weapon_range = weapon.get("range", {})
        normal_range = int(weapon_range.get("normal", 0) or 0)
        long_range = int(weapon_range.get("long", 0) or 0)
        maximum_range = long_range or normal_range
        if maximum_range <= 0 or distance_to_target_feet > maximum_range:
            raise ValueError("target_out_of_range")

    def _ensure_line_of_sight(self, encounter: Encounter, actor: EncounterEntity, target: EncounterEntity) -> None:
        blocking_cells = {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
            and (terrain.get("blocks_los") or terrain.get("type") == "wall")
        }
        if not blocking_cells:
            return

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
                raise ValueError("blocked_by_line_of_sight")

    def _resolve_vantage(
        self,
        *,
        encounter: Encounter,
        requested_vantage: str,
        actor: EncounterEntity,
        target: EncounterEntity,
        attack_kind: str,
        attack_mode: str,
        distance_to_target_feet: int,
        weapon: dict,
        actor_runtime: ConditionRuntime,
        target_runtime: ConditionRuntime,
    ) -> tuple[str, dict[str, list[str]]]:
        advantage_sources: list[str] = []
        disadvantage_sources: list[str] = []

        normalized_vantage = self._normalize_vantage(requested_vantage)
        if normalized_vantage == "advantage":
            advantage_sources.append("requested_advantage")
        elif normalized_vantage == "disadvantage":
            disadvantage_sources.append("requested_disadvantage")

        for condition in sorted(ATTACK_ADVANTAGE_CONDITIONS):
            if actor_runtime.has(condition):
                advantage_sources.append(f"actor_{condition}")
        for condition in sorted(ATTACK_DISADVANTAGE_CONDITIONS):
            if condition == "grappled":
                continue
            if actor_runtime.has(condition):
                disadvantage_sources.append(f"actor_{condition}")
        grappler_sources = actor_runtime.sources_for("grappled")
        if grappler_sources:
            for source in grappler_sources:
                if source and source != target.entity_id:
                    disadvantage_sources.append(f"actor_grappled_by_{source}")
        else:
            if actor_runtime.has("grappled"):
                disadvantage_sources.append("actor_grappled")
        for condition in sorted(TARGET_ATTACK_ADVANTAGE_CONDITIONS):
            if target_runtime.has(condition):
                advantage_sources.append(f"target_{condition}")
        for condition in sorted(TARGET_ATTACK_DISADVANTAGE_CONDITIONS):
            if target_runtime.has(condition):
                disadvantage_sources.append(f"target_{condition}")

        if target_runtime.has("prone"):
            if distance_to_target_feet <= 5:
                advantage_sources.append("target_prone_close")
            else:
                disadvantage_sources.append("target_prone_far")

        properties = {str(prop).lower() for prop in weapon.get("properties", [])}
        weapon_kind = str(weapon.get("kind") or "").lower()
        if "heavy" in properties:
            if weapon_kind == "melee" and self._get_ability_score(actor, "str") < 13:
                disadvantage_sources.append("heavy_melee_low_str")
            if weapon_kind == "ranged" and self._get_ability_score(actor, "dex") < 13:
                disadvantage_sources.append("heavy_ranged_low_dex")

        if attack_kind == "ranged_weapon":
            range_block = weapon.get("thrown_range", {}) if attack_mode == "thrown" else weapon.get("range", {})
            normal_range = int(range_block.get("normal", 0) or 0)
            if normal_range and distance_to_target_feet > normal_range:
                disadvantage_sources.append("long_range")
            if not self._actor_ignores_close_range_disadvantage(actor, attack_kind):
                disadvantage_sources.extend(
                    self._collect_close_range_hostile_sources(
                        encounter=encounter,
                        actor=actor,
                        actor_runtime=actor_runtime,
                    )
                )

        if advantage_sources and disadvantage_sources:
            final_vantage = "normal"
        elif advantage_sources:
            final_vantage = "advantage"
        elif disadvantage_sources:
            final_vantage = "disadvantage"
        else:
            final_vantage = "normal"

        return final_vantage, {
            "advantage": advantage_sources,
            "disadvantage": disadvantage_sources,
        }

    def _normalize_vantage(self, vantage: str) -> str:
        normalized = str(vantage or "normal").lower()
        if normalized not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("invalid_vantage")
        return normalized

    def _normalize_attack_mode(self, attack_mode: str | None) -> str:
        normalized = str(attack_mode or "default").lower()
        if normalized not in {"default", "thrown", "light_bonus"}:
            raise ValueError("invalid_attack_mode")
        return normalized

    def _normalize_grip_mode(self, grip_mode: str | None) -> str:
        normalized = str(grip_mode or "default").lower()
        if normalized not in {"default", "one_handed", "two_handed"}:
            raise ValueError("invalid_grip_mode")
        return normalized

    def _resolve_melee_reach(self, weapon: dict[str, Any]) -> int:
        properties = {str(prop).lower() for prop in weapon.get("properties", [])}
        base_reach = 10 if "reach" in properties else 5
        normal_range = int(weapon.get("range", {}).get("normal", 0) or 0)
        return max(base_reach, normal_range)

    def _ensure_two_handed_hands_available(
        self,
        actor: EncounterEntity,
        weapon: dict[str, Any],
        grip_mode: str,
    ) -> None:
        if not self._requires_two_hands(weapon, grip_mode):
            return
        blocking_slots = self._collect_blocking_hand_slots(actor, weapon)
        if blocking_slots:
            raise ValueError("two_handed_requires_two_free_hands")

    def _ensure_light_bonus_attack_available(self, actor: EncounterEntity, weapon: dict[str, Any]) -> dict[str, Any]:
        combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        trigger = combat_flags.get("light_bonus_trigger")
        if not isinstance(trigger, dict):
            raise ValueError("light_bonus_not_available")

        properties = {str(prop).lower() for prop in weapon.get("properties", [])}
        if "light" not in properties:
            raise ValueError("light_bonus_requires_light_weapon")

        trigger_weapon_id = str(trigger.get("weapon_id") or "")
        trigger_slot = str(trigger.get("slot") or "")
        current_weapon_id = str(weapon.get("weapon_id") or "")
        current_slot = str(weapon.get("slot") or "")

        same_slot = bool(trigger_slot and current_slot and trigger_slot == current_slot)
        same_weapon_without_slot = (
            not trigger_slot and not current_slot and trigger_weapon_id and trigger_weapon_id == current_weapon_id
        )
        if same_slot or same_weapon_without_slot:
            raise ValueError("light_bonus_requires_different_weapon")
        return trigger

    def _requires_two_hands(self, weapon: dict[str, Any], grip_mode: str) -> bool:
        hands_mode = str(weapon.get("hands", {}).get("mode") or "").lower()
        properties = {str(prop).lower() for prop in weapon.get("properties", [])}
        return grip_mode == "two_handed" or hands_mode == "two_handed" or "two_handed" in properties

    def _collect_blocking_hand_slots(
        self,
        actor: EncounterEntity,
        current_weapon: dict[str, Any],
    ) -> set[str]:
        occupied: set[str] = set()
        combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        explicit_slots = combat_flags.get("occupied_hand_slots", [])
        if isinstance(explicit_slots, list):
            for slot in explicit_slots:
                occupied.update(self._expand_hand_slot(slot))

        current_weapon_id = str(current_weapon.get("weapon_id") or "")
        current_weapon_slot = self._normalize_hand_slot(current_weapon.get("slot"))
        skipped_current_weapon = False
        for runtime_weapon in actor.weapons:
            weapon_id = str(runtime_weapon.get("weapon_id") or "")
            weapon_slot = self._normalize_hand_slot(runtime_weapon.get("slot"))
            is_current_weapon = False
            if not skipped_current_weapon and weapon_id == current_weapon_id:
                if current_weapon_slot is None or current_weapon_slot == weapon_slot:
                    is_current_weapon = True
                    skipped_current_weapon = True
            if is_current_weapon:
                continue
            occupied.update(self._expand_hand_slot(weapon_slot))
        return occupied

    def _normalize_hand_slot(self, slot: Any) -> str | None:
        normalized = str(slot or "").strip().lower()
        if normalized in {"main_hand", "off_hand", "both_hands"}:
            return normalized
        return None

    def _expand_hand_slot(self, slot: Any) -> set[str]:
        normalized = self._normalize_hand_slot(slot)
        if normalized == "both_hands":
            return {"main_hand", "off_hand"}
        if normalized in {"main_hand", "off_hand"}:
            return {normalized}
        return set()

    def _get_ability_score(self, actor: EncounterEntity, ability: str) -> int:
        score = actor.ability_scores.get(ability)
        if isinstance(score, int):
            return score
        modifier = actor.ability_mods.get(ability, 0)
        if isinstance(modifier, int):
            return 10 + (modifier * 2)
        return 10

    def _build_formula(self, attack_bonus: int) -> str:
        if attack_bonus >= 0:
            return f"1d20+{attack_bonus}"
        return f"1d20{attack_bonus}"

    def _resolve_primary_damage_type(self, weapon: dict[str, Any]) -> str | None:
        damage_parts = weapon.get("damage", [])
        if not isinstance(damage_parts, list) or not damage_parts:
            return None
        first_part = damage_parts[0]
        if not isinstance(first_part, dict):
            return None
        damage_type = first_part.get("type")
        return str(damage_type) if isinstance(damage_type, str) and damage_type.strip() else None

    def _collect_close_range_hostile_sources(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        actor_runtime: ConditionRuntime,
    ) -> list[str]:
        if actor_runtime.has("invisible"):
            return []

        sources: list[str] = []
        for entity in encounter.entities.values():
            if entity.entity_id == actor.entity_id:
                continue
            if entity.side == actor.side:
                continue
            combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
            if bool(combat_flags.get("is_defeated")):
                continue
            entity_runtime = ConditionRuntime(entity.conditions)
            if entity_runtime.has("blinded"):
                continue
            if any(entity_runtime.has(condition) for condition in BLOCKED_ATTACK_CONDITIONS):
                continue
            if self._distance_feet(actor, entity) > 5:
                continue
            sources.append(f"close_range_hostile:{entity.entity_id}")
        return sources

    def _actor_ignores_close_range_disadvantage(self, actor: EncounterEntity, attack_kind: str) -> bool:
        combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        overrides = combat_flags.get("attack_rule_overrides")
        if not isinstance(overrides, dict):
            return False
        rule = overrides.get("ignore_close_range_disadvantage")
        if rule is True:
            return True
        if not isinstance(rule, dict):
            return False
        applies_to = rule.get("applies_to")
        if not isinstance(applies_to, list) or not applies_to:
            return True
        normalized = {str(item).strip().lower() for item in applies_to if str(item).strip()}
        return "all" in normalized or attack_kind in normalized

    def _generate_request_id(self) -> str:
        return f"req_attack_{uuid4().hex[:12]}"
