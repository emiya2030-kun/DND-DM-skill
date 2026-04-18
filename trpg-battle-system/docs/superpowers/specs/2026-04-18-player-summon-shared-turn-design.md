# Player Summon Shared Turn Design

## Goal

让玩家控制、且从属于某个玩家角色的召唤物不再作为独立行动回合存在，而是并入宿主的回合窗口内，允许玩家在自己的回合中切换操纵宿主与其召唤物。

这项能力的直接目标是支持如下编排：

- 角色移动
- 角色的魔宠或其他召唤物执行 `协助`
- 角色再进行攻击或施法，并正确吃到优势或其他已建立的战术收益

## Current Problem

当前系统中：

- `find_familiar`、`pact_of_the_chain`、`find_steed` 召唤出的实体都会进入 `turn_order`
- 它们作为独立节点占据先攻顺序
- 几乎所有行动校验都默认要求 `actor_id == encounter.current_entity_id`

这会导致一个问题：

- 虽然玩家语义上把魔宠视为自己当前回合内可操纵单位
- 但系统要求等到召唤物自己的独立回合，才能执行其动作

结果就是玩家无法在单个角色回合里完成“自己与召唤物交错行动”的 D&D 常见战术编排。

## Design Decision

采用统一规则，而不是按职业或法术单独特判。

规则定义如下：

- 若一个实体满足以下全部条件，则该实体属于“玩家共享回合召唤物”
- `entity.category == "summon"`
- `entity.controller == "player"`
- `entity.source_ref.summoner_entity_id` 指向某个玩家角色实体

这类召唤物：

- 保留实体本身
- 保留地图占位、生命值、动作经济、条件、反应等独立数据
- 不再作为独立行动节点占据 `turn_order`
- 在其宿主的回合窗口内作为“当前可操纵成员”出现

## Scope

本设计覆盖：

- 玩家控制召唤物的回合编组
- 对外动作调用层的合法性校验
- `GetEncounterState` 的投影摘要
- 先攻表与当前回合 UI 的行为语义

本设计不覆盖：

- 敌方召唤物行为变更
- 自动 AI 行动逻辑
- 新召唤法术的数据建模重做
- 召唤物动作菜单的前端交互重构

## Data Model

### Existing Fields Reused

沿用以下既有字段：

- `category`
- `controller`
- `source_ref.summoner_entity_id`
- `source_ref.familiar`
- `source_ref.controlled_mount`
- `source_ref.shares_initiative_with_summoner`

### New Derived Concept

引入一个统一的派生概念：

- `shared_turn_owner_id`

这不是必须落库存储的新字段；优先作为运行时派生结果计算。

语义：

- 若实体属于玩家共享回合召唤物，则 `shared_turn_owner_id == summoner_entity_id`
- 否则为 `null`

### Turn Order Representation

`turn_order` 中只保留真正的宿主行动节点，不再插入这类共享回合召唤物。

例如原本：

- `Kael -> Orc -> Goblin -> Sphinx`

调整后：

- `Kael -> Orc -> Goblin`

其中 `Sphinx` 仍存在于 `entities` 中，但通过 `Kael` 的共享回合编组被操作。

## Turn Model

### Shared Turn Group

当 `encounter.current_entity_id == 宿主实体` 时，可行动成员包括：

- 宿主自己
- 所有 `shared_turn_owner_id == 宿主.entity_id` 的召唤物

这组成员共同构成“当前回合可操纵编组”。

### Action Economy

每个成员保留自己的动作经济：

- `action_used`
- `bonus_action_used`
- `reaction_used`
- `free_interaction_used`

它们不与宿主共享资源池。

因此允许：

- 宿主先行动
- 召唤物再行动
- 再切回宿主

只要对应成员自己的动作经济仍可用即可。

### Turn Boundaries

宿主回合结束时：

- 共享回合召唤物本回合窗口同时关闭
- 这些成员在该宿主下个回合开始前都不能再主动行动

这意味着它们不再拥有独立的“开始回合 / 结束回合”推进节点。

## Command Layer Impact

### Current Limitation

当前多数对外动作调用层会要求：

- `actor_id` 必须等于 `encounter.current_entity_id`

### New Validation Rule

统一改为：

