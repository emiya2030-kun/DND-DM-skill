from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass
class Event:
    """追加式战斗事件记录."""

    event_id: str
    encounter_id: str
    round: int
    event_type: str
    actor_entity_id: str | None = None
    target_entity_id: str | None = None
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def __post_init__(self) -> None:
        self.event_id = _require_non_empty_string(self.event_id, "event_id")
        self.encounter_id = _require_non_empty_string(self.encounter_id, "encounter_id")
        self.event_type = _require_non_empty_string(self.event_type, "event_type")
        if not isinstance(self.round, int) or self.round < 1:
            raise ValueError("round must be an integer >= 1")
        if self.actor_entity_id is not None:
            self.actor_entity_id = _require_non_empty_string(self.actor_entity_id, "actor_entity_id")
        if self.target_entity_id is not None:
            self.target_entity_id = _require_non_empty_string(self.target_entity_id, "target_entity_id")
        if self.request_id is not None:
            self.request_id = _require_non_empty_string(self.request_id, "request_id")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        if self.created_at is not None and not isinstance(self.created_at, str):
            raise ValueError("created_at must be a string or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "encounter_id": self.encounter_id,
            "round": self.round,
            "event_type": self.event_type,
            "actor_entity_id": self.actor_entity_id,
            "target_entity_id": self.target_entity_id,
            "request_id": self.request_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(**data)
