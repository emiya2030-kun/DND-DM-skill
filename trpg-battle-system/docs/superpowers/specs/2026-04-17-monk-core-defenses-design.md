# 武僧核心防御与机动特性设计

日期：2026-04-17

## 目标

在现有已经落地的武僧基础能力之上，继续把以下五项接成真实可结算的战斗规则：

- `Unarmored Defense`
- `Unarmored Movement`
- `Uncanny Metabolism`
- `Deflect Attacks / Deflect Energy`
- `Evasion`

本次目标是做“最小可用战斗版”。

本次只覆盖：

- 战斗内真实结算
- 现有 encounter runtime
- LLM 可声明、后端可执行的能力
- 与现有 AC、移动、反应、豁免伤害链路的接线

本次明确不覆盖：

- 子职特性
- 战斗外施展或探索期逻辑
- 自动替 LLM 决定是否发动能力
- 所有武僧后续高等级能力

## 设计原则

### 1. 挂到正确主链，不单独造一条武僧总线

这五项规则天然分属不同链路：

- AC 计算
- 速度计算
- 先攻开始
- 受击反应
- DEX 豁免伤害改写

本次不额外抽一个“大武僧 service”承载全部逻辑，而是挂到各自正确的主链中。

### 2. LLM 负责声明，后端负责结算

需要玩家或怪物主动决定的能力，不做自动判断。

例如：

- `Uncanny Metabolism` 是否在投先攻时发动
- `Deflect Attacks` 是否消耗反应
- `Deflect Attacks` 减伤至 0 后是否继续消耗功力反打

这些都由 LLM 显式声明；一旦声明，后端完成全部掷骰、减伤、资源扣减与状态更新。

### 3. 只让前端 / LLM 看摘要，不暴露内部运算细节

前端与 `GetEncounterState` 继续只投影：

- 正常 AC
- 正常速度
- 功力剩余
- 可用反应/已用反应
- 简短 recent activity

不额外暴露内部 AC 公式或复杂中间态。

## 一、Unarmored Defense

### 规则

当实体满足以下条件时：

- 存在 `monk` runtime
- 未穿戴任何护甲
- 未持用盾牌

其基础 AC 改为：

`10 + DEX 调整值 + WIS 调整值`

一旦穿甲或持盾，立刻失效。

### 落点

- `tools/services/combat/defense/armor_profile_resolver.py`

### 结算说明

- 这是基础 AC 替换，不是额外加值
- 护盾术等临时 AC 效果仍然在此基础之上叠加
- 若实体已穿护甲，则仍按护甲链原规则结算

## 二、Unarmored Movement

### 规则

当实体满足以下条件时：

- 存在 `monk` runtime
- 未穿戴任何护甲
- 未持用盾牌

其本回合真实可用移动速度增加：

- `monk.unarmored_movement_bonus_feet`

若不满足条件，则不获得此加值。

### 落点

- `tools/services/encounter/turns/turn_engine.py`
- 真实移动速度读取链

### 结算说明

- 本加值应影响每回合速度刷新后的 `remaining`
- 与护甲速度惩罚、武器精通减速等现有规则共同生效
- `GetEncounterState` 仍可继续投影现有摘要字段 `unarmored_movement_bonus_feet`
- 但真正的可移动距离必须来自后端结算后的速度，而不是 LLM 自己口算

## 三、Uncanny Metabolism

### 规则

本次只做最小可用版：

- 触发时机：投先攻时
- 由 LLM 显式声明是否发动
- 若发动：
  - 恢复全部已消耗功力
  - 恢复 `武艺骰 + 武僧等级` 生命值
- 长休前只能发动一次

### 落点

- 先攻开始 service
- 武僧 runtime 资源读写

### 运行时建议

在 `class_features.monk` 下增加：

```json
{
  "uncanny_metabolism": {
    "available": true
  }
}
```

或等价布尔字段，用于表示本次长休周期内是否还能用。

### 结算说明

- 不做自动触发
- 不做脱离先攻期的其他恢复入口
- 治疗不得超过最大生命值

## 四、Deflect Attacks / Deflect Energy

### 规则分层

#### Deflect Attacks

触发条件必须严格满足：

- 你被一次**攻击检定命中**
- 且该次伤害中**包含钝击、穿刺或挥砍伤害**

若满足条件，武僧可以使用反应减少本次攻击造成的总伤害，减值为：

`1d10 + DEX 调整值 + 武僧等级`

若伤害被减至 0，则可以额外消耗 1 点功力进行反打：

- 原近战攻击：选择你 5 尺内可见生物
- 原远程攻击：选择你 60 尺内且不处于全身掩护后的可见生物

