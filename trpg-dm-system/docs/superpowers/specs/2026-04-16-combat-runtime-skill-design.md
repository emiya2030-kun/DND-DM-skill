# 战斗运行 Skill 设计

日期：2026-04-16

## 目标

新增一个独立的战斗运行 skill，专门给真实 LLM 在战斗期使用。

它的职责不是重写后端规则 service，而是约束和编排这些 service 的调用顺序，让 LLM 能稳定地：

- 理解战斗中的玩家自然语言
- 在玩家、怪物、NPC 回合中做出合法行动
- 严格遵守当前 encounter 的状态与回合顺序
- 在每次状态变化后继续基于最新 `encounter_state` 推理

## 范围

这个新 skill 的定位是：

- 它是一个战斗期全体生物回合执行 skill
- 它负责两类执行：
  - 玩家回合：把玩家自然语言转成合法 tool 调用
  - 怪物/NPC 回合：由 LLM 基于当前战场状态做战术决策，再转成合法 tool 调用
- 它不负责战斗外内容：
  - 探索
  - 剧情推进
  - 社交
  - 长休
  - 战斗外施法
- 它不是底层规则 service 本身，而是建立在现有战斗 service 之上的运行协议
- 它不重新实现 `BeginMoveEncounterEntity`、`ExecuteAttack`、`ExecuteSpell` 等后端能力
- 它负责规定 LLM 在什么时候读状态、调用哪个 tool、何时必须中断等待、何时推进回合

## 设计原则

- 后端继续保留规则 service 作为事实源和执行层
- 新 skill 只收拢“LLM 应如何使用这些 service”
- skill 内只放协议、约束、例子、tool 目录，不搬运规则实现代码
- 每次 mutation tool 返回后，LLM 必须改用最新 `encounter_state`
- 不允许手工修改位置、HP、condition、resources、turn order

## 新 Skill 建议结构

建议新增独立 skill 目录：

- `combat-runtime/SKILL.md`
- `combat-runtime/references/runtime-protocol.md`
- `combat-runtime/references/tool-catalog.md`
- `combat-runtime/references/monster-turn-flow.md`
- `combat-runtime/references/companion-npc-turn-flow.md`
- `combat-runtime/references/intent-examples.md`

### `SKILL.md`

入口文件，只保留最重要的总原则：

- 先读状态
- 判断当前行动者
- 根据玩家输入或怪物决策选择动作
- 调用对应 tool
- 每次 mutation 后改用最新 `encounter_state`
- 回合结束走固定顺序

### `runtime-protocol.md`

最核心的运行协议文件，负责描述：

- 战斗开始前的先攻顺序建立要求
- 战斗内总循环
- 移动中断和 reaction 处理规则
- 回合推进规则
- 硬性禁令

### `tool-catalog.md`

列出主要 tool 的使用目录，不展开实现，只说明：

- 用途
- 什么时候调用
- 关键参数
- 常见返回
- 调用后 LLM 下一步该做什么

### `monster-turn-flow.md`

描述怪物/NPC 回合的最小合法战术协议：

- 先看当前目标和距离
- 再看是否能移动到有效位置
- 再选攻击、施法、撤退或结束回合
- 避免非法行动

第一版先保证合法和稳定，不追求复杂 AI。

### `companion-npc-turn-flow.md`

描述同伴 NPC 在玩家阵营中的战斗回合协议。

核心定位：

- 优先协助玩家阵营
- 不是等待命令的木偶
- 玩家没说时，也会主动做出合理战斗决策

第一版原则：

- 回合开始先读 `GetEncounterState`
- 若玩家已明确给出战术指令，则优先执行
- 若玩家未明确指挥，则自主采取合理行动
- 优先处理玩家当前正在交战或明显受威胁的目标
- 不抢主角位，不擅自做高风险剧情决定
- 仍然必须服从同一套 `runtime-protocol`

### `intent-examples.md`

提供高频战斗语句与合法调用范式，帮助 LLM 快速模仿：

- “我移动到(7,10)再砍兽人”
- “我疾跑到掩体后”
- “我用 3 环火球砸 (8,8)”
- “我放弃借机攻击”
- “我用反应进行借机攻击”

每个例子都应包含：

- 意图解析
- tool 顺序
- 中途如遇特殊返回应如何处理

说明：

- 这些例子不是对玩家输入做固定分类
- 玩家自然语言仍由 LLM 当场理解
- 例子的用途是帮助 LLM 参考合法调用顺序与中断处理范式

## 运行协议主流程

### 0. 建立战斗行动顺序

战斗开始时，必须先根据所有参战生物的先攻值建立行动顺序。

