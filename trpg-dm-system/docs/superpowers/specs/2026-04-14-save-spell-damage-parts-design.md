# Save Spell Damage Parts 设计说明

## 目标

把当前“豁免型法术用总伤害值结算”的旧模式，推进到和武器攻击一致的结构化伤害模式：

- 法术模板定义 `damage_parts`
- 外部 / LLM 按 `source` 传 `damage_rolls`
- 系统内部统一调用 `ResolveDamageParts`
- 系统根据豁免成功 / 失败选择对应 outcome
- 系统自动应用伤害、condition、note
- 返回结构化 `damage_resolution` 给 LLM，用于规则与 RP

这次只覆盖：

- 单目标豁免型法术
- 一次即时结算
- 伤害段
- 成功 / 失败分支
- 条件字符串结果
- 戏法成长
- 高环施法成长

明确不覆盖：

- 攻击型法术
- 持续伤害
- 区域停留伤害
- 回合结束 / 回合开始再触发
- condition 的持续时间、来源解除、重复豁免细则
- 浓缩中断以外的复杂法术状态机

## 为什么要做

当前豁免型法术链仍然依赖：

- `hp_change_on_failed_save`
- `hp_change_on_success`
- `damage_type`

这种模式有三个问题：

1. 系统看不到法术伤害是怎么组成的
2. LLM 拿不到可叙述的逐段伤害 breakdown
3. 戏法成长、高环成长、多段伤害、成功无伤、失败附状态这些场景会越来越难扩展

武器攻击链已经接入 `damage_parts + ResolveDamageParts`。豁免型法术应复用同一套底层规则，而不是继续维护另一套总伤害逻辑。

## 方案比较

### 方案 A：只把总伤害换成结构化伤害，condition 继续维持旧分支

做法：

- `hp_change_on_failed_save` / `hp_change_on_success` 改成结构化伤害
- `conditions_on_failed_save` / `conditions_on_success` 继续单独作为输入

优点：

- 改动最小
- 能较快复用 `ResolveDamageParts`

缺点：

- 豁免型法术结果仍是半结构化
- 伤害和 condition 仍然是两套割裂模型
- 高环成长和戏法成长表达会开始散乱

结论：

- 不推荐

### 方案 B：引入 `failed_save_outcome / successful_save_outcome`

做法：

- 法术模板统一定义两套结果分支
- 每个 outcome 可以包含：
  - `damage_parts`
  - `conditions`
  - `note`
  - 伤害倍率 / 复用规则
- `SavingThrowResult` 只负责“选中 outcome 并执行”

优点：

- 最贴近 DND 豁免法术真实结构
- 能自然表达：
  - 失败全伤 / 成功半伤
  - 失败全伤 / 成功无伤
  - 失败无伤害但附状态
  - 失败伤害 + 状态 / 成功部分伤害
- 最容易继续接戏法成长和高环成长

缺点：

- 需要对法术模板和 `SavingThrowResult` 做一次较完整改造

结论：

- 推荐

### 方案 C：把豁免法术也硬塞成单一路径

做法：

- 不区分成功 / 失败 outcome
- 全靠额外字段描述“成功半伤”“成功无伤”“失败附状态”

优点：

- 表面上更统一

缺点：

- 真实语义不自然
- 越往后越难维护

结论：

- 不推荐

## 推荐方案

采用方案 B：

- 建立全局法术模板知识库
- 模板中定义 `failed_save_outcome` 和 `successful_save_outcome`
- 实体身上只保留轻冗余法术列表
- 豁免型法术入口继续用 `ExecuteSaveSpell`
- 即时结算仍由 `SavingThrowResult` 编排
- 伤害统一走 `ResolveDamageParts`
- condition 统一走现有 `UpdateConditions`

## 数据模型

### 一、全局法术模板知识库

法术模板作为唯一事实源，负责描述“这个法术本来是什么、怎么结算”。

建议顶层结构：

```json
{
  "spell_definitions": {
    "fireball": {
      "id": "fireball",
      "name": "Fireball",
      "level": 3,
      "school": "evocation",
      "casting_time": "1 action",
      "range": "150 feet",
      "components": ["V", "S", "M"],
      "duration": "instantaneous",
      "description": "A bright streak flashes...",
      "requires_attack_roll": false,
      "save_ability": "dex",
      "failed_save_outcome": {
        "damage_parts": [
          {
            "source": "spell:fireball:failed:part_0",
            "formula": "8d6",
            "damage_type": "fire"
          }
        ],
        "conditions": [],
        "note": null
      },
      "successful_save_outcome": {
        "damage_parts_mode": "same_as_failed",
        "damage_multiplier": 0.5,
        "conditions": [],
        "note": null
      },
      "scaling": {
        "cantrip_by_level": null,
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
  }
}
```

### 二、实体持有法术列表

实体上只保留“我会什么”的轻冗余信息，方便 LLM 阅读与前端展示。

建议结构：

