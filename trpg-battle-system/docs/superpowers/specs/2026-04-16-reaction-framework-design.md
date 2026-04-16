# Reaction Framework Design

日期: 2026-04-16

## 目标

把当前只支持最小借机攻击的 reaction 机制，升级成一个面向长期扩展的统一 reaction 框架。

本次设计只覆盖一类内容：

- 会占用 `reaction` 资源的战斗中断或插队能力

例如：

- 借机攻击
- 护盾术
- 反制法术
- 吸收元素
- 地狱 rebuke

这个框架的目标不是重写现有战斗 service，而是在现有战斗 service 之上建立统一的：

- reaction 模板体系
- trigger window 体系
- 候选收集与选择体系
- resolver 分发体系
- 原动作恢复 / 取消 / 追加体系

---

## 非目标

本次设计明确不做：

- 非 reaction 资源触发的通用事件总线
- 探索、剧情、社交中的 trigger 系统
- 所有职业特性与怪物特性的完整 reaction 覆盖
- 纯声明式脚本语言式 resolver
- 反制反制链

另一个明确边界：

- 本次设计按 5r / 2024 规则处理 `Counterspell`
- `Counterspell` 不会再触发新的 `Counterspell` reaction window

---

## 总体结论

采用三层结构：

1. 框架层：管理 reaction window、choice group、option、恢复宿主动作
2. 模板层：定义 reaction 如何影响宿主动作
3. 具体能力层：实现某个具体 reaction 的规则细节

同时引入一层静态知识库：

- `ReactionDefinitionRepository`

用于统一读取 reaction definition。

---

## 为什么按模板而不是按具体能力建模

reaction 框架如果直接按具体能力名扩展，很快会变成：

- 如果是借机攻击，走 A
- 如果是护盾术，走 B
- 如果是反制法术，走 C
- 如果是吸收元素，走 D

这样主流程会迅速堆满 `if/else`，也无法统一解决：

- 谁来开 reaction 窗口
- 同一 actor 同时有多个 reaction 时如何选择
- reaction 结算后原动作是继续、取消还是追加后续动作

因此，本框架先按“结算形状”建模，再把具体能力挂在模板上。

---

## Reaction 模板

长期模板全集定义如下。

### 1. `leave_reach_interrupt`

用途：

- 因主动移动离开敌人触及时触发

典型能力：

- `opportunity_attack`

特点：

- 会阻塞原移动
- 先执行 reaction
- 再判断原移动是否继续

### 2. `targeted_defense_rewrite`

用途：

- 成为攻击目标时，改写这次攻击的结算上下文

典型能力：

- `shield`

特点：

- 不新增独立动作
- 不直接取消原攻击
- 改写原攻击参数后恢复原攻击结算

### 3. `cast_interrupt_contest`

用途：

- 某个法术被声明施放后，对该施法进行打断

典型能力：

- `counterspell`

特点：

- 目标是待结算中的施法事件
- 结算后原施法继续或取消
- 不开启嵌套 `Counterspell` 窗口

### 4. `post_hit_damage_modifier`

用途：

- 在本次伤害正式落到 HP 前改写伤害包

典型能力：

- `absorb_elements`

特点：

- 修改当前 damage packet
- 原伤害流程随后继续

### 5. `post_damage_counter`

用途：

- 受伤后追加一次独立反击

典型能力：

- `hellish_rebuke`

特点：

- 原伤害先完成
- reaction 再追加一个新的攻击 / 施法 / 伤害动作

### 6. `roll_result_modifier`

用途：

- 改写单次攻击检定 / 豁免检定 / 属性检定结果

典型能力：

- 未来的加值、减值、重掷类 reaction

### 7. `readied_action_release`

用途：

- Ready 预存动作在触发条件满足时释放

典型能力：

- 准备攻击
- 准备施法

---

## 第一版正式落地范围

第一版只实现以下模板：

- `leave_reach_interrupt`
- `targeted_defense_rewrite`
- `cast_interrupt_contest`
- `post_hit_damage_modifier`
- `post_damage_counter`

