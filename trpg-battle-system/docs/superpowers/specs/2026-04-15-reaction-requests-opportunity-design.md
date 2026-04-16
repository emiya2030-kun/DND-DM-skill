# Reaction Requests 与最小借机攻击设计

## 目标

为战斗系统增加一层**通用反应请求框架**，但第一批只实现一种反应：

- `opportunity_attack`

这层框架需要满足两个要求：

1. 现在能正确处理“移动途中触发借机攻击”
2. 以后可以继续接入其他反应，例如：
   - 护盾术
   - 反制法术
   - 其他职业/专长反应能力

---

## 本次范围

本次只做最小版：

- 通用 `reaction_requests`
- 通用 `pending_movement`
- `BeginMoveEncounterEntity`
- `ResolveReactionRequest`
- `ContinuePendingMovement`
- 第一种 reaction type：`opportunity_attack`

本次明确**不做**：

- 撤离
- 强制位移
- 长柄武器/额外触及
- 法术型反应
- 怪物之间互相借机
- 复杂职业特性改写
- “玩家稍后再决定”这种延迟反应

---

## 关键规则结论

### 1. 借机攻击是即时阻塞反应

一旦移动途中触发借机攻击：

- 当前移动流程必须暂停
- 必须先处理这次 reaction request
- 处理完成后，才允许继续后续移动

不能先把移动整段走完再回头问玩家。

原因：

- 如果借机攻击把目标打到 `0 HP`
- 那后续移动本来就不该发生

### 2. 多个借机按路径顺序结算

如果一次移动会依次离开多个敌人的近战触及：

- 按路径先后顺序逐个处理
- 不是按先攻顺序
- 也不是按距离最近优先

### 3. 被打断时停在中断点

如果处理到第 N 个借机时：

- 移动者被打到 `0 HP`
- 或不再能继续移动

则：

- 本次移动在第 N 个触发点对应位置中断
- 不回退到起点
- 也不继续走完整条路径

### 4. 阵营限制

第一版只允许“敌对双方”触发借机：

- 玩家/友军离开怪物触及，怪物可借机
- 怪物离开玩家/友军触及，玩家可借机
- 怪物之间不互相借机
- 友军之间不互相借机

---

## 运行时模型

### Encounter.reaction_requests

在 `Encounter` 顶层新增：

```json
{
  "reaction_requests": []
}
```

每条最小结构：

```json
{
  "request_id": "react_001",
  "reaction_type": "opportunity_attack",
  "trigger_type": "leave_melee_reach",
  "status": "pending",
  "actor_entity_id": "ent_ally_eric_001",
  "actor_name": "Eric",
  "target_entity_id": "ent_enemy_orc_001",
  "target_name": "Orc",
  "ask_player": true,
  "auto_resolve": false,
  "source_event_type": "movement_trigger_check",
  "source_event_id": null,
  "payload": {
    "weapon_id": "rapier",
    "weapon_name": "Rapier",
    "trigger_position": {"x": 5, "y": 4},
    "reason": "目标离开了你的近战触及"
  }
}
```

第一版 `status` 只支持：

- `pending`
- `resolved`
- `expired`

本次不单独实现 `declined`。

如果玩家不借机：

- 不单独写 `DeclineReactionRequest`
- 直接继续 pending movement
- 未处理的 request 会在继续流程时被标记为 `expired`

### Encounter.pending_movement

在 `Encounter` 顶层新增：

```json
{
  "pending_movement": null
}
```

有待处理中断移动时：

```json
{
  "movement_id": "move_001",
  "entity_id": "ent_enemy_orc_001",
  "start_position": {"x": 4, "y": 4},
  "target_position": {"x": 8, "y": 4},
  "current_position": {"x": 5, "y": 4},
  "remaining_path": [
    {"x": 6, "y": 4},
    {"x": 7, "y": 4},
    {"x": 8, "y": 4}
  ],
  "count_movement": true,
  "use_dash": false,
  "status": "waiting_reaction",
  "waiting_request_id": "react_001"
}
```

说明：

- `current_position`
  - 当前已经合法走到的位置
- `remaining_path`
  - 后续尚未走的路径
- `waiting_request_id`
  - 当前阻塞移动的 reaction request

第一版同一时刻只允许一个 `pending_movement`。

---

## 借机攻击判定边界

第一版借机攻击只满足以下条件时触发：

1. 移动者执行的是**自愿移动**
2. 移动路径某一步使其**离开敌对单位 5 尺近战触及**
3. 触发者与移动者属于敌对阵营
4. 触发者不是怪物对怪物，也不是友军对友军
5. 触发者 `reaction_used = false`
6. 触发者能进行攻击
7. 触发者有可用近战武器
8. 移动目标仍然合法

