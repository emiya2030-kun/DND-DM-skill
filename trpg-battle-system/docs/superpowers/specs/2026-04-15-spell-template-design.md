# Spell Template 设计说明

## 目标

为战斗系统建立一套可扩展的静态法术知识库，让后端和 LLM 都能从统一模板读取：

- 法术基础信息
- 施法目标与结算方式
- 即时伤害 / 即时 condition
- 触发型持续效果模板
- 戏法成长
- 高环施法成长

同时保持运行时与静态知识分离：

- 静态模板回答“这个法术本来是什么”
- 运行时实例回答“这次施法实际给谁挂了什么效果”

---

## 为什么现在要做

当前项目里法术信息主要散落在几个地方：

- `caster.spells`
- `caster.source_ref.spell_definitions`
- `encounter.metadata.spell_definitions`

这能支撑最小豁免法术，但很快会碰到边界：

1. 同一个法术模板会在多个实体上重复复制
2. LLM 读得到即时 outcome，但读不到统一的持续效果模板
3. 回合开始 / 回合结束触发效果没有正式来源
4. 法术成长、附状态、持续效果会继续膨胀成一堆零散字段

因此需要建立独立的法术知识库层。

---

## 设计原则

1. 静态模板与运行时实例分离
2. 一个统一骨架，按能力模块化扩展
3. 实体上只保留轻冗余法术清单，不复制完整模板
4. 即时结算和持续触发都从同一模板出发
5. 本次只覆盖战斗闭环，不做探索 / 社交 / 完整法术百科

---

## 文件位置

### 设计文档

- `docs/superpowers/specs/2026-04-15-spell-template-design.md`

### 静态知识库

- `data/knowledge/spell_definitions.json`

### 读取仓储

- `tools/repositories/spell_definition_repository.py`

### 主要接入服务

- `tools/services/spells/encounter_cast_spell.py`
- `tools/services/combat/save_spell/`
- `tools/services/encounter/turns/`

这样分层的原因很简单：

- `data/db/` 放运行时快照
- `data/knowledge/` 放静态模板知识
- `tools/repositories/` 负责读取知识库
- `tools/services/` 负责实际结算与状态写回

---

## 总体结构

推荐每个法术模板使用统一骨架：

```json
{
  "id": "hold_person",
  "name": "Hold Person",
  "base": {},
  "targeting": {},
  "resolution": {},
  "on_cast": {},
  "effect_templates": {},
  "scaling": {}
}
```

这个骨架是固定的，但每个模块都可以按需裁剪。

为什么不是一个巨型平铺对象：

1. 法术类型差异太大
2. `fireball`、`hold_person`、`hex`、`moonbeam` 不会用到同一组字段
3. 模块化结构更利于 LLM 理解，也更利于后端按阶段结算

---

## 一、`base`

`base` 负责描述法术的静态身份和展示信息。

建议字段：

```json
{
  "id": "hold_person",
  "name": "Hold Person",
  "base": {
    "level": 2,
    "school": "enchantment",
    "casting_time": "1 action",
    "range": "60 feet",
    "components": ["V", "S", "M"],
    "duration": "concentration_up_to_1_minute",
    "concentration": true,
    "description": "Choose a humanoid...",
    "requires_attack_roll": false
  }
}
```

用途：

- 给 LLM 理解法术本体
- 给前端或日志做展示
- 给后端知道是否专注、是否攻击检定

---

## 二、`targeting`

`targeting` 负责描述这个法术怎么选目标。

建议字段：

```json
{
  "targeting": {
    "type": "single_target",
    "allowed_target_types": ["humanoid"],
    "requires_line_of_sight": true,
    "range_feet": 60
  }
}
```

当前最小只需要这些信息。

以后可扩展：

- `area`
- `self`
- `cone`
- `sphere`
- `cube`
- `ally_only`
- `enemy_only`

但这轮不必一次做完。

---

## 三、`resolution`

`resolution` 负责描述施法当下要怎么判定。

推荐字段：

```json
{
  "resolution": {
    "mode": "save",
    "save_ability": "wis",
    "save_dc_mode": "caster_spell_dc",
    "activation": "action"
  }
}
```

这里的 `mode` 目前建议只支持三类：

- `save`
- `attack_roll`
- `no_roll`

为什么只做这三类：

- 已覆盖当前战斗闭环最常见法术
- 能与现有 `ExecuteSaveSpell` 和未来攻击型法术入口对齐
- 不会过早设计复杂状态机

---

## 四、`on_cast`

`on_cast` 负责描述施法当下的即时结果。

对于豁免型法术，推荐使用：

```json
{
  "on_cast": {
    "on_failed_save": {
      "damage_parts": [],
      "apply_conditions": ["paralyzed"],
      "apply_turn_effects": [
        {
          "effect_template_id": "hold_person_repeat_save"
        }
      ],
      "note": null
    },
    "on_successful_save": {
      "damage_parts": [],
      "apply_conditions": [],
      "apply_turn_effects": [],
      "note": null
    }
  }
}
```

对于即时伤害法术，也使用同一骨架：

```json
{
  "on_cast": {
    "on_failed_save": {
      "damage_parts": [
        {
          "source": "spell:fireball:failed:part_0",
          "formula": "8d6",
          "damage_type": "fire"
        }
      ],
      "apply_conditions": [],
      "apply_turn_effects": [],
      "note": null
    },
    "on_successful_save": {
      "damage_parts_mode": "same_as_failed",
      "damage_multiplier": 0.5,
      "apply_conditions": [],
      "apply_turn_effects": [],
      "note": null
    }
  }
}
```