```json
{
  "spells": {
    "cantrips": [
      {
        "spell_id": "sacred_flame",
        "name": "Sacred Flame"
      }
    ],
    "level_1_spells": {
      "slots_available": 4,
      "spells": [
        {
          "spell_id": "burning_hands",
          "name": "Burning Hands"
        }
      ]
    },
    "level_3_spells": {
      "slots_available": 2,
      "spells": [
        {
          "spell_id": "fireball",
          "name": "Fireball"
        }
      ]
    }
  }
}
```

实体侧允许保留：

- `spell_id`
- `name`
- 必要时的少量展示字段

但不复制完整 outcome / scaling 模板。

### 三、法术 outcome 模型

`failed_save_outcome` 与 `successful_save_outcome` 是本轮核心。

每个 outcome 当前支持：

- `damage_parts`
- `damage_parts_mode`
- `damage_multiplier`
- `conditions`
- `note`

规则：

- `damage_parts`
  - 直接定义该 outcome 自己的伤害段
- `damage_parts_mode = "same_as_failed"`
  - 表示成功 outcome 复用失败 outcome 的伤害段
- `damage_multiplier`
  - 表示在结构化伤害结算后再按倍率修正
  - 本轮典型值：
    - `1.0`
    - `0.5`
    - `0`
- `conditions`
  - 本轮只存字符串，例如 `["blinded"]`
- `note`
  - outcome 命中后要追加的即时说明

### 四、戏法成长与高环成长

#### 戏法成长

示例：

```json
{
  "id": "sacred_flame",
  "name": "Sacred Flame",
  "level": 0,
  "requires_attack_roll": false,
  "save_ability": "dex",
  "failed_save_outcome": {
    "damage_parts": [
      {
        "source": "spell:sacred_flame:failed:part_0",
        "formula": "1d8",
        "damage_type": "radiant"
      }
    ],
    "conditions": [],
    "note": null
  },
  "successful_save_outcome": {
    "damage_parts": [],
    "conditions": [],
    "note": null
  },
  "scaling": {
    "cantrip_by_level": [
      {"caster_level": 5, "replace_formula": "2d8"},
      {"caster_level": 11, "replace_formula": "3d8"},
      {"caster_level": 17, "replace_formula": "4d8"}
    ],
    "slot_level_bonus": null
  }
}
```

#### 高环成长

示例：

