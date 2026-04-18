from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.shared_turns import is_entity_in_current_turn_group


class UseHelpAbilityCheck:
    VALID_CHECK_TYPES = {"skill", "tool"}

    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        ally_id: str,
        check_type: str,
        check_key: str,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        ally = self._get_target_or_raise(encounter, ally_id)
        normalized_check_type = str(check_type or "").strip().lower()
        normalized_check_key = str(check_key or "").strip().lower()
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_target_is_ally(actor, ally)
        self._ensure_check_type(normalized_check_type)
        self._ensure_check_key(normalized_check_key)

        actor.action_economy["action_used"] = True
        ally.turn_effects = [
            effect
            for effect in ally.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "help_ability_check"
                and effect.get("source_entity_id") == actor.entity_id
                and str((effect.get("help_check") or {}).get("check_type") or "").strip().lower()
                == normalized_check_type
                and str((effect.get("help_check") or {}).get("check_key") or "").strip().lower()
                == normalized_check_key
            )
        ]
        ally.turn_effects.append(
            {
                "effect_id": f"effect_help_check_{uuid4().hex[:12]}",
                "effect_type": "help_ability_check",
                "name": "Help Ability Check",
                "source_entity_id": actor.entity_id,
                "source_name": actor.name,
                "trigger": "manual_state",
                "source_ref": "action:help_ability_check",
                "expires_on": "source_next_turn_start",
                "remaining_uses": 1,
                "help_check": {
                    "check_type": normalized_check_type,
                    "check_key": normalized_check_key,
                },
            }
        )
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "ally_id": ally_id,
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

    def _get_target_or_raise(self, encounter: Encounter, ally_id: str) -> EncounterEntity:
        ally = encounter.entities.get(ally_id)
        if ally is None:
            raise ValueError(f"ally '{ally_id}' not found in encounter")
        return ally

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if not is_entity_in_current_turn_group(encounter, actor_id):
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_target_is_ally(self, actor: EncounterEntity, ally: EncounterEntity) -> None:
        if actor.side != ally.side:
            raise ValueError("help_check_target_must_be_ally")

    def _ensure_check_type(self, check_type: str) -> None:
        if check_type not in self.VALID_CHECK_TYPES:
            raise ValueError("invalid_help_check_type")

    def _ensure_check_key(self, check_key: str) -> None:
        if not check_key:
            raise ValueError("help_check_key_required")
