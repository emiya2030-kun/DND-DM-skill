# Battle Runtime HTTP Design

## 背景

当前战斗系统虽然已经具备较完整的底层 service：

- `initialize_encounter`
- `RollInitiativeAndStartEncounter`
- `BeginMoveEncounterEntity`
- `ExecuteAttack`
- `ExecuteSpell`
- `EndTurn / AdvanceTurn / StartTurn`

但实际运行时仍存在两个明显问题：

1. LLM 或调试流程经常通过临时 `python3` 进程拼接多个 service，固定开销过大。
2. LLM 需要自己理解并编排很多底层步骤，容易慢，也容易在多步流程中出错。

因此需要引入一个 **常驻 battle runtime HTTP 服务**，并在其上提供少量 **高层命令型 API**，作为 battlemap、真实 LLM skill、未来宿主层的统一运行入口。

## 目标

第一版 battle runtime 要解决三件事：

1. 让战斗动作不再依赖“每次临时起一个 Python 进程”。
2. 把常用的多步战斗动作收敛为高层 command，降低 LLM 编排复杂度。
3. 保持 `encounter_state` 仍然是页面和 LLM 的唯一事实源。

## 非目标

第一版明确不做：

- websocket 或双向推送
- 全自动怪物 AI 战斗循环
- 完整自然语言解析
- 一次性高层化全部底层 service
- 替换现有底层 service 实现

第一版只建立 runtime 框架，并落地最有价值的三个高层命令。

## 总体架构

### 1. 新增常驻 HTTP runtime 进程

新增脚本：

- `scripts/run_battle_runtime.py`

该进程在启动后常驻内存，内部长期持有：

- `EncounterRepository`
- `EventRepository`
- `EntityDefinitionRepository`
- `SpellDefinitionRepository`
- 常用 service 实例

该进程负责接收命令请求、调用现有底层 service、返回结构化结果与最新 `encounter_state`。

### 2. 使用统一命令入口

只暴露一个主入口：

- `POST /runtime/command`

请求格式统一为：

```json
{
  "command": "move_and_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "ent_ally_ranger_001",
    "target_position": {"x": 6, "y": 10},
    "target_id": "ent_enemy_raider_001",
    "weapon_id": "shortbow"
  }
}
```

返回格式统一为：

```json
{
  "ok": true,
  "command": "move_and_attack",
  "result": {
    "movement_result": {...},
    "attack_result": {...}
  },
  "encounter_state": {...}
}
```

错误返回统一为：

```json
{
  "ok": false,
  "command": "move_and_attack",
  "error_code": "blocked_by_wall",
  "message": "移动路径被墙阻挡",
  "result": null,
  "encounter_state": {...}
}
```

如果错误发生时无法安全读取状态，则 `encounter_state` 可以为 `null`，但应优先返回最新状态。

### 3. 保持现有分层

battle runtime 不重写战斗规则。它只做：

- 参数校验
- 命令分发
- 多个底层 service 的编排
- 错误归一化
- 状态返回统一化

具体规则仍由原有 service 负责，例如：

- 移动合法性：`BeginMoveEncounterEntity`
- 攻击合法性与伤害：`ExecuteAttack`
- 施法：`ExecuteSpell`
- 回合推进：`EndTurn / AdvanceTurn / StartTurn`

## 第一版命令集

### 1. `start_random_encounter`

用途：

- 为指定 `encounter_id` 创建或覆盖一场随机遭遇战
- 初始化地图
- 放入参战者
- 掷先攻并进入首回合

请求：

```json
{
  "command": "start_random_encounter",
  "args": {
    "encounter_id": "enc_preview_demo",
    "theme": "swamp_road"
  }
}
```

说明：

- `theme` 第一版可以是可选参数
- 若未提供，则 runtime 自行从少量预设主题中随机选择
- 第一版允许只用已有模板实体随机组合，不要求完整怪物库

内部流程：

1. 选择一个随机战场模板
2. 选择一组随机参战者模板
3. 调 `EncounterService.initialize_encounter`
4. 调 `RollInitiativeAndStartEncounter.execute_with_state`
5. 返回 `initiative_results + encounter_state`

返回结果中 `result` 至少包含：

- `encounter_name`
- `map_name`
- `initiative_results`
- `turn_order`
- `current_entity_id`

### 2. `move_and_attack`

用途：

- 收口一次“先移动，再攻击”的高频战斗动作

请求：

