# Monster Action Schema Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一套可长期复用的怪物动作 schema，让未来新增怪物主要通过模板数据接入，而不是反复补后端特判。

**Architecture:** 以 `source_ref` 内的结构化动作元数据为中心，统一描述动作、附赠动作、反应、传奇动作、资源、目标限制、形态限制和组合动作。`get_encounter_state` 负责投影给前端和 LLM，战术推荐层负责读取 schema 做决策，执行层负责按 schema 校验合法性、扣资源并触发实际效果。

**Tech Stack:** Python, pytest, JSON knowledge templates

---

## 1. 目标与边界

- [ ] 统一动作描述格式，覆盖：
  - `actions_metadata`
  - `bonus_actions_metadata`
  - `reactions_metadata`
  - `legendary_actions_metadata`
- [ ] 统一动作字段，至少覆盖：
  - `action_type`
  - `category`
  - `availability`
  - `targeting`
  - `resource_cost`
  - `execution_steps`
  - `ai_hints`
  - `resolution`
- [ ] 将 `multiattack` 视为组合动作的一种，而不是单独特判。
- [ ] 保证老模板在迁移期间仍可读取，不要求一次性迁完所有怪物。

**不在本轮强制完成的内容：**

- [ ] 不要求一次做完所有怪物的完整战术智能。
- [ ] 不要求一次接完所有状态机，如巢穴动作、神话动作、阶段切换。
- [ ] 不要求立刻支持所有传奇动作自动执行，但 schema 必须先能表达。

---

## 2. Schema 设计

### 2.1 顶层结构

- [ ] 在 `source_ref` 下引入统一怪物战斗结构：
  - `combat_profile`
  - `traits_metadata`
  - `actions_metadata`
  - `bonus_actions_metadata`
  - `reactions_metadata`
  - `legendary_actions_metadata`

### 2.2 `combat_profile`

- [ ] 统一表达战斗形态与动作资源：
  - `forms`
  - `current_form`
  - `passive_rules`
  - `resources`

建议结构：

```json
{
  "combat_profile": {
    "forms": ["vampire", "bat", "mist"],
    "current_form": "vampire",
    "passive_rules": ["misty_escape", "sunlight_hypersensitivity"],
    "resources": {
      "legendary_resistance": {"max": 3, "remaining": 3, "recharge": "long_rest"},
      "legendary_actions": {"max": 3, "remaining": 3, "recharge": "turn_start"}
    }
  }
}
```

### 2.3 动作通用字段

- [ ] 每个动作条目统一支持：

```json
{
  "action_id": "multiattack",
  "name_zh": "多重攻击",
  "name_en": "Multiattack",
  "summary": "发动两次攻击并追加特殊动作。",
  "action_type": "action",
  "category": "composite",
  "availability": {},
  "targeting": {},
  "resource_cost": {},
  "execution_steps": [],
  "ai_hints": {},
  "resolution": {}
}
```

### 2.4 `availability`

- [ ] 统一承载动作合法性限制：
  - `forms_any_of`
  - `requires_action_available`
  - `requires_bonus_action_available`
  - `requires_reaction_available`
  - `not_in_sunlight`
  - `not_in_running_water`
  - `cooldown_until_turn_start`
  - 未来可扩：`requires_condition_on_target`、`requires_self_condition_absent`

### 2.5 `targeting`

- [ ] 统一承载目标筛选与距离规则：
  - `range_feet`
  - `mode`
  - `target_filters`
  - `allow_any_of_filters`
  - `size_limit`
  - 未来可扩：`line_of_sight_required`、`humanoid_only`

### 2.6 `resource_cost`

- [ ] 统一承载动作消耗：
  - `legendary_actions`
  - `charges`
  - `recharge`
  - 未来可扩：`spell_slot_level`、`class_resource`

### 2.7 `execution_steps`

- [ ] 统一承载组合动作展开步骤：
  - `weapon`
  - `special_action`
  - `move`
  - `repeat`
- [ ] `multiattack` 不再依赖写死逻辑，原则上都应能从 `execution_steps` 或 `multiattack_sequences` 展开。

---

## 3. 分阶段实施

### Phase 1: Schema 可表达

**目标：** 让模板和状态输出先具备统一表达能力。

- [ ] 扩展 `get_encounter_state` 元数据投影：
  - `actor_options.actions`
  - `actor_options.bonus_actions`
  - `actor_options.reactions`
  - `actor_options.legendary_actions`
- [ ] 扩展战场实体 `combat_profile` 输出：
  - `state`
  - `actions`
  - `bonus_actions`
  - `reactions`
  - `legendary_actions`
- [ ] 为模板读取层补测试，确保结构化字段不会被吞掉。

**交付标准：**

- [ ] LLM 能读到完整怪物动作 schema。
- [ ] 前端/调试态能看到结构化动作元数据。

### Phase 2: 推荐层读取 Schema