其中第一批正式接入的具体 ability：

- `opportunity_attack`
- `shield`
- `counterspell`
- `absorb_elements`
- `hellish_rebuke`

---

## 运行时模型

### `Encounter.reaction_requests`

保留现有顶层字段，但升级成通用 reaction request 记录。

每条 request 不再只服务借机攻击，而是服务任意 reaction option 的实际执行记录。

推荐结构：

```json
{
  "request_id": "react_001",
  "status": "pending",
  "reaction_type": "shield",
  "template_type": "targeted_defense_rewrite",
  "trigger_type": "attack_declared",
  "trigger_event_id": "evt_attack_declared_001",
  "actor_entity_id": "pc_miren",
  "target_entity_id": "pc_miren",
  "ask_player": true,
  "auto_resolve": false,
  "resource_cost": {
    "reaction": true,
    "spell_slot": null
  },
  "priority": 100,
  "payload": {}
}
```

第一版 `status` 支持：

- `pending`
- `resolved`
- `expired`
- `declined`

说明：

- 相比最小借机版，这里新增 `declined`
- 因为统一框架下，玩家明确放弃某个 actor 的 reaction 选择是一个有意义的运行态结果

### `Encounter.pending_reaction_window`

新增 encounter 顶层字段：

```json
{
  "pending_reaction_window": null
}
```

有窗口时：

```json
{
  "window_id": "rw_001",
  "status": "waiting_reaction",
  "trigger_event_id": "evt_attack_declared_001",
  "trigger_type": "attack_declared",
  "blocking": true,
  "host_action_type": "attack",
  "host_action_id": "atk_001",
  "host_action_snapshot": {},
  "choice_groups": [],
  "resolved_group_ids": []
}
```

作用：

- 表示当前有一个 reaction 窗口正在阻塞宿主动作
- 主流程只要看到它，就必须暂停原动作
- 处理完成后，框架根据 resolver 结果恢复 / 取消 / 结束宿主动作

### `choice_groups`

`pending_reaction_window` 里不直接挂一堆平级 request，而是按 actor 分组。

原因：

- 同一 actor 在同一个触发点，只能使用一次 reaction
- 如果同一 actor 同时满足多个 reaction 条件，例如：
  - `absorb_elements`
  - 另一个防御型 reaction
- 这些能力必须竞争同一个 reaction 资源

推荐结构：

```json
{
  "group_id": "rg_001",
  "actor_entity_id": "pc_miren",
  "ask_player": true,
  "status": "pending",
  "resource_pool": "reaction",
  "group_priority": 100,
  "trigger_sequence": 1,
  "relationship_rank": 1,
  "tie_break_key": "pc_miren",
  "options": []
}
```

### `options`

每个 group 下面是该 actor 当前可以选择的具体 reaction。

```json
{
  "option_id": "opt_shield_001",
  "reaction_type": "shield",
  "template_type": "targeted_defense_rewrite",
  "request_id": "react_001",
  "label": "护盾术",
  "status": "pending"
}
```

结论：

- 窗口管事件
- group 管 actor 的反应选择权
- option 管具体能力

---

## 宿主动作何时喊停

reaction 不是随时检查，而是宿主动作在固定规则检查点主动检查。

### 1. 移动

宿主动作：

- `BeginMoveEncounterEntity`
- `ContinuePendingMovement`

检查点：

- 每走完一步后
- 如果本步导致离开敌人触及，检查 `leave_reach_interrupt`

若有候选：

- 原移动停在当前步终点
- 返回 `waiting_reaction`

### 2. 攻击

宿主动作：

- `ExecuteAttack`

检查点：

- 攻击目标、武器、攻击总值已知
- 命中尚未锁定前
- 检查 `targeted_defense_rewrite`

若有候选：

- 攻击暂停
- 返回 `waiting_reaction`

### 3. 施法

宿主动作：

- `cast_spell`

检查点：

