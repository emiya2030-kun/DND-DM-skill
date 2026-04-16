# ExecuteSpell 统一法术战斗入口设计

## 目标

为战斗中的法术施放补齐一条统一闭环：

1. LLM 声明施法意图
2. 后端校验这次施法是否合法
3. 后端按统一入口结算法术效果
4. 结果立即投影到 `encounter_state` 与 battlemap

本轮只覆盖三类最小可用法术：

- 攻击型法术：如 `Eldritch Blast`
- 豁免伤害型法术：如 `Fireball`
- 豁免 + condition 型法术：如 `Hold Person`

后续再扩展更多法术模板，但本次先把统一骨架打通。

## 非目标

本轮不做：

- 战斗外施法完整流程
- 全量官方法术覆盖
- 复杂多阶段法术
- 召唤系完整运行时
- 法术按钮/UI 交互重构

## 总体结构

统一入口拆成两层：

1. `SpellRequest`
   - 只负责合法性校验与标准化
   - 不直接扣 HP，不直接上 condition
2. `ExecuteSpell`
   - 吃 `SpellRequest` 的标准化结果
   - 执行攻击、豁免、伤害、condition、专注实例创建

这样可以把“能不能施放”和“施放后发生什么”严格分开。

## 一、SpellRequest

### 输入

```python
{
  "encounter_id": str,
  "actor_id": str,
  "spell_id": str,
  "cast_level": int,
  "target_entity_ids": list[str] | None,
  "target_point": {"x": int, "y": int} | None,
  "declared_action_cost": str | None,
  "context": dict[str, Any] | None,
}
```

### 校验顺序

1. encounter 与 actor 是否存在
2. actor 是否拥有该法术
3. actor 当前状态是否允许施法
   - 如 `incapacitated / paralyzed / unconscious`
4. `cast_level` 是否合法
5. 法术位是否足够
6. 动作经济是否允许
7. 目标声明是否合法
8. 目标类型是否合法
9. 距离是否合法
10. 专注替换是否合法

### 升环施法

`SpellRequest` 必须在校验阶段直接处理升环施法，不允许留给 `ExecuteSpell` 临时猜。

#### 1. 戏法

- `base_level == 0`
- `cast_level` 必须等于 `0`
- 戏法成长不看法术位，只看施法者等级档位

#### 2. 非戏法，且不可升环

- `cast_level` 必须等于 `base_level`
- 若玩家声明更高环，本次直接报错

#### 3. 可升环法术

- `cast_level >= base_level`
- 检查对应法术位剩余次数
- 计算：

```python
upcast_delta = cast_level - base_level
```

### 支持的升环类型

本轮只支持三类升环：

1. 额外伤害骰
   - 例：`Fireball`
2. 额外目标数
   - 例：`Hold Person`
3. 持续时间变化
   - 例：`Hex`

### 标准化输出

成功时返回：

```python
{
  "ok": True,
  "actor_id": "ent_ally_wizard_001",
  "spell_id": "fireball",
  "base_level": 3,
  "cast_level": 5,
  "upcast_delta": 2,
  "is_cantrip": False,
  "action_cost": "action",
  "target_entity_ids": [],
  "target_point": {"x": 10, "y": 12},
  "requires_concentration": False,
  "will_replace_concentration": False,
  "scaling_mode": "slot",
  "resolved_scaling": {
    "extra_damage_parts": [
      {"formula": "2d6", "damage_type": "fire"}
    ]
  },
  "spell_definition": {...}
}
```

失败时返回：

```python
{
  "ok": False,
  "error_code": "spell_slot_insufficient",
  "message": "3环法术位不足"
}
```

## 二、ExecuteSpell

### 职责

`ExecuteSpell` 只吃校验通过后的标准化请求。

它负责：

1. 消耗动作经济
2. 消耗法术位
3. 分发到对应结算类型
4. 更新 encounter
5. 返回统一结果 + `encounter_state`

### 三类结算模式

#### 1. 攻击型法术

例：`Eldritch Blast`

流程：

1. 生成攻击请求
2. 比较命中
3. 命中后结算伤害
4. 将结果写回 `UpdateHp`

