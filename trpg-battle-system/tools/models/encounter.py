from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tools.models.encounter_entity import EncounterEntity
from tools.models.map import EncounterMap


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass
class Encounter:
    """单场遭遇战的顶层运行态对象."""

    encounter_id: str
    name: str
    status: str
    round: int
    current_entity_id: str | None
    turn_order: list[str]
    entities: dict[str, EncounterEntity]
    map: EncounterMap
    encounter_notes: list[dict[str, Any]] = field(default_factory=list)
    spell_instances: list[dict[str, Any]] = field(default_factory=list)
    reaction_requests: list[dict[str, Any]] = field(default_factory=list)
    pending_reaction_window: dict[str, Any] | None = None
    pending_movement: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        self.encounter_id = _require_non_empty_string(self.encounter_id, "encounter_id")
        self.name = _require_non_empty_string(self.name, "name")
        self.status = _require_non_empty_string(self.status, "status")
        if not isinstance(self.round, int) or self.round < 1:
            raise ValueError("round must be an integer >= 1")
        if self.current_entity_id is not None:
            self.current_entity_id = _require_non_empty_string(self.current_entity_id, "current_entity_id")
        if not isinstance(self.turn_order, list):
            raise ValueError("turn_order must be a list")
        if not isinstance(self.entities, dict):
            raise ValueError("entities must be a dict")
        if not isinstance(self.map, EncounterMap):
            raise ValueError("map must be an EncounterMap")
        if not isinstance(self.encounter_notes, list):
            raise ValueError("encounter_notes must be a list")
        if not isinstance(self.spell_instances, list):
            raise ValueError("spell_instances must be a list")
        if not isinstance(self.reaction_requests, list):
            raise ValueError("reaction_requests must be a list")
        if self.pending_reaction_window is not None and not isinstance(self.pending_reaction_window, dict):
            raise ValueError("pending_reaction_window must be a dict or None")
        if self.pending_movement is not None and not isinstance(self.pending_movement, dict):
            raise ValueError("pending_movement must be a dict or None")

        # 把嵌套 dict 统一转换成模型对象,保证仓储读出来的数据和内存里
        # 直接构造的数据走同一套校验逻辑.
        normalized_entities: dict[str, EncounterEntity] = {}
        for entity_key, entity_value in self.entities.items():
            if isinstance(entity_value, dict):
                entity = EncounterEntity.from_dict(entity_value)
            elif isinstance(entity_value, EncounterEntity):
                entity = entity_value
            else:
                raise ValueError("entities values must be EncounterEntity or dict")

            # entities 的 key 本身就是 schema 的一部分,必须和内部的
            # entity_id 保持一致,否则后续按 key 查找会出错.
            if entity_key != entity.entity_id:
                raise ValueError(f"entities key '{entity_key}' does not match entity_id '{entity.entity_id}'")
            normalized_entities[entity_key] = entity
        self.entities = normalized_entities

        # turn_order 是回合顺序的唯一事实源,所以这里要提前拦住
        # "引用不存在实体" 和 "重复实体" 两类错误.
        seen_entity_ids: set[str] = set()
        for entity_id in self.turn_order:
            entity_id = _require_non_empty_string(entity_id, "turn_order item")
            if entity_id not in self.entities:
                raise ValueError(f"turn_order contains unknown entity_id '{entity_id}'")
            if entity_id in seen_entity_ids:
                raise ValueError(f"turn_order contains duplicate entity_id '{entity_id}'")
            seen_entity_ids.add(entity_id)

        if self.current_entity_id is not None:
            if self.current_entity_id not in self.entities:
                raise ValueError("current_entity_id must exist in entities")
            if self.current_entity_id not in self.turn_order:
                raise ValueError("current_entity_id must exist in turn_order")

    def to_dict(self) -> dict[str, Any]:
        """把模型序列化回 TinyDB 中保存的 schema 结构."""
        return {
            "encounter_id": self.encounter_id,
            "name": self.name,
            "status": self.status,
            "round": self.round,
            "current_entity_id": self.current_entity_id,
            "turn_order": self.turn_order,
            "entities": {entity_id: entity.to_dict() for entity_id, entity in self.entities.items()},
            "map": self.map.to_dict(),
            "encounter_notes": self.encounter_notes,
            "spell_instances": self.spell_instances,
            "reaction_requests": self.reaction_requests,
            "pending_reaction_window": self.pending_reaction_window,
            "pending_movement": self.pending_movement,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Encounter":
        """先把嵌套字段转成子模型,再构造 Encounter."""
        encounter_data = dict(data)
        encounter_data["entities"] = {
            entity_id: EncounterEntity.from_dict(entity_data)
            for entity_id, entity_data in encounter_data["entities"].items()
        }
        encounter_data["map"] = EncounterMap.from_dict(encounter_data["map"])
        return cls(**encounter_data)