- `actor_id` 必须是当前实体本人
- 或者 `actor_id` 属于当前实体的共享回合编组成员

这样现有命令接口可以继续沿用，不需要把对外 API 重做成“主控角色 + 子单位动作”双层协议。

### External API Compatibility

对外动作调用层继续使用既有参数：

- `encounter_id`
- `actor_id`
- 其他动作自身参数

例如：

```json
{
  "command": "use_help_attack",
  "args": {
    "encounter_id": "enc_warlock_lv5_test",
    "actor_id": "ent_familiar_5152238c5994",
    "target_id": "ent_goblin_archer_b_001"
  }
}
```

只要当前回合属于该魔宠的宿主，就应合法通过。

## Encounter State Projection

`GetEncounterState` 需要新增一个轻量摘要，供 LLM 和前端直接判断当前共享回合编组。

建议字段：

```json
{
  "current_turn_group": {
    "owner_entity_id": "ent_warlock_lv5_001",
    "owner_name": "Kael",
    "controlled_members": [
      {
        "entity_id": "ent_warlock_lv5_001",
        "name": "Kael",
        "relation": "owner"
      },
      {
        "entity_id": "ent_familiar_5152238c5994",
        "name": "Sphinx of Wonder",
        "relation": "summon"
      }
    ]
  }
}
```

要求：

- 只给摘要，不暴露过多内部判定细节
- 无共享回合时，该字段仍应存在，但 `controlled_members` 仅含当前实体自己

## UI / Battlemap Expectations

### Initiative List

先攻表不再把共享回合召唤物单独列为独立后续回合。

### Current Turn Panel

当前行动区域应能显示：

- 当前宿主
- 本回合可操纵成员列表

例如：

- `当前回合：Kael`
- `本回合可操纵：Kael / Sphinx of Wonder`

### Command Semantics for LLM

LLM 不需要新学一套“召唤物专用动作层”，仍然直接对召唤物传其自身 `actor_id`。

## Rule Boundaries

### Included

- 玩家魔宠
- 玩家召唤物
- 玩家受控坐骑

前提都是：

- `controller == "player"`
- 存在明确的宿主映射

### Excluded

以下仍保持独立行为：

- `controller != "player"` 的召唤物
- 敌方召唤物
- 普通 NPC / 友方随从，但没有 `summoner_entity_id`

## Behavioral Examples

### Example 1: Familiar Help Into Owner Attack

合法流程：

1. `Kael` 移动
2. `Sphinx` 使用 `use_help_attack`
3. `Kael` 使用 `execute_attack` 或 `cast_spell`

只要三步都发生在 `Kael` 的回合窗口内，且各自动作经济合法，就应通过。

### Example 2: End of Turn

若 `Kael` 结束回合后，`Sphinx` 再尝试行动：

- 应被拒绝
- 原因是共享回合窗口已关闭

## Implementation Outline

1. 抽出“共享回合成员解析”公共函数
2. 调整 turn order 构建与召唤物插入逻辑
3. 调整动作合法性校验
4. 调整 `GetEncounterState` 投影
5. 补充共享回合测试
6. 联调 `battlemap localhost` 与 runtime

## Risks

### Turn Effects

若有依赖“每个实体单独经历一次 turn advance”的效果，需要确认共享回合召唤物是否仍需要单独触发。

当前建议：

- 默认不再给共享回合召唤物单独推进 turn lifecycle
- 若未来存在必须单独处理的效果，再做显式特判

### Legacy Summon Ordering

已有测试依赖“召唤物插入先攻表”时，需要区分：

- 共享回合召唤物
- 仍应独立占位的普通召唤物

## Testing Strategy

至少覆盖：

1. 玩家共享回合召唤物不会插入 `turn_order`
2. 当前宿主回合内可以用召唤物 `actor_id` 执行动作
3. 非当前宿主回合内，召唤物动作被拒绝
4. 宿主和召唤物动作经济彼此独立
5. `GetEncounterState` 正确投影 `current_turn_group`
6. battlemap 页面与 runtime 可以正确展示和操作该语义

## Recommended Next Step

基于本 spec 编写实现计划，然后按以下顺序落地：

- 先改 runtime / service 合法性模型
- 再改 summon turn order 逻辑
- 最后做 battle test 与 UI 投影验证
