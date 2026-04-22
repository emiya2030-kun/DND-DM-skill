from __future__ import annotations

from random import randint
from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import get_monk_runtime
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState


class UsePatientDefense:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spend_focus: bool = False,
        temp_hp_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        monk = get_monk_runtime(actor)
        if not monk:
            raise ValueError("patient_defense_not_available")

        focus_points = monk.get("focus_points")
        if spend_focus:
            if not isinstance(focus_points, dict):
                raise ValueError("patient_defense_requires_focus_points")
            remaining = focus_points.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                raise ValueError("patient_defense_requires_focus_points")
            focus_points["remaining"] = remaining - 1

        actor.action_economy["bonus_action_used"] = True
        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_patient_defense_disengage_{uuid4().hex[:12]}",
                "effect_type": "disengage",
                "name": "Patient Defense",
                "trigger": "class_feature",
                "source_ref": "monk:patient_defense",
                "expires_at": "end_of_current_turn",
            },
        )
        applied_effects = ["disengage"]
        temp_hp_gained = 0
        if spend_focus:
            add_or_replace_turn_effect(
                actor,
                {
                    "effect_id": f"effect_patient_defense_dodge_{uuid4().hex[:12]}",
                    "effect_type": "dodge",
                    "name": "Patient Defense",
                    "trigger": "class_feature",
                    "source_ref": "monk:patient_defense",
                    "expires_at": "start_of_next_turn",
                },
            )
            applied_effects.append("dodge")
            heightened_focus = monk.get("heightened_focus")
            if isinstance(heightened_focus, dict) and bool(heightened_focus.get("enabled")):
                temp_hp_gained = self._resolve_heightened_focus_temp_hp(
                    monk=monk,
                    temp_hp_roll=temp_hp_roll,
                )
                actor.hp["temp"] = max(int(actor.hp.get("temp", 0) or 0), temp_hp_gained)

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "patient_defense": {
                    "spent_focus": spend_focus,
                    "applied_effects": applied_effects,
                    "temp_hp_gained": temp_hp_gained,
                }
            },
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
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _resolve_heightened_focus_temp_hp(
        self,
        *,
        monk: dict[str, Any],
        temp_hp_roll: dict[str, Any] | None,
    ) -> int:
        rolls = temp_hp_roll.get("rolls") if isinstance(temp_hp_roll, dict) else None
        if rolls is not None:
            if not isinstance(rolls, list):
                raise ValueError("temp_hp_roll.rolls must be a list")
            total = 0
            for roll in rolls:
                if not isinstance(roll, int):
                    raise ValueError("temp_hp_roll.rolls must contain integers")
                total += roll
            return total

        martial_arts_die = monk.get("martial_arts_die")
        if not isinstance(martial_arts_die, str) or not martial_arts_die.startswith("1d"):
            raise ValueError("patient_defense_requires_martial_arts_die")
        sides = int(martial_arts_die[2:])
        return randint(1, sides) + randint(1, sides)