- 法术已声明
- 动作 / 资源已确认
- 法术效果尚未正式落地前
- 检查 `cast_interrupt_contest`

若有候选：

- 施法暂停
- 返回 `waiting_reaction`

### 4. 伤害结算

宿主动作：

- `UpdateHp` 或更上层 damage resolution 流程

检查点分两类：

#### `post_hit_damage_modifier`

- damage parts 已确定
- HP 尚未写入前

#### `post_damage_counter`

- HP 已写入后
- 原宿主动作继续前

---

## 排序规则

reaction window 内的 group 不按先攻排序。

采用“事件优先级”排序。

排序字段：

- `group_priority`
- `trigger_sequence`
- `relationship_rank`
- `tie_break_key`

主排序规则：

1. `group_priority` 小者先
2. `trigger_sequence` 小者先
3. `relationship_rank` 小者先
4. `tie_break_key` 小者先

### 第一版硬规则

- `leave_reach_interrupt`
  - 按路径触发先后顺序
- `targeted_defense_rewrite`
  - 被攻击目标本人优先
- `cast_interrupt_contest`
  - 同一施法事件只处理一层 `Counterspell`
- `post_hit_damage_modifier`
  - 受伤者本人优先
- `post_damage_counter`
  - 按伤害应用顺序

---

## Reaction pipeline

### A. 宿主动作到达检查点

宿主动作先构造 `trigger_event`。

### B. `CollectReactionCandidates`

职责：

- 根据 `trigger_event` 找出理论上可响应该事件的 actor
- 读取这些 actor 的 reaction definitions
- 跑 definition 要求的 eligibility checks
- 为每个 actor 生成候选 option

### C. `OpenReactionWindow`

职责：

- 若没有候选 option，返回 `no_window_opened`
- 若存在候选 option：
  - 生成 `pending_reaction_window`
  - 生成 `choice_groups`
  - 生成对应 `reaction_requests`
  - 宿主动作返回 `waiting_reaction`

### D. 主程序 / LLM 处理选择

若 `ask_player = true`：

- LLM 必须询问玩家

若 `auto_resolve = true`：

- 系统或 AI 可直接结算

### E. `ResolveReactionOption`

职责：

- 定位 `window_id / group_id / option_id`
- 最终合法性复检
- 扣 reaction 资源
- 分派到对应模板 resolver
- 标记 request / option / group 状态

### F. `CloseReactionWindow`

职责：

- 看当前窗口是否还有未处理 group
- 如无，关闭窗口
- 将结果交给 `ResumeHostAction`

---

## Resolver 结果形状

所有模板 resolver 最终只允许返回三类结果。

### 1. `rewrite_host_action`

reaction 改写宿主动作的结算上下文后，恢复宿主动作继续。

适用：

- `shield`
- `absorb_elements`

### 2. `cancel_host_action`

reaction 直接让宿主动作失效或终止。

适用：

- `counterspell`

### 3. `append_followup_action`

reaction 追加一个新的独立动作或结算。

适用：

- `opportunity_attack`
- `hellish_rebuke`

### 特例：借机攻击

`opportunity_attack` 主类型是 `append_followup_action`，但允许带：

- `host_action_post_check`

因为它在追加一次攻击后，还会影响原移动是否继续。

---

## `host_action_snapshot`

`pending_reaction_window` 必须带最小宿主动作快照。

统一必填字段：

- `host_action_type`
- `host_action_id`
- `phase`

### 1. 移动快照

```json
{
  "movement_id": "move_001",
  "entity_id": "ent_enemy_orc_001",
  "start_position": {"x": 4, "y": 4},
  "current_position": {"x": 5, "y": 4},
  "target_position": {"x": 8, "y": 4},
  "remaining_path": [{"x": 6, "y": 4}],
  "count_movement": true,
  "use_dash": false,
  "phase": "after_step_before_continue"
}
```

### 2. 攻击快照

