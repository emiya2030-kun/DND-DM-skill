from __future__ import annotations

from typing import TYPE_CHECKING, Any

import math

from tools.models import Encounter
from tools.services.class_features.shared import (
    get_class_runtime,
    get_fighter_runtime,
    get_monk_runtime,
    has_any_spell_slot,
    has_fighting_style,
)
from tools.services.encounter.movement_rules import get_center_position

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

            target = encounter.entities.get(target_id)
            if target is None:
                return []

            candidates: list[dict[str, Any]] = []
            for definition in definitions:
                reaction_type = definition.get("reaction_type")
                if reaction_type == "shield" and self._eligible_for_shield(target):
                    candidates.append(
                        {
                            "actor_entity_id": target_id,
                            "reaction_definition": definition,
                        }
                    )
                elif reaction_type == "deflect_attacks" and self._eligible_for_deflect_attacks(
                    entity=target,
                    trigger_event=trigger_event,
                ):
                    candidates.append(
                        {
                            "actor_entity_id": target_id,
                            "reaction_definition": definition,
                        }
                    )
                elif reaction_type == "uncanny_dodge" and self._eligible_for_uncanny_dodge(
                    entity=target,
                    trigger_event=trigger_event,
                ):
                    candidates.append(
                        {
                            "actor_entity_id": target_id,
                            "reaction_definition": definition,
                        }
                    )
            source = self._resolve_attack_source(encounter, trigger_event)
            for entity in encounter.entities.values():
                if entity.entity_id == target.entity_id:
                    continue
                if source is not None and entity.entity_id == source.entity_id:
                    continue
                for definition in definitions:
                    reaction_type = definition.get("reaction_type")
                    if reaction_type == "interception" and self._eligible_for_interception(
                        entity=entity,
                        target=target,
                        source=source,
                    ):
                        candidates.append(
                            {
                                "actor_entity_id": entity.entity_id,
                                "reaction_definition": definition,
                            }
                        )
                    elif reaction_type == "protection" and self._eligible_for_protection(
                        entity=entity,
                        target=target,
                        source=source,
                    ):
                        candidates.append(
                            {
                                "actor_entity_id": entity.entity_id,
                                "reaction_definition": definition,
                            }
                        )
            return candidates

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
            payload = trigger_event.get("payload")
            if isinstance(payload, dict):
                metamagic = payload.get("metamagic")
                if isinstance(metamagic, dict) and bool(metamagic.get("subtle_spell")):
                    return []
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
                if not self._eligible_for_counterspell(entity, caster):
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

        if trigger_type == "failed_save":
            target_id = trigger_event.get("target_entity_id")
            if not isinstance(target_id, str):
                return []
            target = encounter.entities.get(target_id)
            if target is None:
                return []

            definitions = [definition for definition in definitions if definition.get("reaction_type") == "indomitable"]
            if not definitions or not self._eligible_for_indomitable(target):
                return []

            return [
                {
                    "actor_entity_id": target.entity_id,
                    "reaction_definition": definition,
                }
                for definition in definitions
            ]

        if trigger_type == "failed_ability_check":
            target_id = trigger_event.get("target_entity_id")
            if not isinstance(target_id, str):
                return []
            target = encounter.entities.get(target_id)
            if target is None:
                return []

            definitions = [definition for definition in definitions if definition.get("reaction_type") == "tactical_mind"]
            if not definitions or not self._eligible_for_tactical_mind(target):
                return []

            return [
                {
                    "actor_entity_id": target.entity_id,
                    "reaction_definition": definition,
                }
                for definition in definitions
            ]

        return []

    def _eligible_for_shield(self, entity: Any) -> bool:
        return (
            self._reaction_available(entity)
            and self._has_spell(entity, "shield")
            and self._has_spell_slot(entity, minimum_level=1)
        )

    def _eligible_for_counterspell(self, entity: Any, caster: Any) -> bool:
        return (
            self._reaction_available(entity)
            and self._has_spell(entity, "counterspell")
            and self._has_spell_slot(entity, minimum_level=3)
            and self._within_counterspell_range(entity, caster)
        )

    def _eligible_for_deflect_attacks(self, *, entity: Any, trigger_event: dict[str, Any]) -> bool:
        if not self._reaction_available(entity):
            return False
        monk_runtime = get_monk_runtime(entity)
        if not monk_runtime:
            return False
        deflect_state = monk_runtime.get("deflect_attacks")
        if not isinstance(deflect_state, dict) or not bool(deflect_state.get("enabled")):
            return False
        host_snapshot = trigger_event.get("host_action_snapshot")
        if not isinstance(host_snapshot, dict):
            return False
        primary_damage_type = str(host_snapshot.get("primary_damage_type") or "").lower()
        if primary_damage_type in {"bludgeoning", "piercing", "slashing"}:
            return True
        deflect_energy = monk_runtime.get("deflect_energy")
        if isinstance(deflect_energy, dict) and bool(deflect_energy.get("enabled")):
            return True
        level = monk_runtime.get("level", 0)
        return isinstance(level, int) and level >= 13

    def _eligible_for_uncanny_dodge(self, *, entity: Any, trigger_event: dict[str, Any]) -> bool:
        if not self._reaction_available(entity):
            return False
        rogue_runtime = get_class_runtime(entity, "rogue")
        if not isinstance(rogue_runtime, dict) or not rogue_runtime:
            return False
        level = rogue_runtime.get("level", 0)
        if isinstance(level, bool) or not isinstance(level, int) or level < 5:
            return False
        uncanny_dodge = rogue_runtime.get("uncanny_dodge")
        if isinstance(uncanny_dodge, dict):
            return bool(uncanny_dodge.get("enabled"))
        host_snapshot = trigger_event.get("host_action_snapshot")
        return isinstance(host_snapshot, dict) and isinstance(host_snapshot.get("actor_id"), str)

    def _eligible_for_interception(self, *, entity: Any, target: Any, source: Any) -> bool:
        if source is None:
            return False
        if not self._reaction_available(entity):
            return False
        if entity.side != target.side or entity.side == source.side:
            return False
        if not self._within_five_feet(entity, target):
            return False
        if not has_fighting_style(entity, "interception"):
            return False
        return self._has_interception_equipment(entity)

    def _eligible_for_protection(self, *, entity: Any, target: Any, source: Any) -> bool:
        if source is None:
            return False
        if not self._reaction_available(entity):
            return False
        if entity.side != target.side or entity.side == source.side:
            return False
        if not self._within_five_feet(entity, target):
            return False
        if not has_fighting_style(entity, "protection"):
            return False
        return isinstance(getattr(entity, "equipped_shield", None), dict)

    def _eligible_for_indomitable(self, entity: Any) -> bool:
        class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
        fighter = class_features.get("fighter")
        if not isinstance(fighter, dict):
            return False

        fighter_level = fighter.get("fighter_level", fighter.get("level", 0))
        if isinstance(fighter_level, bool) or not isinstance(fighter_level, int) or fighter_level < 9:
            return False

        indomitable_state = fighter.get("indomitable")
        if not isinstance(indomitable_state, dict):
            return False
        remaining_uses = indomitable_state.get("remaining_uses")
        return isinstance(remaining_uses, int) and not isinstance(remaining_uses, bool) and remaining_uses > 0

    def _eligible_for_tactical_mind(self, entity: Any) -> bool:
        fighter = get_fighter_runtime(entity)
        if not isinstance(fighter, dict) or not fighter:
            return False

        level = fighter.get("level", fighter.get("fighter_level", 0))
        if isinstance(level, bool) or not isinstance(level, int) or level < 2:
            return False

        tactical_mind = fighter.get("tactical_mind")
        if isinstance(tactical_mind, dict) and not bool(tactical_mind.get("enabled", False)):
            return False

        second_wind = fighter.get("second_wind")
        if not isinstance(second_wind, dict):
            return False
        remaining_uses = second_wind.get("remaining_uses")
        return isinstance(remaining_uses, int) and not isinstance(remaining_uses, bool) and remaining_uses > 0

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
        return has_any_spell_slot(entity, minimum_level=minimum_level)

    def _within_counterspell_range(self, entity: Any, caster: Any) -> bool:
        try:
            distance = self._distance_feet(entity, caster)
        except (KeyError, TypeError):
            return False
        return distance <= 60

    def _within_five_feet(self, entity: Any, target: Any) -> bool:
        try:
            return self._distance_feet(entity, target) <= 5
        except (KeyError, TypeError):
            return False

    def _has_interception_equipment(self, entity: Any) -> bool:
        if isinstance(getattr(entity, "equipped_shield", None), dict):
            return True
        for weapon in getattr(entity, "weapons", []) or []:
            if not isinstance(weapon, dict):
                continue
            category = str(weapon.get("category") or "").strip().lower()
            if category in {"simple", "martial"}:
                return True
        return False

    def _resolve_attack_source(self, encounter: Encounter, trigger_event: dict[str, Any]) -> Any:
        host_snapshot = trigger_event.get("host_action_snapshot")
        if not isinstance(host_snapshot, dict):
            return None
        actor_id = host_snapshot.get("actor_id")
        if not isinstance(actor_id, str):
            return None
        return encounter.entities.get(actor_id)

    def _distance_feet(self, source: Any, target: Any) -> int:
        source_center = get_center_position(source)
        target_center = get_center_position(target)
        dx = abs(source_center["x"] - target_center["x"])
        dy = abs(source_center["y"] - target_center["y"])
        return math.ceil(max(dx, dy)) * 5
