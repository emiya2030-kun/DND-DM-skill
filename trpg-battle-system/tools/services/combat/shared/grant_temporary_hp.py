from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class GrantTemporaryHp:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        temp_hp_amount: int,
        reason: str,
        source_entity_id: str | None = None,
        mode: str = "auto_higher",
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        target = self._get_entity_or_raise(encounter, target_id)

        if not isinstance(temp_hp_amount, int) or temp_hp_amount < 0:
            raise ValueError("temp_hp_amount must be an integer >= 0")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")

        normalized_mode = self._normalize_mode(mode)
        temp_hp_before = int(target.hp.get("temp", 0) or 0)
        current_hp_before = int(target.hp.get("current", 0) or 0)
        temp_hp_after, decision = self._resolve_temp_hp_after(
            temp_hp_before=temp_hp_before,
            temp_hp_amount=temp_hp_amount,
            mode=normalized_mode,
        )
        target.hp["temp"] = temp_hp_after

        self.encounter_repository.save(encounter)

        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="temporary_hp_granted",
            actor_entity_id=source_entity_id,
            target_entity_id=target_id,
            payload={
                "target_id": target_id,
                "source_entity_id": source_entity_id,
                "reason": reason,
                "mode": normalized_mode,
                "temp_hp_amount": temp_hp_amount,
                "temp_hp_before": temp_hp_before,
                "temp_hp_after": temp_hp_after,
                "decision": decision,
                "current_hp_before": current_hp_before,
                "current_hp_after": int(target.hp.get("current", 0) or 0),
            },
        )

        response = {
            "encounter_id": encounter_id,
            "target_id": target_id,
            "event_id": event.event_id,
            "event_type": "temporary_hp_granted",
            "source_entity_id": source_entity_id,
            "reason": reason,
            "mode": normalized_mode,
            "temp_hp_amount": temp_hp_amount,
            "temp_hp_before": temp_hp_before,
            "temp_hp_after": temp_hp_after,
            "decision": decision,
            "current_hp_before": current_hp_before,
            "current_hp_after": int(target.hp.get("current", 0) or 0),
        }
        if include_encounter_state:
            response["encounter_state"] = self.get_encounter_state.execute(encounter_id)
        return response

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

    def _normalize_mode(self, mode: str) -> str:
        normalized_mode = str(mode or "auto_higher").strip().lower()
        if normalized_mode not in {"auto_higher", "keep", "replace"}:
            raise ValueError("mode must be one of: auto_higher, keep, replace")
        return normalized_mode

    def _resolve_temp_hp_after(self, *, temp_hp_before: int, temp_hp_amount: int, mode: str) -> tuple[int, str]:
        if mode == "keep":
            return temp_hp_before, "kept_existing"
        if mode == "replace":
            return temp_hp_amount, "replace"
        if temp_hp_amount > temp_hp_before:
            return temp_hp_amount, "replace"
        return temp_hp_before, "kept_existing"
