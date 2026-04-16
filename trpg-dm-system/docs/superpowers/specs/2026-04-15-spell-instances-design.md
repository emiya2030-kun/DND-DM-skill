# Spell Instances 设计说明

## 目标

为战斗运行时增加一层正式的 `spell_instances`，用来描述：

- 这是哪一次法术施放
- 谁施放的
- 当前影响了哪些目标
- 创建了哪些 condition
- 创建了哪些 `turn_effects`
- 是否还在持续
- 是否依赖专注
- 是否存在额外运行时能力，例如 `Hex` 的可转移资格

这层是后端真实结构，不直接原样暴露给 LLM。

---

## 为什么现在要做

当前系统已经有：

- `conditions`
- `turn_effects`
- 静态法术模板 `spell_definitions`

这些已经能支撑：

- `Fireball` 即时伤害
- `Hold Person` 失败附 `paralyzed`
- `Hold Person` 回合结束再豁免
- `Hex` 命中附加 `1d6` 暗蚀伤害

但现在这些结果仍然是碎片化的：

- `conditions` 只知道“现在有什么状态”
- `turn_effects` 只知道“开始/结束回合会触发什么”
- 系统还不知道这些碎片是不是来自**同一次法术施放**

这会直接影响后续这些场景：

1. 专注断开后，整套效果如何一起清理
2. `Hex` 目标死亡后，施法者是否还保有转移资格
3. 同一次法术同时影响多个目标时，如何统一管理
4. 给 LLM 投影“来自敌人A的定身术”这类摘要时，事实源放哪里

所以需要新增 `spell_instances`。

---

## 设计原则

1. `conditions` 继续只表示当前状态
2. `turn_effects` 继续只表示开始/结束回合触发规则
3. `spell_instances` 负责把这些结果组织成“一次法术施放”
4. 后端保留完整结构，`GetEncounterState` 只输出摘要
5. 第一版只覆盖战斗内持续法术，不覆盖完整战斗外 runtime

---

## 放在哪里

推荐放在 `Encounter` 顶层：

```json
{
  "spell_instances": []
}
```

不建议放在单个 `entity` 里。

原因：

- 一个法术实例通常同时关联施法者、一个或多个目标、若干 `turn_effects`
- 它天然是 encounter 级运行时对象
- 放在单个实体里会让边界变得模糊

---

## 最小结构

建议第一版结构：

```json
{
  "instance_id": "spell_hold_person_001",
  "spell_id": "hold_person",
  "spell_name": "Hold Person",
  "caster_entity_id": "ent_enemy_a",
  "caster_name": "敌人A",
  "cast_level": 2,
  "concentration": {
    "required": true,
    "active": true
  },
  "targets": [
    {
      "entity_id": "ent_ally_milun",
      "applied_conditions": ["paralyzed"],
      "turn_effect_ids": ["effect_abc123"]
    }
  ],
  "lifecycle": {
    "status": "active",
    "started_round": 1
  },
  "special_runtime": {
    "retargetable": false
  }
}
```

---

## 字段说明

### `instance_id`

- 每次施法运行时实例唯一 id
- 用来做后续关联、移除和调试

### `spell_id`

- 对应静态模板 id
- 例如：`hold_person`、`hex`

### `spell_name`

- 给日志、调试和摘要投影用

### `caster_entity_id`

- 施法者运行时 id

### `caster_name`

- 仅用于调试和摘要投影

### `cast_level`

- 本次实际施法位
- 对 `Hex` 时长、`Hold Person` 额外目标等都可能需要

### `concentration`

```json
{
  "required": true,
  "active": true
}
```

- `required`
  - 这个法术是否要求专注
- `active`
  - 当前这一实例是否还因专注而维持

第一版先不做更复杂的 concentration link，只记录最小状态。

### `targets`

每个目标元素最小包含：

```json
{
  "entity_id": "ent_ally_milun",
  "applied_conditions": ["paralyzed"],
  "turn_effect_ids": ["effect_abc123"]
}
```

用途：

