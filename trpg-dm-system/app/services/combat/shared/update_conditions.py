from __future__ import annotations

from typing import Any

from app.models.encounter import Encounter
from app.models.encounter_entity import EncounterEntity
from app.repositories.encounter_repository import EncounterRepository
from app.services.events.append_event import AppendEvent


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
    ) -> dict[str, Any]:
        """执行一次 condition 更新.

        `operation` 目前支持:
        - `apply`
        - `remove`
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        target = self._get_entity_or_raise(encounter, target_id)
        normalized_condition = self._normalize_condition(condition)

        if operation == "apply":
            changed = self._apply_condition(target, normalized_condition)
            event_type = "condition_applied"
        elif operation == "remove":
            changed = self._remove_condition(target, normalized_condition)
            event_type = "condition_removed"
        else:
            raise ValueError("operation must be 'apply' or 'remove'")

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

        return {
            "encounter_id": encounter.encounter_id,
            "target_id": target_id,
            "condition": normalized_condition,
            "operation": operation,
            "changed": changed,
            "conditions_after": list(target.conditions),
            "event_id": event.event_id,
            "event_type": event.event_type,
        }

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

    def _apply_condition(self, target: EncounterEntity, condition: str) -> bool:
        # condition 采用去重列表,避免同一效果重复塞进快照.
        if condition in target.conditions:
            return False
        target.conditions.append(condition)
        return True

    def _remove_condition(self, target: EncounterEntity, condition: str) -> bool:
        if condition not in target.conditions:
            return False
        target.conditions.remove(condition)
        return True