#### 2. 豁免伤害型法术

例：`Fireball`

流程：

1. 计算区域内目标
2. 对每个目标生成豁免请求
3. 成功/失败分别结算伤害
4. 伤害统一走 `UpdateHp`

#### 3. 豁免 + condition 型法术

例：`Hold Person`

流程：

1. 对目标进行豁免
2. 失败则附加 condition
3. 若法术需要持续，则创建 `spell_instance`
4. 并把持续性豁免写成 `turn_effect`

## 三、知识库字段

法术定义需要支持以下最小字段：

```json
{
  "id": "hold_person",
  "name": "定身类人",
  "base_level": 2,
  "casting_time": "action",
  "range_feet": 60,
  "targeting": {
    "mode": "entities",
    "target_type": "humanoid",
    "max_targets": 1
  },
  "resolution_mode": "save_condition",
  "save": {
    "ability": "wis"
  },
  "on_failed_save": {
    "apply_conditions": ["paralyzed"]
  },
  "concentration": {
    "required": true
  },
  "scaling": {
    "mode": "slot",
    "per_slot_above_base": {
      "extra_targets": 1
    }
  }
}
```

### Fireball 示例

```json
{
  "id": "fireball",
  "name": "火球术",
  "base_level": 3,
  "casting_time": "action",
  "range_feet": 150,
  "targeting": {
    "mode": "point",
    "shape": "sphere",
    "radius_feet": 20
  },
  "resolution_mode": "save_damage",
  "save": {
    "ability": "dex"
  },
  "damage_parts": [
    {"formula": "8d6", "damage_type": "fire"}
  ],
  "save_damage_mode": "half_on_success",
  "scaling": {
    "mode": "slot",
    "per_slot_above_base": {
      "extra_damage_parts": [
        {"formula": "1d6", "damage_type": "fire"}
      ]
    }
  }
}
```

### Hex 示例

```json
{
  "id": "hex",
  "name": "脆弱诅咒",
  "base_level": 1,
  "casting_time": "bonus_action",
  "range_feet": 90,
  "targeting": {
    "mode": "entities",
    "target_type": "creature",
    "max_targets": 1
  },
  "resolution_mode": "apply_spell_instance",
  "concentration": {
    "required": true
  },
  "special_runtime": {
    "retarget_available": true
  },
  "attack_bonus_damage_parts": [
    {"formula": "1d6", "damage_type": "necrotic"}
  ],
  "scaling": {
    "mode": "slot",
    "duration_by_cast_level": {
      "1": "1 hour",
      "2": "4 hours",
      "3": "8 hours",
      "4": "8 hours",
      "5": "24 hours"
    }
  }
}
```

## 四、状态更新

所有即时伤害必须仍然统一走 `UpdateHp`。

所有持续法术必须写入现有：

- `spell_instances`
- `turn_effects`

这样可以复用现有：

- 专注终止
- ongoing effect 展示
- `get_encounter_state` 投影
- battlemap 角色卡显示

## 五、返回结果

`ExecuteSpell` 返回结构统一为：

```python
{
  "encounter_id": str,
  "spell_id": str,
  "actor_id": str,
  "cast_level": int,
  "resolution_mode": str,
  "spell_resolution": {...},
  "resource_update": {...},
  "encounter_state": {...},
}
```

## 六、实施顺序

第一阶段先打通最小闭环：

1. `SpellRequest`
2. `ExecuteSpell`
3. `Fireball`
4. `Hold Person`
5. `Eldritch Blast`

其中：

- `Fireball` 覆盖区域 + 豁免 + 伤害 + 升环伤害
- `Hold Person` 覆盖目标合法性 + 豁免 + condition + 专注 + 升环目标数
- `Eldritch Blast` 覆盖攻击型法术 + 戏法等级成长

## 七、成功标准

满足以下条件即视为本轮完成：

1. LLM 可以用统一入口声明这三类法术
2. 后端能严格校验施法合法性
3. 升环施法能在请求阶段被正确解析
4. 结果能正确更新 HP / condition / spell_instance
5. 页面和 `get_encounter_state` 能立即反映结果
