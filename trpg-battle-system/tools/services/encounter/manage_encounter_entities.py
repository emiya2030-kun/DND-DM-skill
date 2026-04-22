from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.map import EncounterMap
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.entity_definition_repository import EntityDefinitionRepository
from tools.services.characters.player_character_builder import PlayerCharacterBuilder
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns import AdvanceTurn, EndTurn, StartTurn


class EncounterService:
    """本地 encounter 管理服务，负责实体维护和回合推进。"""

    def __init__(
        self,
        repository: EncounterRepository,
        entity_definition_repository: EntityDefinitionRepository | None = None,
    ):
        self.repository = repository
        self.entity_definition_repository = entity_definition_repository or EntityDefinitionRepository()
        self.player_character_builder = PlayerCharacterBuilder()

    def create_encounter(self, encounter: Encounter) -> Encounter:
        """创建并保存一场新的 encounter。"""
        return self.repository.save(encounter)

    def create_encounter_with_state(self, encounter: Encounter) -> dict[str, object]:
        saved = self.create_encounter(encounter)
        return self._build_state_response(saved.encounter_id)

    def initialize_encounter(
        self,
        encounter_id: str,
        *,
        map_setup: dict[str, Any],
        entity_setups: list[dict[str, Any]],
    ) -> Encounter:
        encounter = self._get_encounter_or_raise(encounter_id)

        encounter.map = EncounterMap(
            map_id=str(map_setup["map_id"]),
            name=str(map_setup["name"]),
            description=str(map_setup.get("description", "")),
            width=int(map_setup["width"]),
            height=int(map_setup["height"]),
            grid_size_feet=int(map_setup.get("grid_size_feet", 5)),
            terrain=list(map_setup.get("terrain", [])),
            auras=list(map_setup.get("auras", [])),
            zones=list(map_setup.get("zones", [])),
            remains=list(map_setup.get("remains", [])),
        )

        initialized_entities: dict[str, EncounterEntity] = {}
        for entity_setup in entity_setups:
            entity = self._build_entity_from_template(entity_setup)
            self._validate_position_within_map(encounter, entity.position["x"], entity.position["y"])
            initialized_entities[entity.entity_id] = entity

        encounter.entities = initialized_entities
        encounter.turn_order = []
        encounter.current_entity_id = None
        encounter.round = 1
        encounter.reaction_requests = []
        encounter.pending_movement = None
        encounter.spell_instances = []
        encounter.encounter_notes = list(map_setup.get("battlemap_details", []))

        return self.repository.save(encounter)

    def initialize_encounter_with_state(
        self,
        encounter_id: str,
        *,
        map_setup: dict[str, Any],
        entity_setups: list[dict[str, Any]],
    ) -> dict[str, object]:
        updated = self.initialize_encounter(
            encounter_id,
            map_setup=map_setup,
            entity_setups=entity_setups,
        )
        return {
            "encounter_id": updated.encounter_id,
            "status": "initialized",
            "initialized_entities": list(updated.entities.keys()),
            "map_summary": {
                "map_id": updated.map.map_id,
                "name": updated.map.name,
                "width": updated.map.width,
                "height": updated.map.height,
            },
            "encounter_state": GetEncounterState(self.repository).execute(updated.encounter_id),
        }

    def get_encounter(self, encounter_id: str) -> Encounter:
        """读取 encounter，不存在时直接抛错，方便上层少写空值判断。"""
        return self._get_encounter_or_raise(encounter_id)

    def add_entity(
        self,
        encounter_id: str,
        entity: EncounterEntity,
        add_to_turn_order: bool = False,
        make_current_if_empty: bool = True,
    ) -> Encounter:
        """向 encounter 中加入一个实体。"""
        encounter = self._get_encounter_or_raise(encounter_id)

        if entity.entity_id in encounter.entities:
            raise ValueError(f"entity '{entity.entity_id}' already exists in encounter")

        self._validate_position_within_map(encounter, entity.position["x"], entity.position["y"])
        encounter.entities[entity.entity_id] = entity

        if add_to_turn_order:
            encounter.turn_order.append(entity.entity_id)

        if make_current_if_empty and encounter.current_entity_id is None and encounter.turn_order:
            encounter.current_entity_id = encounter.turn_order[0]

        return self.repository.save(encounter)

    def add_entity_with_state(
        self,
        encounter_id: str,
        entity: EncounterEntity,
        add_to_turn_order: bool = False,
        make_current_if_empty: bool = True,
    ) -> dict[str, object]:
        updated = self.add_entity(
            encounter_id,
            entity,
            add_to_turn_order=add_to_turn_order,
            make_current_if_empty=make_current_if_empty,
        )
        return self._build_state_response(updated.encounter_id)

    def remove_entity(self, encounter_id: str, entity_id: str) -> Encounter:
        """从 encounter 中移除实体，并同步清理 turn_order / current_entity_id。"""
        encounter = self._get_encounter_or_raise(encounter_id)
        self._get_entity_or_raise(encounter, entity_id)

        del encounter.entities[entity_id]
        encounter.turn_order = [current_id for current_id in encounter.turn_order if current_id != entity_id]

        if encounter.current_entity_id == entity_id:
            encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None

        return self.repository.save(encounter)

    def remove_entity_with_state(self, encounter_id: str, entity_id: str) -> dict[str, object]:
        updated = self.remove_entity(encounter_id, entity_id)
        return self._build_state_response(updated.encounter_id)

    def set_turn_order(self, encounter_id: str, turn_order: list[str]) -> Encounter:
        """设置回合顺序，只允许使用当前 encounter 中已存在的实体。"""
        encounter = self._get_encounter_or_raise(encounter_id)

        seen_ids: set[str] = set()
        for entity_id in turn_order:
            if entity_id not in encounter.entities:
                raise ValueError(f"turn_order contains unknown entity_id '{entity_id}'")
            if entity_id in seen_ids:
                raise ValueError(f"turn_order contains duplicate entity_id '{entity_id}'")
            seen_ids.add(entity_id)

        encounter.turn_order = list(turn_order)

        # 如果原 current_entity_id 已经不在新顺序中，自动回退到第一个；
        # 没有顺序则清空当前行动者。
        if encounter.current_entity_id not in encounter.turn_order:
            encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None

        return self.repository.save(encounter)

    def set_turn_order_with_state(self, encounter_id: str, turn_order: list[str]) -> dict[str, object]:
        updated = self.set_turn_order(encounter_id, turn_order)
        return self._build_state_response(updated.encounter_id)

    def set_current_entity(self, encounter_id: str, entity_id: str | None) -> Encounter:
        """显式设置当前行动者。"""
        encounter = self._get_encounter_or_raise(encounter_id)

        if entity_id is None:
            encounter.current_entity_id = None
            return self.repository.save(encounter)

        self._get_entity_or_raise(encounter, entity_id)
        if entity_id not in encounter.turn_order:
            raise ValueError("current_entity_id must exist in turn_order")

        encounter.current_entity_id = entity_id
        return self.repository.save(encounter)

    def set_current_entity_with_state(self, encounter_id: str, entity_id: str | None) -> dict[str, object]:
        updated = self.set_current_entity(encounter_id, entity_id)
        return self._build_state_response(updated.encounter_id)

    def advance_turn(self, encounter_id: str) -> Encounter:
        """推进到下一个行动者，并通过 turn engine 统一重置回合资源。"""
        return AdvanceTurn(self.repository).execute(encounter_id)

    def advance_turn_with_state(self, encounter_id: str) -> dict[str, object]:
        return AdvanceTurn(self.repository).execute_with_state(encounter_id)

    def start_turn(self, encounter_id: str) -> Encounter:
        """开始当前行动者的回合，并统一刷新回合资源。"""
        return StartTurn(self.repository).execute(encounter_id)

    def start_turn_with_state(self, encounter_id: str) -> dict[str, object]:
        return StartTurn(self.repository).execute_with_state(encounter_id)

    def end_turn(self, encounter_id: str) -> Encounter:
        """结束当前行动者的回合，不推进先攻也不刷新下一位资源。"""
        return EndTurn(self.repository).execute(encounter_id)

    def end_turn_with_state(self, encounter_id: str) -> dict[str, object]:
        return EndTurn(self.repository).execute_with_state(encounter_id)

    def update_entity_position(self, encounter_id: str, entity_id: str, x: int, y: int) -> Encounter:
        """更新实体坐标，并保证不会移动到地图边界之外。"""
        encounter = self._get_encounter_or_raise(encounter_id)
        entity = self._get_entity_or_raise(encounter, entity_id)

        self._validate_position_within_map(encounter, x, y)
        entity.position["x"] = x
        entity.position["y"] = y

        return self.repository.save(encounter)

    def update_entity_position_with_state(self, encounter_id: str, entity_id: str, x: int, y: int) -> dict[str, object]:
        updated = self.update_entity_position(encounter_id, entity_id, x, y)
        return self._build_state_response(updated.encounter_id)

    def update_entity_hp(
        self,
        encounter_id: str,
        entity_id: str,
        *,
        current_hp: int | None = None,
        max_hp: int | None = None,
        temp_hp: int | None = None,
    ) -> Encounter:
        """更新实体 HP 相关字段，并保证不会写入明显非法的数值。"""
        encounter = self._get_encounter_or_raise(encounter_id)
        entity = self._get_entity_or_raise(encounter, entity_id)

        new_max_hp = entity.hp["max"] if max_hp is None else max_hp
        new_temp_hp = entity.hp["temp"] if temp_hp is None else temp_hp
        new_current_hp = entity.hp["current"] if current_hp is None else current_hp

        if not isinstance(new_max_hp, int) or new_max_hp < 0:
            raise ValueError("max_hp must be an integer >= 0")
        if not isinstance(new_temp_hp, int) or new_temp_hp < 0:
            raise ValueError("temp_hp must be an integer >= 0")
        if not isinstance(new_current_hp, int) or new_current_hp < 0:
            raise ValueError("current_hp must be an integer >= 0")
        if new_current_hp > new_max_hp:
            raise ValueError("current_hp cannot be greater than max_hp")

        entity.hp["max"] = new_max_hp
        entity.hp["temp"] = new_temp_hp
        entity.hp["current"] = new_current_hp

        return self.repository.save(encounter)

    def update_entity_hp_with_state(
        self,
        encounter_id: str,
        entity_id: str,
        *,
        current_hp: int | None = None,
        max_hp: int | None = None,
        temp_hp: int | None = None,
    ) -> dict[str, object]:
        updated = self.update_entity_hp(
            encounter_id,
            entity_id,
            current_hp=current_hp,
            max_hp=max_hp,
            temp_hp=temp_hp,
        )
        return self._build_state_response(updated.encounter_id)

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _validate_position_within_map(self, encounter: Encounter, x: int, y: int) -> None:
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("position must use integer coordinates")
        if x < 1 or y < 1:
            raise ValueError("position must be inside map bounds")
        if x > encounter.map.width or y > encounter.map.height:
            raise ValueError("position must be inside map bounds")

    def _build_state_response(self, encounter_id: str) -> dict[str, object]:
        return {
            "encounter_id": encounter_id,
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }

    def _build_entity_from_template(self, entity_setup: dict[str, Any]) -> EncounterEntity:
        template_ref = entity_setup.get("template_ref")
        if not isinstance(template_ref, dict):
            raise ValueError("entity_setup.template_ref must be a dict")

        template_id = template_ref.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("template_ref.template_id must be a non-empty string")

        template = self.entity_definition_repository.get(template_id)
        if template is None:
            raise ValueError(f"entity template '{template_id}' not found")

        runtime_overrides = entity_setup.get("runtime_overrides", {})
        if not isinstance(runtime_overrides, dict):
            raise ValueError("entity_setup.runtime_overrides must be a dict")

        payload = deepcopy(template)
        payload["entity_id"] = str(entity_setup["entity_instance_id"])
        payload["entity_def_id"] = str(template.get("entity_def_id") or template_id)

        source_ref = payload.get("source_ref")
        if not isinstance(source_ref, dict):
            source_ref = {}
        source_ref["source_type"] = template_ref.get("source_type")
        source_ref["template_id"] = template_id
        payload["source_ref"] = source_ref

        self._deep_merge(payload, runtime_overrides)
        if template_ref.get("source_type") == "pc" and isinstance(payload.get("character_build"), dict):
            return self.player_character_builder.build(
                template=payload,
                entity_id=str(entity_setup["entity_instance_id"]),
            )
        return EncounterEntity.from_dict(payload)

    def _deep_merge(self, base: dict[str, Any], overrides: dict[str, Any]) -> None:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)
