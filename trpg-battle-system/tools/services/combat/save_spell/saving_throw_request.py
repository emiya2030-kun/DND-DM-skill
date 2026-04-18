from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.repositories.armor_definition_repository import ArmorDefinitionRepository
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.combat.actions import has_dodge_effect
from tools.services.combat.defense.armor_profile_resolver import ArmorProfileResolver
from tools.services.combat.rules.conditions import ConditionRuntime


class SavingThrowRequest:
    """根据当前 encounter 状态生成一次目标豁免请求。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        spell_definition_repository: SpellDefinitionRepository | None = None,
        armor_definition_repository: ArmorDefinitionRepository | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()
        self.armor_profile_resolver = ArmorProfileResolver(armor_definition_repository or ArmorDefinitionRepository())

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        spell_id: str,
        vantage: str = "normal",
        description: str | None = None,
        force_save_ability: str | None = None,
        save_dc_bonus: int = 0,
        metamagic: dict[str, object] | None = None,
    ) -> RollRequest:
        """为目标生成一次豁免请求。

        这里沿用现有的 RollRequest 模型，但要注意语义：
        - `actor_entity_id` 是实际要掷豁免骰的目标
        - `target_entity_id` 也是受法术影响的目标
        - 施法者信息放在 `context.caster_entity_id`

        之所以这样设计，是因为豁免型法术里真正“掷骰的人”不是施法者。
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        caster = self._get_current_entity_or_raise(encounter)
        target = self._get_entity_or_raise(encounter, target_id)
        spell_definition = self._get_spell_definition_or_raise(encounter, caster, spell_id)
        self.armor_profile_resolver.refresh_entity_armor_class(target)
        target_runtime = ConditionRuntime(target.conditions)

        save_ability = force_save_ability or spell_definition.get("save_ability")
        if not isinstance(save_ability, str) or not save_ability.strip():
            raise ValueError(f"spell '{spell_id}' does not define save_ability")

        save_dc = self._resolve_save_dc(caster, spell_definition, save_dc_bonus=save_dc_bonus)
        distance_to_target_feet = self._distance_feet(caster, target)
        normalized_vantage = self._normalize_vantage(vantage)
        armor_profile = self.armor_profile_resolver.resolve(target)
        vantage_sources = {"advantage": [], "disadvantage": []}
        if normalized_vantage == "advantage":
            vantage_sources["advantage"].append("requested_advantage")
        elif normalized_vantage == "disadvantage":
            vantage_sources["disadvantage"].append("requested_disadvantage")
        metamagic_context = self._normalize_metamagic(metamagic)
        if (
            bool(metamagic_context.get("heightened_spell"))
            and metamagic_context.get("heightened_target_id") == target.entity_id
        ):
            vantage_sources["disadvantage"].append("metamagic_heightened_spell")
        if armor_profile["wearing_untrained_armor"] and save_ability.strip().lower() in {"str", "dex"}:
            vantage_sources["disadvantage"].append("armor_untrained")
        if (
            save_ability.strip().lower() == "dex"
            and has_dodge_effect(target)
            and not target_runtime.has("incapacitated")
            and int(target.speed.get("walk", 0) or 0) > 0
        ):
            vantage_sources["advantage"].append("dodge")
        barbarian = ensure_barbarian_runtime(target) if target.class_features.get("barbarian") else {}
        if (
            save_ability.strip().lower() == "dex"
            and barbarian.get("danger_sense", {}).get("enabled")
            and not target_runtime.has("incapacitated")
        ):
            vantage_sources["advantage"].append("barbarian_danger_sense")
        if vantage_sources["advantage"] and vantage_sources["disadvantage"]:
            normalized_vantage = "normal"
        elif vantage_sources["advantage"]:
            normalized_vantage = "advantage"
        elif vantage_sources["disadvantage"]:
            normalized_vantage = "disadvantage"
        else:
            normalized_vantage = "normal"
        auto_success = (
            bool(metamagic_context.get("careful_spell"))
            and target.entity_id in metamagic_context.get("careful_target_ids", [])
        )
        resolved_spell_id = spell_definition.get("spell_id") or spell_definition.get("id") or spell_id
        resolved_spell_name = spell_definition.get("name") or spell_id

        return RollRequest(
            request_id=self._generate_request_id(),
            encounter_id=encounter.encounter_id,
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            roll_type="saving_throw",
            formula="1d20+save_modifier",
            reason=description or f"{target.name} makes a {save_ability.upper()} save against {resolved_spell_name}",
            context={
                "spell_id": resolved_spell_id,
                "spell_name": resolved_spell_name,
                "spell_level": spell_definition.get("level", 0),
                "save_ability": save_ability,
                "spell_definition": spell_definition,
                "save_dc": save_dc,
                "caster_entity_id": caster.entity_id,
                "caster_name": caster.name,
                "damage": spell_definition.get("damage", []),
                "half_on_success": spell_definition.get("half_on_success", False),
                "vantage": normalized_vantage,
                "vantage_sources": vantage_sources,
                "auto_success": auto_success,
                "metamagic": metamagic_context,
                "distance_to_target": f"{distance_to_target_feet} ft",
                "distance_to_target_feet": distance_to_target_feet,
            },
        )

    def _normalize_metamagic(self, metamagic: dict[str, object] | None) -> dict[str, object]:
        if not isinstance(metamagic, dict):
            return {
                "selected": [],
                "heightened_spell": False,
                "heightened_target_id": None,
                "careful_spell": False,
                "careful_target_ids": [],
                "empowered_spell": False,
                "extended_spell": False,
                "seeking_spell": False,
                "transmuted_spell": False,
                "twinned_spell": False,
                "transmuted_damage_type": None,
            }
        careful_target_ids = metamagic.get("careful_target_ids")
        return {
            "selected": list(metamagic.get("selected", [])) if isinstance(metamagic.get("selected"), list) else [],
            "heightened_spell": bool(metamagic.get("heightened_spell")),
            "heightened_target_id": metamagic.get("heightened_target_id"),
            "careful_spell": bool(metamagic.get("careful_spell")),
            "careful_target_ids": list(careful_target_ids) if isinstance(careful_target_ids, list) else [],
            "empowered_spell": bool(metamagic.get("empowered_spell")),
            "extended_spell": bool(metamagic.get("extended_spell")),
            "seeking_spell": bool(metamagic.get("seeking_spell")),
            "transmuted_spell": bool(metamagic.get("transmuted_spell")),
            "twinned_spell": bool(metamagic.get("twinned_spell")),
            "transmuted_damage_type": metamagic.get("transmuted_damage_type"),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_current_entity_or_raise(self, encounter: Encounter) -> EncounterEntity:
        if encounter.current_entity_id is None:
            raise ValueError("encounter has no current_entity_id")
        entity = encounter.entities.get(encounter.current_entity_id)
        if entity is None:
            raise ValueError("current_entity_id not found in entities")
        return entity

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _get_spell_definition_or_raise(
        self,
        encounter: Encounter,
        caster: EncounterEntity,
        spell_id: str,
    ) -> dict:
        global_spell_definition = self.spell_definition_repository.get(spell_id)
        if isinstance(global_spell_definition, dict):
            return global_spell_definition

        encounter_metadata = getattr(encounter, "metadata", None)
        if isinstance(encounter_metadata, dict):
            encounter_spell_definitions = encounter_metadata.get("spell_definitions")
            if isinstance(encounter_spell_definitions, dict):
                spell_definition = encounter_spell_definitions.get(spell_id)
                if isinstance(spell_definition, dict):
                    return spell_definition

        source_ref_spell_definitions = caster.source_ref.get("spell_definitions")
        if isinstance(source_ref_spell_definitions, dict):
            spell_definition = source_ref_spell_definitions.get(spell_id)
            if isinstance(spell_definition, dict):
                return spell_definition

        for spell in caster.spells:
            if spell.get("spell_id") == spell_id:
                embedded_spell_definition = spell.get("spell_definition")
                if isinstance(embedded_spell_definition, dict):
                    return embedded_spell_definition
                return spell
        raise ValueError(f"spell '{spell_id}' not found on caster '{caster.entity_id}'")

    def _resolve_save_dc(self, caster: EncounterEntity, spell: dict, *, save_dc_bonus: int = 0) -> int:
        if isinstance(spell.get("save_dc"), int):
            return spell["save_dc"] + save_dc_bonus

        spellcasting_ability = caster.source_ref.get("spellcasting_ability")
        if spellcasting_ability is None:
            raise ValueError("caster.source_ref.spellcasting_ability is required to calculate save DC")

        ability_mod = caster.ability_mods.get(spellcasting_ability)
        if not isinstance(ability_mod, int):
            raise ValueError(f"ability_mods['{spellcasting_ability}'] is required to calculate save DC")

        return 8 + caster.proficiency_bonus + ability_mod + save_dc_bonus

    def _distance_feet(self, source: EncounterEntity, target: EncounterEntity) -> int:
        source_x = source.position.get("x")
        source_y = source.position.get("y")
        target_x = target.position.get("x")
        target_y = target.position.get("y")
        if not all(isinstance(value, int) for value in (source_x, source_y, target_x, target_y)):
            raise ValueError("source and target positions must contain integer x and y")
        dx = abs(source_x - target_x)
        dy = abs(source_y - target_y)
        return max(dx, dy) * 5

    def _normalize_vantage(self, vantage: str) -> str:
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("vantage must be 'normal', 'advantage', or 'disadvantage'")
        return vantage

    def _generate_request_id(self) -> str:
        return f"req_save_{uuid4().hex[:12]}"
