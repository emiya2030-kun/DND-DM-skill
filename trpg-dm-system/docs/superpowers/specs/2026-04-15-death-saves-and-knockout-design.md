# 死亡豁免与击晕不杀设计

## 目标

在现有战斗系统里补齐以下规则闭环：

1. `pc / npc` 在 `HP=0` 时进入正常濒死流程，并在自己回合开始时自动进行死亡豁免。
2. 死亡豁免不引入 `stable` 状态，而是采用“3 次成功直接恢复 1 HP，3 次失败死亡”的简化版本。
3. 近战攻击支持由 LLM 明确声明的“击晕不杀”意图。
4. 失能或死亡会立刻终止专注。
5. 页面把“0 HP 未死”和“真正死亡”区分展示。

## 范围

本次只覆盖战斗内规则，不扩展到战斗外恢复、长休、医疗检定或完整时间推进系统。

包括：

- `pc / npc` 的 `HP=0`、死亡豁免、再次受伤、真正死亡
- `monster` 与 `summon` 的 `HP=0` 分流
- “击晕不杀”运行态与再次受伤时转回正常濒死
- 专注在 `unconscious` 或 `is_dead=True` 时立刻终止
- battlemap / 角色卡状态展示

不包括：

- `stable`
- 濒死目标的战斗外苏醒逻辑
- 死亡后的复活规则
- 完整的战斗外时间系统

## 最终规则

### 1. `HP=0` 分流

#### `monster`

- `HP=0` 后从 `encounter.entities` 与 `turn_order` 中移除。
- 地图原地追加一个 `💀` 残骸标记。

#### `summon`

- `HP=0` 后直接从 `encounter.entities` 与 `turn_order` 中移除。
- 不留残骸。

#### `pc / npc`

- `HP=0` 后保留实体。
- 自动附加 `unconscious`。
- 初始化或保留死亡豁免计数。
- 若当前正在专注，立刻终止专注。

### 2. 正常死亡豁免

仅当以下条件全部满足时，实体在自己回合开始时自动进行一次死亡豁免：

- `category in {"pc", "npc"}`
- `hp.current == 0`
- `conditions` 包含 `unconscious`
- 未处于“击晕不杀保护态”
- `combat_flags.is_dead != True`

死亡豁免结果：

- `d20 >= 10`：成功 `+1`
- `d20 < 10`：失败 `+1`
- `d20 == 1`：失败 `+2`
- `d20 == 20`：
  - 恢复 `1 HP`
  - 清空死亡豁免计数
  - 移除 `unconscious`

累计结果：

- `3` 次成功：
  - 恢复 `1 HP`
  - 清空死亡豁免计数
  - 移除 `unconscious`
- `3` 次失败：
  - `combat_flags.is_dead = True`
  - 保留实体在地图上
  - 清空或冻结死亡豁免计数，不再继续投死亡豁免

### 3. `HP=0` 时再次受伤

仅适用于 `pc / npc` 且 `hp.current == 0` 且 `is_dead != True`。

- 普通受伤：死亡豁免失败 `+1`
- 来自重击：死亡豁免失败 `+2`
- 单次伤害 `>= hp.max`：立即死亡
- 累计失败达到 `3`：立即死亡

若目标当前处于“击晕不杀保护态”，则顺序如下：

1. 先移除保护态
2. 再按本次伤害走正常濒死规则

### 4. 击晕不杀

“击晕不杀”只允许通过近战攻击触发，并且必须由 LLM 明确表达。

建议后端入口参数：

- `zero_hp_intent="knockout"`

触发条件：

- 攻击为近战攻击
- 这次攻击把目标打到 `0 HP`
- LLM 明确传入 `zero_hp_intent="knockout"`

生效结果：

- 目标保持 `hp.current = 0`
- 目标附加 `unconscious`
- 不进入正常死亡豁免
- 挂一个持续 `1 小时` 的运行时效果
- 若正在专注，立刻终止专注

这个保护态不是永久安全。

如果目标在这 `1 小时` 内再次受伤：

- 先移除该保护态
- 然后立刻转回正常濒死规则

