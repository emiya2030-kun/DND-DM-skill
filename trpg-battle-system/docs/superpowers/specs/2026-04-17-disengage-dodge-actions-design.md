# 撤离与回避动作设计

日期：2026-04-17

## 目标

为 `trpg-battle-system` 增加两个基础战斗动作：

- `Disengage`
- `Dodge`

本次目标是做“最小正确版”：

- LLM 可以把玩家自然语言稳定转成标准 tool 调用
- 后端独立完成规则生效，不依赖 LLM 手工补算
- 与现有移动、借机攻击、攻击检定、豁免检定链路自然接合
- 为后续职业特性复用保留扩展点

## 本次范围

本次只覆盖：

- 普通动作版 `Disengage`
- 普通动作版 `Dodge`
- `Disengage` 对借机攻击触发的抑制
- `Dodge` 对攻击检定与敏捷豁免的改写
- `GetEncounterState` 对这两个动作状态的摘要投影
- LLM skill 中的调用规则更新

本次明确不覆盖：

- 盗贼 `Cunning Action` 的附赠 `Disengage`
- 武僧 `Patient Defense` 的附赠 `Dodge`
- 完整隐匿 / 可见性 / 感知模型
- 复杂“看不见攻击者”的视线系统
- 其他动作如 `Hide`、`Ready`

## 设计原则

### 1. 动作本体要独立成显式 tool

LLM 说“我要撤离”或“我要回避”时，不应通过修改移动请求或攻击请求间接表达。

这两个都是标准动作，应有自己的显式 service / runtime command：

- `use_disengage`
- `use_dodge`

这样边界清晰：

- 先声明动作
- 后续效果由后端自动生效
- 若动作后还要移动或结束回合，再走现有链路

### 2. 运行态挂在 `turn_effects`，不塞进 `combat_flags`

`Disengage` 和 `Dodge` 都属于“短时持续效果”。

如果把它们直接塞进：

- `action_economy`
- `combat_flags`

会让这两个结构越来越混杂，既保存资源事实，又保存规则效果，后续职业特性和法术更难维护。

因此本次统一挂到实体的 `turn_effects`：

- `Disengage`：本回合剩余时间有效
- `Dodge`：直到下个自己回合开始前有效

这和现有：

- `Deflect Attacks`
- `Stunning Strike`
- 各类开始/结束回合效果

的运行态风格一致。

### 3. 第一版优先做“效果正确”，不强求完整感知模型

`Dodge` 的规则里有一条：

- “除非你看不见攻击者”

当前项目尚无完整“谁能看见谁”的感知系统。

因此第一版采用最小可接受实现：

- 若攻击者具有 `invisible` 条件，则视为“目标看不见攻击者”
- 否则按“目标看得见攻击者”处理

也就是说：

- 当前版 `Dodge` 的“无效条件”只接入已有 `invisible`
- 不额外引入复杂 LOS / 视线阻挡 / 遮蔽系统

后续若补完整可见性模型，再把这里切到统一可见性判断函数。

### 4. 失效条件优先动态判断，不急着物理删除效果

`Dodge` 的失效条件：

- 目标陷入 `incapacitated`
- 目标速度降至 0

第一版不要求系统在每次状态变化时都主动删除 `Dodge` effect。

而是在读取效果时动态判断是否仍可生效：

- 攻击检定读取时判定
- 敏捷豁免读取时判定

这样实现简单、稳定，也避免到处加“清理 Dodge”分支。

## 一、服务结构

### 新增 service

- `tools/services/combat/actions/use_disengage.py`
- `tools/services/combat/actions/use_dodge.py`

### 新增 runtime command

- `runtime/commands/use_disengage.py`
- `runtime/commands/use_dodge.py`

### 复用的既有主链

- 移动链
- 借机攻击反应链
- `AttackRollRequest`
- 敏捷豁免请求 / 结算链
- `GetEncounterState`

## 二、运行态模型

### 1. Disengage effect

成功使用 `Disengage` 后，在 actor 身上追加一个 `turn_effect`：

```json
{
  "effect_id": "effect_disengage_001",
  "effect_type": "disengage",
  "name": "Disengage",
  "trigger": "manual_state",
  "source_ref": "action:disengage",
  "expires_at": "end_of_current_turn"
}
```

语义：

- 只对该 actor 生效
- 只在“本回合剩余时间内”阻止借机攻击触发

### 2. Dodge effect

成功使用 `Dodge` 后，在 actor 身上追加一个 `turn_effect`：

```json
{
  "effect_id": "effect_dodge_001",
  "effect_type": "dodge",
  "name": "Dodge",
  "trigger": "manual_state",
  "source_ref": "action:dodge",
  "expires_at": "start_of_next_turn"
}
```

语义：

- 只对该 actor 生效
- 在其下个自己回合开始前，读取时提供：
  - 被攻击时攻击者劣势
  - 自身敏捷豁免优势

### 为什么继续用 `turn_effects`

虽然这两个效果不是传统的“开始/结束回合自动结算效果”，但它们本质仍是短时战斗状态。

放进 `turn_effects` 的好处：

- 能统一投影到前端与 LLM
- 后续职业复用时不用再造平行状态系统
- 清理策略可与现有效果体系保持一致

## 三、Disengage 设计

### 输入

`use_disengage.execute(...)`

- `encounter_id`
- `actor_id`

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `action_economy.action_used == false`
- actor 未失能到无法执行动作

