from __future__ import annotations

from typing import Any

from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import get_class_runtime, get_monk_runtime, resolve_entity_proficiencies

from tools.models.encounter_entity import EncounterEntity
from tools.repositories.armor_definition_repository import ArmorDefinitionRepository

_TRAINED_ARMOR_CATEGORIES = {"light", "medium", "heavy"}


class ArmorProfileResolver:
    """合并实体装备、职业受训和静态护甲模板，产出战斗可用防御快照。"""

    def __init__(self, armor_definition_repository: ArmorDefinitionRepository | None = None):
        self.armor_definition_repository = armor_definition_repository or ArmorDefinitionRepository()

    def resolve(self, actor: EncounterEntity) -> dict[str, Any]:
        training = self._resolve_armor_training(actor)
        armor = self._resolve_equipped_item(actor.equipped_armor)
        shield = self._resolve_equipped_item(actor.equipped_shield)
        temporary_ac_bonus = self._active_temporary_ac_bonus(actor)
        fighting_style_bonus = self._resolve_fighting_style_ac_bonus(actor, armor)
        unarmored_defense_base_ac = self._resolve_unarmored_defense_base_ac(actor)

        if armor is None and shield is None:
            base_ac = (
                unarmored_defense_base_ac
                if isinstance(unarmored_defense_base_ac, int)
                else max(0, actor.ac - temporary_ac_bonus)
            )
            current_ac = base_ac + temporary_ac_bonus
            return {
                "armor": None,
                "shield": None,
                "armor_training": training,
                "wearing_untrained_armor": False,
                "shield_trained": False,
                "speed_penalty_feet": 0,
                "stealth_disadvantage_sources": [],
                "base_ac": base_ac,
                "current_ac": current_ac,
                "ac_breakdown": {
                    "base_armor_ac": base_ac,
                    "fighting_style_bonus": 0,
                    "shield_bonus": 0,
                    "shield_spell_bonus_active": temporary_ac_bonus,
                    "current_ac": current_ac,
                },
            }

        dex_mod = self._ability_mod(actor, "dex")
        armor_category = str(armor.get("category") or "").lower() if armor else ""
        shield_category = str(shield.get("category") or "").lower() if shield else ""
        armor_trained = self._is_equipment_trained(actor.equipped_armor, armor_category, training) if armor else False
        shield_trained = self._is_equipment_trained(actor.equipped_shield, shield_category, training) if shield else False
        stealth_disadvantage_sources: list[str] = []

        if armor is None:
            if isinstance(unarmored_defense_base_ac, int):
                base_armor_ac = unarmored_defense_base_ac
            else:
                base_armor_ac = 10 + dex_mod
        else:
            ac_data = armor.get("ac") if isinstance(armor.get("ac"), dict) else {}
            armor_base = int(ac_data.get("base", 10))
            add_dex_modifier = bool(ac_data.get("add_dex_modifier", armor_category != "heavy"))
            dex_cap = ac_data.get("dex_cap")
            applied_dex = dex_mod if add_dex_modifier else 0
            if isinstance(dex_cap, int):
                applied_dex = min(applied_dex, dex_cap)
            base_armor_ac = armor_base + applied_dex
            if bool(armor.get("stealth_disadvantage")):
                stealth_disadvantage_sources.append(str(armor.get("armor_id") or "armor"))

        shield_bonus = 0
        if shield is not None and shield_trained:
            shield_ac = shield.get("ac") if isinstance(shield.get("ac"), dict) else {}
            shield_bonus = int(shield_ac.get("bonus", 0) or 0)

        current_ac = base_armor_ac + shield_bonus + fighting_style_bonus + temporary_ac_bonus
        strength_requirement = armor.get("strength_requirement") if armor else None
        strength_score = self._ability_score(actor, "str")
        speed_penalty_feet = 0
        if isinstance(strength_requirement, int) and strength_score < strength_requirement:
            speed_penalty_feet = 10

        wearing_untrained_armor = bool(armor) and armor_category in _TRAINED_ARMOR_CATEGORIES and not armor_trained
        return {
            "armor": self._project_item(armor),
            "shield": self._project_item(shield),
            "armor_training": training,
            "wearing_untrained_armor": wearing_untrained_armor,
            "shield_trained": shield_trained,
            "speed_penalty_feet": speed_penalty_feet,
            "stealth_disadvantage_sources": stealth_disadvantage_sources,
            "base_ac": base_armor_ac + shield_bonus + fighting_style_bonus,
            "current_ac": current_ac,
            "ac_breakdown": {
                "base_armor_ac": base_armor_ac,
                "fighting_style_bonus": fighting_style_bonus,
                "shield_bonus": shield_bonus,
                "shield_spell_bonus_active": temporary_ac_bonus,
                "current_ac": current_ac,
            },
        }

    def refresh_entity_armor_class(self, actor: EncounterEntity) -> dict[str, Any]:
        profile = self.resolve(actor)
        if actor.equipped_armor is not None or actor.equipped_shield is not None or profile["ac_breakdown"]["shield_spell_bonus_active"]:
            actor.ac = profile["current_ac"]
        return profile

    def _resolve_equipped_item(self, runtime_item: dict[str, Any] | None) -> dict[str, Any] | None:
        if runtime_item is None:
            return None
        if not isinstance(runtime_item, dict):
            raise ValueError("equipped_armor and equipped_shield must be dict when provided")
        armor_id = runtime_item.get("armor_id")
        if not isinstance(armor_id, str) or not armor_id.strip():
            raise ValueError("equipped item must define armor_id")
        definition = self.armor_definition_repository.get(armor_id)
        if definition is None:
            raise ValueError(f"armor_definition_not_found:{armor_id}")
        resolved = dict(definition)
        resolved.update(runtime_item)
        return resolved

    def _resolve_armor_training(self, actor: EncounterEntity) -> list[str]:
        return resolve_entity_proficiencies(actor)["armor_training"]

    def _resolve_unarmored_defense_base_ac(self, actor: EncounterEntity) -> int | None:
        barbarian_runtime = get_class_runtime(actor, "barbarian")
        if barbarian_runtime and actor.equipped_armor is None:
            barbarian = ensure_barbarian_runtime(actor)
            return 10 + self._ability_mod(actor, "dex") + self._ability_mod(actor, "con")

        monk_runtime = get_monk_runtime(actor)
        if not monk_runtime:
            return None
        if actor.equipped_armor is not None or actor.equipped_shield is not None:
            return None
        return 10 + self._ability_mod(actor, "dex") + self._ability_mod(actor, "wis")

    def _is_equipment_trained(
        self,
        runtime_item: dict[str, Any] | None,
        category: str,
        training: list[str],
    ) -> bool:
        if not isinstance(runtime_item, dict):
            return False
        explicit = runtime_item.get("is_trained")
        if isinstance(explicit, bool):
            return explicit
        return category in set(training)

    def _active_temporary_ac_bonus(self, actor: EncounterEntity) -> int:
        total = 0
        for effect in actor.turn_effects:
            if not isinstance(effect, dict):
                continue
            if effect.get("effect_type") != "shield_ac_bonus":
                continue
            bonus = effect.get("ac_bonus", 0)
            if isinstance(bonus, int):
                total += bonus
        return total

    def _resolve_fighting_style_ac_bonus(self, actor: EncounterEntity, armor: dict[str, Any] | None) -> int:
        fighter_runtime = get_class_runtime(actor, "fighter")
        if not fighter_runtime or armor is None:
            return 0
        fighting_style = fighter_runtime.get("fighting_style")
        if not isinstance(fighting_style, dict):
            return 0
        style_id = str(fighting_style.get("style_id") or "").strip().lower()
        return 1 if style_id == "defense" else 0

    def _project_item(self, item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "armor_id": item.get("armor_id"),
            "name": item.get("name"),
            "category": item.get("category"),
        }

    def _ability_mod(self, actor: EncounterEntity, ability: str) -> int:
        value = actor.ability_mods.get(ability, 0)
        return value if isinstance(value, int) else 0

    def _ability_score(self, actor: EncounterEntity, ability: str) -> int:
        value = actor.ability_scores.get(ability, 0)
        return value if isinstance(value, int) else 0


def refresh_entity_armor_class(
    actor: EncounterEntity,
    armor_definition_repository: ArmorDefinitionRepository | None = None,
) -> dict[str, Any]:
    return ArmorProfileResolver(armor_definition_repository).refresh_entity_armor_class(actor)


def get_armor_speed_penalty(
    actor: EncounterEntity,
    armor_definition_repository: ArmorDefinitionRepository | None = None,
) -> int:
    return int(ArmorProfileResolver(armor_definition_repository).resolve(actor)["speed_penalty_feet"])