要求：

- 先生成并确认 `turn_order`
- 再确定 `current_turn_entity`
- 如果战斗已经在进行中，则直接读取现有 `turn_order`
- LLM 不自行手工写入先攻顺序，除非有明确的后端 service 支持

### 1. 战斗循环

在先攻顺序已经建立后，进入总循环：

1. 调用 `GetEncounterState`
2. 读取：
   - `turn_order`
   - `current_turn_entity`
   - 地图、位置、HP、conditions、ongoing effects、reaction requests
3. 判断当前轮到谁行动
4. 如果是玩家回合，则等待并解析玩家输入
5. 如果是怪物/NPC 回合，则由 LLM 基于状态做合法决策
6. 将本次意图拆解为一个或多个合法步骤
7. 按顺序调用对应 tool
8. 每次 tool 返回后，如状态变化，则立即改用新的 `encounter_state`
9. 当前生物明确结束回合时，按 `EndTurn -> AdvanceTurn -> StartTurn` 推进到下一位
10. 重复直到战斗结束

## 动作分解原则

- 一句自然语言不等于一次 tool 调用
- LLM 必须先拆意图，再执行
- 例如“我移动到 7,10 然后攻击兽人”应拆成：
  1. 移动
  2. 若移动成功且无待处理 reaction，重新读取或采用新状态
  3. 检查目标是否仍合法
  4. 再攻击

## 状态刷新原则

- 任何 mutation tool 返回后，旧推理立即失效
- 后续判断必须基于最新 `encounter_state`

以下场景必须重新判定：

- 移动后目标是否还在攻击或施法范围内
- 借机攻击后自己或目标是否仍存活
- 法术结算后目标是否新增 condition
- 推离或其他强制位移后站位是否变化
- 回合开始或结束触发后资源与状态是否变化

## 中断原则

- 只要 tool 返回 `waiting_reaction`，主流程必须暂停
- 这时不能继续移动、攻击、施法或结束回合
- 必须先处理 `reaction_request`
- 若 `ask_player = true`，LLM 不得替玩家决定
- 玩家放弃则继续主流程
- 玩家使用反应则先结算反应，再回到原流程

## 移动协议

- 任何主动移动都先经过 `BeginMoveEncounterEntity`
- 如果返回：
  - `completed`：才能继续后续动作
  - `waiting_reaction`：先处理中断
  - `blocked` 或 `failed`：向玩家解释原因，并停止这段移动后的后续动作
- 移动后如果原计划还有攻击或施法，必须重新核对：
  - 目标是否仍合法
  - 距离是否足够
  - 路径变化是否导致原计划失效

## 攻击与施法协议

攻击或施法前，必须先确认：

- 当前行动者仍是自己
- 目标仍存在且可作为合法目标
- 所需动作资源仍可用
- 范围、视线、触及等前提仍满足

若 tool 返回非法结构，不强行往下执行，而是告诉玩家原因并请求新决定。

## 回合推进协议

- `EndTurn` 只做“结束当前回合”
- `AdvanceTurn` 只做“先攻表推进到下一位”
- `StartTurn` 才做“下一位正式开始回合”的开始时结算
- 这三个顺序不能跳、不能合并理解

## 硬性禁令

- 不手工修改位置、HP、conditions、resources、turn order
- 不跳过等待中的 reaction
- 不在移动尚未完成时提前结算后续攻击、施法或其他动作
- 不用旧状态继续推理下一步
- 不替玩家决定需要确认的 reaction 或声明
- 不把“重新施法”和“转移已有持续法术目标”混为一谈

## 新增先攻初始化 Service 需求

为了让 `runtime-protocol` 真正闭环，当前项目还需要补一个战斗开始入口 service。

建议名：

- `RollInitiativeAndStartEncounter`

建议职责：

1. 读取所有参战实体
2. 计算每个实体的先攻结果
3. 生成 `turn_order`
4. 写入 `current_entity_id`
5. 立即触发一次 `StartTurn`

建议返回：

- `initiative_results`
- `turn_order`
- `current_entity_id`
- `encounter_state`

### 先攻排序规则

`RollInitiativeAndStartEncounter` 生成 `turn_order` 时，按以下顺序排序：

1. `initiative_total` 高者优先
2. 若相同，则 `initiative_modifier` 高者优先
3. 若仍相同，则比较一个仅限本次先攻使用的两位小数随机值

这个两位小数随机值的约束：

- 只用于本次先攻排序
- 不参与任何其他 d20 判定或伤害结算
- 作为内部排序字段存在
- 不对玩家或 LLM 的常规战斗播报展示

