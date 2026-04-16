# Development Plan

## 目标

这份文档定义 TRPG DM 系统接下来的开发顺序，用来指导从 schema 进入可运行代码实现。

它不重复定义数据结构细节；数据契约以 [encounter-schema.md](/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/docs/encounter-schema.md) 为准。

## 开发原则

1. 先搭骨架，再补规则。
2. 先做可验证的最小闭环，再扩展复杂战斗能力。
3. 存储层、服务层、视图层分开实现，避免逻辑混杂。
4. 先保证 `encounter`、`entity`、`event` 的边界稳定，再接本地掷骰输入。
5. 每个阶段都要有最小可验证结果，不做只能“看起来合理”的空实现。
6. service 目录优先按“`execute_*` 入口在上、其下游 request / resolve / update service 在下”的方式分层组织。

## 阶段划分

### 阶段 1: 数据骨架

目标：

- 把 schema 落成代码
- 建立 encounter 的基础读写能力
- 让系统能稳定保存和加载遭遇战状态

建议产出：

- `app/models/` 或等价目录
- `app/repositories/` 或等价目录
- `app/services/encounter/`

建议实现项：

1. 定义核心模型
   - `Encounter`
   - `EncounterEntity`
   - `Map`
   - `Event`
   - `RollRequest`
   - `RollResult`
2. 定义基础校验规则
   - `entity_id` 必须唯一
   - `current_entity_id` 必须存在于 `turn_order` 和 `entities` 中
   - `turn_order` 中每个 ID 必须存在于 `entities`
3. 封装数据读写
   - `create_encounter`
   - `get_encounter`
   - `save_encounter`
   - `delete_encounter`
4. 写最小测试
   - 创建 encounter
   - 持久化再加载
   - 校验非法结构会报错

完成标准：

- 可以创建一场空遭遇战并落库
- 可以从数据库读回完整 encounter
- 可以发现并拒绝明显非法数据

### 阶段 2: Encounter 管理能力

目标：

- 让系统能管理参与者和回合流转
- 先跑通“战场上有哪些人、现在轮到谁”

建议实现项：

1. `entity` 管理
   - `add_entity`
   - `remove_entity`
   - `update_entity_position`
   - `update_entity_hp`
   - `move_encounter_entity`
2. 回合顺序管理
   - `set_turn_order`
   - `set_current_entity`
   - `advance_turn`
   - `start_round`
3. 地图关联
   - 读取和保存 `map`
   - 校验坐标是否合法
4. 最小测试
   - 添加多个实体
   - 设置回合顺序
   - 推进到下一个实体
   - 回合末进入新 round

完成标准：

- 系统知道场上有谁
- 系统知道当前轮到谁
- 推进回合时状态变化正确
- 可以通过独立 service tool 执行一次带规则校验的移动

### 阶段 3: 视图层投影

目标：

- 实现 `get_encounter_state`
- 让 LLM / UI 拿到稳定、可读的当前战斗信息

建议实现项：

1. 编写 projector / serializer
   - 底层输入：`Encounter`
   - 输出：`get_encounter_state` 视图对象
2. 输出以下视图块
   - `current_turn_entity`
   - `turn_order`
   - `battlemap_details`
   - `encounter_notes`
3. 处理格式化逻辑
   - HP 格式化
   - 位置格式化
   - 剩余移动格式化
   - 武器和法术列表整理
   - 目标距离整理
4. 最小测试
   - 当前行动者投影正确
   - `current_entity_id` 切换后视图同步变化
   - 没有法术或武器时返回空列表而不是报错

完成标准：

- 能稳定输出一份完整的 `get_encounter_state`
- 输出内容既能给 LLM 看，也能直接给前端用

### 阶段 4: 事件日志系统

目标：

- 把“过程”和“结果”分开保存
- 为回放、调试、审计、摘要生成打底

建议实现项：

1. 事件存储接口
   - `append_event`
   - `list_events`
   - `get_events_by_encounter`
2. 定义首批事件类型
   - `entity_added`
   - `entity_removed`
   - `turn_started`
   - `turn_ended`
   - `movement_resolved`
   - `attack_resolved`
   - `damage_applied`
   - `resource_spent`
3. 定义状态更新策略
   - 简单方案：service 直接更新 encounter，并同时追加 event
   - 进阶方案：通过 event 驱动状态更新
4. 最小测试
   - 追加事件后能按 encounter 查询
   - 同一场战斗事件顺序正确
   - 事件内容能支持回放或摘要生成

完成标准：

- 系统能清楚记录“发生了什么”
- 当前 encounter 状态与事件链能对应起来

### 阶段 5: Roll 流程

目标：

- 接住本地掷骰输入
- 跑通从 roll request 到状态更新的闭环

建议实现项：

1. `RollRequest` 生成
   - 攻击请求
   - 法术攻击请求
   - 豁免请求
2. `RollResult` 接收与解析
   - 命中判定
   - 是否暴击
   - 伤害是否需要继续请求
3. 生成对应事件
   - `attack_resolved`
   - `damage_applied`
   - `resource_spent`
4. 最小闭环优先
   - 单体攻击命中
   - 单体伤害应用
   - 扣减 HP
5. 最小测试
   - 命中
   - 未命中
   - 暴击
   - 目标掉到 0 HP

完成标准：

- 一次标准攻击可以从请求掷骰走到更新状态

### 阶段 6: 基础规则层

目标：

- 补足战斗中最常见、最通用的规则处理

建议优先级：

1. 动作经济
   - `action`
   - `bonus_action`
   - `reaction`
   - `movement`