```json
{
  "attack_id": "atk_001",
  "actor_entity_id": "enemy_orc_001",
  "target_entity_id": "pc_miren",
  "weapon_id": "spear",
  "attack_mode": "default",
  "grip_mode": "one_handed",
  "attack_total": 17,
  "target_ac_before_reaction": 15,
  "vantage": "normal",
  "phase": "before_hit_locked"
}
```

说明：

- 不提前存最终 `hit`
- 因为 `shield` 会改写这个结果

### 3. 施法快照

```json
{
  "spell_action_id": "spell_001",
  "caster_entity_id": "enemy_mage_001",
  "spell_id": "fireball",
  "spell_level": 3,
  "declared_targets": [{"x": 6, "y": 6}],
  "action_cost": "action",
  "phase": "before_spell_resolves"
}
```

### 4. 伤害快照

伤害前：

```json
{
  "damage_action_id": "dmg_001",
  "source_entity_id": "enemy_mage_001",
  "target_entity_id": "pc_miren",
  "damage_parts": [{"type": "fire", "amount": 12}],
  "total_damage_before_reaction": 12,
  "phase": "before_hp_applied"
}
```

伤害后：

```json
{
  "damage_action_id": "dmg_001",
  "source_entity_id": "enemy_mage_001",
  "target_entity_id": "pc_miren",
  "damage_parts": [{"type": "fire", "amount": 12}],
  "hp_applied": true,
  "phase": "after_hp_applied"
}
```

---

## 静态定义仓库

本次设计明确引入 reaction 定义仓库。

### 文件位置

- `data/knowledge/reaction_definitions.json`
- `tools/repositories/reaction_definition_repository.py`

### 仓库职责

- 按 `reaction_type` 读取 definition
- 按 `trigger_type` 枚举 definition
- 返回给 `CollectReactionCandidates`

### 与运行态的边界

静态仓库存：

- 某个 reaction 属于哪个模板
- 监听什么 trigger
- 需要哪些合法性检查
- 调哪个 resolver

运行态 encounter 存：

- 当前窗口
- 当前候选 request
- 玩家是否已选择
- 某个 reaction 是否已 resolve / expire / decline

结论：

- definition repository 只存规则定义
- encounter 只存当前战斗现场

---

## `reaction_definition` 结构

推荐一条 definition 至少包含：

```json
{
  "reaction_type": "shield",
  "template_type": "targeted_defense_rewrite",
  "name": "护盾术",
  "trigger_type": "attack_declared",
  "resource_cost": {
    "reaction": true,
    "spell_slot": {
      "level": 1,
      "allow_higher_slot": true
    }
  },
  "timing": {
    "window_phase": "before_attack_result_locked",
    "blocking": true
  },
  "targeting": {
    "scope": "self",
    "requires_visible_source": false,
    "requires_hostile_source": false
  },
  "eligibility_checks": [
    "reaction_not_used",
    "actor_is_target_of_trigger",
    "actor_can_cast_reaction_spell",
    "actor_has_spell_shield"
  ],
  "ask_mode": "player_or_auto_ai",
  "resolver": {
    "service": "resolve_shield_reaction"
  },
  "ui": {
    "prompt": "你要使用护盾术吗？",
    "short_label": "护盾术"
  }
}
```

说明：

- definition 不负责具体数值规则实现
- 例如 `shield` 的 AC 加值、`counterspell` 的成功规则、`absorb_elements` 的元素过滤，仍在具体 resolver 中实现

这样可以避免 definition 变成半套脚本语言。

---

## Service 边界

### 1. 框架层

建议放在：

- `tools/services/combat/rules/reactions/`

建议 service：

- `open_reaction_window.py`
- `collect_reaction_candidates.py`
- `resolve_reaction_option.py`
- `close_reaction_window.py`
- `resume_host_action.py`

### 2. 模板层

建议放在：

- `tools/services/combat/rules/reactions/templates/`

建议文件：

- `leave_reach_interrupt.py`
- `targeted_defense_rewrite.py`
- `cast_interrupt_contest.py`
- `post_hit_damage_modifier.py`
- `post_damage_counter.py`
- `roll_result_modifier.py`
- `readied_action_release.py`