这里的关键点是：

- 即时结算继续复用 `damage_parts`
- condition 继续复用 `UpdateConditions`
- 新增 `apply_turn_effects`，用来把静态效果模板实例化到目标身上

---

## 五、`effect_templates`

这是本轮最关键的新模块。

它负责定义“如果某个法术会留下持续效果，这个持续效果长什么样”。

推荐结构：

```json
{
  "effect_templates": {
    "hold_person_repeat_save": {
      "name": "Hold Person Ongoing Save",
      "trigger": "end_of_turn",
      "save": {
        "ability": "wis",
        "dc_mode": "caster_spell_dc",
        "on_success_remove_effect": true
      },
      "on_trigger": {
        "damage_parts": [],
        "apply_conditions": [],
        "remove_conditions": []
      },
      "on_save_success": {
        "damage_parts": [],
        "apply_conditions": [],
        "remove_conditions": ["paralyzed"]
      },
      "on_save_failure": {
        "damage_parts": [],
        "apply_conditions": [],
        "remove_conditions": []
      },
      "remove_after_trigger": false
    }
  }
}
```

这不会直接挂到实体身上。

真正施法命中后，系统会把它转换成运行时 `turn_effects` 实例，并补上：

- `effect_id`
- `source_entity_id`
- `source_name`
- `source_ref`
- 实际 `dc`

也就是说：

- `effect_templates` 是静态蓝图
- `turn_effects` 是战斗中的实际实例

---

## 六、`scaling`

`scaling` 负责描述成长。

推荐分成两种：

```json
{
  "scaling": {
    "cantrip_by_level": [
      {"caster_level": 5, "replace_formula": "2d8"},
      {"caster_level": 11, "replace_formula": "3d8"},
      {"caster_level": 17, "replace_formula": "4d8"}
    ],
    "slot_level_bonus": {
      "base_slot_level": 3,
      "additional_damage_parts": [
        {
          "source": "spell:fireball:slot_scaling",
          "formula_per_extra_level": "1d6",
          "damage_type": "fire"
        }
      ]
    }
  }
}
```

为什么拆两类：

- 戏法成长看角色等级
- 高环施法看实际施法位

这是 DND 的天然差异，硬压成一类只会更难读。

---

## 七、实体侧法术列表

实体上不应该复制整份模板。

建议 `EncounterEntity.spells` 只保留轻冗余信息：

```json
[
  {
    "spell_id": "hold_person",
    "name": "Hold Person",
    "level": 2
  },
  {
    "spell_id": "fireball",
    "name": "Fireball",
    "level": 3
  }
]
```

必要时允许带少量展示字段，但不复制：

- `on_cast`
- `effect_templates`
- `scaling`

原因：

1. 模板复制会导致版本漂移
2. 后续修一个法术会改很多份
3. LLM 其实主要需要 `spell_id + name`

---

## 八、运行时实例化

当施法命中或豁免失败后，如果 `on_cast` 中含有：

```json
{
  "apply_turn_effects": [
    {
      "effect_template_id": "hold_person_repeat_save"
    }
  ]
}
```

系统会做两步：

1. 从当前法术模板的 `effect_templates` 里取出蓝图
2. 生成挂到目标身上的 `turn_effects` 实例

实例化后的结果大致像这样：

```json
{
  "effect_id": "effect_hold_person_001",
  "name": "Hold Person Ongoing Save",
  "source_entity_id": "ent_enemy_vampire_mage_001",
  "source_name": "吸血鬼法师",
  "source_type": "spell",
  "source_ref": "hold_person",
  "trigger": "end_of_turn",
  "save": {
    "ability": "wis",
    "dc": 15,
    "on_success_remove_effect": true
  },
  "on_trigger": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "on_save_success": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": ["paralyzed"]
  },
  "on_save_failure": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "remove_after_trigger": false
}
```

---

## 九、首批覆盖范围

本轮建议只正式支持 3 类法术模板：

### 1. 即时伤害

例：

- `fireball`
- `burning_hands`

特点：

- 只用 `on_cast`
- 不用 `effect_templates`

### 2. 即时附状态 + 回合末再豁免

例：

- `hold_person`
- `blindness_deafness`

特点：

- `on_cast` 会附状态
- `effect_templates` 会生成持续 effect

### 3. 即时挂持续附伤 / 标记

例：

- `hex`

特点：

- 当下未必直接造成全部效果
- 之后靠运行时 effect 或附伤规则继续生效

这三类足够把知识库骨架跑稳。

---

## 十、本次明确不做

- 完整 SRD / 全量法术收录
- 区域停留伤害模板
- 召唤物完整模板
- `spiritual weapon` 这类半持续半独立实体法术
- 完整 concentration 反向清理所有挂载效果
- 多目标持续效果联动

这些后续都能在同一个骨架上继续扩。

---

## 推荐实施顺序

1. 建 `data/knowledge/spell_definitions.json`
2. 建 `SpellDefinitionRepository`
3. 让 `EncounterCastSpell` 优先从全局知识库读模板
4. 让 `ExecuteSaveSpell` / `SavingThrowResult` 改为从 `on_cast` 读即时效果
5. 新增 `apply_turn_effects` 到目标 `turn_effects`
6. 先补 3 个样例法术：
   - `fireball`
   - `hold_person`
   - `hex`