```json
{
  "command": "move_and_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "ent_ally_ranger_001",
    "target_position": {"x": 6, "y": 10},
    "target_id": "ent_enemy_raider_001",
    "weapon_id": "shortbow"
  }
}
```

内部流程：

1. 调 `BeginMoveEncounterEntity.execute_with_state`
2. 若返回 `movement_status == "waiting_reaction"`：
   - 立即停止
   - 原样返回等待态
   - 不提前执行攻击
3. 若移动完成：
   - 用最新 encounter 状态继续
   - 调 `ExecuteAttack.execute`
4. 返回攻击结果与最新 `encounter_state`

返回结构中 `result` 至少包含：

- `movement_result`
- `attack_result`

特殊情况：

- 若移动成功但攻击非法，例如目标已超出射程，应返回：
  - `ok: false`
  - `error_code: "attack_invalid_after_movement"`
  - 并附带攻击链返回的结构化错误详情
- 此时移动结果仍然保留，因为移动已经发生

### 3. `end_turn_and_advance`

用途：

- 固定执行一次完整的回合结束与回合推进

请求：

```json
{
  "command": "end_turn_and_advance",
  "args": {
    "encounter_id": "enc_preview_demo"
  }
}
```

内部流程：

1. `EndTurn.execute_with_state`
2. `AdvanceTurn.execute_with_state`
3. `StartTurn.execute_with_state`
4. 返回新的 `current_turn_entity`

返回结构中 `result` 至少包含：

- `ended_entity_id`
- `current_entity_id`
- `round`
- `turn_effect_resolutions`

## HTTP 接口设计

### `POST /runtime/command`

职责：

- battle runtime 的统一命令入口

请求字段：

- `command: str`
- `args: dict`

基础错误码：

- `unknown_command`
- `invalid_args`
- `internal_error`

运行类错误码直接透传或归一化自底层 service，例如：

- `actor_not_current_turn_entity`
- `blocked_by_wall`
- `insufficient_movement`
- `target_out_of_range`
- `waiting_reaction`
- `attack_invalid_after_movement`

### `GET /runtime/health`

职责：

- 返回 runtime 是否存活
- 用于 battlemap dev 模式和宿主探活

返回：

```json
{
  "ok": true,
  "service": "battle_runtime"
}
```

### `GET /runtime/encounter-state?encounter_id=...`

职责：

- 直接读取最新 `encounter_state`

说明：

- 这是 runtime 版状态读取入口
- battlemap 页面后续应优先从这里取状态
- 这样页面就与 runtime 使用同一事实源通道

## battlemap 接入方式

### 当前问题

当前 battlemap localhost 页面直接从仓储读取 encounter，并轮询 `/api/encounter-state`。

这能工作，但 battle 控制动作仍然主要依赖外部临时脚本修改状态。

### 第一版接入目标

battlemap 页面保持“只负责展示”，但读取路径改为统一走 runtime：

- 页面轮询：`GET /runtime/encounter-state`
- 调试或宿主动作：`POST /runtime/command`

这样 battlemap 页面不会直接负责编排战斗步骤，只展示 runtime 产出的状态。

### 开发模式关系

第一版可以保持两个进程：

1. `run_battlemap_dev.py`
   - 负责页面热重载
2. `run_battle_runtime.py`
   - 负责战斗命令和 encounter_state

后续可考虑让 dev supervisor 顺带拉起 runtime worker，但不是第一版必需项。

## 模块拆分建议

### 新增目录

- `runtime/`

第一版建议结构：

- `runtime/server.py`
  - HTTP handler
  - 路由分发
- `runtime/command_dispatcher.py`
  - 命令注册与分发
- `runtime/command_context.py`
  - 统一持有 repositories 与常用 services
- `runtime/commands/start_random_encounter.py`
  - 高层命令实现
- `runtime/commands/move_and_attack.py`
  - 高层命令实现
- `runtime/commands/end_turn_and_advance.py`
  - 高层命令实现
- `runtime/response.py`
  - 统一结果结构构造

### 设计原则

- 每个 command 文件只负责一个高层动作
- dispatcher 不写业务规则，只做注册和调用
- command_context 负责复用 repository / service 实例，避免每次请求重建
- response 工具统一构造：
  - `ok`
  - `command`
  - `result`
  - `error_code`
  - `message`
  - `encounter_state`

## 随机遭遇战生成策略

第一版只要求最小正确版，不做复杂生成器。

### 地图来源

