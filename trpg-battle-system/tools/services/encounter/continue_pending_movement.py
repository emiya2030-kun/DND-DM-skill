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
        declined_actor_ids: set[str] = set()
        pending_window = encounter.pending_reaction_window
        if isinstance(pending_window, dict) and pending_window.get("status") == "waiting_reaction":
            for group in pending_window.get("choice_groups", []):
                if group.get("status") != "pending":
                    continue
                actor_id = group.get("actor_entity_id")
                if isinstance(actor_id, str):
                    declined_actor_ids.add(actor_id)
                for option in group.get("options", []):
                    if option.get("status") != "pending":
                        continue
                    request_id = option.get("request_id")
                    if isinstance(request_id, str):
                        request = self._get_request_or_raise(encounter, request_id)
                        if request.get("status") == "pending":
                            request["status"] = "declined"
                    option["status"] = "declined"
                group["status"] = "declined"
            pending_window["status"] = "closed"
            encounter.pending_reaction_window = None
        else:
            waiting_request_id = pending.get("waiting_request_id")
            if waiting_request_id:
                request = self._get_request_or_raise(encounter, str(waiting_request_id))
                if request.get("status") == "pending":
                    request["status"] = "declined"
                actor_id = request.get("actor_entity_id")
                if isinstance(actor_id, str):
                    declined_actor_ids.add(actor_id)

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

        ignored_actor_ids = set(declined_actor_ids)
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
        trigger_event = self.begin_move_helper._build_leave_reach_trigger_event(
            movement_id=str(pending.get("movement_id")),
            mover=mover,
            start_position=dict(pending.get("start_position", {})),
            trigger_position=dict(next_trigger["trigger_position"]),
            target_position=dict(pending.get("target_position", {})),
            remaining_path=next_trigger["remaining_path"],
            count_movement=bool(pending.get("count_movement", True)),
            use_dash=bool(pending.get("use_dash")),
            reactor_entity_id=str(next_request["actor_entity_id"]),
            request_payloads={str(next_request["actor_entity_id"]): dict(next_request.get("payload", {}))},
            request_overrides={str(next_request["actor_entity_id"]): dict(next_request)},
        )
        window_result = self.begin_move_helper.open_reaction_window.execute(
            encounter_id=encounter_id,
            trigger_event=trigger_event,
        )
        if window_result["status"] != "waiting_reaction":
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
        encounter.pending_reaction_window = window_result["pending_reaction_window"]
        encounter.reaction_requests.extend(window_result["reaction_requests"])
        request_id = None
        if window_result["reaction_requests"]:
            request_id = window_result["reaction_requests"][0].get("request_id")
        pending["current_position"] = dict(next_trigger["trigger_position"])
        pending["remaining_path"] = next_trigger["remaining_path"]
        pending["status"] = "waiting_reaction"
        pending["waiting_request_id"] = request_id
        self.repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "entity_id": mover.entity_id,
            "movement_status": "waiting_reaction",
            "reaction_requests": window_result["reaction_requests"],
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