目标进行敏捷豁免，失败则受到：

`2 个武艺骰 + DEX 调整值`

伤害类型与原攻击伤害类型一致。

#### Deflect Energy

本次实现上预留升级位。

13 级后其差异只体现在：

- 允许对抗任意伤害类型的攻击

其余结算结构沿用 `Deflect Attacks`。

### 落点

- 现有 reaction 框架
- 命中后、伤害正式写入 HP 前的结算点

### 设计

新增武僧反应定义，按现有 reaction framework 接入：

- 先判断是否可开窗
- LLM 选择是否使用
- 后端自动完成减伤掷骰
- 若减伤后总伤害仍大于 0，则按改写后的伤害继续结算
- 若减至 0，则返回“可继续反打”的分支结果

### 反打范围

本次后端支持完整结算，但仍要求 LLM 明确传入反打目标。

也就是：

- “只减伤不反打” 可以直接完成
- “减到 0 后继续反打” 时，LLM 需明确目标，后端自动掷伤害与豁免

### 资源规则

- `Deflect Attacks` 本身只消耗反应
- 仅当减到 0 并继续反打时，才额外消耗 1 点功力
- 若反打条件不满足，则不会错误扣减功力

## 五、Evasion

### 规则

当武僧：

- 未处于 `incapacitated`
- 遭受一个“允许进行敏捷豁免，成功则只承受一半伤害”的效果

则：

- 豁免成功：改为 0 伤害
- 豁免失败：改为一半伤害

### 落点

- `tools/services/combat/save_spell/saving_throw_result.py`
- `tools/services/combat/save_spell/execute_save_spell.py`
- 其他复用相同保存伤害结果链的地方

### 结算边界

只改写这类条件全部满足的伤害结算：

- 是 `DEX` 豁免
- 成功 outcome 为半伤
- 失败 outcome 为正常伤害

不改写：

- 非 DEX 豁免
- 纯状态型效果
- 成功无伤、失败半伤以外的特殊自定义 outcome

## 六、运行时结构

本次武僧 runtime 建议至少支持：

```json
{
  "monk": {
    "level": 7,
    "martial_arts_die": "1d8",
    "focus_points": {
      "max": 7,
      "remaining": 4
    },
    "unarmored_movement_bonus_feet": 15,
    "stunning_strike": {
      "uses_this_turn": 0,
      "max_per_turn": 1
    },
    "uncanny_metabolism": {
      "available": true
    },
    "deflect_attacks": {
      "enabled": true
    },
    "evasion": {
      "enabled": true
    }
  }
}
```

本次不强求所有字段都必须预置；但运行时读取必须兼容缺失字段并安全降级。

## 七、与现有系统的衔接

### AC 链

- 继续由护甲解析器产出最终基础 AC
- 武僧无甲防御只作为一种新的基础 AC 方案

### 回合开始链

- 继续由 `turn_engine.reset_turn_resources` 刷新移动与动作
- 武僧无甲移动应在这里反映到真实 `remaining`

### 先攻链

- 先攻生成完成前后，允许接入 `Uncanny Metabolism`
- 该能力只在此窗口期可用

### 反应链

- `Deflect Attacks` 复用现有 reaction request / resolve 体系
- 不新增另一套独立“武僧受击窗口”

### 豁免伤害链

- `Evasion` 只改写最终伤害，不改写 save roll 本身

## 八、测试策略

本次至少补以下测试：

### AC

- 武僧未着甲未持盾时，基础 AC 使用 `10 + DEX + WIS`
- 武僧穿甲时，不触发无甲防御
- 武僧持盾时，不触发无甲防御

### 速度

- 武僧未着甲未持盾时，回合开始 `remaining` 含无甲移动加值
- 穿甲或持盾时，不获得该加值

### 运转周天

- 投先攻时显式发动后，功力恢复到满值
- 同时恢复 `武艺骰 + 武僧等级` HP
- 已消耗后再次发动会被拒绝

### 拨挡攻击

- 仅当命中且伤害中包含 B/P/S 时才会开窗
- 纯元素伤害攻击不会触发
- 减伤后若未归零，则只改写最终伤害
- 减伤到 0 后可继续反打，且仅此时消耗 1 点功力

### 反射闪避

- 火球术这类 DEX 半伤法术，成功时伤害变 0
- 失败时伤害变半伤
- `incapacitated` 时不生效

## 九、非目标

本次不处理：

- `Patient Defense`
- `Step of the Wind`
- `Slow Fall`
- `Self-Restoration`
- `Disciplined Survivor`
- `Perfect Focus`
- `Superior Defense`
- 子职

这些能力后续再单独设计，不并入本次范围。
