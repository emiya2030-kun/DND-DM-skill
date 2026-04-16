# Turn Effects 设计说明

## 目标

为战斗系统增加“开始回合 / 结束回合触发效果”的最小运行时模型，让后端能自动处理这几类 DND 场景：

- 回合开始或结束时触发一次伤害
- 回合开始或结束时进行一次豁免
- 豁免成功后移除某个 condition
- 豁免失败后维持原效果

本次只覆盖单实体身上的持续效果，不覆盖区域停留伤害、复杂法术状态机、多目标联动和完整持续时间系统。

---

## 为什么不放进 `conditions`

`conditions` 表示“这个实体当前处于什么状态”，例如：

- `blinded`
- `restrained`
- `exhaustion:2`

但“到了开始/结束回合时要再做什么”不是状态本身，而是一个独立的结算规则。

如果把这类规则硬塞进 `conditions` 字符串，会出现三个问题：

1. condition 既要表达“当前状态”，又要表达“未来触发逻辑”，语义混乱
2. 条件字符串会迅速膨胀，难以解析和维护
3. 以后做区域效果、可解除效果、来源追踪时会反复碰壁

因此本次采用：

- `conditions` 继续只表示当前状态
- `turn_effects` 专门表示开始/结束回合触发的运行时效果

---

## 为什么不放进 `combat_flags`

`combat_flags` 现在承担的是轻量运行标记，例如：

- 是否专注
- 是否击败
- 本回合已花费多少移动力

它适合放简单布尔值和数字，不适合承载一组可触发、可移除、可结算的复杂对象。

`turn_effects` 如果塞进 `combat_flags`，会让 `combat_flags` 失去“轻量标记”的边界，后续阅读和维护都会变差。

---

## 推荐模型

在 `EncounterEntity` 上新增字段：

```json
{
  "turn_effects": []
}
```

每个元素表示一个挂在该实体身上的开始/结束回合效果。

### 最小结构

```json
{
  "effect_id": "effect_hold_person_001",
  "name": "定身术持续效果",
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

### 字段说明

- `effect_id`
  - 单个效果实例 id，用于结果回传和移除
- `name`
  - 给 LLM、日志和调试看的可读名称
- `source_entity_id`
  - 效果来源实体 id
- `source_name`
  - 来源名称，方便结果展示
- `source_type`
  - 当前只做展示和调试，典型值如 `spell`、`feature`
- `source_ref`
  - 来源模板或规则引用，例如 `hold_person`
- `trigger`
  - 只允许 `start_of_turn` 或 `end_of_turn`
- `save`
  - 若存在，表示触发时要做一次豁免
- `on_trigger`
  - 每次触发时必定执行的一段效果
- `on_save_success`
  - 只有存在 `save` 且豁免成功时才执行
- `on_save_failure`
  - 只有存在 `save` 且豁免失败时才执行
- `remove_after_trigger`
  - 触发一次后就移除该 effect

---

## Outcome 结构

`on_trigger`、`on_save_success`、`on_save_failure` 使用同一套最小结构：

```json
{
  "damage_parts": [],
  "apply_conditions": [],
  "remove_conditions": []
}
```

本次故意不加 `note`、区域信息、持续时间递减等字段，保持范围最小。

### 为什么这三个键就够

因为这轮只需要打通战斗内自动结算：

- 伤害：继续走 `damage_parts + ResolveDamageParts`
- condition 变化：继续走 `UpdateConditions`
- 触发完是否消失：由 effect 自己控制

这样可以复用现有战斗基础设施，不需要再造第三套伤害 / 状态系统。

---

## 典型例子

### 1. 回合结束再豁免解除 `paralyzed`

```json
{
  "effect_id": "effect_hold_person_001",
  "name": "定身术持续效果",
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

### 2. 回合结束固定酸伤，触发一次后移除

```json
{
  "effect_id": "effect_melfs_acid_arrow_001",
  "name": "强酸箭残留酸蚀",
  "source_entity_id": "ent_enemy_mage_001",
  "source_name": "法师",
  "source_type": "spell",
  "source_ref": "melfs_acid_arrow",
  "trigger": "end_of_turn",
  "save": null,
  "on_trigger": {
    "damage_parts": [
      {
        "source": "effect:melfs_acid_arrow:end_turn",
        "formula": "2d4",
        "damage_type": "acid"
      }
    ],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "on_save_success": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "on_save_failure": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "remove_after_trigger": true
}
```

---

## 执行流程

### `StartTurn`

`StartTurn` 的职责保持：

1. 确认当前单位
2. 刷新该单位本回合资源
3. 结算该单位身上 `trigger = start_of_turn` 的 `turn_effects`

这样符合用户已确认的语义：

- 回合开始时才重置 action / bonus action / reaction / 移动
- 开始回合触发效果挂在这里，而不是 `AdvanceTurn`

### `EndTurn`

`EndTurn` 的职责变为：

1. 验证当前单位存在
2. 结算该单位身上 `trigger = end_of_turn` 的 `turn_effects`
3. 写入 `turn_ended` 事件

`EndTurn` 仍然不切人、不刷新资源。

### `AdvanceTurn`

`AdvanceTurn` 继续只负责：

- 按先攻顺序切到下一位
- 到队尾时 round +1

它不参与任何开始/结束回合规则结算。

---

## 服务边界

为了不破坏现有分层，本次新增一个 encounter 子模块：

- `tools/services/encounter/turns/turn_effects.py`

它负责：

- 过滤当前 trigger 对应的 effect
- 对每个 effect 执行 `on_trigger`
- 如有 `save`，计算豁免成功/失败
- 执行 `on_save_success` 或 `on_save_failure`
- 根据规则移除 effect 自身
- 返回结构化结算结果

它不会负责：

- 攻击结算
- 地图移动
- 区域持续效果
- 复杂法术状态机

底层复用现有服务：

- 伤害：`ResolveDamageParts` + `UpdateHp`
- condition：`UpdateConditions`

---

## 返回结果

`StartTurn.execute_with_state()` 和 `EndTurn.execute_with_state()` 继续返回：

- `encounter_id`
- `encounter_state`

并追加：

- `turn_effect_resolutions`

每个 resolution 建议至少包含：

```json
{
  "effect_id": "effect_hold_person_001",
  "name": "定身术持续效果",
  "trigger": "end_of_turn",
  "target_entity_id": "ent_ally_milun_001",
  "source_entity_id": "ent_enemy_vampire_mage_001",
  "save": {
    "ability": "wis",
    "dc": 15,
    "total": 16,
    "success": true
  },
  "trigger_damage_resolution": null,
  "success_damage_resolution": null,
  "failure_damage_resolution": null,
  "condition_updates": [],
  "effect_removed": true
}
```

这样 LLM 可以直接拿它做规则判断和 RP 描述，不需要自己再推一遍。

---

## 本次明确不做

- 区域停留伤害
- 多目标持续效果
- 回合数倒计时
- 浓缩失效后自动批量清理所有 effect
- 与地图地形、区域图片、AOE 模板的联动
- 更复杂的“成功则半伤并结束、失败则满伤并附状态两回合”这类状态机

这些都可以在 `turn_effects` 已稳定后继续扩。

---

## 推荐实现顺序

1. 给 `EncounterEntity` 增加 `turn_effects`
2. 写一个最小 `resolve_turn_effects(...)`
3. 在 `StartTurn` / `EndTurn` 接进去
4. 先补两类测试：
   - 回合结束再豁免解除状态
   - 回合结束持续伤害并移除 effect
5. 更新 LLM runtime 文档