### 3. 具体能力层

建议放在：

- `tools/services/combat/rules/reactions/definitions/`

建议文件：

- `opportunity_attack.py`
- `shield.py`
- `counterspell.py`
- `absorb_elements.py`
- `hellish_rebuke.py`

---

## 旧 service 的演进

旧 service 不立即删除，而是逐步接管。

### 保留

- `BeginMoveEncounterEntity`
- `ContinuePendingMovement`
- `resolve_reaction_request.py`

### 演进方式

- `BeginMoveEncounterEntity`
  - 不再直接自己拼借机 request
  - 改为在触发点调用 `OpenReactionWindow`

- `ContinuePendingMovement`
  - 不只看借机 request
  - 改看统一 `pending_reaction_window + pending_movement`

- `resolve_reaction_request.py`
  - 逐步退化为兼容包装层
  - 内部改调 `ResolveReactionOption`

---

## 第一版落地顺序

### 阶段 1

- 扩 encounter 运行态：
  - `pending_reaction_window`
  - 升级 `reaction_requests`
  - `choice_groups / options`

### 阶段 2

- 建 `ReactionDefinitionRepository`
- 建 `reaction_definitions.json`
- 先录入：
  - `opportunity_attack`
  - `shield`
  - `counterspell`
  - `absorb_elements`
  - `hellish_rebuke`

### 阶段 3

- 落框架层：
  - `CollectReactionCandidates`
  - `OpenReactionWindow`
  - `ResolveReactionOption`

### 阶段 4

- 落第一批模板层：
  - `leave_reach_interrupt`
  - `targeted_defense_rewrite`
  - `cast_interrupt_contest`

### 阶段 5

- 落第一批具体 resolver：
  - `ResolveOpportunityAttackReaction`
  - `ResolveShieldReaction`
  - `ResolveCounterspellReaction`

### 阶段 6

- 把移动接入新 reaction 框架
- 把攻击接入 `shield` 窗口
- 把施法接入 `counterspell` 窗口

### 阶段 7

- 再补：
  - `absorb_elements`
  - `hellish_rebuke`

---

## 测试策略

第一版必须覆盖以下测试族：

### 运行态结构

- 可创建空 `pending_reaction_window`
- 可创建多个 group
- 同 actor 多 option 时只生成一个 group

### 候选收集

- 借机攻击正确收集敌对近战反应者
- `shield` 只收集被攻击目标自己
- `counterspell` 只收集合格施法打断者

### 选择冲突

- 同 actor 同窗口多个 option 只能 resolve 一个
- 选一个后同组其他 option 自动失效

### 宿主动作恢复

- `shield` 改写 AC 后原攻击重算命中
- `counterspell` 取消原施法
- 借机攻击后移动中断 / 继续判定正确

### 5r 专项

- `Counterspell` 不会触发新的 `Counterspell` 窗口

---

## 风险与约束

### 1. 不要一次把所有 reaction 都接进来

如果一开始就试图覆盖大量职业特性，框架很容易失控。

### 2. 不要让 definition 过度脚本化

definition 负责挂接，不负责承载完整规则语言。

### 3. 不要让主程序自己猜恢复路径

恢复 / 取消 / 追加逻辑必须由模板 resolver 和 `ResumeHostAction` 明确决定。

### 4. 不要把 reaction 永远绑在移动上

必须有统一 `pending_reaction_window`，否则后续 `shield`、`counterspell` 无法自然接入。

---

## 设计结论

本次 reaction 框架的最终形态是：

- 用模板统一 reaction 的结算形状
- 用 definition repository 统一 reaction 的静态知识定义
- 用 reaction window / choice group / option 统一运行态选择
- 用 resolver 分型统一 reaction 对宿主动作的影响

这个设计既能兼容现有最小借机攻击链，也能自然向：

- `shield`
- `counterspell`
- `absorb_elements`
- `hellish_rebuke`
- 未来的 Ready / roll modifier reaction

继续扩展。
