from __future__ import annotations

import re
from typing import Any

from tools.models.encounter_entity import EncounterEntity
from tools.repositories.weapon_definition_repository import WeaponDefinitionRepository
from tools.services.class_features.shared import get_monk_runtime, has_fighting_style, resolve_entity_proficiencies


class WeaponProfileResolver:
    """把实体持有武器与静态武器模板合并成攻击链可直接使用的对象。"""

    def __init__(self, weapon_definition_repository: WeaponDefinitionRepository | None = None):
        self.weapon_definition_repository = weapon_definition_repository

    def resolve(self, actor: EncounterEntity, weapon_id: str) -> dict[str, Any]:
        if weapon_id == "unarmed_strike":
            return self._build_unarmed_strike_profile(actor)

        runtime_weapon = self._get_runtime_weapon_or_raise(actor, weapon_id)
        template = self._get_template(weapon_id)

        resolved: dict[str, Any] = {}
        if template is not None:
            resolved.update(self._normalize_template(template))

        runtime_copy = dict(runtime_weapon)
        display_name = runtime_copy.pop("display_name", None)
        base_damage_override = runtime_copy.pop("base_damage_override", None)
        versatile_damage_override = runtime_copy.pop("versatile_damage_override", None)
        extra_damage_parts = runtime_copy.pop("extra_damage_parts", [])
        custom_properties = runtime_copy.pop("custom_properties", [])

        resolved.update(runtime_copy)
        resolved["weapon_id"] = weapon_id
        resolved["name"] = self._resolve_name(display_name, runtime_copy, resolved, weapon_id)
        resolved["properties"] = self._merge_properties(
            runtime_properties=runtime_weapon.get("properties"),
            resolved_properties=resolved.get("properties"),
            custom_properties=custom_properties,
        )
        resolved["is_proficient"] = self._resolve_weapon_proficiency(
            actor=actor,
            runtime_weapon=runtime_weapon,
            resolved_weapon=resolved,
        )

        damage_parts = self._resolve_damage_parts(
            resolved=resolved,
            base_damage_override=base_damage_override,
            versatile_damage_override=versatile_damage_override,
            extra_damage_parts=extra_damage_parts,
        )
        damage_parts = self._apply_monk_weapon_martial_arts(
            actor=actor,
            weapon=resolved,
            damage_parts=damage_parts,
        )
        if damage_parts:
            resolved["damage"] = damage_parts

        return resolved

    def _get_runtime_weapon_or_raise(self, actor: EncounterEntity, weapon_id: str) -> dict[str, Any]:
        for weapon in actor.weapons:
            if weapon.get("weapon_id") == weapon_id:
                return weapon
        raise ValueError(f"weapon '{weapon_id}' not found on actor '{actor.entity_id}'")

    def _get_template(self, weapon_id: str) -> dict[str, Any] | None:
        if self.weapon_definition_repository is None:
            return None
        return self.weapon_definition_repository.get(weapon_id)

    def _normalize_template(self, template: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(template)
        if "damage" not in normalized:
            damage_parts: list[dict[str, Any]] = []
            base_damage = normalized.get("base_damage")
            if isinstance(base_damage, dict):
                formula = base_damage.get("formula")
                damage_type = base_damage.get("damage_type")
                if isinstance(formula, str) and formula.strip():
                    damage_parts.append({"formula": formula.strip(), "type": damage_type})
            if damage_parts:
                normalized["damage"] = damage_parts
        return normalized

    def _resolve_name(
        self,
        display_name: Any,
        runtime_weapon: dict[str, Any],
        resolved_weapon: dict[str, Any],
        weapon_id: str,
    ) -> str:
        for candidate in (display_name, runtime_weapon.get("name"), resolved_weapon.get("name"), weapon_id):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return weapon_id

    def _merge_properties(
        self,
        *,
        runtime_properties: Any,
        resolved_properties: Any,
        custom_properties: Any,
    ) -> list[str]:
        merged: list[str] = []
        source = runtime_properties if isinstance(runtime_properties, list) else resolved_properties
        for values in (source, custom_properties):
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                normalized = value.strip().lower()
                if normalized not in merged:
                    merged.append(normalized)
        return merged

    def _resolve_damage_parts(
        self,
        *,
        resolved: dict[str, Any],
        base_damage_override: Any,
        versatile_damage_override: Any,
        extra_damage_parts: Any,
    ) -> list[dict[str, Any]]:
        if isinstance(resolved.get("damage"), list) and resolved["damage"]:
            damage_parts = [dict(part) for part in resolved["damage"] if isinstance(part, dict)]
        else:
            damage_parts = []

        if isinstance(base_damage_override, dict):
            damage_parts = [self._normalize_damage_part(base_damage_override)]

        if resolved.get("hands", {}).get("mode") == "versatile" and isinstance(versatile_damage_override, dict):
            damage_parts = [self._normalize_damage_part(versatile_damage_override)]

        if isinstance(extra_damage_parts, list):
            for part in extra_damage_parts:
                if isinstance(part, dict):
                    damage_parts.append(self._normalize_damage_part(part))

        return [part for part in damage_parts if part]

    def _build_unarmed_strike_profile(self, actor: EncounterEntity) -> dict[str, Any]:
        return {
            "weapon_id": "unarmed_strike",
            "name": "Unarmed Strike",
            "category": "simple",
            "kind": "melee",
            "properties": [],
            "is_proficient": True,
            "damage": [{"formula": self._resolve_unarmed_damage_formula(actor), "type": "bludgeoning"}],
            "range": {"normal": 5, "long": 5},
            "hands": {"mode": "one_handed"},
        }

    def _resolve_unarmed_damage_formula(self, actor: EncounterEntity) -> str:
        if has_fighting_style(actor, "unarmed_fighting"):
            has_both_hands_free = self._has_both_hands_free(actor)
            die = "1d8" if has_both_hands_free else "1d6"
            modifier = actor.ability_mods.get("str", 0)
            return self._append_modifier_to_formula(die, modifier)
        monk_runtime = get_monk_runtime(actor)
        monk_die = monk_runtime.get("martial_arts_die")
        if isinstance(monk_die, str) and monk_die.strip():
            die = monk_die.strip()
            modifier = actor.ability_mods.get("dex", 0)
            return self._append_modifier_to_formula(die, modifier)
        modifier = actor.ability_mods.get("str", 0)
        return self._append_modifier_to_formula("1d4", modifier)

    def _has_both_hands_free(self, actor: EncounterEntity) -> bool:
        occupied: set[str] = set()
        for runtime_weapon in actor.weapons:
            slot = str(runtime_weapon.get("slot") or "").strip().lower()
            if slot == "both_hands":
                occupied.update({"main_hand", "off_hand"})
            elif slot in {"main_hand", "off_hand"}:
                occupied.add(slot)
        if actor.equipped_shield is not None:
            occupied.add("off_hand")
        return "main_hand" not in occupied and "off_hand" not in occupied

    def _append_modifier_to_formula(self, formula: str, modifier: Any) -> str:
        if isinstance(modifier, bool) or not isinstance(modifier, int):
            return formula
        if modifier > 0:
            return f"{formula}+{modifier}"
        if modifier < 0:
            return f"{formula}{modifier}"
        return formula

    def _normalize_damage_part(self, part: dict[str, Any]) -> dict[str, Any]:
        formula = part.get("formula")
        damage_type = part.get("type", part.get("damage_type"))
        normalized: dict[str, Any] = {}
        if isinstance(formula, str) and formula.strip():
            normalized["formula"] = formula.strip()
        if damage_type is not None:
            normalized["type"] = damage_type
        return normalized

    def is_monk_weapon(self, actor: EncounterEntity, weapon: dict[str, Any]) -> bool:
        monk_runtime = get_monk_runtime(actor)
        martial_arts = monk_runtime.get("martial_arts")
        if not isinstance(martial_arts, dict) or not bool(martial_arts.get("enabled")):
            return False

        category = str(weapon.get("category") or "").strip().lower()
        kind = str(weapon.get("kind") or "").strip().lower()
        properties = {
            str(entry).strip().lower()
            for entry in weapon.get("properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        if kind != "melee":
            return False
        if category == "simple":
            return True
        return category == "martial" and "light" in properties

    def _apply_monk_weapon_martial_arts(
        self,
        *,
        actor: EncounterEntity,
        weapon: dict[str, Any],
        damage_parts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not damage_parts or not self.is_monk_weapon(actor, weapon):
            return damage_parts

        monk_runtime = get_monk_runtime(actor)
        monk_die = monk_runtime.get("martial_arts_die")
        if not isinstance(monk_die, str) or not monk_die.strip():
            return damage_parts

        updated_parts = [dict(part) for part in damage_parts]
        formula = str(updated_parts[0].get("formula") or "").strip()
        rewritten = self._rewrite_monk_weapon_damage_formula(
            actor=actor,
            weapon=weapon,
            formula=formula,
            martial_arts_die=monk_die.strip(),
        )
        if rewritten:
            updated_parts[0]["formula"] = rewritten
        return updated_parts

    def _rewrite_monk_weapon_damage_formula(
        self,
        *,
        actor: EncounterEntity,
        weapon: dict[str, Any],
        formula: str,
        martial_arts_die: str,
    ) -> str:
        parsed_formula = self._parse_single_damage_formula(formula)
        parsed_martial_arts = self._parse_single_damage_formula(martial_arts_die)
        if parsed_formula is None or parsed_martial_arts is None:
            return formula

        dice_count, die_size, explicit_flat_bonus = parsed_formula
        martial_arts_die_size = parsed_martial_arts[1]
        resolved_die_size = max(die_size, martial_arts_die_size)

        if explicit_flat_bonus is None:
            return f"{dice_count}d{resolved_die_size}"

        standard_modifier = self._resolve_standard_weapon_modifier_value(actor, weapon)
        monk_modifier = self._resolve_monk_weapon_modifier_value(actor)
        adjusted_flat_bonus = explicit_flat_bonus + (monk_modifier - standard_modifier)
        return self._build_damage_formula(
            dice_count=dice_count,
            die_size=resolved_die_size,
            flat_bonus=adjusted_flat_bonus,
        )

    def _parse_single_damage_formula(self, formula: str) -> tuple[int, int, int | None] | None:
        match = re.fullmatch(r"\s*(\d+)d(\d+)([+-]\d+)?\s*", formula)
        if match is None:
            return None
        explicit_bonus = match.group(3)
        return int(match.group(1)), int(match.group(2)), int(explicit_bonus) if explicit_bonus else None

    def _build_damage_formula(self, *, dice_count: int, die_size: int, flat_bonus: int) -> str:
        base = f"{dice_count}d{die_size}"
        if flat_bonus > 0:
            return f"{base}+{flat_bonus}"
        if flat_bonus < 0:
            return f"{base}{flat_bonus}"
        return base

    def _resolve_standard_weapon_modifier_value(self, actor: EncounterEntity, weapon: dict[str, Any]) -> int:
        modifier_name = self._resolve_standard_weapon_modifier_name(actor, weapon)
        return int(actor.ability_mods.get(modifier_name, 0) or 0)

    def _resolve_standard_weapon_modifier_name(self, actor: EncounterEntity, weapon: dict[str, Any]) -> str:
        properties = {
            str(entry).strip().lower()
            for entry in weapon.get("properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        kind = str(weapon.get("kind") or "").strip().lower()
        normal_range = int(weapon.get("range", {}).get("normal", 0) or 0)

        if "finesse" in properties:
            str_mod = int(actor.ability_mods.get("str", 0) or 0)
            dex_mod = int(actor.ability_mods.get("dex", 0) or 0)
            return "dex" if dex_mod >= str_mod else "str"
        if kind == "ranged" or normal_range > 10:
            return "dex"
        return "str"

    def resolve_monk_weapon_modifier_name(self, actor: EncounterEntity) -> str:
        str_mod = int(actor.ability_mods.get("str", 0) or 0)
        dex_mod = int(actor.ability_mods.get("dex", 0) or 0)
        return "dex" if dex_mod >= str_mod else "str"

    def _resolve_monk_weapon_modifier_value(self, actor: EncounterEntity) -> int:
        return int(actor.ability_mods.get(self.resolve_monk_weapon_modifier_name(actor), 0) or 0)

    def _resolve_weapon_proficiency(
        self,
        *,
        actor: EncounterEntity,
        runtime_weapon: dict[str, Any],
        resolved_weapon: dict[str, Any],
    ) -> bool:
        explicit = runtime_weapon.get("is_proficient")
        if isinstance(explicit, bool):
            return explicit

        category = str(resolved_weapon.get("category") or "").strip().lower()
        weapon_id = str(resolved_weapon.get("weapon_id") or runtime_weapon.get("weapon_id") or "").strip().lower()
        properties = {
            str(entry).strip().lower()
            for entry in resolved_weapon.get("properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        proficiencies = resolve_entity_proficiencies(actor)["weapon_proficiencies"]
        normalized = {entry.strip().lower() for entry in proficiencies if isinstance(entry, str)}
        if self._matches_proficiency_selector(
            category=category,
            weapon_id=weapon_id,
            properties=properties,
            proficiencies=normalized,
        ):
            return True

        if self._has_runtime_class_binding(actor):
            return False

        return self._looks_like_legacy_proficient_weapon(
            runtime_weapon=runtime_weapon,
            resolved_weapon=resolved_weapon,
        )

    def _matches_proficiency_selector(
        self,
        *,
        category: str,
        weapon_id: str,
        properties: set[str],
        proficiencies: set[str],
    ) -> bool:
        if category and category in proficiencies:
            return True
        if weapon_id and weapon_id in proficiencies:
            return True
        if category == "martial" and "martial_light" in proficiencies and "light" in properties:
            return True
        if (
            category == "martial"
            and "martial_finesse_or_light" in proficiencies
            and ("finesse" in properties or "light" in properties)
        ):
            return True
        return False

    def _has_runtime_class_binding(self, actor: EncounterEntity) -> bool:
        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        return any(isinstance(value, dict) for value in class_features.values())

    def _looks_like_legacy_proficient_weapon(
        self,
        *,
        runtime_weapon: dict[str, Any],
        resolved_weapon: dict[str, Any],
    ) -> bool:
        has_name = any(
            isinstance(candidate, str) and bool(candidate.strip())
            for candidate in (runtime_weapon.get("name"), resolved_weapon.get("name"))
        )
        has_damage = any(
            isinstance(candidate, list) and bool(candidate)
            for candidate in (runtime_weapon.get("damage"), resolved_weapon.get("damage"))
        )
        has_range = any(
            isinstance(candidate, dict)
            for candidate in (runtime_weapon.get("range"), resolved_weapon.get("range"))
        )
        return has_name and has_damage and has_range
