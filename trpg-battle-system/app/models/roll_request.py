from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass
class RollRequest:
    """发给平台的掷骰请求."""

    request_id: str
    encounter_id: str
    actor_entity_id: str
    roll_type: str
    formula: str
    target_entity_id: str | None = None
    reason: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    type: str = "request_roll"

    def __post_init__(self) -> None:
        if self.type != "request_roll":
            raise ValueError("type must be 'request_roll'")
        self.request_id = _require_non_empty_string(self.request_id, "request_id")
        self.encounter_id = _require_non_empty_string(self.encounter_id, "encounter_id")
        self.actor_entity_id = _require_non_empty_string(self.actor_entity_id, "actor_entity_id")
        self.roll_type = _require_non_empty_string(self.roll_type, "roll_type")
        self.formula = _require_non_empty_string(self.formula, "formula")
        if self.target_entity_id is not None:
            self.target_entity_id = _require_non_empty_string(self.target_entity_id, "target_entity_id")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        if not isinstance(self.context, dict):
            raise ValueError("context must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "encounter_id": self.encounter_id,
            "actor_entity_id": self.actor_entity_id,
            "target_entity_id": self.target_entity_id,
            "roll_type": self.roll_type,
            "formula": self.formula,
            "reason": self.reason,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RollRequest":
        return cls(**data)