```json
{
  "id": "fireball",
  "name": "Fireball",
  "level": 3,
  "failed_save_outcome": {
    "damage_parts": [
      {
        "source": "spell:fireball:failed:part_0",
        "formula": "8d6",
        "damage_type": "fire"
      }
    ],
    "conditions": [],
    "note": null
  },
  "successful_save_outcome": {
    "damage_parts_mode": "same_as_failed",
    "damage_multiplier": 0.5,
    "conditions": [],
    "note": null
  },
  "scaling": {
    "cantrip_by_level": null,
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

说明：

- 每高于基础环位一级，额外追加一段或多段伤害
- 这些追加段与基础伤害一起进入 `ResolveDamageParts`

## 运行时输入模型

### ExecuteSaveSpell 新输入

当前旧输入：

- `hp_change_on_failed_save`
- `hp_change_on_success`
- `damage_reason`
- `damage_type`

建议逐步迁移为：

```json
{
  "encounter_id": "enc_001",
  "target_id": "ent_enemy_001",
  "spell_id": "fireball",
  "cast_level": 3,
  "base_roll": 9,
  "damage_rolls": [
    {
      "source": "spell:fireball:failed:part_0",
      "rolls": [6, 5, 3, 4, 2, 1, 6, 4]
    }
  ]
}
```

原则：

- 伤害骰仍由外部 / LLM 提供
- 但只按 `source` 提供，不再手传总伤害值
- 系统根据豁免结果选择应用哪个 outcome

### 为什么只传一份 `damage_rolls`

因为豁免型法术常见模式里：

- 成功半伤与失败全伤共用同一批骰子
- 成功无伤直接跳过伤害结算
- 失败附状态无需伤害骰

所以一份 `damage_rolls` 足够，没必要把 `failed_save` / `successful_save` 各传一份。

## Service 设计

### ExecuteSaveSpell

继续保持“完整单目标豁免型法术入口”的职责：

1. 声明施法并扣资源
2. 生成豁免请求
3. 计算豁免结果
4. 调用 `SavingThrowResult` 做即时 outcome 结算

建议新输入新增：

- `damage_rolls: list[dict[str, Any]] | None = None`

旧的 `hp_change_on_failed_save` / `hp_change_on_success` 先保留兼容，但新主路径不再依赖它们。

### SavingThrowResult

从“吃两个整数伤害值”升级为“根据 outcome 执行完整即时结算”。

新职责：

1. 判断豁免成功 / 失败
2. 记录 `saving_throw_resolved`
3. 选择 `failed_save_outcome` 或 `successful_save_outcome`
4. 应用成长规则，生成本次实际 `damage_parts`
5. 如果有伤害：
   - 调 `ResolveDamageParts`
   - 再调 `UpdateHp`
6. 如果有 `conditions`：
   - 自动调 `UpdateConditions`
7. 如果有 `note`：
   - 自动调 `UpdateEncounterNotes`

边界仍然是：

- `SavingThrowResult` 决定“这次 outcome 要做什么”
- `UpdateHp` / `UpdateConditions` / `UpdateEncounterNotes` 负责真正落库

### UpdateConditions

本轮不新造 service，继续复用现有：

- `tools/services/combat/shared/update_conditions.py`

使用方式：

- `SavingThrowResult` 选中 outcome 后，遍历 `conditions`
- 对每个 condition 自动调用一次 `UpdateConditions.execute(...)`
- `condition_updates` 只是把这些结果回传给 LLM，不让 LLM 自己手动维护状态

## 执行流程

推荐数据流：

1. `EncounterCastSpell`
2. `SavingThrowRequest`
3. `ResolveSavingThrow`
4. `SavingThrowResult`
   - 读取法术模板
   - 判定成功 / 失败
   - 选中 outcome
   - 应用成长
   - 解析 outcome 伤害与状态
   - 触发后续更新

### 成功半伤示例：Fireball

- 失败 outcome：`8d6 fire`
- 成功 outcome：`same_as_failed + damage_multiplier = 0.5`

流程：

- 外部传一份 `8d6` 的骰子
- 如果豁免失败：
  - 全额进入 `ResolveDamageParts`
- 如果豁免成功：
  - 同一份骰子先正常结算
  - 再在 outcome 层做半伤

### 成功无伤示例：Sacred Flame

- 失败 outcome：`Xd8 radiant`
- 成功 outcome：空伤害

流程：

- 先根据施法者等级应用戏法成长
- 失败才需要消费 `damage_rolls`
- 成功直接跳过伤害结算

### 失败附状态示例

```json
{
  "failed_save_outcome": {
    "damage_parts": [],
    "conditions": ["blinded"],
    "note": "强光使目标暂时失明"
  },
  "successful_save_outcome": {
    "damage_parts": [],
    "conditions": [],
    "note": null
  }
}
```

流程：

- 失败时不上伤害，但自动调用 `UpdateConditions`
- 成功时无变化

### 失败伤害 + 状态示例

```json
{
  "failed_save_outcome": {
    "damage_parts": [
      {
        "source": "spell:frost_burst:failed:part_0",
        "formula": "3d6",
        "damage_type": "cold"
      }
    ],
    "conditions": ["restrained"],
    "note": "寒霜冻结了目标行动"
  },
  "successful_save_outcome": {
    "damage_parts_mode": "same_as_failed",
    "damage_multiplier": 0.5,
    "conditions": [],
    "note": null
  }
}
```

## 返回结构

建议保持和攻击链相近：

```json
{
  "resolution": {
    "success": false,
    "failed": true,
    "selected_outcome": "failed_save",
    "damage_resolution": {
      "is_critical_hit": false,
      "parts": [
        {
          "source": "spell:fireball:failed:part_0",
          "formula": "8d6",
          "resolved_formula": "8d6",
          "damage_type": "fire",
          "rolled_total": 27,
          "adjusted_total": 27,
          "adjustment_rule": "normal"
        }
      ],
      "total_damage": 27
    },
    "hp_update": {
      "...": "..."
    },
    "condition_updates": [
      {
        "condition": "blinded",
        "operation": "apply"
      }
    ],
    "note_update": {
      "...": "..."
    }
  }
}
```

关键点：

- `selected_outcome`
  - 明确本次结算走的是成功还是失败分支
- `damage_resolution`
  - 只有真的有伤害时才返回
- `condition_updates`
  - 记录系统已经应用了哪些 condition
- LLM 只读取结果，不手动维护状态

## 与现有系统的关系

### 保留的边界

- `ResolveDamageParts`
  - 继续只负责结构化伤害规则
- `UpdateHp`
  - 继续只负责应用最终生命值变更
- `UpdateConditions`
  - 继续只负责真正写入 condition

### 需要迁移的旧字段

以下旧字段最终不应继续作为新主路径事实源：

- `hp_change_on_failed_save`
- `hp_change_on_success`
- `damage_type`

它们可以在过渡期暂时兼容，但设计目标是让豁免型法术和武器攻击共用同一套结构化伤害模式。

## 测试范围

至少应覆盖：

- 豁免失败时从法术模板生成 `damage_parts`
- 豁免成功半伤时复用同一批 `damage_rolls`
- 豁免成功无伤时跳过伤害结算
- 失败附状态时自动调用 `UpdateConditions`
- 失败伤害 + 状态时两者都会触发
- 戏法成长能正确替换公式
- 高环施法能正确追加伤害段
- `damage_rolls.source` 缺失 / 多余 / 重复时会报错
- 成功无伤时即使传多余 `damage_rolls`，是否允许忽略，需要在实现计划中明确

## 本轮结论

这轮推荐把豁免型法术推进到与武器攻击一致的规则核心：

- 同样的 `damage_parts`
- 同样的 `damage_rolls[source]`
- 同样的 `ResolveDamageParts`

但在法术层额外保留 outcome 分支：

- `failed_save_outcome`
- `successful_save_outcome`

这是最贴合 DND 豁免法术结构、也最便于后续扩展海量法术模板的方案。
