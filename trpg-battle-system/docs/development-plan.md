# Development Plan

## 目标

这份文档记录 `trpg-battle-system` 当前已经完成的开发范围、各阶段落地状态，以及接下来最自然的开发优先级。

它不重复定义底层数据结构契约；模型与运行时结构以仓库内实际代码和测试为准。

## 开发原则

1. 先做可验证闭环，再补复杂规则。
2. 优先让后端独立完成规则结算，不依赖 LLM 手工补算。
3. `request / resolve / update / execute` 分层保持清晰，避免大而全的魔法入口。
4. 前端与 `GetEncounterState` 只看摘要和投影，不暴露不必要的内部运行细节。
5. 每一条规则都尽量有对应测试，避免“看起来能跑”的空实现。
6. 反应、持续效果、职业特性优先挂到既有主链，不额外造平行系统。

## 当前总览

当前系统已经从“遭遇战 schema + 基础服务”推进到“可运行战斗 runtime”。

已经完成的核心闭环包括：

- 遭遇战初始化
- 先攻与回合顺序
- 回合开始 / 结束 / 推进
- 移动、中断移动、借机攻击
- 完整攻击执行链
- 完整施法执行链
- 条件、伤害、专注、死亡豁免
- 区域效果、法术区域、强制位移
- 武器 / 护甲知识库与规则基础
- reaction runtime
- battle runtime 常驻服务
- 前端战场展示与事件日志侧栏
- 部分战士 / 武僧 / 盗贼职业特性

全量测试当前状态：

- `python3 -m unittest discover -s test -v`
- 最近一次结果：`576 tests OK`

## 阶段划分与状态

### 阶段 1: 数据骨架

状态：`已完成`

已完成内容：

1. 核心模型
   - `Encounter`
   - `EncounterEntity`
   - `EncounterMap`
   - `Event`
   - `RollRequest`
   - `RollResult`
2. 基础校验
   - `entity_id` 唯一
   - `current_entity_id` 必须存在
   - `turn_order` 必须引用有效实体
3. 仓储读写
   - encounter repository
   - event repository
4. 模型与仓储测试
   - roundtrip
   - 非法结构拒绝
   - 持久化 / 读取稳定

完成标准：

- encounter 可稳定落库、读回、校验

### 阶段 2: Encounter 管理能力

状态：`已完成`

已完成内容：

1. 实体管理
   - `initialize_encounter`
   - `add_entity`
   - `remove_entity`
   - `update_entity_position`
   - `update_entity_hp`
2. 回合管理
   - `StartTurn`
   - `EndTurn`
   - `AdvanceTurn`
   - `RollInitiativeAndStartEncounter`
3. 地图管理
   - 地图尺寸
   - 地形格
   - 区域效果
   - 地图备注
4. 运行时 encounter 初始化
   - 根据 LLM 提供的战场与参战者生成实际 encounter

完成标准：

- 系统能知道战场上有谁、现在轮到谁、地图上发生了什么

### 阶段 3: 视图层投影

状态：`已完成`

已完成内容：

1. `GetEncounterState`
   - `current_turn_entity`
   - `turn_order`
   - `battlemap_details`
   - `encounter_notes`
2. 可读视图投影
   - HP / AC / speed / conditions
   - 武器与法术摘要
   - 法术持续效果摘要
   - pending reaction / pending movement
   - death saves / recent activity
3. 前端投影
   - battlemap view
   - 先攻表
   - 最近事件日志
   - 区域与法术 overlay

完成标准：

- LLM 和前端都能从统一 state 读取稳定战斗信息

### 阶段 4: 事件日志系统

状态：`已完成`

已完成内容：

1. 事件存储
   - `append_event`
   - `list_by_encounter`
2. 首批事件类型
   - `turn_started`
   - `turn_ended`
   - `movement_resolved`
   - `attack_resolved`
   - `damage_applied`
   - `saving_throw_resolved`
   - `spell_declared`
   - `turn_effect_resolved`
   - 其他战斗相关事件
3. recent activity 投影
   - 最近战斗行为摘要
   - 强制位移摘要
   - turn effect 摘要

完成标准：

- 系统能记录“发生了什么”，并投影到前端 / LLM 摘要

### 阶段 5: Roll 流程

状态：`已完成`

已完成内容：

1. 攻击请求与结算
   - `AttackRollRequest`
   - `AttackRollResult`
   - `ExecuteAttack`
2. 豁免请求与结算
   - `SavingThrowRequest`
   - `ResolveSavingThrow`
   - `SavingThrowResult`
   - `ExecuteSaveSpell`
3. 专注检定
   - request / resolve / result / execute 全链路
4. 后端自动掷骰
   - d20
   - 伤害骰
   - 法术豁免

完成标准：

- 攻击、豁免、伤害、专注已形成完整自动结算闭环

### 阶段 6: 基础规则层

状态：`已完成`

已完成内容：

1. 动作经济
   - `action`
   - `bonus_action`
   - `reaction`
   - movement
2. 移动与距离
   - 基础距离判定
   - 斜角 5/10
   - 困难地形
   - prone crawl
   - 力竭速度惩罚
3. 伤害结算
   - temp hp
   - resistance
   - vulnerability
   - immunity
4. conditions
   - 标准 condition 写入 / 移除
   - sourced condition
   - exhaustion 层级
5. resources
   - spell slots
   - 职业能力次数
   - focus points

完成标准：

- 常见单体战斗规则无需 LLM 额外手算

### 阶段 7: 扩展规则与内容能力

状态：`大部分已完成，仍在继续扩展`

已完成内容：

