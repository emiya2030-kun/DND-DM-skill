from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.shared_turns import is_entity_in_current_turn_group
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseHelpAttack:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str, target_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        target = self._get_target_or_raise(encounter, target_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_target_is_enemy(actor, target)
        self._ensure_target_within_help_range(actor, target)

        actor.action_economy["action_used"] = True
        target.turn_effects = [
            effect
            for effect in target.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "help_attack"
                and effect.get("source_entity_id") == actor.entity_id
            )
        ]
        target.turn_effects.append(
            {
                "effect_id": f"effect_help_attack_{uuid4().hex[:12]}",
                "effect_type": "help_attack",
                "name": "Help Attack",
                "source_entity_id": actor.entity_id,
                "source_name": actor.name,
                "source_side": actor.side,
                "trigger": "manual_state",
                "source_ref": "action:help_attack",
                "expires_on": "source_next_turn_start",
                "remaining_uses": 1,
            }
        )
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor

    def _get_target_or_raise(self, encounter: Encounter, target_id: str) -> EncounterEntity:
        target = encounter.entities.get(target_id)
        if target is None:
            raise ValueError(f"target '{target_id}' not found in encounter")
        return target

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if not is_entity_in_current_turn_group(encounter, actor_id):
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_target_is_enemy(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        if actor.side == target.side:
            raise ValueError("help_attack_target_must_be_enemy")

    def _ensure_target_within_help_range(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        dx = abs(int(actor.position.get("x", 0)) - int(target.position.get("x", 0)))
        dy = abs(int(actor.position.get("y", 0)) - int(target.position.get("y", 0)))
        if max(dx, dy) > 1:
            raise ValueError("target_not_within_help_attack_range")
