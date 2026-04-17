from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.grapple.shared import release_grapple_if_invalid
from tools.services.combat.rules.conditions import ConditionRuntime, parse_condition
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


@dataclass(frozen=True)
class _ConditionRequest:
    name: str
    raw: str
    source: str | None
    level: int | None
    dynamic: bool = False


class UpdateConditions:
    """给 encounter 中的实体施加或移除 condition."""

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        condition: str,
        operation: str,
        source_entity_id: str | None = None,
        reason: str | None = None,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        """执行一次 condition 更新.

        `operation` 目前支持:
        - `apply`
        - `remove`
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        target = self._get_entity_or_raise(encounter, target_id)
        normalized_condition = self._normalize_condition(condition)
        condition_request = self._build_condition_request(normalized_condition)
        self._normalize_legacy_exhaustion(target)
        runtime = ConditionRuntime(target.conditions)

        if operation == "apply":
            changed = self._apply_condition(target, condition_request, runtime)
            event_type = "condition_applied"
        elif operation == "remove":
            changed = self._remove_condition(target, condition_request, runtime)
            event_type = "condition_removed"
        else:
            raise ValueError("operation must be 'apply' or 'remove'")

        grapple_ids_to_validate: set[str] = set()
        if isinstance(target.combat_flags, dict) and isinstance(target.combat_flags.get("active_grapple"), dict):
            grapple_ids_to_validate.add(target.entity_id)
        if condition_request.name == "grappled" and isinstance(condition_request.source, str):
            grapple_ids_to_validate.add(condition_request.source)
        for grappler_id in grapple_ids_to_validate:
            release_grapple_if_invalid(encounter, grappler_id)

        self.encounter_repository.save(encounter)

        payload = {
            "target_id": target_id,
            "condition": normalized_condition,
            "operation": operation,
            "changed": changed,
            "reason": reason,
            "conditions_after": list(target.conditions),
        }
        event = self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type=event_type,
            actor_entity_id=source_entity_id,
            target_entity_id=target_id,
            payload=payload,
        )

        result = {
            "encounter_id": encounter.encounter_id,
            "target_id": target_id,
            "condition": normalized_condition,
            "operation": operation,
            "changed": changed,
            "conditions_after": list(target.conditions),
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result

    def _build_condition_request(self, normalized_condition: str) -> _ConditionRequest:
        if normalized_condition == "exhaustion":
            return _ConditionRequest(
                name="exhaustion",
                raw=normalized_condition,
                source=None,
                level=None,
                dynamic=True,
            )
        parsed = parse_condition(normalized_condition)
        return _ConditionRequest(
            name=parsed.name,
            raw=normalized_condition,
            source=parsed.source,
            level=parsed.level,
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _normalize_condition(self, condition: str) -> str:
        if not isinstance(condition, str) or not condition.strip():
            raise ValueError("condition must be a non-empty string")
        return condition.strip().lower()

    def _normalize_legacy_exhaustion(self, target: EncounterEntity) -> None:
        normalized: list[str] = []
        changed = False
        for condition in target.conditions:
            if condition == "exhaustion":
                normalized.append("exhaustion:1")
                changed = True
            else:
                normalized.append(condition)
        if changed:
            target.conditions[:] = normalized

    def _apply_condition(
        self,
        target: EncounterEntity,
        request: _ConditionRequest,
        runtime: ConditionRuntime,
    ) -> bool:
        if request.name == "exhaustion":
            return self._apply_exhaustion(target, request, runtime)

        if request.name == "poisoned" and runtime.has("petrified"):
            return False

        if request.raw in target.conditions:
            return False
        target.conditions.append(request.raw)
        return True

    def _apply_exhaustion(
        self,
        target: EncounterEntity,
        request: _ConditionRequest,
        runtime: ConditionRuntime,
    ) -> bool:
        current_level = runtime.exhaustion_level()
        if request.level is not None:
            desired_level = request.level
        else:
            desired_level = current_level + 1
        desired_level = min(desired_level, 6)
        if desired_level == current_level:
            return False

        self._clear_exhaustion_conditions(target)
        target.conditions.append(f"exhaustion:{desired_level}")
        if desired_level == 6:
            target.hp["current"] = 0
            target.combat_flags["is_defeated"] = True
        return True

    def _remove_condition(
        self,
        target: EncounterEntity,
        request: _ConditionRequest,
        runtime: ConditionRuntime,
    ) -> bool:
        if request.name == "exhaustion":
            return self._remove_exhaustion(target, request, runtime)

        if request.raw not in target.conditions:
            return False
        target.conditions.remove(request.raw)
        return True

    def _remove_exhaustion(
        self,
        target: EncounterEntity,
        request: _ConditionRequest,
        runtime: ConditionRuntime,
    ) -> bool:
        if request.level is not None:
            target_condition = f"exhaustion:{request.level}"
            if target_condition not in target.conditions:
                return False
            target.conditions.remove(target_condition)
            return True

        current_level = runtime.exhaustion_level()
        if current_level == 0:
            return False

        self._clear_exhaustion_conditions(target)
        updated_level = current_level - 1
        if updated_level > 0:
            target.conditions.append(f"exhaustion:{updated_level}")
        return True

    def _clear_exhaustion_conditions(self, target: EncounterEntity) -> None:
        target.conditions[:] = [
            condition for condition in target.conditions if not condition.startswith("exhaustion:")
        ]