建议在运行时内部为每个实体保留以下先攻结果字段：

- `initiative_roll`
- `initiative_modifier`
- `initiative_total`
- `initiative_tiebreak_decimal`

### `RollInitiativeAndStartEncounter` 当前已确认规则

本次讨论已确认以下约束：

- 这是战斗开始入口 service，不是战斗中反复调用的普通回合工具
- 它的职责是：
  - 为当前参战实体掷先攻
  - 生成 `turn_order`
  - 设置 `current_entity_id`
  - 立即进入首个行动者的 `StartTurn`
- 先攻基础公式为：
  - `1d20 + 敏捷调整值`
- 排序规则为：
  1. `initiative_total` 高者优先
  2. 若相同，则 `initiative_modifier` 高者优先
  3. 若仍相同，则比较仅限本次先攻使用的两位小数随机值
- 这个两位小数随机值：
  - 只用于本次先攻排序
  - 不参与其他任何 d20 判定、伤害结算或规则裁定
  - 只作为内部排序字段保存
  - 不对玩家或常规战斗播报展示
- `RollInitiativeAndStartEncounter` 的返回中应至少包含：
  - `initiative_results`
  - `turn_order`
  - `current_entity_id`
  - `encounter_state`
- `initiative_results` 中应包含可供 LLM 播报的可见字段：
  - `initiative_roll`
  - `initiative_modifier`
  - `initiative_total`
- `initiative_tiebreak_decimal` 只保留为内部排序字段，不进入常规玩家播报

## 初始化遭遇战 Service 需求

为了让 LLM 能先布场、再开战，还需要一个遭遇战初始化入口。

建议名：

- `initialize_encounter`

它的定位不是自动设计战场，而是把 LLM 决定好的战斗配置写入运行态。

### `initialize_encounter` 的职责

- 刷新或装载当前战斗地图
- 填入本场参战实体
- 根据模板引用展开为完整运行态实体
- 应用本场遭遇战专属的覆盖值
- 清理旧战斗残留状态
- 返回新的完整 `encounter_state` 供前端整页重绘

### 输入结构

建议分为两大块：

- `map_setup`
- `entity_setups`

其中：

- `map_setup` 由 LLM 决定地图尺寸、地形、区域效果、地图备注等战场信息
- `entity_setups` 采用“模板引用 + 运行时覆盖值”的模式

每个实体应包含：

- `entity_instance_id`
- `template_ref`
- `runtime_overrides`

其中：

- `template_ref` 是基础事实源
- `runtime_overrides` 只属于这一次遭遇战实例

### `initialize_encounter` 的返回

建议至少包含：

- `encounter_id`
- `status`
- `initialized_entities`
- `map_summary`
- `encounter_state`

## 战斗开始时序

战斗正式开始前，LLM 应按以下顺序执行：

1. 根据剧情决定战场和参战者
2. 调 `initialize_encounter`
3. 页面刷新，玩家先看到战场
4. 进入先攻阶段，调 `RollInitiativeAndStartEncounter`
5. LLM 根据返回的 `initiative_results` 告诉玩家各生物的先攻值
6. 宣布先攻顺序与当前行动者
7. 进入正常战斗主循环

这里的边界必须明确：

- `initialize_encounter` = 布场
- `RollInitiativeAndStartEncounter` = 开战

两者不合并。

## 同伴 NPC 回合原则

同伴 NPC 与怪物都由 LLM 代为行动，但其战术目标不同。

### 同伴 NPC 的目标

- 优先保护玩家阵营利益
- 在玩家没有明确指挥时，也能主动做出合理战斗决策
- 默认辅助、补位、支援、集火，而不是抢戏

### 同伴 NPC 的决策倾向

- 近战同伴优先顶住逼近玩家的敌人，进行补位、卡位、夹击
- 远程或施法同伴优先处理高威胁后排，或控制对玩家最危险的敌人
- 支援型同伴优先救急，例如保护濒危玩家、补控制、补治疗、打断关键敌人

### 同伴 NPC 的自主决策边界

- 可以自主攻击、移动、支援、防御
- 可以根据局势自行选择合理目标
- 若玩家已明确下达战术指令，则优先执行该指令
- 不擅自替玩家做关键剧情选择
- 不无提示地浪费稀缺资源，除非局势已经明显危险

## 待补充问题

以下问题尚未在本文定稿，后续需要继续补完：

- `RollInitiativeAndStartEncounter` 的精确输入参数与完整返回 schema
- 怪物/NPC 回合的最低战术准则细节
- 玩家自然语言映射的高频例子模板
