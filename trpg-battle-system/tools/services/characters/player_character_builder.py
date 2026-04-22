from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.models import EncounterEntity
from tools.services.checks.check_catalog import SKILL_TO_ABILITY
from tools.services.class_features.shared import (
    ensure_barbarian_runtime,
    ensure_fighter_runtime,
    ensure_spell_slots_runtime,
    resolve_entity_save_proficiencies,
)

_CLASS_SPELLCASTING_ABILITIES = {
    "bard": "cha",
    "cleric": "wis",
    "druid": "wis",
    "paladin": "cha",
    "ranger": "wis",
    "sorcerer": "cha",
    "warlock": "cha",
    "wizard": "int",
}


class PlayerCharacterBuilder:
    """从角色定义模板构建标准化玩家角色实体。"""

    def build(self, *, template: dict[str, Any], entity_id: str) -> EncounterEntity:
        payload = deepcopy(template)
        payload["entity_id"] = str(entity_id)

        character_build = payload.get("character_build")
        if not isinstance(character_build, dict):
            raise ValueError("player_character_builder_requires_character_build")
        payload.pop("character_build", None)

        classes = self._normalize_classes(character_build.get("classes"))
        if not classes:
            raise ValueError("character_build.classes must contain at least one class")

        classes = self._resolve_effective_classes(payload=payload, character_build=character_build, classes=classes)
        primary_class_name = self._resolve_primary_class_name(
            payload=payload,
            character_build=character_build,
            classes=classes,
        )
        total_level = sum(level for _, level in classes)

        payload["class_features"] = self._merge_class_levels(
            existing=payload.get("class_features"),
            classes=classes,
        )
        payload["initial_class_name"] = self._resolve_initial_class_name(
            character_build=character_build,
            payload=payload,
            classes=classes,
        )
        payload["ability_mods"] = self._resolve_ability_mods(payload.get("ability_scores"), payload.get("ability_mods"))
        payload["proficiency_bonus"] = self._resolve_proficiency_bonus(
            total_level=total_level,
            explicit=payload.get("proficiency_bonus"),
        )
        payload["skill_modifiers"] = self._resolve_skill_modifiers(
            skill_training=payload.get("skill_training"),
            ability_mods=payload["ability_mods"],
            proficiency_bonus=payload["proficiency_bonus"],
            explicit_modifiers=payload.get("skill_modifiers"),
        )
        payload["spells"] = self._normalize_spells(payload.get("spells"), primary_class_name=primary_class_name)

        source_ref = dict(payload.get("source_ref")) if isinstance(payload.get("source_ref"), dict) else {}
        source_ref["class_name"] = primary_class_name
        source_ref["level"] = total_level
        spellcasting_ability = self._resolve_spellcasting_ability(
            class_name=primary_class_name,
            explicit=source_ref.get("spellcasting_ability"),
        )
        if spellcasting_ability is not None:
            source_ref["spellcasting_ability"] = spellcasting_ability
        else:
            source_ref.pop("spellcasting_ability", None)
        payload["source_ref"] = source_ref

        entity = EncounterEntity.from_dict(payload)
        if not isinstance(payload.get("save_proficiencies"), list) or not payload.get("save_proficiencies"):
            entity.save_proficiencies = resolve_entity_save_proficiencies(entity)
        self._ensure_martial_runtimes(entity)
        ensure_spell_slots_runtime(entity)
        return entity

    def _resolve_effective_classes(
        self,
        *,
        payload: dict[str, Any],
        character_build: dict[str, Any],
        classes: list[tuple[str, int]],
    ) -> list[tuple[str, int]]:
        source_ref = payload.get("source_ref")
        explicit_class_name = None
        if isinstance(source_ref, dict):
            value = source_ref.get("class_name")
            if isinstance(value, str) and value.strip():
                explicit_class_name = value.strip().lower()
        if explicit_class_name is None or explicit_class_name == classes[0][0]:
            return classes

        explicit_level = None
        class_features = payload.get("class_features")
        if isinstance(class_features, dict):
            bucket = class_features.get(explicit_class_name)
            if isinstance(bucket, dict):
                value = bucket.get("level")
                if isinstance(value, int) and value > 0:
                    explicit_level = value
        if explicit_level is None and isinstance(source_ref, dict):
            value = source_ref.get("level")
            if isinstance(value, int) and value > 0:
                explicit_level = value
        if explicit_level is None:
            explicit_level = sum(level for _, level in classes)
        return [(explicit_class_name, explicit_level)]

    def _normalize_classes(self, classes: Any) -> list[tuple[str, int]]:
        if not isinstance(classes, list):
            return []
        normalized: list[tuple[str, int]] = []
        for entry in classes:
            if not isinstance(entry, dict):
                continue
            class_id = entry.get("class_id")
            level = entry.get("level")
            if not isinstance(class_id, str) or not class_id.strip():
                continue
            if not isinstance(level, int) or level <= 0:
                continue
            normalized.append((class_id.strip().lower(), level))
        return normalized

    def _resolve_primary_class_name(
        self,
        *,
        payload: dict[str, Any],
        character_build: dict[str, Any],
        classes: list[tuple[str, int]],
    ) -> str:
        source_ref = payload.get("source_ref")
        if isinstance(source_ref, dict):
            explicit = source_ref.get("class_name")
            if isinstance(explicit, str) and explicit.strip():
                return explicit.strip().lower()
        explicit = character_build.get("primary_class_name")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        return classes[0][0]

    def _resolve_initial_class_name(
        self,
        *,
        character_build: dict[str, Any],
        payload: dict[str, Any],
        classes: list[tuple[str, int]],
    ) -> str:
        explicit = character_build.get("initial_class_name")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        payload_initial = payload.get("initial_class_name")
        if isinstance(payload_initial, str) and payload_initial.strip():
            return payload_initial.strip().lower()
        return classes[0][0]

    def _merge_class_levels(
        self,
        *,
        existing: Any,
        classes: list[tuple[str, int]],
    ) -> dict[str, Any]:
        normalized = dict(existing) if isinstance(existing, dict) else {}
        for class_id, level in classes:
            bucket = normalized.get(class_id)
            merged_bucket = dict(bucket) if isinstance(bucket, dict) else {}
            merged_bucket["level"] = level
            normalized[class_id] = merged_bucket
        return normalized

    def _resolve_ability_mods(self, ability_scores: Any, explicit_mods: Any) -> dict[str, int]:
        if isinstance(ability_scores, dict) and ability_scores:
            normalized: dict[str, int] = {}
            for key, value in ability_scores.items():
                if not isinstance(key, str) or not isinstance(value, int):
                    continue
                normalized[key.strip().lower()] = (value - 10) // 2
            if normalized:
                return normalized
        return dict(explicit_mods) if isinstance(explicit_mods, dict) else {}

    def _resolve_proficiency_bonus(self, *, total_level: int, explicit: Any) -> int:
        if isinstance(explicit, int) and explicit > 0:
            return explicit
        return 2 + max(0, total_level - 1) // 4

    def _resolve_spellcasting_ability(self, *, class_name: str, explicit: Any) -> str | None:
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        normalized_class_name = class_name.strip().lower()
        return _CLASS_SPELLCASTING_ABILITIES.get(normalized_class_name)

    def _resolve_skill_modifiers(
        self,
        *,
        skill_training: Any,
        ability_mods: dict[str, int],
        proficiency_bonus: int,
        explicit_modifiers: Any,
    ) -> dict[str, int]:
        normalized = dict(explicit_modifiers) if isinstance(explicit_modifiers, dict) else {}
        if not isinstance(skill_training, dict):
            return normalized

        for raw_skill, raw_training in skill_training.items():
            if not isinstance(raw_skill, str) or not raw_skill.strip():
                continue
            if not isinstance(raw_training, str):
                continue
            skill = raw_skill.strip().lower()
            training = raw_training.strip().lower()
            if skill in normalized and isinstance(normalized[skill], int):
                continue
            ability = SKILL_TO_ABILITY.get(skill)
            if ability is None:
                continue
            ability_modifier = int(ability_mods.get(ability, 0) or 0)
            if training == "expertise":
                normalized[skill] = ability_modifier + proficiency_bonus * 2
            elif training == "proficient":
                normalized[skill] = ability_modifier + proficiency_bonus
            elif training == "none":
                normalized[skill] = ability_modifier
        return normalized

    def _normalize_spells(self, spells: Any, *, primary_class_name: str) -> list[dict[str, Any]]:
        if not isinstance(spells, list):
            return []
        normalized: list[dict[str, Any]] = []
        for raw_spell in spells:
            if not isinstance(raw_spell, dict):
                continue
            spell = dict(raw_spell)
            if not isinstance(spell.get("casting_class"), str) or not spell.get("casting_class", "").strip():
                spell["casting_class"] = primary_class_name
            normalized.append(spell)
        return normalized

    def _ensure_martial_runtimes(self, entity: EncounterEntity) -> None:
        class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
        if isinstance(class_features.get("fighter"), dict):
            ensure_fighter_runtime(entity)
        if isinstance(class_features.get("barbarian"), dict):
            ensure_barbarian_runtime(entity)