第一版默认武器选择：

- 第一把可用近战武器

---

## 玩家与怪物的处理差异

### 玩家可借机

如果触发者是玩家控制角色：

- 生成 `reaction_request`
- 不自动结算
- LLM 必须立刻询问玩家：
  - 是否使用借机攻击
- 在玩家回应前，移动不能继续

### 怪物可借机

如果触发者是怪物：

- 第一版仍走同一套 `reaction_request`
- 但 `auto_resolve = true`
- 上层流程可直接自动调用 `ResolveReactionRequest`

这样保持结构统一，不单独分叉一套怪物专用逻辑。

---

## Service 设计

### 1. BeginMoveEncounterEntity

职责：

- 接收一次移动意图
- 计算完整路径
- 沿路径逐步检查反应触发点
- 若没有反应，直接完成整段移动
- 若出现第一个阻塞反应：
  - 只把移动推进到触发点
  - 写入 `pending_movement`
  - 追加 `reaction_request`
  - 返回“等待反应处理”

返回重点：

- `movement_status`
  - `completed`
  - `waiting_reaction`
- `reaction_requests`
- `encounter_state`

### 2. ResolveReactionRequest

职责：

- 处理一个 `pending` 的 reaction request
- 第一版只支持：
  - `reaction_type = opportunity_attack`

行为：

- 校验 request 合法
- 校验触发者反应未使用
- 消耗 `reaction_used`
- 调用现有攻击链结算最小近战攻击
- request 标记为 `resolved`

重要：

- 借机攻击不消耗 `action`
- 借机攻击不消耗 `bonus_action`

### 3. ContinuePendingMovement

职责：

- 在当前阻塞 reaction 处理完后继续剩余移动
- 若后续路径再次触发 reaction：
  - 再次暂停
  - 生成下一个 request
- 若不再触发：
  - 完成整段移动
  - 清空 `pending_movement`

如果上一个 reaction 没有真正执行：

- 视为跳过
- 对应 request 标记为 `expired`
- 然后继续移动

---

## 为什么不做 DeclineReactionRequest

本次不单独实现 `DeclineReactionRequest`。

原因：

- 最小版里“玩家不借机”只是一种继续移动的分支
- 不值得专门多加一个 tool
- 由 `ContinuePendingMovement` 统一把当前阻塞 request 标成 `expired` 即可

---

## 和现有链路的关系

### 和 MoveEncounterEntity 的关系

`MoveEncounterEntity` 目前是“一次性完成移动”的 service。

本次不建议直接在它内部硬塞完整反应流程。

建议：

- 保留它作为“无中断整段移动”的低层 service
- 新增 `BeginMoveEncounterEntity` / `ContinuePendingMovement`
- 由新入口负责：
  - 分段推进
  - reaction request 管理
  - 必要时调用底层移动逻辑

### 和攻击链的关系

`ResolveReactionRequest` 第一版最终复用现有攻击链。

区别只在上下文：

- 这是 reaction 攻击
- 不是普通 action 攻击

所以：

- 要消耗 `reaction_used`
- 不能消耗 `action_used`

---

## LLM 工作流

第一版推荐工作流：

1. LLM 调 `BeginMoveEncounterEntity`
2. 如果结果是 `completed`
   - 直接刷新状态
3. 如果结果是 `waiting_reaction`
   - 看 `reaction_requests`
   - 若 `ask_player = true`，立刻询问玩家是否借机
4. 如果玩家回答“要”
   - 调 `ResolveReactionRequest`
5. 如果玩家回答“不要”
   - 直接调 `ContinuePendingMovement`
6. 重复直到移动完成或被中断

---

## 测试范围

第一版至少覆盖：

1. 敌人离开玩家触及时，生成 `pending` 借机请求
2. 玩家不借机时，`ContinuePendingMovement` 会继续移动
3. 玩家借机命中但未打倒目标时，移动继续
4. 玩家借机把目标打到 `0 HP` 时，移动中断在触发点
5. 多个借机按路径顺序逐个触发
6. 怪物之间不互相借机
7. 触发者 `reaction_used = true` 时不生成请求
8. `ResolveReactionRequest` 只消耗反应，不消耗动作

---

## 本次完成后的收益

完成这一层后，系统将首次具备：

- 真实“移动中断”
- 真实“即时反应”
- 真实“路径顺序借机结算”

同时保留以后扩展空间：

- 受到攻击时触发的反应
- 施法时触发的反应
- 职业特性反应
- 法术型反应
