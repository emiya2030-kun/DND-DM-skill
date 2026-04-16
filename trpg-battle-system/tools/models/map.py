from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


@dataclass
class EncounterMap:
    """战场地图元数据,不包含实体位置."""

    map_id: str
    name: str
    description: str
    width: int
    height: int
    grid_size_feet: int = 5
    terrain: list[dict[str, Any]] = field(default_factory=list)
    auras: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    remains: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.map_id = _require_non_empty_string(self.map_id, "map_id")
        self.name = _require_non_empty_string(self.name, "name")
        if not isinstance(self.description, str):
            raise ValueError("description must be a string")
        self.width = _require_positive_int(self.width, "width")
        self.height = _require_positive_int(self.height, "height")
        self.grid_size_feet = _require_positive_int(self.grid_size_feet, "grid_size_feet")

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.map_id,
            "name": self.name,
            "description": self.description,
            "width": self.width,
            "height": self.height,
            "grid_size_feet": self.grid_size_feet,
            "terrain": self.terrain,
            "auras": self.auras,
            "zones": self.zones,
            "remains": self.remains,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EncounterMap":
        return cls(**data)
