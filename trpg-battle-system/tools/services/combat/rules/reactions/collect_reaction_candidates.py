from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tools.models import Encounter

if TYPE_CHECKING:
    from tools.repositories import EncounterRepository
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository


class CollectReactionCandidates:
    """Pulls candidate actors and definitions for a trigger event."""

    def __init__(
        self,
        encounter_repository: "EncounterRepository",
        definition_repository: "ReactionDefinitionRepository",
    ) -> None:
        self.encounter_repository = encounter_repository
        self.definition_repository = definition_repository

    def execute(self, *, encounter: Encounter, trigger_event: dict[str, Any]) -> list[dict[str, Any]]:
        trigger_type = str(trigger_event.get("trigger_type", ""))
        definitions = self.definition_repository.list_by_trigger_type(trigger_type)
        if trigger_type == "attack_declared":
            target_id = trigger_event.get("target_entity_id")
            if not isinstance(target_id, str) or target_id not in encounter.entities:
                return []

            definitions = [definition for definition in definitions if definition.get("reaction_type") == "shield"]
            if not definitions:
                return []

            target = encounter.entities.get(target_id)
            if target is None or not self._eligible_for_shield(target):
                return []

            return [
                {
                    "actor_entity_id": target_id,
                    "reaction_definition": definition,
                }
                for definition in definitions
            ]

        if trigger_type == "leave_reach":
            actor_ids: list[str] = []
            reactor_id = trigger_event.get("reactor_entity_id")
            if isinstance(reactor_id, str):
                actor_ids.append(reactor_id)
            for key in ("reactor_entity_ids", "candidate_actor_ids"):
                raw_ids = trigger_event.get(key)
                if isinstance(raw_ids, list):
                    actor_ids.extend(str(item) for item in raw_ids)
            actor_ids = [actor_id for actor_id in dict.fromkeys(actor_ids) if actor_id in encounter.entities]
            if not actor_ids:
                return []
            return [
                {
                    "actor_entity_id": actor_id,
                    "reaction_definition": definition,
                }
                for actor_id in actor_ids
                for definition in definitions
            ]

        if trigger_type == "spell_declared":
            caster_id = trigger_event.get("caster_entity_id")
            if not isinstance(caster_id, str):
                return []
            caster = encounter.entities.get(caster_id)
            if caster is None:
                return []

            definitions = [definition for definition in definitions if definition.get("reaction_type") == "counterspell"]
            if not definitions:
                return []

            actor_ids: list[str] = []
            for entity in encounter.entities.values():
                if entity.entity_id == caster.entity_id:
                    continue
                if entity.side == caster.side:
                    continue
                if not self._eligible_for_counterspell(entity):
                    continue
                actor_ids.append(entity.entity_id)
            if not actor_ids:
                return []
            return [
                {
                    "actor_entity_id": actor_id,
                    "reaction_definition": definition,
                }
                for actor_id in actor_ids
                for definition in definitions
            ]

        return []

    def _eligible_for_shield(self, entity: Any) -> bool:
        return (
            self._reaction_available(entity)
            and self._has_spell(entity, "shield")
            and self._has_spell_slot(entity, minimum_level=1)
        )

    def _eligible_for_counterspell(self, entity: Any) -> bool:
        return (
            self._reaction_available(entity)
            and self._has_spell(entity, "counterspell")
            and self._has_spell_slot(entity, minimum_level=3)
        )

    def _reaction_available(self, entity: Any) -> bool:
        action_economy = entity.action_economy if isinstance(entity.action_economy, dict) else {}
        if "reaction_used" not in action_economy:
            return False
        return not bool(action_economy.get("reaction_used"))

    def _has_spell(self, entity: Any, spell_id: str) -> bool:
        spell_id = str(spell_id)
        if not spell_id:
            return False
        for spell in getattr(entity, "spells", []) or []:
            if not isinstance(spell, dict):
                continue
            if spell.get("spell_id") == spell_id or spell.get("id") == spell_id:
                return True
            embedded = spell.get("spell_definition")
            if isinstance(embedded, dict):
                if embedded.get("spell_id") == spell_id or embedded.get("id") == spell_id:
                    return True
        source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
        spell_definitions = source_ref.get("spell_definitions")
        if isinstance(spell_definitions, dict):
            if spell_id in spell_definitions:
                return True
        return False

    def _has_spell_slot(self, entity: Any, *, minimum_level: int) -> bool:
        resources = entity.resources if isinstance(entity.resources, dict) else {}
        spell_slots = resources.get("spell_slots")
        if not isinstance(spell_slots, dict):
            return False
        for level_key, slot in spell_slots.items():
            if not isinstance(slot, dict):
                continue
            remaining = slot.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                continue
            try:
                level = int(level_key)
            except (TypeError, ValueError):
                continue
            if level >= minimum_level:
                return True
        return False