如果期间获得任意治疗：

- 恢复正常 `HP`
- 移除 `unconscious`
- 清空死亡豁免计数
- 移除击晕保护态

### 5. 专注终止

以下两类情况，本次不再等待额外专注检定，直接终止专注：

- 目标因 `HP=0` 附加 `unconscious`
- 目标进入真正死亡 `is_dead=True`

实现上复用现有专注结束清理链，确保：

- `combat_flags.is_concentrating = False`
- 活动中的专注法术实例被关闭
- 挂在目标上的相关 `conditions` / `turn_effects` 被清理

## 数据设计

### `conditions`

继续保留规则态：

- `unconscious`

本次不新增 `stable`、`dead` 条件。

### `combat_flags`

新增或标准化：

```json
{
  "is_dead": false,
  "death_saves": {
    "successes": 0,
    "failures": 0
  }
}
```

说明：

- `is_dead` 是真正死亡终态。
- `death_saves` 是运行时计数器，不放进 `conditions`。

### `turn_effects`

新增一种运行时效果用于“击晕不杀”：

```json
{
  "effect_type": "knockout_protection",
  "name": "Knocked Out",
  "trigger": "time_expire",
  "duration_seconds": 3600,
  "started_at": "<timestamp>",
  "remove_conditions_on_expire": ["unconscious"]
}
```

这里的关键语义不是“到点立即结算”，而是保留明确结构，以便未来时间推进系统接入。当前阶段至少需要：

- 能被识别为“这名目标不走正常死亡豁免”
- 在再次受伤时被移除

## 服务职责

### `UpdateHp`

负责：

- `HP=0` 分流
- `pc / npc` 的 `unconscious`
- `HP=0` 时再次受伤的死亡豁免失败累计
- 大伤害直接死亡
- `is_dead=True` 终态写入
- 进入 `unconscious` 或 `is_dead=True` 时终止专注
- 识别并移除“击晕不杀保护态”

不负责：

- 回合开始自动掷死亡豁免

### `StartTurn`

负责：

- 检查当前回合实体是否要进行死亡豁免
- 自动生成 / 结算一次死亡豁免
- 把结果投影到 `encounter_state`

不负责：

- 一般 HP 扣减
- 击晕不杀意图判断

### `ExecuteAttack`

负责：

- 接收 `zero_hp_intent="knockout"`
- 仅在近战攻击里把这个意图传给 `UpdateHp`

不负责：

- 猜测玩家是不是想活捉

## 视图层

### `pc / npc`

- `hp.current == 0` 且 `is_dead != True`
  - 保留原职业 token
  - 红色外框
- `combat_flags.is_dead == True`
  - 保留原职业 token
  - 更深红色外框
  - 角色卡显示“死亡”

### `monster`

- 仍然移除实体
- 地图只显示 `💀` 残骸

### `summon`

- 不显示 token
- 不显示残骸

## 错误处理

- 若 `zero_hp_intent="knockout"` 但攻击不是近战：
  - 忽略该意图
  - 仍按普通 `HP=0` 流程处理
- 若 `death_saves` 缺失：
  - 读取时按 `{successes: 0, failures: 0}` 兜底
- 若 `pc / npc` 已经 `is_dead=True`：
  - 不再进行死亡豁免
  - 额外伤害不再改变死亡豁免计数

## 测试策略

至少覆盖以下场景：

1. `pc / npc` 掉到 `0 HP` 后进入 `unconscious`
2. `pc / npc` 在自己回合开始时自动进行死亡豁免
3. `3` 次成功后恢复 `1 HP`
4. `3` 次失败后 `is_dead=True`
5. `0 HP` 时受普通伤害记 `1` 次失败
6. `0 HP` 时受重击记 `2` 次失败
7. 单次伤害 `>= hp.max` 立即死亡
8. 近战 `knockout` 把目标打到 `0 HP` 后附加保护态
9. `knockout` 目标再次受伤后转回正常濒死规则
10. `unconscious` 或 `is_dead=True` 时专注立即终止
11. 页面正确区分“0 HP 未死”和“真正死亡”