### 结算

成功时：

- 消耗 `action_economy.action_used`
- 若已有旧的 `disengage` effect，先清理同类旧 effect
- 写入新的 `disengage` effect
- 返回最新 `encounter_state`

### 对移动链的影响

移动链在检查“是否触发借机攻击”前，先读取移动者身上是否存在有效 `disengage` effect。

若存在，则：

- 本次剩余移动不生成 `opportunity_attack` request

这条判断应只影响“自愿移动触发借机”的链路，不影响：

- 强制位移
- 其他反应类型

### 清理策略

最小版在 `reset_turn_resources(...)` 时清理 actor 身上的 `disengage` effect。

理由：

- 它只应在“本回合剩余时间内”生效
- 到下个自己回合开始前，肯定已经失效

## 四、Dodge 设计

### 输入

`use_dodge.execute(...)`

- `encounter_id`
- `actor_id`

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `action_economy.action_used == false`
- actor 未失能到无法执行动作

### 结算

成功时：

- 消耗 `action_economy.action_used`
- 清理旧的 `dodge` effect
- 写入新的 `dodge` effect
- 返回最新 `encounter_state`

### 对攻击检定的影响

在 `AttackRollRequest` 里，解析攻击目标的劣势来源时新增：

- 若 target 有有效 `dodge` effect
- 且 target 当前看得见 attacker
- 且 target 未 `incapacitated`
- 且 target 当前速度不为 0

则加入：

- `vantage_sources["disadvantage"].append("dodge")`

### 对“看不见攻击者”的最小实现

第一版最小判断：

- 若 attacker 具有 `invisible` 条件，则 `Dodge` 不提供这条攻击劣势

本次不做：

- 视线遮挡
- 感知盲区
- 黑暗 / 遮蔽

### 对敏捷豁免的影响

在敏捷豁免请求链里新增：

- 若 target 有有效 `dodge` effect
- 且未 `incapacitated`
- 且当前速度不为 0

则该次敏捷豁免加入优势来源：

- `dodge`

### 失效条件

以下任一成立时，`Dodge` effect 视为存在但不生效：

- entity 具有 `incapacitated`
- entity 当前速度为 0

### 清理策略

在该实体下个自己回合开始时，由 `reset_turn_resources(...)` 清理 `dodge` effect。

这对应规则文本：

- “直至你的下个回合开始”

## 五、GetEncounterState 投影

### 当前行动者 / 先攻列表

`GetEncounterState` 中已有：

- `conditions`
- `ongoing_effects`

本次把 `Disengage` / `Dodge` 也投影进 `ongoing_effects`，例如：

- `["Disengage"]`
- `["Dodge"]`

### 为什么不单独开新字段

第一版没有必要专门新增：

- `is_dodging`
- `is_disengaged`

因为：

- 这两个状态本来就属于短时 effect
- `ongoing_effects` 足够给 LLM 和前端阅读

## 六、LLM 调用协议

### 1. 撤离

玩家说：

- “我撤离”
- “我脱离接触后跑开”
- “我不想吃借机，先跑”

LLM 应先调用：

```json
{
  "command": "use_disengage",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_sabur"
  }
}
```

若玩家还要继续移动，再单独调用移动工具。

`Disengage` 不自动移动。

### 2. 回避

玩家说：

- “我回避”
- “我全力防守”
- “我专心闪躲”

LLM 应调用：

```json
{
  "command": "use_dodge",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_sabur"
  }
}
```

后续不需要再额外声明攻击劣势或敏捷豁免优势，后端自动处理。

## 七、测试策略

### use_disengage

新增测试覆盖：

1. 自己回合可成功使用 `Disengage`
2. 成功后消耗动作
3. 成功后写入 `disengage` effect
4. 非自己回合拒绝
5. 已消耗动作时拒绝

### Disengage 对移动链

新增测试覆盖：

1. 已 `Disengage` 的移动不会打开借机窗口
2. 未 `Disengage` 的同类移动仍会打开借机窗口

### use_dodge

新增测试覆盖：

1. 自己回合可成功使用 `Dodge`
2. 成功后消耗动作
3. 成功后写入 `dodge` effect
4. 非自己回合拒绝
5. 已消耗动作时拒绝

### Dodge 对攻击链

新增测试覆盖：

1. 目标 `Dodge` 时，攻击检定获得劣势来源 `dodge`
2. 攻击者 `invisible` 时，这条 `dodge` 劣势不生效
3. 目标 `incapacitated` 时，这条 `dodge` 劣势不生效
4. 目标速度为 0 时，这条 `dodge` 劣势不生效

### Dodge 对敏捷豁免链

新增测试覆盖：

1. `Dodge` 让目标的敏捷豁免具有优势
2. `incapacitated` 时不生效
3. 速度为 0 时不生效

### GetEncounterState

新增测试覆盖：

1. `ongoing_effects` 正确显示 `Disengage`
2. `ongoing_effects` 正确显示 `Dodge`

## 八、后续扩展点

本次设计完成后，可以自然复用到：

- 盗贼 `Cunning Action -> Disengage`
- 武僧 `Patient Defense -> Dodge`
- 未来的 `Hide`
- 其他“声明动作后获得一个短时状态”的基础动作

换句话说，这次不是只为两个动作打补丁，而是在现有战斗运行态里补上一类非常典型的“动作触发型短时效果”模板。
