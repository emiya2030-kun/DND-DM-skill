# Runtime Execute Attack Command Design

## 目标

新增一个独立的 runtime command: `execute_attack`，作为战斗期所有武器攻击的统一入口。

这个 command 覆盖以下场景：

- 当前回合中的普通攻击
- 轻型额外攻击
- 投掷攻击
- 借机攻击等回合外攻击

它不负责移动，不负责更高层自然语言解析，只负责把结构化攻击意图转交给现有 `ExecuteAttack` service，并把结果包装成 runtime 标准返回。

## 为什么这样做

当前 runtime 已有：

- `move_and_attack`
- `cast_spell`
- `end_turn_and_advance`
- `start_random_encounter`

其中 `move_and_attack` 已经能复用 `ExecuteAttack`，但“原地攻击”或“借机攻击”仍缺少独立入口。继续把所有攻击都塞进 `move_and_attack` 会造成两个问题：

1. 语义不准确。很多攻击并不伴随移动。
2. LLM 调用协议不统一。以后同一轮里出现“普通攻击 + 轻型补刀 + 借机攻击”时，缺少稳定的统一 command。

因此需要一个单独的 runtime command，把所有武器攻击汇总到同一个外部协议上。

## 非目标

本次不做以下内容：

- 不新增“战斗动作总线”或 `perform_combat_action`
- 不处理法术施法，仍由 `cast_spell` 负责
- 不改变 `ExecuteAttack` 现有规则判定边界
- 不移除 `move_and_attack`
- 不为前端新增按钮层

## 方案对比

### 方案 A：单一 `execute_attack` command

通过一个 command 覆盖普通攻击、轻型额外攻击、投掷攻击、借机攻击。

优点：

- LLM 记忆成本最低
- runtime command 边界和底层 `ExecuteAttack` 一致
- 后续新增职业特性时更容易继续扩参数，而不是扩 command 数量

缺点：

- 参数较多，需要明确哪些有默认值

### 方案 B：拆成多个 command

例如：

- `execute_attack`
- `execute_opportunity_attack`
- `execute_bonus_attack`

优点：

- 每个 command 语义单纯

缺点：

- 参数与逻辑高度重复
- LLM 更容易选错 command
- 后续 command 数量会膨胀

### 方案 C：更高层统一战斗动作入口

例如 `perform_combat_action`

优点：

- 长期可能更像完整宿主协议

缺点：

- 当前范围过大
- 会把攻击、施法、移动、资源消耗全部混成一层

## 结论

采用方案 A。

## Command 契约

### Command Name

`execute_attack`

### 必填参数

- `encounter_id`
- `actor_id`
- `target_id`
- `weapon_id`

### 可选参数

- `attack_mode`
  - `default`
  - `light_bonus`
  - `thrown`
- `grip_mode`
  - `default`
  - `one_handed`
  - `two_handed`
- `vantage`
  - `normal`
  - `advantage`
  - `disadvantage`
- `description`
- `zero_hp_intent`
  - 例如 `knockout`
- `allow_out_of_turn_actor`
  - 默认 `false`
- `consume_action`
  - 默认 `true`
- `consume_reaction`
  - 默认 `false`
- `consume_bonus_action`
  - 不作为 runtime 参数暴露；仍由 `ExecuteAttack` 内部根据 `attack_mode=light_bonus` 自动决定
- `damage_rolls`
  - 仅保留为低层覆盖入口
  - runtime 正常使用不要求传入
- `include_encounter_state`
  - runtime command 固定返回 encounter state，不对外暴露

### 默认行为

如果外部不传攻击骰与伤害骰：

- 由后端自动掷攻击骰
- 由后端自动掷伤害骰
- 返回结构化命中/伤害结果

这与当前 `ExecuteAttack` 已实现的自动掷骰能力保持一致。

## 参数语义

### 普通攻击

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_demo",
    "actor_id": "pc_sabur",
    "target_id": "enemy_raider_1",
    "weapon_id": "longbow"
  }
}
```

### 轻型额外攻击

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_demo",
    "actor_id": "pc_sabur",
    "target_id": "enemy_raider_1",
    "weapon_id": "dagger",
    "attack_mode": "light_bonus"
  }
}
```

