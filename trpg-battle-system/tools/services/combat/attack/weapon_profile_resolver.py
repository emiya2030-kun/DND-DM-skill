from __future__ import annotations

from typing import Any

from tools.models.encounter_entity import EncounterEntity
from tools.repositories.weapon_definition_repository import WeaponDefinitionRepository
from tools.services.class_features.shared import resolve_entity_proficiencies


class WeaponProfileResolver:
    """把实体持有武器与静态武器模板合并成攻击链可直接使用的对象。"""

    def __init__(self, weapon_definition_repository: WeaponDefinitionRepository | None = None):
        self.weapon_definition_repository = weapon_definition_repository

    def resolve(self, actor: EncounterEntity, weapon_id: str) -> dict[str, Any]:
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

    def _normalize_damage_part(self, part: dict[str, Any]) -> dict[str, Any]:
        formula = part.get("formula")
        damage_type = part.get("type", part.get("damage_type"))
        normalized: dict[str, Any] = {}
        if isinstance(formula, str) and formula.strip():
            normalized["formula"] = formula.strip()
        if damage_type is not None:
            normalized["type"] = damage_type
        return normalized

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
        proficiencies = resolve_entity_proficiencies(actor)["weapon_proficiencies"]
        normalized = {entry.strip().lower() for entry in proficiencies if isinstance(entry, str)}
        if category and category in normalized:
            return True

        return self._looks_like_legacy_proficient_weapon(runtime_weapon=runtime_weapon, resolved_weapon=resolved_weapon)

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
