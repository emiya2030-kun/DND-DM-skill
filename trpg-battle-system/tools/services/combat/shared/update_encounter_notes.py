from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UpdateEncounterNotes:
    """维护 encounter 级别的特殊持续说明。"""

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event

    def execute(
        self,
        *,
        encounter_id: str,
        action: str,
        note: str | None = None,
        note_id: str | None = None,
        entity_id: str | None = None,
        actor_entity_id: str | None = None,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        """新增、更新或移除 encounter note。"""
        encounter = self._get_encounter_or_raise(encounter_id)

        if action == "add":
            normalized_note = self._normalize_note(note)
            record = {
                "note_id": note_id or self._generate_note_id(),
                "entity_id": entity_id,
                "note": normalized_note,
            }
            encounter.encounter_notes.append(record)
            event_type = "encounter_note_added"
        elif action == "update":
            normalized_note = self._normalize_note(note)
            record = self._get_note_or_raise(encounter, note_id)
            record["note"] = normalized_note
            record["entity_id"] = entity_id
            event_type = "encounter_note_updated"
        elif action == "remove":
            record = self._get_note_or_raise(encounter, note_id)
            encounter.encounter_notes = [
                existing_note
                for existing_note in encounter.encounter_notes
                if existing_note.get("note_id") != record.get("note_id")
            ]
            event_type = "encounter_note_removed"
        else:
            raise ValueError("action must be 'add', 'update', or 'remove'")

        self.encounter_repository.save(encounter)

        payload = {
            "note_id": record.get("note_id"),
            "entity_id": record.get("entity_id"),
            "note": record.get("note"),
            "action": action,
        }
        event = self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type=event_type,
            actor_entity_id=actor_entity_id,
            target_entity_id=entity_id,
            payload=payload,
        )

        result = {
            "encounter_id": encounter.encounter_id,
            "note_id": record.get("note_id"),
            "entity_id": record.get("entity_id"),
            "note": record.get("note"),
            "action": action,
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_note_or_raise(self, encounter: Encounter, note_id: str | None) -> dict[str, Any]:
        if not isinstance(note_id, str) or not note_id.strip():
            raise ValueError("note_id must be a non-empty string")
        for note in encounter.encounter_notes:
            if note.get("note_id") == note_id:
                return note
        raise ValueError(f"note '{note_id}' not found in encounter")

    def _normalize_note(self, note: str | None) -> str:
        if not isinstance(note, str) or not note.strip():
            raise ValueError("note must be a non-empty string")
        return note.strip()

    def _generate_note_id(self) -> str:
        return f"note_{uuid4().hex[:12]}"