### 投掷攻击

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_demo",
    "actor_id": "pc_sabur",
    "target_id": "enemy_raider_1",
    "weapon_id": "dagger",
    "attack_mode": "thrown"
  }
}
```

### 借机攻击

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_demo",
    "actor_id": "pc_sabur",
    "target_id": "enemy_raider_1",
    "weapon_id": "shortsword",
    "allow_out_of_turn_actor": true,
    "consume_action": false,
    "consume_reaction": true
  }
}
```

## 返回结构

沿用现有 runtime 包装格式：

```json
{
  "ok": true,
  "command": "execute_attack",
  "result": {
    "encounter_id": "enc_demo",
    "attack_result": {
      "...": "ExecuteAttack 原始结果"
    }
  },
  "encounter_state": {
    "...": "最新 encounter state"
  }
}
```

### 失败路径

分两类：

1. 参数缺失或格式不合法
   - 由 runtime dispatcher 返回 `ok: false`
2. 攻击非法但属于规则内可恢复情形
   - 例如目标不在范围内、视线被挡、动作已用完
   - 由 `ExecuteAttack` 返回 `status=invalid_attack`
   - runtime command 继续包装成成功 command 调用结果，但 `result.attack_result` 保留该结构化非法结果

这样 LLM 能继续根据 `message_for_llm` 做后续决策，而不是把规则非法混成 transport error。

## 与 move_and_attack 的关系

`move_and_attack` 保留，职责不变：

1. 先处理移动
2. 若没有反应中断，再调用攻击

实现上可以继续直接调用 `ExecuteAttack`，也可以转为复用 runtime 层内部公共辅助函数。

本次优先保持最小改动，不强制重构 `move_and_attack` 去调用新的 runtime command。

## 实现边界

新增文件：

- `runtime/commands/execute_attack.py`

修改文件：

- `runtime/commands/__init__.py`
- 相关 runtime 测试

`runtime/commands/execute_attack.py` 只做：

- 参数读取与基础校验
- 创建 `AppendEvent`
- 创建 `ExecuteAttack`
- 固定 `include_encounter_state=True`
- 返回标准 runtime payload

它不复制规则逻辑，不单独实现命中/伤害判定。

## 测试设计

至少覆盖以下用例：

1. 普通攻击
   - 不传攻击骰
   - 后端自动掷骰
   - 返回 attack_result 和 encounter_state

2. 借机攻击
   - `allow_out_of_turn_actor=true`
   - `consume_action=false`
   - `consume_reaction=true`
   - 验证 reaction 被消耗

3. 轻型额外攻击
   - `attack_mode=light_bonus`
   - 验证 bonus action 相关规则仍由底层处理

4. 投掷攻击
   - `attack_mode=thrown`
   - 验证命令参数被正确传入底层

5. 非法攻击
   - 底层返回 `invalid_attack`
   - runtime 仍返回标准 payload，而不是抛 transport error

6. 参数缺失
   - 缺少 `encounter_id` / `actor_id` / `target_id` / `weapon_id`
   - 返回 dispatcher 的结构化错误

## 风险与约束

### 风险 1：runtime command 与 move_and_attack 行为不一致

约束：

- 两者都直接依赖同一个 `ExecuteAttack` service
- 不在 runtime command 内复制规则

### 风险 2：LLM 混淆动作消耗参数

约束：

- 借机攻击明确要求：
  - `allow_out_of_turn_actor=true`
  - `consume_action=false`
  - `consume_reaction=true`
- 普通攻击默认：
  - `consume_action=true`
  - `consume_reaction=false`

### 风险 3：低层覆盖参数破坏默认体验

约束：

- `damage_rolls` 仅作为保留入口
- 正常 runtime 使用说明中不推荐传这些低层骰值

## 成功标准

完成后，LLM 可以直接调用：

- 普通攻击：`execute_attack`
- 借机攻击：`execute_attack`
- 轻型额外攻击：`execute_attack`
- 投掷攻击：`execute_attack`

且这些调用都不再需要外部手动提供攻击骰与伤害骰。