- 记录这次法术对哪个目标生效
- 记录它给这个目标挂了哪些状态
- 记录它给这个目标挂了哪些 `turn_effects`

这样后面如果要整套移除，就能沿着实例找到所有碎片。

### `lifecycle`

```json
{
  "status": "active",
  "started_round": 1
}
```

第一版 `status` 只建议支持：

- `active`
- `ended`

以后再扩：

- `broken_concentration`
- `retarget_pending`
- `expired`

### `special_runtime`

这是给少数特殊法术留的运行时扩展槽。

例如 `Hex`：

```json
{
  "retargetable": true,
  "current_target_id": "ent_enemy_goblin_001"
}
```

第一版不建议过度泛化，只留一个 dict 容器即可。

---

## 和现有字段的边界

### `conditions`

继续只表示当前状态：

```json
["paralyzed"]
```

不要放：

- 法术名
- 中文来源说明
- 持续时间逻辑
- 清理规则

### `turn_effects`

继续只表示开始/结束回合触发规则：

- 回合结束再做感知豁免
- 回合结束吃一次伤害

### `spell_instances`

负责把它们组织成“这是一次完整的法术施放后果”。

---

## 首批覆盖法术

### `Hold Person`

创建实例时记录：

- `spell_id = hold_person`
- `caster_entity_id`
- `cast_level`
- `concentration.required = true`
- `targets[0].entity_id`
- `targets[0].applied_conditions = ["paralyzed"]`
- `targets[0].turn_effect_ids = [回合结束再豁免 effect_id]`

这样未来如果专注断开，可以直接：

1. 找到这个 `spell_instance`
2. 清 `paralyzed`
3. 清对应 `turn_effect`
4. 把实例标成 `ended`

### `Hex`

创建实例时记录：

- `spell_id = hex`
- `caster_entity_id`
- `cast_level`
- `concentration.required = true`
- `targets[0].entity_id = 当前被诅咒目标`
- `targets[0].turn_effect_ids = [hex_mark effect_id]`
- `special_runtime.retargetable = true`
- `special_runtime.current_target_id = 当前目标`

第一版先不做真正的转移动作，但结构要留好。

### `Fireball`

不需要 `spell_instance`。

原因：

- 它是一次即时结算法术
- 不留下持续状态或触发 effect

规则上应该保持“不是所有法术都必须创建实例”。

---

## `GetEncounterState` 如何投影

`spell_instances` 不直接原样暴露给 LLM。

只做两类摘要投影：

### 1. 实体级摘要

例如目标米伦：

```json
{
  "conditions": [
    "paralyzed",
    "来自敌人A的定身术"
  ],
  "ongoing_effects": [
    "回合结束进行感知豁免，成功则结束"
  ]
}
```

### 2. 全局专注摘要

例如：

```json
[
  "敌人A正在专注：Hold Person",
  "Eric正在专注：Hex"
]
```

这层只是展示摘要，不是事实源。

---

## 为什么不用中文字符串做事实源

像：

```json
["paralyzed", "来自敌人A的定身术"]
```

这种格式适合给 LLM 看，但不适合后端规则判断。

原因：

1. 无法稳定关联同一次施法的多个碎片
2. 无法可靠处理整套清理
3. 法术同名、多目标、多个施法者时会很快混乱

所以最终分层必须是：

- 后端：结构化 `spell_instances`
- LLM：中文摘要投影

---

## 第一版明确不做

- 完整战斗外 `campaign_runtime` 法术实例
- 完整 concentration 断开自动清理
- `Hex` 真正转移动作
- 召唤物类法术实例
- 区域持续法术实例

第一版只做最小骨架和首批法术接入。

---

## 推荐实施顺序

1. `Encounter` 新增 `spell_instances`
2. `Hold Person` 施法时创建实例并记录 `turn_effect_ids`
3. `Hex` 施法时创建实例并记录当前目标
4. `GetEncounterState` 新增摘要投影
5. 下一轮再接 concentration 清理和 `Hex` 转移
