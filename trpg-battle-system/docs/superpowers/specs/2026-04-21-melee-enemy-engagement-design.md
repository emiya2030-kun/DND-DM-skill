# 近战敌人接敌投影设计

## 目标

在现有 `current_turn_context.enemy_tactical_brief` 的基础上，新增“本回合可接敌目标”投影，让 LLM 不只知道“当前已经能打谁”，还知道“靠通用动作经济，这回合能贴到谁，以及是否要承担借机攻击风险”。

本次扩展只覆盖：

- 普通移动接敌
- `Dash` 接敌
- `Disengage` 安全重定位
- 离开现有敌人威胁范围时是否可能触发借机攻击

本次不覆盖：

- 职业/怪物特性带来的额外移动能力
- 武僧疾步如风、盗贼附赠疾走/撤离等职业特例
- 更复杂的路径收益比较
- 真实自动执行移动或攻击

## 设计原则

### 1. 保留现有 `candidate_targets`

`candidate_targets` 继续表示：

- 当前站位下
- 不需要额外移动规划
- 本回合已经在近战攻击范围内

其 `score` 逻辑保持现有规则为主，不重做大改。

### 2. 新增 `reachable_targets`

`reachable_targets` 表示：

- 当前回合内
- 依靠通用动作经济
- 是否能够接敌到目标

这里的“通用动作经济”仅包括：

- 普通移动
- `Dash`
- `Disengage`

### 3. 结构分层，而不是把两类目标混在一起

原因：

- “已经能攻击” 与 “只能接敌但未必能攻击” 不是同一层价值
- 把它们混成一个排序列表会让 LLM 更难理解
- 后续要加黑暗、地形、危险区域时，也更适合挂在接敌层

## 输出结构

在 `enemy_tactical_brief` 下新增：

```json
{
  "candidate_targets": [
    {
      "entity_id": "ent_ally_miren_001",
      "in_attack_range": true,
      "score": 8.86,
      "attack_has_advantage": false
    }
  ],
  "reachable_targets": [
    {
      "entity_id": "ent_ally_eric_001",
      "score": 7.5,
      "distance_feet": 25,
      "movement_cost_feet": 25,
      "can_attack_this_turn": true,
      "engage_mode": "move_and_attack",
      "requires_action_dash": false,
      "requires_action_disengage": false,
      "opportunity_attack_risk": false,
      "risk_sources": []
    },
    {
      "entity_id": "ent_ally_caster_001",
      "score": 8.25,
      "distance_feet": 45,
      "movement_cost_feet": 45,
      "can_attack_this_turn": false,
      "engage_mode": "dash_to_engage",
      "requires_action_dash": true,
      "requires_action_disengage": false,
      "opportunity_attack_risk": true,
      "risk_sources": ["ent_ally_guard_001"]
    }
  ]
}
```

## 接敌判定规则

### 1. 只使用当前剩余速度

接敌判定使用 `actor.speed["remaining"]` 作为当前可用移动力事实源。

### 2. 接敌目标定义

某目标进入 `reachable_targets`，需满足：

- 是敌对单位
- 当前不是自己
- 对方不是同侧单位
- 当前回合通过普通移动或 `Dash` 可以进入近战触及范围

### 3. 可攻击与可贴近要分开

对每个可接敌目标，都要区分：

- `can_attack_this_turn = true`
  - 说明普通移动后仍保留动作，且能进入近战触及
- `can_attack_this_turn = false`
  - 说明只有 `Dash` 才能贴近，动作会被用于疾走，因此本回合通常不能再攻击

### 4. `Disengage` 的使用场景

若当前行动者已经处在其他敌对单位近战威胁范围内，则接敌到另一个目标时，可能需要考虑：

- 直接移动离开，承担借机攻击风险
- 使用 `Disengage`，安全离开，但通常失去攻击动作

因此 `reachable_targets` 中允许出现：

- `engage_mode = "disengage_to_engage"`

这表示：

- 本回合能安全贴近
- 但通常不能攻击

## 借机攻击风险规则

### 1. 风险判断范围

第一版只做保守近似判断：

- 如果行动者当前在某个敌对单位的近战触及内
- 且为了接近新目标需要离开该敌对单位触及
- 则记为存在借机攻击风险

### 2. 不做的精细规则

第一版不做：

- 逐步路径逐格判定多个威胁源
- 特殊能力导致的“不可借机”
- 反应是否已用尽的精确推导
- 每个风险源真实武器触及差异的全量模拟

### 3. 风险字段

每个 `reachable_targets` 项目包含：

- `opportunity_attack_risk`
- `risk_sources`

其中 `risk_sources` 用来告诉 LLM：若硬冲，可能是谁打借机。

## 评分规则

### 1. 继续高参照现有 `score`

`reachable_targets[*].score` 继续以现有目标价值评分为基础：

- 低 AC
- 专注
- 低血量比例
- 低最大 HP
- 小幅优势加分
- 召唤物大幅减分

### 2. 在基础分上叠加接敌方式修正

在现有目标分数基础上加入轻量修正：

- `move_and_attack`: 不减分
- `dash_to_engage`: 小幅减分
- `disengage_to_engage`: 中幅减分
- 有借机攻击风险：额外减分

原则：

- 已能攻击 > 普通移动后可攻击 > Dash 才能贴近 > 为了贴近还要承担借机
- 但若目标本身非常高价值，例如正在专注的脆皮法师，仍可能保留较高排序

### 3. 怪物何时愿意 `Dash`

默认倾向：

- 若当前已有高价值可攻击目标，通常不 `Dash`
- 若当前没有可攻击目标，但能通过 `Dash` 压迫高价值目标，则允许进入高位候选
- 若只是为了接近召唤物或低价值目标，不值得 `Dash`

### 4. 怪物何时愿意冒借机

默认倾向：

- 若只是换一个价值相近目标，不值得冒借机
- 若能威胁高价值专注目标，且收益明显高于当前接战对象，可保留为候选
- 冒借机的候选应存在明确减分，不应轻易压过安全方案

## 当前可复用的后端能力

本次优先复用已有移动规则与距离规则：

- 距离计算
- 路径合法性/移动成本
- 现有借机攻击触发语义

但 `get_encounter_state` 本身只做投影，不直接发起真实移动命令或创建 reaction request。

## 验收标准

完成后应满足：

- `candidate_targets` 继续表示“当前已能攻击的目标”
- `reachable_targets` 表示“本回合靠通用动作经济可接敌的目标”
- 能区分普通移动可攻击、`Dash` 贴近、`Disengage` 安全贴近三类方式
- 能标记是否存在借机攻击风险及主要风险来源
- 接敌排序仍以现有目标价值 `score` 为高参照，而不是推翻重做
- 不自动替 LLM 执行动作，只提供后端可读的战术投影