2. 移动与距离
   - 格子移动
   - 剩余移动
   - 基础距离判断
3. 伤害结算
   - temp hp
   - 抗性
   - 易伤
   - 免疫
4. conditions
   - 添加
   - 移除
   - 基础限制判断
   - 后续把优势 / 劣势来源也收进 condition 体系
5. resources
   - 法术位
   - 限次能力

完成标准：

- 常见单体战斗结算不需要手工补大量状态

### 阶段 7: 扩展规则与内容能力

目标：

- 逐步进入复杂战斗和内容驱动场景

建议实现项：

1. 法术与豁免
   - saving throw
   - spell save DC
   - 半伤 / 全伤
2. concentration
   - 受伤触发检定
   - 失败移除专注效果
   - 根据 condition / 特性 / 规则来源决定优势或劣势
3. AoE 和多目标
   - 多目标豁免
   - 区域伤害
4. 召唤物和临时实体
   - 动态 `add_entity`
   - 持续时间结束自动移除
5. 特殊机制
   - 光环
   - 地形效果
   - 回合开始 / 结束触发

完成标准：

- 系统能处理复杂战斗而不是只支持单次攻击

## 推荐落地顺序

如果现在开始正式开发，建议按下面顺序推进：

1. 阶段 1：数据骨架
2. 阶段 2：Encounter 管理能力
3. 阶段 3：视图层投影
4. 阶段 4：事件日志系统
5. 阶段 5：Roll 流程
6. 阶段 6：基础规则层
7. 阶段 7：扩展规则与内容能力

## 第一轮建议范围

第一轮不要做太大，建议只覆盖：

- encounter 数据模型
- repository / service
- `add_entity`
- `set_turn_order`
- `set_current_entity`
- `advance_turn`
- `get_encounter_state`
- `append_event`

这第一轮完成后，系统就已经具备“能管理一场战斗”的基本形态。

## 第一轮验收标准

满足以下几点，就说明第一轮开发合格：

1. 可以创建 encounter 并持久化。
2. 可以添加多个 entity。
3. 可以设置 `turn_order` 和 `current_entity_id`。
4. 可以推进回合并正确切换当前实体。
5. 可以输出一份完整的 `get_encounter_state`。
6. 可以记录基础事件日志。

## 暂不做的内容

为了避免第一轮失控，以下内容建议延后：

- 复杂法术特例
- 法术库驱动的完整效果定义
- 多目标 AoE 结算
- 完整 D&D 5e 条件系统
- 地图高级寻路
- 自动叙事生成
- 全量 NPC AI 决策

## 当前已完成进度

截至当前，本地战斗系统已经完成这些能力：

1. 核心数据与存储
   - `Encounter`
   - `EncounterEntity`
   - `EncounterMap`
   - `Event`
   - `RollRequest`
   - `RollResult`
   - `EncounterRepository`
   - `EventRepository`
2. encounter 管理
   - `manage_encounter_entities.py`
   - 支持添加/移除实体、设置当前行动者、推进回合、更新位置和 HP
3. 视图层
   - `get_encounter_state.py`
   - 能输出当前行动者、回合顺序、地图信息、遭遇战 note
4. 事件日志
   - `append_event.py`
   - 各条战斗链路都已开始写结构化事件
5. 攻击链路
   - `attack_roll_request.py`
   - `attack_roll_result.py`
   - `update_hp.py`
   - `execute_attack.py`
6. 豁免型法术链路
   - `encounter_cast_spell.py`
   - `saving_throw_request.py`
   - `resolve_saving_throw.py`
   - `saving_throw_result.py`
   - `update_conditions.py`
   - `update_encounter_notes.py`
   - `execute_save_spell.py`

当前系统已经具备两条完整入口：

- `execute_attack.py`
- `execute_save_spell.py`

也就是说，系统已经不只是“能存数据”，而是已经能跑通：

- 单目标攻击命中/未命中结算
- 命中后自动扣血
- 单目标豁免型法术结算
- 豁免成功/失败的数值比较
- 豁免失败后自动加 condition / note

## 法术库相关决定

当前的豁免型法术链路已经可运行，但法术效果参数仍然主要由调用方显式传入，例如：

- `conditions_on_failed_save`
- `note_on_failed_save`
- `hp_change_on_failed_save`
- `hp_change_on_success`

这部分后续会交给“法术库”统一提供，而不是继续在当前阶段内联扩展。

也就是说，后续目标是：

- 由法术定义自身携带效果数据
- 执行入口自动从法术定义中读取效果
- LLM 不再每次手工拼完整法术效果参数

但这一块当前明确暂缓，等法术库准备阶段再统一开发。

## service 分层约定

为了避免后续 service 数量越来越多后难以维护，当前采用下面这套分层约定：

1. 顶层优先放“完整入口”
   - 例如：
     - `execute_attack.py`
     - `execute_save_spell.py`
     - `execute_concentration_check.py`
2. 规则实现再按入口下面的子步骤拆分
   - 例如专注规则模块：
     - `request_concentration_check.py`
     - `resolve_concentration_check.py`
     - `resolve_concentration_result.py`
3. 再按规则域收子目录
   - 例如：
     - `combat/rules/concentration/`

这样做的目的：

- 先看目录就能知道“系统有哪些完整入口”
- 再看每个入口下面具体分了哪些步骤
- 比纯平铺 service 更适合长期维护

## 备注

开发过程中如果 schema 调整，应先更新 [encounter-schema.md](/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/docs/encounter-schema.md)，再改实现代码。
