from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass
class RollResult:
    """本地系统接收到的原始掷骰结果。"""

    request_id: str
    encounter_id: str
    actor_entity_id: str
    roll_type: str
    final_total: int
    dice_rolls: dict[str, Any]
    target_entity_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    rolled_at: str | None = None
    type: str = "roll_result"

    def __post_init__(self) -> None:
        if self.type != "roll_result":
            raise ValueError("type must be 'roll_result'")
        self.request_id = _require_non_empty_string(self.request_id, "request_id")
        self.encounter_id = _require_non_empty_string(self.encounter_id, "encounter_id")
        self.actor_entity_id = _require_non_empty_string(self.actor_entity_id, "actor_entity_id")
        self.roll_type = _require_non_empty_string(self.roll_type, "roll_type")
        # final_total 表示 d20 和各种修正值全部结算后的最终结果。
        if not isinstance(self.final_total, int):
            raise ValueError("final_total must be an integer")
        if not isinstance(self.dice_rolls, dict):
            raise ValueError("dice_rolls must be a dict")
        if self.target_entity_id is not None:
            self.target_entity_id = _require_non_empty_string(self.target_entity_id, "target_entity_id")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        if self.rolled_at is not None and not isinstance(self.rolled_at, str):
            raise ValueError("rolled_at must be a string or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "encounter_id": self.encounter_id,
            "actor_entity_id": self.actor_entity_id,
            "target_entity_id": self.target_entity_id,
            "roll_type": self.roll_type,
            "final_total": self.final_total,
            "dice_rolls": self.dice_rolls,
            "metadata": self.metadata,
            "rolled_at": self.rolled_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RollResult":
        return cls(**data)
