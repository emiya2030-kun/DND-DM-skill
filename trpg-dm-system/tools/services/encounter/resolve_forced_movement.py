from __future__ import annotations

from typing import Any

from tools.models import Encounter, EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.movement_rules import get_occupied_cells
from tools.services.events.append_event import AppendEvent


class ResolveForcedMovement:
    """处理不消耗移动力、不中断为借机攻击的强制位移。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event

    def execute(
        self,
        *,
        encounter_id: str,
        entity_id: str,
        path: list[dict[str, int]],
        reason: str,
        source_entity_id: str | None = None,
    ) -> dict[str, Any]:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        if not isinstance(path, list):
            raise ValueError("invalid_forced_movement_path")

        start_position = {"x": entity.position["x"], "y": entity.position["y"]}
        attempted_path: list[dict[str, int]] = []
        resolved_path: list[dict[str, int]] = []
        blocked = False
        block_reason: str | None = None

        for anchor in path:
            next_anchor = self._normalize_anchor(anchor)
            attempted_path.append(next_anchor)
            step_block_reason = self._get_block_reason(encounter, entity, next_anchor)
            if step_block_reason is not None:
                blocked = True
                block_reason = step_block_reason
                break
            entity.position = {"x": next_anchor["x"], "y": next_anchor["y"]}
            resolved_path.append(next_anchor)

        self.repository.save(encounter)
        result = {
            "encounter_id": encounter_id,
            "entity_id": entity_id,
            "start_position": start_position,
            "final_position": {"x": entity.position["x"], "y": entity.position["y"]},
            "attempted_path": attempted_path,
            "resolved_path": resolved_path,
            "moved_feet": len(resolved_path) * 5,
            "stopped_early": blocked,
            "blocked": blocked,
            "block_reason": block_reason,
            "reason": reason,
            "source_entity_id": source_entity_id,
        }
        self._append_forced_movement_event(
            encounter=encounter,
            source_entity_id=source_entity_id,
            target_entity_id=entity_id,
            result=result,
        )
        return result

    def _normalize_anchor(self, anchor: Any) -> dict[str, int]:
        if not isinstance(anchor, dict) or "x" not in anchor or "y" not in anchor:
            raise ValueError("invalid_forced_movement_path")
        x = anchor["x"]
        y = anchor["y"]
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("invalid_forced_movement_path")
        return {"x": x, "y": y}

    def _get_block_reason(
        self,
        encounter: Encounter,
        mover: EncounterEntity,
        anchor: dict[str, int],
    ) -> str | None:
        occupied_cells = get_occupied_cells(mover, anchor)
        if not self._cells_within_map(encounter, occupied_cells):
            return "out_of_bounds"
        if self._cells_hit_wall(encounter, occupied_cells):
            return "wall"
        if not self._is_occupancy_legal(encounter, mover, occupied_cells):
            return "occupied_tile"
        return None

    def _cells_within_map(self, encounter: Encounter, cells: set[tuple[int, int]]) -> bool:
        return all(1 <= x <= encounter.map.width and 1 <= y <= encounter.map.height for x, y in cells)

    def _cells_hit_wall(self, encounter: Encounter, cells: set[tuple[int, int]]) -> bool:
        wall_cells = {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if terrain.get("type") == "wall"
            and isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
        }
        return any(cell in wall_cells for cell in cells)

    def _is_occupancy_legal(
        self,
        encounter: Encounter,
        mover: EncounterEntity,
        cells: set[tuple[int, int]],
    ) -> bool:
        for entity in encounter.entities.values():
            if entity.entity_id == mover.entity_id:
                continue
            if get_occupied_cells(entity) & cells:
                return False
        return True

    def _append_forced_movement_event(
        self,
        *,
        encounter: Encounter,
        source_entity_id: str | None,
        target_entity_id: str,
        result: dict[str, Any],
    ) -> None:
        if self.append_event is None:
            return
        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="forced_movement_resolved",
            actor_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            payload={
                "reason": result["reason"],
                "source_entity_id": result["source_entity_id"],
                "from_position": result["start_position"],
                "to_position": result["final_position"],
                "attempted_path": result["attempted_path"],
                "resolved_path": result["resolved_path"],
                "moved_feet": result["moved_feet"],
                "blocked": result["blocked"],
                "block_reason": result["block_reason"],
            },
        )