**目标：** 战术推荐不再只靠硬编码。

- [ ] 让近战 / 远程 / 混合怪推荐逻辑优先读取：
  - `availability`
  - `targeting`
  - `multiattack_sequences`
  - `ai_hints`
- [ ] 对高 AC、近战贴身、可远程压制、可特殊动作压制等情况，优先由模板数据驱动选择。
- [ ] 逐步减少“尸妖特判”、“某怪专用 if 分支”。

**交付标准：**

- [ ] `recommended_tactic` 能稳定从 schema 构造执行计划。
- [ ] 新怪物若 schema 完整，不需要额外补一套推荐逻辑。

### Phase 3: 执行层读取 Schema

**目标：** 动作不只是“能看”，而是“能执行”。

- [ ] 通用执行校验读取：
  - `availability`
  - `resource_cost`
  - `targeting`
- [ ] 通用资源扣减：
  - 传奇动作点
  - 充能
  - 未来可扩其他怪物资源
- [ ] 对 `execution_steps` 提供统一展开器。

**交付标准：**

- [ ] 新怪物动作只靠模板即可判断合法性和资源消耗。
- [ ] 组合动作不需要专门手写一条执行链。

### Phase 4: 高阶 Boss 能力

**目标：** 支持更复杂的怪物玩法。

- [ ] 传奇动作
- [ ] 巢穴动作
- [ ] 神话阶段 / 变身阶段
- [ ] 自动弱点触发
- [ ] 被动逃生或强制形态切换

**交付标准：**

- [ ] 吸血鬼、龙、恶魔、巢穴 Boss 这类模板可以按统一结构逐步接入。

---

## 4. 首批模板迁移名单

### 已完成样板

- [ ] `monster_wight`
- [ ] `pseudodragon`
- [ ] `monster_vampire`

### 建议下一批

- [ ] 带传奇动作的 Boss 怪
- [ ] 带附赠动作控制能力的 humanoid caster
- [ ] 带形态切换的怪物
- [ ] 带多种多重攻击分支的怪物

---

## 5. 推荐文件改动范围

### 模板与知识库

- [ ] `data/knowledge/entity_definitions.json`
- [ ] `tools/services/spells/summons/find_familiar_builder.py`

### 状态与推荐层

- [ ] `tools/services/encounter/get_encounter_state.py`
- [ ] 如后续拆分，建议新增：
  - `tools/services/encounter/monster_action_schema.py`
  - `tools/services/encounter/monster_action_planner.py`

### 测试

- [ ] `test/test_entity_definition_repository.py`
- [ ] `test/test_find_familiar_builder.py`
- [ ] `test/test_get_encounter_state.py`
- [ ] 后续若执行层接入，再补：
  - `test/test_execute_attack.py`
  - `test/test_encounter_service.py`
  - `test/test_resolve_reaction_option.py`

---

## 6. 风险与注意事项

- [ ] 不要把 schema 设计成过重 DSL，避免模板作者无法维护。
- [ ] 保持老模板兼容，迁移期允许：
  - 有 summary 但没结构字段
  - 有 `multiattack` 但没 `legendary_actions_metadata`
- [ ] `target_filters` 不要一开始做成无限自由表达，优先白名单枚举。
- [ ] `execution_steps` 先支持有限步骤类型，后续再扩。
- [ ] 资源值要有统一归属：
  - 模板定义 `max`
  - 运行时实体记录 `remaining`

---

## 7. 验证标准

### 结构验证

- [ ] 模板仓储读取后，结构化字段完整保留。
- [ ] `get_encounter_state` 中：
  - `actor_options`
  - `battlemap.entities[*].combat_profile`
  - `current_turn_context`
  
  都能看到新字段。

### 行为验证

- [ ] `multiattack` 推荐与执行计划正确展开。
- [ ] 传奇动作和附赠动作能进入元数据输出。
- [ ] 目标限制与形态限制至少能在推荐层生效。

### 回归验证

- [ ] 现有角色卡与战术建议测试不能回退。
- [ ] 新 schema 字段不会破坏老模板读取。

---

## 8. 近期实施顺序

- [ ] 第一步：完成状态投影层通用化
- [ ] 第二步：完成吸血鬼模板作为完整样板
- [ ] 第三步：让推荐层统一读取 `availability / targeting / resource_cost`
- [ ] 第四步：把执行层改成 schema 驱动
- [ ] 第五步：逐个迁移高价值怪物模板

---

## 9. 成功定义

当满足以下条件时，可以认为怪物 schema 主线完成：

- [ ] 新增一个怪物模板时，主要工作是写 JSON 数据，而不是补 Python 特判。
- [ ] `get_encounter_state` 能完整输出怪物的结构化动作信息。
- [ ] 推荐层能按模板数据挑动作。
- [ ] 执行层能按模板数据判合法性并扣资源。
- [ ] 至少一类传奇怪和一类多形态怪已经用同一套 schema 跑通。
