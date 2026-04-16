# Action Economy Activation 设计说明

## 目标

为未来的武器、法术、职业特性建立一套统一的"发动方式"描述结构.

这套设计当前只覆盖**战斗内动作经济**:

- `action`
- `bonus_action`
- `reaction`

同时要求:

- 现在先不要把法术位、气点、职业次数硬塞进实现
- 但结构必须允许以后平滑扩展到这些资源
- 不把动作经济逻辑散落到 `execute_attack`、`encounter_cast_spell`、职业特性入口里各自手写

## 问题定义

当前系统已经开始出现动作经济判断:

- 武器攻击会校验和消耗 `action_used`
- 后续法术会区分 `action`、`bonus action`、`reaction`
- 职业特性会进一步改写回合资源使用方式

如果继续按"每个入口自己写规则"的方式推进,很快会出现几个问题:

- 同一套资源规则在多个 service 中重复实现
- 武器、法术、职业特性的成本表达方式不统一
- LLM 很难稳定知道"该读哪个字段、该扣哪个资源"
- 后续加入例外规则时,多个入口都要同步改

所以需要把"这个能力如何发动"从执行逻辑里抽出来,变成能力定义的一部分.

## 推荐方案

为每个可执行能力增加 `activation` 定义.

这里的"能力"包括但不限于:

- 武器攻击
- 法术
- 职业特性
- 特殊战斗动作

`activation` 只回答一件事:

**这个能力发动时,需要支付什么战斗内动作经济成本.**

推荐结构:

```json
{
  "activation": {
    "costs": ["action"]
  }
}
```

原因:

- `activation` 比 `action_cost` 更通用,后续不需要改名
- `costs` 是显式结构,适合未来从简单字符串扩展到对象成本
- 执行层只要读 `activation.costs`,不用再把成本规则写死在入口里

## 范围

本次设计包含:

- `activation` 的基础数据结构
- `action_economy` 的定位
- 动作经济成本的标准化表示
- 统一的校验与消费流程
- 武器 / 法术 / 特性未来接入方式

本次设计不包含:

- 法术位扣减统一建模
- 气点、充能、职业次数的统一建模
- 多重攻击、借机攻击、Action Surge 等复杂例外的完整规则实现
- 前端展示改版

## 数据模型

### EncounterEntity.action_economy

`EncounterEntity` 继续保留战斗内回合资源:

```json
{
  "action_economy": {
    "action_used": false,
    "bonus_action_used": false,
    "reaction_used": false
  }
}
```

说明:

- 它表示**当前回合的事实状态**
- 它不是能力定义
- 它不负责描述"某个能力应该扣什么"

### 能力上的 activation

能力定义新增:

```json
{
  "activation": {
    "costs": ["action"]
  }
}
```

当前阶段允许的成本值:

- `action`
- `bonus_action`
- `reaction`

示例:

```json
{
  "weapon_id": "rapier",
  "name": "Rapier",
  "activation": {
    "costs": ["action"]
  }
}
```

```json
{
  "spell_id": "misty_step",
  "name": "Misty Step",
  "activation": {
    "costs": ["bonus_action"]
  }
}
```

```json
{
  "feature_id": "opportunity_attack",
  "name": "Opportunity Attack",
  "activation": {
    "costs": ["reaction"]
  }
}
```

### 未来扩展空间

虽然当前 `costs` 先用字符串数组,但协议要预留为对象成本:

```json
{
  "activation": {
    "costs": [
      {"type": "action"},
      {"type": "spell_slot", "level": 1},
      {"type": "resource", "resource_id": "ki", "amount": 1}
    ]
  }
}
```

也就是说:

- 当前实现只支持字符串成本
- 将来可以兼容"字符串或对象"两种表示
- 不需要把字段名从 `activation` 改掉

## 执行层职责

推荐增加统一的动作经济处理层,而不是让各个战斗入口自己写.

建议拆出三个统一动作:

### 1. normalize_activation_costs

输入:

- 能力上的 `activation.costs`

输出:

- 内部标准化后的成本列表

职责:

- 把缺省值处理成统一结构
- 校验成本类型是否合法
- 为未来对象成本兼容预留入口

### 2. can_pay_activation_costs

输入:

- `EncounterEntity.action_economy`
- 标准化后的成本列表

输出:

- `True / False`
- 或结构化失败原因

职责:

- 判断当前实体还能不能支付这些动作经济成本
- 不修改状态

### 3. apply_activation_costs

输入:

- `EncounterEntity`
- 标准化后的成本列表

职责:

- 真正修改 `action_economy`
- 只做扣减,不做攻击/施法效果结算

## 建议流程

未来任意战斗入口都遵循同一流程:

1. 读到能力定义
2. 取出 `activation`
3. `normalize_activation_costs`
4. `can_pay_activation_costs`
5. 通过后再执行能力效果
6. 成功声明该能力后 `apply_activation_costs`
7. 返回最新 `encounter_state`

这样职责会清楚:

- 能力库负责描述能力
- 执行层负责结算能力
- 资源层负责检查和消费动作经济

## 各入口如何接入

### 武器攻击

当前阶段可以先约定:

- 武器默认 `activation.costs = ["action"]`

后续:

- `execute_attack` 不再自己假定"武器攻击一定吃 action"
- 而是从武器定义里读 `activation`

### 法术

法术定义新增:

- `activation.costs`

例如:

- 普通施法:`["action"]`
- 迷踪步:`["bonus_action"]`
- 盾牌术:`["reaction"]`

### 职业特性

职业特性未来也走同一套定义方式.

这能解决两个问题:

- LLM 不需要记忆"某个入口里写死了什么"
- 系统能以同一方式处理武器、法术、特性

## 兼容策略

为了不一次性重构全系统,建议分阶段接入:

### 阶段 1

- 保持现有 `action_economy`
- 保持现有 `execute_attack` 逻辑可运行
- 给未来能力定义补 `activation`

### 阶段 2

- 增加统一的 `normalize / can_pay / apply`
- 让 `execute_attack` 先接入这套层

### 阶段 3

- `encounter_cast_spell` 接入

### 阶段 4

- 职业特性、反应能力、特殊动作逐步迁入

## 约束与设计原则

- 不让 `action_economy` 同时承担"状态"和"规则定义"两种职责
- 不让 `execute_attack`、`encounter_cast_spell` 变成规则泥球
- 当前只做战斗内动作经济,不提前实现其他资源
- 结构必须允许以后扩展到法术位、气点、职业次数
- 允许空成本:

```json
{
  "activation": {
    "costs": []
  }
}
```

用于未来的免费能力或特殊声明

## LLM 视角

这套设计对 LLM 的价值很直接:

- LLM 不需要硬背"这招吃 action 还是 bonus action"
- 只要先找到能力定义,再读取 `activation`
- 规则层统一判断能否发动
- 失败时可以返回明确原因,比如:
  - `action_already_used`
  - `bonus_action_already_used`
  - `reaction_already_used`

这会让自然语言到 tool 的转换更稳定.

## 测试要求

未来真正实现时,至少覆盖:

- `["action"]` 能正确校验和扣减
- `["bonus_action"]` 能正确校验和扣减
- `["reaction"]` 能正确校验和扣减
- 已用资源重复支付会失败
- 空成本不会报错
- `GetEncounterState` 能稳定暴露动作经济状态
- 武器 / 法术入口接入后仍返回同步后的 `encounter_state`

## 结论

推荐把未来的动作经济系统设计成:

- **实体上保存回合资源事实:** `action_economy`
- **能力上保存发动方式定义:** `activation.costs`
- **执行层通过统一资源服务进行校验和消费**

这样当前实现不会过度复杂,同时后续把法术和职业特性接进来时,也不会把规则写散.
