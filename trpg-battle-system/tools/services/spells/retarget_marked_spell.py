from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent
from tools.services.spells.build_turn_effect_instance import build_turn_effect_instance


class RetargetMarkedSpell:
    """把一个已获得转移资格的持续标记法术改挂到新目标上。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        spell_definition_repository: SpellDefinitionRepository | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()

    def execute(
        self,
        *,
        encounter_id: str,
        spell_instance_id: str,
        new_target_id: str,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        caster = self._get_current_entity_or_raise(encounter)
        new_target = self._get_entity_or_raise(encounter, new_target_id)
        instance = self._get_spell_instance_or_raise(encounter, spell_instance_id)

        self._ensure_instance_owned_by_caster(instance, caster)
        self._ensure_bonus_action_available(caster)
        self._ensure_retarget_available(instance)
        self._ensure_valid_new_target(new_target)

        spell_definition = self._get_spell_definition_or_raise(str(instance.get("spell_id") or ""))
        effect_template_id = self._get_single_retarget_effect_template_id_or_raise(spell_definition)
        effect = build_turn_effect_instance(
            spell_definition=spell_definition,
            effect_template_id=effect_template_id,
            caster=caster,
            save_dc=None,
        )
        new_target.turn_effects.append(effect)

        previous_target_id = self._extract_previous_target_id(instance)
        instance["targets"] = [
            {
                "entity_id": new_target.entity_id,
                "applied_conditions": [],
                "turn_effect_ids": [effect["effect_id"]],
            }
        ]
        special_runtime = instance.setdefault("special_runtime", {})
        special_runtime["current_target_id"] = new_target.entity_id
        special_runtime["retarget_available"] = False
        caster.action_economy["bonus_action_used"] = True

        self.encounter_repository.save(encounter)
        event = self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="spell_retargeted",
            actor_entity_id=caster.entity_id,
            target_entity_id=new_target.entity_id,
            payload={
                "spell_instance_id": spell_instance_id,
                "spell_id": instance.get("spell_id"),
                "spell_name": instance.get("spell_name"),
                "previous_target_id": previous_target_id,
                "new_target_id": new_target.entity_id,
                "slot_consumed": None,
                "effect_id": effect["effect_id"],
            },
        )

        result = {
            "encounter_id": encounter.encounter_id,
            "spell_instance_id": spell_instance_id,
            "spell_id": instance.get("spell_id"),
            "spell_name": instance.get("spell_name"),
            "previous_target_id": previous_target_id,
            "new_target_id": new_target.entity_id,
            "slot_consumed": None,
            "effect_id": effect["effect_id"],
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result

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

    def _get_spell_instance_or_raise(self, encounter: Encounter, spell_instance_id: str) -> dict[str, Any]:
        for instance in encounter.spell_instances:
            if instance.get("instance_id") == spell_instance_id:
                return instance
        raise ValueError(f"spell_instance '{spell_instance_id}' not found")

    def _ensure_instance_owned_by_caster(self, instance: dict[str, Any], caster: EncounterEntity) -> None:
        if instance.get("caster_entity_id") != caster.entity_id:
            raise ValueError("spell_instance_not_owned_by_current_entity")

    def _ensure_bonus_action_available(self, caster: EncounterEntity) -> None:
        if bool(caster.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_retarget_available(self, instance: dict[str, Any]) -> None:
        concentration = instance.get("concentration", {})
        lifecycle = instance.get("lifecycle", {})
        special_runtime = instance.get("special_runtime", {})
        if not isinstance(concentration, dict) or not concentration.get("active"):
            raise ValueError("spell_instance_not_active")
        if not isinstance(lifecycle, dict) or lifecycle.get("status") != "active":
            raise ValueError("spell_instance_not_active")
        if not isinstance(special_runtime, dict) or not special_runtime.get("retarget_available"):
            raise ValueError("spell_instance_not_retargetable")
        if special_runtime.get("current_target_id") is not None:
            raise ValueError("spell_instance_already_has_target")

    def _ensure_valid_new_target(self, new_target: EncounterEntity) -> None:
        if new_target.hp["current"] <= 0 or bool(new_target.combat_flags.get("is_defeated")):
            raise ValueError("new_target_invalid")

    def _get_spell_definition_or_raise(self, spell_id: str) -> dict[str, Any]:
        spell_definition = self.spell_definition_repository.get(spell_id)
        if not isinstance(spell_definition, dict):
            raise ValueError(f"spell '{spell_id}' not found in repository")
        return spell_definition

    def _get_single_retarget_effect_template_id_or_raise(self, spell_definition: dict[str, Any]) -> str:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            raise ValueError("spell_definition.on_cast must be a dict")
        on_resolve = on_cast.get("on_resolve")
        if not isinstance(on_resolve, dict):
            raise ValueError("spell_definition.on_cast.on_resolve must be a dict")
        raw_effects = on_resolve.get("apply_turn_effects", [])
        if not isinstance(raw_effects, list) or len(raw_effects) != 1:
            raise ValueError("retarget spell must define exactly one apply_turn_effect")
        effect_template_id = raw_effects[0].get("effect_template_id")
        if not isinstance(effect_template_id, str) or not effect_template_id.strip():
            raise ValueError("effect_template_id must be a non-empty string")
        return effect_template_id.strip()

    def _extract_previous_target_id(self, instance: dict[str, Any]) -> str | None:
        targets = instance.get("targets", [])
        if not isinstance(targets, list) or not targets:
            return None
        first_target = targets[0]
        if not isinstance(first_target, dict):
            return None
        entity_id = first_target.get("entity_id")
        return entity_id if isinstance(entity_id, str) else None