1. 法术与豁免
   - save-damage
   - save-condition
   - attack-roll spell
   - no-roll spell
   - 升环施法
2. concentration
   - 受伤专注检定
   - 失败终止专注
   - 0 HP / 失能终止专注
3. AoE 和多目标
   - 多目标豁免
   - 区域伤害
   - 法术球形区域
4. 临时实体与战场变化
   - encounter 中动态增删实体
   - summon 0 HP 移除
   - monster 0 HP 留骷髅残骸
5. reaction framework
   - 借机攻击
   - Shield
   - Counterspell
   - Indomitable
   - Deflect Attacks
6. 强制位移
   - Push
   - 通用 forced movement service
   - 不触发借机攻击
7. 区域与 zone
   - zone definitions
   - start / end / enter trigger
   - 困难地形区域

仍待继续扩展的方向：

- 更多 reaction 模板
- 更多职业特性与子职
- 更复杂的战斗外施法与探索期逻辑

## 已完成能力清单

### 战斗主循环

- [x] 初始化遭遇战
- [x] 掷先攻并开始战斗
- [x] 宣布 turn order
- [x] 回合开始刷新
- [x] 回合结束自动结算
- [x] 推进到下一行动者

### 移动与位置

- [x] 正常移动
- [x] Dash
- [x] 剩余移动力计算
- [x] 对角移动 5/10
- [x] 困难地形
- [x] prone crawl
- [x] begin / continue pending movement
- [x] 被反应打断的移动
- [x] 强制位移

### 攻击

- [x] 攻击请求合法性校验
- [x] 武器命中结算
- [x] 自动伤害掷骰
- [x] 自动 HP 结算
- [x] 非法攻击结构化返回
- [x] 攻击动作消耗
- [x] 贴脸远程劣势
- [x] two-handed 基础限制

### 借机攻击与反应

- [x] 借机攻击触发
- [x] 玩家反应请求
- [x] 怪物自动反应
- [x] Shield
- [x] Counterspell
- [x] Indomitable
- [x] Deflect Attacks
- [x] 13级 Deflect Energy 触发窗口

### 武器与护甲

- [x] weapon definitions repository
- [x] armor definitions repository
- [x] finesse
- [x] heavy
- [x] reach
- [x] thrown
- [x] versatile
- [x] light
- [x] nick
- [x] loading 基础限制
- [x] armor training 基础
- [x] shield 基础

### 武器精通

- [x] vex
- [x] sap
- [x] slow
- [x] topple
- [x] graze
- [x] push

### 法术系统

- [x] SpellRequest
- [x] ExecuteSpell
- [x] Fireball
- [x] Hex
- [x] Hold Person
- [x] Hunter’s Mark
- [x] Shield
- [x] Counterspell
- [x] Eldritch Blast
- [x] spell instances
- [x] turn effect instances
- [x] spell area overlay

### 持续效果与区域

- [x] start_of_turn effect
- [x] end_of_turn effect
- [x] repeat save effect
- [x] concentration break cleanup
- [x] zone enter/start/end effect
- [x] difficult terrain zones

### 生命值、倒地与死亡

- [x] temp hp
- [x] resistance / vulnerability / immunity
- [x] 0 HP
- [x] dying / unconscious / stable / dead
- [x] death saving throws
- [x] massive damage death
- [x] knockout intent
- [x] concentration ends on incapacitated or 0 HP

### 职业特性

- [x] Fighter
  - [x] Extra Attack
  - [x] Second Wind
  - [x] Tactical Shift
  - [x] Action Surge 基础接线
  - [x] Indomitable
  - [x] Studied Attacks
  - [x] Tactical Master
- [x] Monk
  - [x] Martial Arts 基础接线
  - [x] Unarmored Defense
  - [x] Unarmored Movement
  - [x] Uncanny Metabolism
  - [x] Deflect Attacks
  - [x] Evasion
  - [x] Stunning Strike
- [x] Rogue
  - [x] Sneak Attack 每回合一次
  - [x] Sneak Attack 完整触发条件
  - [x] 借机攻击可触发 Sneak Attack

### Runtime 与前端

- [x] 常驻 battle runtime
- [x] runtime dispatcher
- [x] runtime HTTP API
- [x] start_random_encounter command
- [x] execute_attack command
- [x] cast_spell command
- [x] end_turn_and_advance command
- [x] 本地 battlemap 页面
- [x] 热重载开发模式
- [x] 先攻表
- [x] recent activity 面板

## 当前最高优先级

以下是当前最自然、性价比最高的后续开发方向：

1. 更多职业特性
   - 尤其是武力系职业通用模板与职业运行时扩展
2. 更完整 reaction 模板库
   - 把更多“改写宿主动作”的反应统一接到现有框架
3. 更细的持物 / 装填 / 空手要求
4. 更完整的战斗外施法与探索期逻辑
5. 更多法术模板与更多怪物 / 职业数据

## 暂未完成或仅做基础版的部分

- [ ] 更多职业子职
- [ ] 更完整的 Deflect Energy 细化规则
- [ ] 更复杂的战斗外施法
- [ ] 更完整的社交 / 探索 / 长休系统
- [ ] 更完整的装备持握与弹药管理
- [ ] 更完整的 LLM 战斗协议文档拆分

## 维护方式

这份文档不是最初阶段的“计划草稿”，而是当前开发现状文档。

后续维护规则：

1. 每次完成一组稳定能力后，更新对应阶段状态与能力清单。
2. 若某个系统从“基础版”提升为“完整规则版”，应同步更新“暂未完成”部分。
3. 若测试总量显著变化，可同步更新“当前总览”中的测试统计。
