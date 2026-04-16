# Encounter Schema

> 运行时给 LLM 的统一操作说明请优先查看 [`docs/llm-runtime-tool-guide.md`](./llm-runtime-tool-guide.md)。本文件主要定义数据结构与状态投影，不承担完整运行流程说明。

## 目录

- [目标](#目标)
- [设计原则](#设计原则)
- [核心对象](#核心对象)
  - [1. Encounter](#1-encounter)
  - [2. Encounter Entity](#2-encounter-entity)
  - [3. Map](#3-map)
  - [4. Roll Request](#4-roll-request)
  - [5. Roll Result](#5-roll-result)
  - [6. Event](#6-event)
- [存储层 vs 视图层](#存储层-vs-视图层)
  - [存储层](#存储层)
  - [视图层](#视图层)
- [`get_encounter_state` 推荐返回结构](#get_encounter_state-推荐返回结构)
  - [`current_turn_entity`](#current_turn_entity)
  - [`turn_order`](#turn_order)
  - [`battlemap_details`](#battlemap_details)
- [命名建议](#命名建议)
  - [ID 命名](#id-命名)
  - [状态命名](#状态命名)
- [最小落地顺序](#最小落地顺序)

## 目标

这份文档定义 TRPG DM 系统的核心数据契约，作为后续重写 `combat_manager.py`、补测试、完善本地执行流程时的统一依据。

当前结论：

- 内部主键统一使用 `entity_id`，不再使用 `name` 作为唯一标识。
- 持久化层保存结构化、可计算的数据。
- 面向 LLM 或前端的 `get_encounter_state` 返回值是视图层，可以在查询时格式化。
- `current_turn_entity`、`turn_order` 这类视图字段由 encounter 运行态动态展开，不作为唯一事实源。

## 设计原则

1. `entity_id` 是运行时唯一标识。
2. `entity_def_id` 指向静态定义，可选。
3. `name` 仅用于展示，不参与主键判断。
4. 所有数值字段在存储层尽量保持数值类型，不保存 `"80 / 80 HP"` 这类展示字符串。
5. 事件日志记录战斗过程；encounter 状态只保存当前结果。日志只追加，不回头改旧记录。
6. API 视图允许冗余，但底层存储尽量规范化。

## 内部 Service Tool 约定

当前项目里的内部 tool 统一落在 `tools.services` 下，以可直接实例化并调用 `.execute(...)` 的 service class 形式存在。

当前已稳定的 encounter 相关内部 tool 包括：

- `EncounterService`
  - 管理实体增删、基础坐标更新、回合推进
- `GetEncounterState`
  - 把 encounter 运行态投影成只读视图
- `MoveEncounterEntity`
  - 执行带规则校验的移动
  - 读取并写回 encounter
  - 校验体型占格、逐步路径、墙体、困难地形、同伴/敌人占位、斜线移动消耗
  - 当注入 `AppendEvent` 时追加 `movement_resolved` 事件

## 核心对象

### 1. Encounter

遭遇战运行态顶层对象。

```json
{
  "encounter_id": "enc_day1_iron_duster",
  "name": "Iron Duster Ambush",
  "status": "active",
  "round": 1,
  "current_entity_id": "ent_pc_eric_001",
  "turn_order": [
    "ent_pc_eric_001",
    "ent_enemy_iron_duster_001",
    "ent_enemy_hellhound_001"
  ],
  "entities": {
    "ent_pc_eric_001": {},
    "ent_enemy_iron_duster_001": {}
  },
  "map": {},
  "encounter_notes": [],
  "created_at": "2026-04-13T12:00:00+09:00",
  "updated_at": "2026-04-13T12:00:00+09:00"
}
```

#### Encounter 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `encounter_id` | `string` | 是 | 遭遇战唯一标识 |
| `name` | `string` | 是 | 遭遇战显示名 |
| `status` | `string` | 是 | `pending` / `active` / `paused` / `completed` |
| `round` | `integer` | 是 | 当前轮次，从 `1` 开始 |
| `current_entity_id` | `string \| null` | 是 | 当前行动者，对应 `turn_order` 中当前轮到的实体 |
| `turn_order` | `string[]` | 是 | 仅保存 `entity_id` 列表 |
| `entities` | `object` | 是 | `entity_id -> encounter_entity` |
| `map` | `object` | 是 | 地图与环境信息 |
| `encounter_notes` | `array` | 否 | 特殊战场笔记 |
| `created_at` | `string` | 否 | ISO 8601 时间 |
| `updated_at` | `string` | 否 | ISO 8601 时间 |

### 2. Encounter Entity

遭遇战中的单个运行时实体。这个对象是所有规则计算的核心。

```json
{
  "entity_id": "ent_pc_eric_001",
  "entity_def_id": "pc_eric_lv5",
  "source_ref": {
    "character_id": "pc_eric_001",
    "spellcasting_ability": "cha"
  },
  "name": "Eric",
  "side": "ally",
  "category": "pc",
  "controller": "player",
  "position": {
    "x": 15,
    "y": 19
  },
  "hp": {
    "current": 80,
    "max": 80,
    "temp": 0
  },
  "ac": 16,
  "speed": {
    "walk": 30,
    "remaining": 30
  },
  "initiative": 14,
  "size": "medium",
  "ability_scores": {
    "str": 10,
    "dex": 18,
    "con": 12,
    "int": 14,
    "wis": 10,
    "cha": 16
  },
  "ability_mods": {
    "str": 0,
    "dex": 4,
    "con": 1,
    "int": 2,
    "wis": 0,
    "cha": 3
  },
  "proficiency_bonus": 3,
  "save_proficiencies": [
    "wis",
    "cha"
  ],
  "skill_modifiers": {
    "arcana": 5,
    "deception": 6,
    "stealth": 7
  },
  "conditions": [],
  "resources": {
    "spell_slots": {
      "1": {
        "max": 4,
        "remaining": 2
      },
      "2": {
        "max": 3,
        "remaining": 1
      }
    },
    "feature_uses": {
      "action_surge": {
        "max": 1,
        "remaining": 1
      }
    }
  },
  "action_economy": {
    "action_used": false,
    "bonus_action_used": false,
    "reaction_used": false,
    "free_interaction_used": false
  },
  "combat_flags": {
    "is_active": true,
    "is_defeated": false,
    "is_concentrating": false
  },
  "weapons": [],
  "spells": [],
  "resistances": [],
  "immunities": [],
  "vulnerabilities": [],
  "notes": []
}
```

#### Entity 最低必需字段

后续实现至少应保证这些字段一定存在：

- `entity_id`
- `name`
- `side`
- `category`
- `controller`
- `position`
- `hp`
- `ac`
- `speed`
- `initiative`
- `size`
- `conditions`
- `resources`
- `action_economy`

#### Entity 字段约束

| 字段 | 类型 | 说明 |
|---|---|---|
| `entity_id` | `string` | 运行态唯一 ID |
| `entity_def_id` | `string \| null` | 静态模板 ID，可选 |
| `source_ref` | `object` | 外部来源引用，可包含 `character_id`、`monster_id`、本地模板 ID 等；如果该实体要参与施法 DC 计算，当前应至少提供 `spellcasting_ability` |
| `side` | `string` | `ally` / `enemy` / `neutral` / `summon` |
| `category` | `string` | `pc` / `npc` / `monster` / `summon` / `hazard` |
| `controller` | `string` | `player` / `gm` / `system` |
| `position` | `object` | `{ "x": int, "y": int }` |
| `hp` | `object` | `{ "current": int, "max": int, "temp": int }` |
| `ac` | `integer` | 最终 AC 数值 |
| `speed` | `object` | `{ "walk": int, "remaining": int }`，单位为英尺 |
| `initiative` | `integer` | 先攻结果 |
| `size` | `string` | `tiny` / `small` / `medium` / `large` / `huge` / `gargantuan`；决定占格大小，默认 `medium` |
| `ability_scores` | `object` | 六维属性原始值 |
| `ability_mods` | `object` | 六维属性修正值 |
| `save_proficiencies` | `string[]` | 豁免熟练 |
| `skill_modifiers` | `object` | 技能名到修正值 |
| `conditions` | `array` | 标准状态或系统状态 |
| `resources` | `object` | 法术位、职业资源、限次能力 |
| `action_economy` | `object` | 回合内动作消耗状态 |
| `combat_flags` | `object` | 是否活动、是否被击败、是否专注 |
| `weapons` | `array` | 可选，攻击可用武器清单 |
| `spells` | `array` | 可选，法术清单 |
| `notes` | `array` | 非标准说明 |

#### `source_ref` 当前建议最小结构

`source_ref` 本质上是运行时引用和补充元数据容器。当前战斗链路里，已经实际会读这些字段：

| 字段 | 类型 | 用途 |
|---|---|---|
| `character_id` | `string` | 关联本地角色卡或上层角色定义 |
| `monster_id` | `string` | 关联怪物模板定义 |
| `spellcasting_ability` | `string` | 施法属性，例如 `str` / `dex` / `con` / `int` / `wis` / `cha`；当法术没有显式写死 `save_dc` 时，系统会用它来计算 `8 + 熟练加值 + 施法属性调整值` |

如果一个实体不会施法，`spellcasting_ability` 可以不填。

如果一个实体要参与豁免型法术结算，当前最低建议准备这些字段：

- `source_ref.spellcasting_ability`
- `ability_mods`
- `proficiency_bonus`
- `spells`

如果一个实体要作为豁免目标被系统自动计算豁免总值，当前最低建议准备这些字段：

- `ability_mods`
- `proficiency_bonus`
- `save_proficiencies`

### 3. Map

```json
{
  "map_id": "map_factory_floor_01",
  "name": "Factory Floor",
  "description": "A metal floor with narrow walkways and furnace vents.",
  "width": 30,
  "height": 30,
  "grid_size_feet": 5,
  "terrain": [
    {
      "terrain_id": "ter_wall_001",
      "type": "wall",
      "x": 10,
      "y": 8,
      "blocks_movement": true,
      "blocks_los": true
    }
  ],
  "auras": [],
  "zones": []
}
```

#### Map 原则

- 地图只描述环境，不存单位。
- 单位位置全部保存在 `entities[*].position`。
- `terrain`、`auras`、`zones` 可被规则系统读取。

### 4. Roll Request

这是本地规则流程里生成的掷骰请求，不直接等于最终事件。

```json
{
  "type": "request_roll",
  "request_id": "req_attack_001",
  "encounter_id": "enc_day1_iron_duster",
  "actor_entity_id": "ent_pc_eric_001",
  "target_entity_id": "ent_enemy_iron_duster_001",
  "roll_type": "spell_attack",
  "formula": "1d20+7",
  "reason": "Eldritch Blast attack roll",
  "context": {
    "target_ac": 16,
    "ability": "cha",
    "proficiency_applied": true,
    "spell_id": "eldritch_blast",
    "action_cost": "action"
  }
}
```

#### `roll_type` 建议枚举

- `attack_roll`
- `spell_attack`
- `saving_throw`
- `ability_check`
- `damage_roll`
- `initiative`

### 5. Roll Result

这是系统接收到的原始掷骰结果。结果本身不负责改状态，只负责提供事实。

```json
{
  "type": "roll_result",
  "request_id": "req_attack_001",
  "encounter_id": "enc_day1_iron_duster",
  "actor_entity_id": "ent_pc_eric_001",
  "target_entity_id": "ent_enemy_iron_duster_001",
  "roll_type": "spell_attack",
  "final_total": 10,
  "dice_rolls": {
    "base_rolls": [3],
    "modifier": 4,
    "proficiency": 3,
    "other_bonus": 0
  },
  "metadata": {
    "advantage_state": "normal",
    "is_critical_hit": false,
    "is_critical_fail": false
  },
  "rolled_at": "2026-04-13T12:03:00+09:00"
}
```

#### Roll Result 原则

- `roll_result` 是原始反馈，不混入叙述文本。
- 命中与否可以即时判断，但建议单独沉淀为事件。
- 若结果里已经给出拆解明细，系统不再二次推导原始骰面。

### 6. Event

Event 是真正的行为记录，供回放、审计、摘要生成使用。

```json
{
  "event_id": "evt_20260413_0001",
  "encounter_id": "enc_day1_iron_duster",
  "round": 1,
  "event_type": "attack_resolved",
  "actor_entity_id": "ent_pc_eric_001",
  "target_entity_id": "ent_enemy_iron_duster_001",
  "request_id": "req_attack_001",
  "payload": {
    "roll_type": "spell_attack",
    "attack_total": 10,
    "target_ac": 16,
    "hit": false,
    "damage": [],
    "hp_before": 45,
    "hp_after": 45
  },
  "created_at": "2026-04-13T12:03:01+09:00"
}
```

#### `event_type` 建议枚举

- `turn_started`
- `turn_ended`
- `movement_resolved`
- `attack_declared`
- `attack_resolved`
- `spell_declared`
- `spell_resolved`
- `damage_applied`
- `healing_applied`
- `condition_applied`
- `condition_removed`
- `resource_spent`
- `entity_added`
- `entity_removed`
- `encounter_note_added`

## 存储层 vs 视图层

### 存储层

用于持久化、规则计算、事件回放。要求：

- 字段稳定
- 类型严格
- 方便比较与计算

例如：

```json
{
  "hp": {
    "current": 80,
    "max": 80,
    "temp": 0
  }
}
```

### 视图层

用于 `get_encounter_state` 或 LLM 消费，可更友好。

例如：

```json
{
  "hp": "80 / 80 HP",
  "position": "(15, 19)",
  "movement_remaining": "30 feet"
}
```

建议把 `get_encounter_state` 定义为“从 encounter 运行态投影出来的只读视图”，不要把视图对象原样写回数据库。

## `get_encounter_state` 推荐返回结构

```json
{
  "encounter_id": "enc_day1_iron_duster",
  "round": 1,
  "current_turn_entity": {},
  "turn_order": [],
  "battlemap_details": {},
  "encounter_notes": []
}
```

### `current_turn_entity`

这是从 `entities[current_entity_id]` 投影出来的展示对象，是 `get_encounter_state` 最重要的部分。

它面向 LLM 和前端消费，可以保留用户友好的文本字段，但底层仍然应从结构化存储推导。

推荐示例：

```json
{
  "id": "ent_ally_eric_001",
  "name": "Eric",
  "level": 5,
  "hp": "80 / 80 HP",
  "class": "Pureblood Vampire Warlock",
  "description": "A composed vampire warlock who prefers precise ranged pressure and tactical repositioning.",
  "position": "(15, 19)",
  "movement_remaining": "30 feet",
  "ac": 16,
  "speed": 30,
  "spell_save_dc": 15,
  "available_actions": {
    "weapons": [],
    "spells": [],
    "spell_slots_available": {
      "1": 2,
      "2": 1
    }
  },
  "weapon_ranges": {
    "max_melee_range": "5 ft",
    "max_ranged_range": "120 ft",
    "targets_within_melee_range": [],
    "targets_within_ranged_range": [
      {
        "entity_id": "ent_enemy_iron_duster_001",
        "name": "Iron Duster",
        "distance": "15 ft"
      }
    ]
  },
  "conditions": "No active conditions.",
  "resources": "Warlock Spell Slots: 1st 2/4, 2nd 1/3"
}
```

#### `current_turn_entity` 字段建议

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `string` | 当前行动实体的 `entity_id` |
| `name` | `string` | 展示名称 |
| `level` | `integer \| null` | 角色等级或挑战等级，可选 |
| `hp` | `string` | 展示文本，例如 `"80 / 80 HP"` |
| `class` | `string \| null` | 角色职业或怪物分类展示 |
| `description` | `string \| null` | 角色描述、背景或简要说明 |
| `position` | `string` | 展示文本，例如 `"(15, 19)"` |
| `movement_remaining` | `string` | 展示文本，例如 `"30 feet"` |
| `ac` | `integer` | 护甲等级 |
| `speed` | `integer` | 基础移动速度 |
| `spell_save_dc` | `integer \| null` | 若可施法则提供 |
| `available_actions` | `object` | 当前可用武器、法术、法术位 |
| `weapon_ranges` | `object` | 近战/远程有效范围与可选目标 |
| `conditions` | `string \| array` | 视图层可返回文本，也可返回结构化数组 |
| `resources` | `string \| object` | 视图层可返回摘要文本，也可返回结构化资源 |

#### `available_actions`

建议把“当前回合实体可做什么”集中放在这里，至少包含以下字段：

- `weapons`
- `spells`
- `spell_slots_available`

##### `available_actions.weapons`

推荐按“当前装备可用武器”返回列表。每项建议包含：

- `slot`
- `weapon_id`
- `name`
- `damage`
- `properties`
- `bonus`
- `note`

示例：

```json
[
  {
    "slot": "right_hand",
    "weapon_id": "wpn_infernal_rapier",
    "name": "Infernal Rapier",
    "damage": "1d8 Slashing + 1d8 Fire",
    "properties": [
      "Finesse",
      "Magic"
    ],
    "bonus": "+1 attack, +1 damage",
    "note": "Counts as a magical weapon."
  }
]
```

##### `available_actions.spells`

推荐按法术等级分组返回，便于前端直接渲染法术列表。

示例：

```json
{
  "cantrips": [
    {
      "id": "eldritch_blast",
      "name": "Eldritch Blast",
      "description": "A beam of crackling energy streaks toward a creature within range.",
      "damage": [
        {
          "formula": "1d10",
          "type": "force"
        }
      ],
      "requires_attack_roll": true,
      "at_higher_levels": "Creates additional beams at higher character levels."
    }
  ],
  "level_1_spells": [
    {
      "id": "hex",
      "name": "Hex",
      "description": "Place a curse on a creature, dealing extra necrotic damage on hits.",
      "damage": [
        {
          "formula": "1d6",
          "type": "necrotic"
        }
      ],
      "requires_attack_roll": false,
      "at_higher_levels": null
    }
  ]
}
```

##### `available_actions.spell_slots_available`

建议保留轻量视图，按等级返回剩余法术位数量：

```json
{
  "1": 2,
  "2": 1
}
```

#### `weapon_ranges`

这是对当前实体攻击范围的即时投影，供 LLM 判断是否需要近战移动、远程攻击或目标选择。

建议包含：

- `max_melee_range`
- `max_ranged_range`
- `targets_within_melee_range`
- `targets_within_ranged_range`

其中目标项建议至少包含：

- `entity_id`
- `name`
- `distance`

#### `conditions` 和 `resources`

你刚补充的信息更偏视图层展示，所以这里建议兼容两种返回方式：

- 简洁模式：直接返回字符串，方便 LLM 阅读
- 结构化模式：返回数组或对象，方便程序继续处理

例如：

```json
{
  "conditions": "Blinded, Prone",
  "resources": "Warlock Spell Slots: 2/4, Eldritch Invocations: 3/3"
}
```

或者：

```json
{
  "conditions": [
    "blinded",
    "prone"
  ],
  "resources": {
    "warlock_spell_slots": {
      "max": 4,
      "remaining": 2
    },
    "eldritch_invocations": {
      "max": 3,
      "remaining": 3
    }
  }
}
```

#### 存储映射建议

以下字段建议由底层 encounter entity 投影而来：

- `id` <- `entity_id`
- `hp` <- `hp.current` + `hp.max`
- `position` <- `position.x` + `position.y`
- `movement_remaining` <- `speed.remaining`
- `ac` <- `ac`
- `speed` <- `speed.walk`
- `conditions` <- `conditions`
- `resources` <- `resources`
- `available_actions` <- `weapons` + `spells` + `resources.spell_slots`

`current_turn_entity` 的选择来源于 encounter 顶层的 `current_entity_id`。

### `turn_order`

这是一个排序后的视图数组，每个元素至少包含：

- `id`
- `name`
- `type`
- `hp`
- `ac`
- `position`
- `distance_from_current_turn_entity`

### `battlemap_details`

从 `map` 投影而来，保留：

- `name`
- `description`
- `dimensions`
- `grid_size`

## 命名建议

### ID 命名

- `encounter_id`: `enc_<chapter>_<slug>`
- `entity_id`: `ent_<side>_<slug>_<seq>`
- `event_id`: `evt_<timestamp>_<seq>`
- `request_id`: `req_<action>_<seq>`

### 状态命名

标准条件尽量使用 5e 规则名称，内部可以统一英文 key，视图层再翻译。

例如：

- 存储：`["blinded", "prone"]`
- 展示：`"Blinded, Prone"` 或 `"目盲, 倒地"`

## 最小落地顺序

如果你后面要重写 `combat_manager.py`，建议按这个顺序：

1. 先把 encounter 顶层结构和 `entities` 字典定下来。
2. 再实现 `get_encounter_state` 的只读投影。
3. 再补 `request_roll -> roll_result -> event` 的处理链。
4. 最后再做动作经济、条件系统、法术资源这些规则层细节。
