from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.shared_turns import is_entity_in_current_turn_group


class UseDisengage:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)

        actor.action_economy["action_used"] = True
        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_disengage_{uuid4().hex[:12]}",
                "effect_type": "disengage",
                "name": "Disengage",
                "trigger": "manual_state",
                "source_ref": "action:disengage",
                "expires_at": "end_of_current_turn",
            },
        )
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
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

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if not is_entity_in_current_turn_group(encounter, actor_id):
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")
