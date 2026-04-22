from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import get_monk_runtime
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseStepOfTheWind:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spend_focus: bool = False,
        passenger_id: str | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        monk = get_monk_runtime(actor)
        if not monk:
            raise ValueError("step_of_the_wind_not_available")

        focus_points = monk.get("focus_points")
        if spend_focus:
            if not isinstance(focus_points, dict):
                raise ValueError("step_of_the_wind_requires_focus_points")
            remaining = focus_points.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                raise ValueError("step_of_the_wind_requires_focus_points")
            focus_points["remaining"] = remaining - 1

        actor.action_economy["bonus_action_used"] = True
        actor.action_economy["dash_available"] = int(actor.action_economy.get("dash_available", 0)) + 1
        jump_distance_multiplier = 1
        carried_passenger_id: str | None = None
        if spend_focus:
            add_or_replace_turn_effect(
                actor,
                {
                    "effect_id": f"effect_step_of_the_wind_disengage_{uuid4().hex[:12]}",
                    "effect_type": "disengage",
                    "name": "Step of the Wind",
                    "trigger": "class_feature",
                    "source_ref": "monk:step_of_the_wind",
                    "expires_at": "end_of_current_turn",
                },
            )
            jump_distance_multiplier = 2
            add_or_replace_turn_effect(
                actor,
                {
                    "effect_id": f"effect_step_of_the_wind_jump_{uuid4().hex[:12]}",
                    "effect_type": "jump_distance_multiplier",
                    "name": "Step of the Wind",
                    "trigger": "class_feature",
                    "source_ref": "monk:step_of_the_wind",
                    "expires_at": "end_of_current_turn",
                    "multiplier": jump_distance_multiplier,
                },
            )
            heightened_focus = monk.get("heightened_focus")
            if (
                passenger_id
                and isinstance(heightened_focus, dict)
                and bool(heightened_focus.get("enabled"))
            ):
                passenger = self._get_actor_or_raise(encounter, passenger_id)
                self._ensure_valid_passenger(encounter=encounter, actor=actor, passenger=passenger)
                add_or_replace_turn_effect(
                    passenger,
                    {
                        "effect_id": f"effect_step_of_the_wind_passenger_disengage_{uuid4().hex[:12]}",
                        "effect_type": "disengage",
                        "name": "Step of the Wind",
                        "trigger": "class_feature",
                        "source_ref": "monk:step_of_the_wind",
                        "source_entity_id": actor.entity_id,
                        "expires_at": "end_of_current_turn",
                    },
                )
                carried_passenger_id = passenger.entity_id

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "step_of_the_wind": {
                    "spent_focus": spend_focus,
                    "grants_dash": True,
                    "jump_distance_multiplier": jump_distance_multiplier,
                    "passenger_entity_id": carried_passenger_id,
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

    def _ensure_valid_passenger(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        passenger: EncounterEntity,
    ) -> None:
        if passenger.entity_id == actor.entity_id:
            raise ValueError("step_of_the_wind_passenger_invalid")
        if passenger.side != actor.side:
            raise ValueError("step_of_the_wind_passenger_must_be_ally")
        if passenger.size not in {"tiny", "small", "medium", "large"}:
            raise ValueError("step_of_the_wind_passenger_too_large")

        grid_size = int(encounter.map.grid_size_feet or 5)
        dx = abs(int(actor.position["x"]) - int(passenger.position["x"]))
        dy = abs(int(actor.position["y"]) - int(passenger.position["y"]))
        if max(dx, dy) * grid_size > 5:
            raise ValueError("step_of_the_wind_passenger_not_adjacent")
