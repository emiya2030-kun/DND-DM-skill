from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.begin_move_encounter_entity import BeginMoveEncounterEntity
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import (
    DIFFICULT_TERRAIN_TYPE,
    MovementStep,
    MovementValidationResult,
    calculate_step_cost,
    classify_step,
    get_occupied_cells,
)
from tools.services.events.append_event import AppendEvent


class ContinuePendingMovement:
    """在 reaction 窗口处理后继续剩余移动。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event
        self.begin_move_helper = BeginMoveEncounterEntity(repository, append_event)

    def execute_with_state(self, *, encounter_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        pending = self._get_pending_movement_or_raise(encounter)
        request = self._get_request_or_raise(encounter, str(pending["waiting_request_id"]))
        if request.get("status") == "pending":
            request["status"] = "expired"

        mover = encounter.entities.get(str(pending["entity_id"]))
        if mover is None:
            encounter.pending_movement = None
            self.repository.save(encounter)
            return {
                "encounter_id": encounter_id,
                "entity_id": str(pending["entity_id"]),
                "movement_status": "interrupted",
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }
        mover.position = dict(pending["current_position"])

        if self._movement_should_stop(mover):
            encounter.pending_movement = None
            self.repository.save(encounter)
            return {
                "encounter_id": encounter_id,
                "entity_id": mover.entity_id,
                "movement_status": "interrupted",
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }

        movement = self._build_remaining_movement(encounter, mover, pending)
        if not movement.path:
            encounter.pending_movement = None
            self.repository.save(encounter)
            return {
                "encounter_id": encounter_id,
                "entity_id": mover.entity_id,
                "movement_status": "completed",
                "reaction_requests": [],
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }

        ignored_actor_ids = {str(request["actor_entity_id"])}
        next_trigger = self.begin_move_helper._find_first_opportunity_trigger(
            encounter,
            mover,
            movement,
            ignored_actor_entity_ids_for_first_step=ignored_actor_ids,
        )
        if next_trigger is None:
            mover.position = dict(pending["target_position"])
            self.begin_move_helper._apply_movement_progress(
                mover,
                movement.feet_cost,
                bool(pending.get("use_dash")),
                bool(pending.get("count_movement", True)),
            )
            encounter.pending_movement = None
            self.repository.save(encounter)
            return {
                "encounter_id": encounter_id,
                "entity_id": mover.entity_id,
                "movement_status": "completed",
                "reaction_requests": [],
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }

        mover.position = dict(next_trigger["trigger_position"])
        self.begin_move_helper._apply_movement_progress(
            mover,
            int(next_trigger["feet_spent_before_trigger"]),
            bool(pending.get("use_dash")),
            bool(pending.get("count_movement", True)),
        )
        next_request = next_trigger["request"]
        encounter.reaction_requests.append(next_request)
        pending["current_position"] = dict(next_trigger["trigger_position"])
        pending["remaining_path"] = next_trigger["remaining_path"]
        pending["status"] = "waiting_reaction"
        pending["waiting_request_id"] = next_request["request_id"]
        self.repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "entity_id": mover.entity_id,
            "movement_status": "waiting_reaction",
            "reaction_requests": [next_request],
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }

    def _build_remaining_movement(
        self,
        encounter: Encounter,
        mover: EncounterEntity,
        pending: dict[str, Any],
    ) -> MovementValidationResult:
        remaining_path = pending.get("remaining_path", [])
        if not isinstance(remaining_path, list):
            raise ValueError("pending_movement.remaining_path must be a list")

        current_anchor = (mover.position["x"], mover.position["y"])
        steps: list[MovementStep] = []
        total_cost = 0
        diagonal_toggle = 0
        difficult_cells = self._difficult_terrain_cells(encounter)

        previous_cells = get_occupied_cells(mover, {"x": current_anchor[0], "y": current_anchor[1]})
        for raw_anchor in remaining_path:
            if not isinstance(raw_anchor, dict):
                raise ValueError("pending_movement.remaining_path contains invalid anchor")
            next_anchor = {"x": int(raw_anchor["x"]), "y": int(raw_anchor["y"])}
            movement_kind = classify_step(current_anchor, (next_anchor["x"], next_anchor["y"]))
            next_cells = get_occupied_cells(mover, next_anchor)
            entered_cells = next_cells - previous_cells
            step_cost, diagonal_toggle = calculate_step_cost(
                movement_kind,
                diagonal_toggle,
                enters_difficult=any(cell in difficult_cells for cell in entered_cells),
            )
            steps.append(
                MovementStep(
                    anchor=next_anchor,
                    occupied_cells=next_cells,
                    feet_cost=step_cost,
                    movement_kind=movement_kind,
                )
            )
            total_cost += step_cost
            current_anchor = (next_anchor["x"], next_anchor["y"])
            previous_cells = next_cells

        return MovementValidationResult(
            path=steps,
            feet_cost=total_cost,
            used_dash=bool(pending.get("use_dash")),
            movement_counted=bool(pending.get("count_movement", True)),
            blocked_reason=None,
        )

    def _difficult_terrain_cells(self, encounter: Encounter) -> set[tuple[int, int]]:
        return {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if terrain.get("type") == DIFFICULT_TERRAIN_TYPE
            and isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
        }

    def _movement_should_stop(self, mover: EncounterEntity) -> bool:
        if mover.hp["current"] <= 0:
            return True
        if bool(mover.combat_flags.get("is_defeated")):
            return True
        runtime = self.begin_move_helper._safe_condition_runtime(mover.conditions)
        return runtime.has("grappled") or runtime.has("paralyzed") or runtime.has("petrified") or runtime.has(
            "restrained"
        ) or runtime.has("stunned") or runtime.has("unconscious")

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_pending_movement_or_raise(self, encounter: Encounter) -> dict[str, Any]:
        pending = encounter.pending_movement
        if pending is None:
            raise ValueError("pending_movement_not_found")
        if not isinstance(pending, dict):
            raise ValueError("pending_movement_invalid")
        return pending

    def _get_request_or_raise(self, encounter: Encounter, request_id: str) -> dict[str, Any]:
        for request in encounter.reaction_requests:
            if request.get("request_id") == request_id:
                return request
        raise ValueError(f"reaction_request '{request_id}' not found")

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