第一版使用少量预设主题模板，例如：

- `swamp_road`
- `forest_ambush`
- `bridge_hold`

每个模板包含：

- 地图尺寸
- 地形格
- 区域效果
- 战场备注
- 初始出生点建议

### 实体来源

第一版直接从已有 `entity_definitions.json` 中选模板组合。

例如：

- 友方：
  - `pc_sabur`
  - `pc_miren`
  - 可选 `npc_companion_guard`
- 敌方：
  - 现阶段先允许重复使用 `monster_sabur` 模板并覆盖名称、HP、位置

这不是最终怪物系统，只是第一版高层命令的可运行来源。

## 命令返回约束

runtime 的所有命令必须遵守以下统一约束：

1. 成功时总是返回最新 `encounter_state`
2. 可恢复错误时尽量也返回最新 `encounter_state`
3. 不直接返回“前端 patch 指令”
4. 不手工拼 UI 结构
5. 所有状态展示仍以 `GetEncounterState` 为准

## 与现有 runtime-protocol 的关系

新的 battle runtime 不替代当前 `combat-runtime` 规则文档，而是把其中高频步骤收口。

### 原协议继续保留

例如：

- 每次 mutation 后必须使用最新状态
- `waiting_reaction` 必须优先处理
- 不允许跳过回合推进顺序

### 新的执行建议

对于高频动作，LLM 以后应优先调用高层 command，而不是手工编排底层 service。

例如：

- “移动到墙边然后攻击”  
  优先 `move_and_attack`

- “结束回合”  
  优先 `end_turn_and_advance`

- “来一场随机遭遇战”  
  优先 `start_random_encounter`

复杂特例仍允许回退到底层 service。

## 错误处理

### command 分发层错误

- command 不存在
- args 缺字段
- args 类型错误

这些由 dispatcher 直接返回统一错误。

### 业务错误

例如：

- actor 不是当前行动者
- 移动被墙挡住
- 攻击目标不合法
- 法术位不足

这些优先保留底层错误码语义，避免 LLM 看不懂。

### reaction 中断

`move_and_attack` 中如果移动阶段返回 `waiting_reaction`，必须：

- 不再继续攻击
- 把 `reaction_requests`
- `pending_movement`
- `encounter_state`
  一并返回给调用方

这是第一版的硬约束。

## 测试策略

第一版需要三层测试：

### 1. command 单元测试

分别测试：

- `start_random_encounter`
- `move_and_attack`
- `end_turn_and_advance`

验证：

- 返回结构
- 调用顺序
- 遇到 reaction 时提前停止

### 2. runtime HTTP 测试

测试：

- `POST /runtime/command`
- `GET /runtime/health`
- `GET /runtime/encounter-state`

验证：

- JSON 结构正确
- 错误码正确
- 状态能被正确返回

### 3. battlemap 集成测试

验证 battlemap 页面能从 runtime 读取 encounter_state，而不是依赖临时脚本落库后手工刷新。

## 风险与约束

### 风险 1：高层 command 范围膨胀

如果第一版就试图把所有战斗动作都高层化，runtime 会迅速失控。

控制策略：

- 第一版只做 3 个 command

### 风险 2：battlemap 与 runtime 出现双事实源

如果页面仍直接读仓储，而命令走 runtime，后续边界会混乱。

控制策略：

- 页面读取路径逐步切到 runtime 提供的状态接口

### 风险 3：command 内部绕过现有规则

如果 command 直接手改 encounter，会破坏现有规则系统。

控制策略：

- command 只调用现有底层 service，不手写规则结算

## 实施顺序

建议实现顺序：

1. 新建 runtime server 骨架与统一响应结构
2. 实现 `GET /runtime/health`
3. 实现 `GET /runtime/encounter-state`
4. 实现 `start_random_encounter`
5. 实现 `end_turn_and_advance`
6. 实现 `move_and_attack`
7. 让 battlemap 页面切到 runtime 状态读取
8. 更新 `SKILL.md` 与 runtime guide

## 结论

第一版 battle runtime 应采用：

- **常驻 HTTP 进程**
- **命令型 API**
- **少量高层 command**
- **现有底层 service 复用**

这能同时解决当前最核心的两个问题：

1. 性能上，不再依赖每次临时启动 Python 进程
2. 运行上，LLM 不必每次都手工编排底层 service

而且这条路径与“未来给真实 LLM skill 使用”的目标一致，不会把 battlemap demo 变成唯一宿主。
