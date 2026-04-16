from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_int(value: Any, field_name: str, minimum: int | None = None) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return value


def _require_dict_keys(value: dict[str, Any], field_name: str, keys: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    missing_keys = [key for key in keys if key not in value]
    if missing_keys:
        raise ValueError(f"{field_name} is missing required keys: {', '.join(missing_keys)}")
    return value


@dataclass
class EncounterEntity:
    """遭遇战中的单个运行时实体,用于规则计算、存储和视图投影."""

    # 运行时唯一 id.整个 encounter 内部都靠它定位实体.
    entity_id: str
    # 展示名称,给 LLM、日志和视图层阅读用.
    name: str
    # 阵营归属,例如 ally / enemy / neutral.
    side: str
    # 实体类别,例如 pc / npc / monster / summon.
    category: str
    # 当前由谁控制,例如 player / gm / system.
    controller: str
    # 地图上的格子坐标,作为距离和移动判定的事实源.
    position: dict[str, int]
    # 生命值快照:当前 HP、最大 HP、临时 HP.
    hp: dict[str, int]
    # 最终 AC 数值,攻击命中时直接拿它比较.
    ac: int
    # 速度信息:基础移动力和本回合剩余移动力.
    speed: dict[str, int]
    # 先攻结果,用来决定回合顺序.
    initiative: int
    # 可选的静态模板 id,用来关联角色卡或怪物模板.
    entity_def_id: str | None = None
    # 来源引用信息,可挂角色卡 id、怪物模板 id、施法属性等额外元数据.
    source_ref: dict[str, Any] = field(default_factory=dict)
    # 六维属性原始值,例如 STR 10、DEX 18.
    ability_scores: dict[str, int] = field(default_factory=dict)
    # 六维属性调整值,例如 DEX +4、CHA +3.
    ability_mods: dict[str, int] = field(default_factory=dict)
    # 熟练加值,攻击、豁免、技能等都会复用它.
    proficiency_bonus: int = 0
    # 拥有熟练的豁免列表,例如 ["wis", "cha"].
    save_proficiencies: list[str] = field(default_factory=list)
    # 技能修正值,例如 stealth、arcana 等.
    skill_modifiers: dict[str, int] = field(default_factory=dict)
    # 当前实体身上的标准状态列表,例如 blinded / prone.
    conditions: list[str] = field(default_factory=list)
    # 可消耗资源,例如法术位、职业能力次数、充能等.
    resources: dict[str, Any] = field(default_factory=dict)
    # 动作经济使用情况,例如 action、bonus action、reaction 是否已用.
    action_economy: dict[str, Any] = field(default_factory=dict)
    # 战斗运行标记,例如是否活动、是否倒地、是否专注.
    combat_flags: dict[str, Any] = field(default_factory=dict)
    # 武器清单,攻击请求会从这里读取攻击方式和伤害结构.
    weapons: list[dict[str, Any]] = field(default_factory=list)
    # 法术清单,施法声明、攻击型法术、豁免型法术都会从这里读取.
    spells: list[dict[str, Any]] = field(default_factory=list)
    # 伤害抗性列表,例如 fire、cold.
    resistances: list[str] = field(default_factory=list)
    # 伤害免疫列表.
    immunities: list[str] = field(default_factory=list)
    # 伤害易伤列表.
    vulnerabilities: list[str] = field(default_factory=list)
    # 额外运行时备注,放那些不适合结构化建模的小型说明.
    notes: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entity_id = _require_non_empty_string(self.entity_id, "entity_id")
        self.name = _require_non_empty_string(self.name, "name")
        self.side = _require_non_empty_string(self.side, "side")
        self.category = _require_non_empty_string(self.category, "category")
        self.controller = _require_non_empty_string(self.controller, "controller")

        self.position = _require_dict_keys(self.position, "position", ["x", "y"])
        self.hp = _require_dict_keys(self.hp, "hp", ["current", "max", "temp"])
        self.speed = _require_dict_keys(self.speed, "speed", ["walk", "remaining"])

        # 位置、HP、速度是后续最常被修改的字段,先在这里统一成合法数值,
        # 避免服务层到处写重复的类型保护.
        for key in ("x", "y"):
            self.position[key] = _require_int(self.position[key], f"position.{key}")

        for key in ("current", "max", "temp"):
            self.hp[key] = _require_int(self.hp[key], f"hp.{key}", minimum=0)
        if self.hp["current"] > self.hp["max"]:
            raise ValueError("hp.current cannot be greater than hp.max")

        for key in ("walk", "remaining"):
            self.speed[key] = _require_int(self.speed[key], f"speed.{key}", minimum=0)
        if self.speed["remaining"] > self.speed["walk"]:
            raise ValueError("speed.remaining cannot be greater than speed.walk")

        self.ac = _require_int(self.ac, "ac", minimum=0)
        self.initiative = _require_int(self.initiative, "initiative")
        self.proficiency_bonus = _require_int(self.proficiency_bonus, "proficiency_bonus", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        """返回符合 encounter schema 的普通 dict."""
        return {
            "entity_id": self.entity_id,
            "entity_def_id": self.entity_def_id,
            "source_ref": self.source_ref,
            "name": self.name,
            "side": self.side,
            "category": self.category,
            "controller": self.controller,
            "position": self.position,
            "hp": self.hp,
            "ac": self.ac,
            "speed": self.speed,
            "initiative": self.initiative,
            "ability_scores": self.ability_scores,
            "ability_mods": self.ability_mods,
            "proficiency_bonus": self.proficiency_bonus,
            "save_proficiencies": self.save_proficiencies,
            "skill_modifiers": self.skill_modifiers,
            "conditions": self.conditions,
            "resources": self.resources,
            "action_economy": self.action_economy,
            "combat_flags": self.combat_flags,
            "weapons": self.weapons,
            "spells": self.spells,
            "resistances": self.resistances,
            "immunities": self.immunities,
            "vulnerabilities": self.vulnerabilities,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EncounterEntity":
        return cls(**data)
