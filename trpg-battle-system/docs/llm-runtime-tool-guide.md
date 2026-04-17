# LLM 运行时 Tool 总手册

这份文档是当前项目给 LLM 的单一运行手册。

目标很简单：

- 让 LLM 知道战斗中该读什么状态
- 让 LLM 知道不同意图该调用什么 tool
- 让 LLM 知道 tool 返回后如何刷新前端
- 让 LLM 知道哪些结果只读、哪些结果由系统自动维护

如果后续规则、tool 或前端交互发生变化，优先更新这份文档。

---

## 1. 一句话原则

LLM 不手工维护战斗状态，也不手工修 DOM。

LLM 的职责只有三步：

1. 读取当前 `encounter_state`
2. 选择正确的 service tool 执行动作
3. 把最新 `encounter_state` 交给页面重绘

---

## 2. 短版主规范

先看这一节就够了。后面章节是补充说明。

### 8 步流程

1. 先读取最新 `encounter_state`
2. 根据 `current_turn_entity` 判断当前轮到谁行动
3. 如果要移动，先调 `BeginMoveEncounterEntity`
4. 如果返回 `waiting_reaction`，立刻检查当前 `reaction_request`
5. 若该 reaction 需要玩家决定，就先询问玩家；玩家放弃则调 `ContinuePendingMovement`，玩家使用则先调 `ResolveReactionRequest` 再调 `ContinuePendingMovement`
6. 只有移动真正完成后，才能继续攻击、施法或别的动作
7. 每次 tool 返回后，都以新的 `encounter_state` 为准并刷新前端
8. 回合结束时按 `EndTurn -> AdvanceTurn -> StartTurn` 推进

### 5 条禁令

- 不手工修改位置、HP、condition、资源或回合顺序
- 不跳过 `waiting_reaction` 对应的玩家询问
- 不在移动未完成前结算后续攻击、施法或其他动作
- 不用旧状态继续推理下一步
- 不替玩家决定 `ask_player = true` 的 reaction

---

## 3. 唯一事实源

### 底层运行态

- `Encounter` 是底层运行时事实源
- 实体位置、HP、条件、资源、回合顺序都存这里

### 只读视图

- `GetEncounterState` 是唯一状态投影入口
- 地图、先攻、角色卡、战场备注、当前位置、当前行动者，都以 `encounter_state` 为准
- 前端不拼局部状态
- LLM 不猜测局部更新

---

## 4. 详细说明

### 第一步：读取状态

在判断移动、攻击目标、施法范围、当前行动者之前，先读取：

```python
state = GetEncounterState(encounter_repository).execute(encounter_id)
```

如果页面已经有状态，也可以读取：

```js
const currentState = window.getEncounterState()
```

### 第二步：执行 tool

根据玩家意图，调用对应 service tool。

关于专注法术：

- 如果 `ExecuteConcentrationCheck` 结算失败，系统不只是把施法者的 `is_concentrating` 改成 `false`
- 还会自动结束该施法者当前仍在生效的专注法术实例
- 并清理这些实例曾经挂到目标身上的持续状态与 `turn_effects`
- 因此前端与 LLM 都应直接信任新的 `encounter_state`，不要试图手动补删状态

### 第三步：刷新页面

如果 tool 返回中已经带有 `encounter_state`：

```js
window.applyToolResult(result)
```

如果 tool 没带 `encounter_state`，则重新读取一次：

```js
const nextState = await getEncounterState(...)
window.applyEncounterState(nextState)
```

---

## 5. 前端刷新约定

当前 battlemap 页面可用接口：

- `window.getEncounterState()`
  - 读取当前页面中的完整 `encounter_state`
- `window.applyEncounterState(nextState)`
  - 用完整状态重绘页面
- `window.applyToolResult(toolResult)`
  - 推荐入口
  - 自动从 `toolResult.encounter_state` 中取状态并调用 `applyEncounterState`
- `window.getLastToolResult()`
  - 读取最近一次成功应用的 tool 返回

### 刷新原则

- 只要 encounter 真实发生变化，就应该刷新页面
- 不要只改单个 token、单个血条、单个先攻行
- 不要自己手写局部 DOM patch

常见会触发刷新的一类 tool：

- `MoveEncounterEntity`
- `BeginMoveEncounterEntity`
- `ContinuePendingMovement`
- `ExecuteAttack`
- `ResolveReactionRequest`
- `ExecuteSaveSpell`
- `ExecuteConcentrationCheck`
- `UpdateHp`
- `UpdateConditions`
- `UpdateEncounterNotes`
- 其他任何会写回 `Encounter` 的 service tool

---

## 6. 核心 Tool 一览

## 6.1 读取状态

## 战士职业特性运行时

- `use_second_wind(...)`
  - 这是一个附赠动作恢复入口
  - 返回治疗结果
  - 若角色拥有 `Tactical Shift`，结果里还会带 `free_movement_after_second_wind`
- `use_action_surge(...)`
  - 这是一个主动声明入口
  - 会给当前回合增加 `extra_non_magic_action_available`
  - 该额外动作不能用于 `Magic action`
- `Extra Attack`
  - 不需要单独 tool
  - 只要角色执行 `Attack action`，攻击链会自动按运行时的 `extra_attack_count` 允许连续攻击
  - 多职业来源不叠加，只取最高值
- `Studied Attacks`
  - 不需要单独 tool
  - 攻击失手后，系统会给该目标写入下一次攻击优势标记
  - 下次对同目标攻击时，攻击请求会自动带上优势并在结算后消费
- `Tactical Master`
  - 不需要单独 service
  - 当战士具备该特性时，可以在 `ExecuteAttack(...)` 里传 `mastery_override`
  - 当前只允许改为 `push / sap / slow`
- `Indomitable`
  - 不属于普通动作，也不消耗 `reaction`
  - 它会以 `failed_save` 触发的反应窗口形式出现
  - 选择后由后端自动重掷豁免，并额外加上 `fighter_level`

### `GetEncounterState`

用途：

- 读取当前战斗完整视图
- 给 LLM 判断当前位置、HP、AC、先攻、地图备注、当前行动者
- 给前端渲染整页

返回重点：

- `current_turn_entity`
- `turn_order`
- `active_spell_summaries`
- `retargetable_spell_actions`
- `battlemap_details`
- `battlemap_view`
- `map_notes`
- `reaction_requests`
- `pending_movement`
- `encounter_notes`

持续法术相关说明：

- 后端运行时内部已经有 `spell_instances`
- `GetEncounterState` 不直接把 `spell_instances` 原样暴露给 LLM
- LLM 只会看到摘要字段，例如：
  - `active_spell_summaries`
  - `retargetable_spell_actions`
  - `current_turn_entity.ongoing_effects`
  - `turn_order[].ongoing_effects`
  - 当某单位正被持续法术影响时，`conditions` 也可能是更易读的列表，例如 `["paralyzed", "来自Eric的Hold Person"]`
- 这些摘要只是展示层，不是规则事实源

`retargetable_spell_actions` 说明：

- 这是给 LLM 的结构化动作提示
- 只会列出“当前行动者此刻可以执行”的标记转移动作
- 当前用于：
  - `Hex`
  - `Hunter's Mark`
- 每项通常包含：
  - `spell_instance_id`
  - `spell_id`
  - `spell_name`
  - `previous_target_id`
  - `previous_target_name`
  - `activation`
- 如果这个数组非空，说明后端已经确认这些法术实例进入“可转移待命”
- 这时若玩家说“我把诅咒/印记转移到另一个目标”，应优先调用 `RetargetMarkedSpell`
- 不要把这种情况当成重新施法

适用时机：

- 每次做行动判断前
- mutation tool 没带最新状态时
- 前端需要全量重绘时

---

## 6.2 回合与移动

### `AdvanceTurn`

用途：

- 推进到下一个行动者
- 到达回合末尾时自动进入下一轮

适用时机：

- 当前单位明确结束回合时
- 需要把控制权切给下一个先攻单位时

LLM 不需要做的事：

- 不自己手动修改 `current_entity_id`

典型调用：

```python
result = AdvanceTurn(encounter_repository).execute_with_state("enc_preview_demo")
```

返回后：

- 这一步只表示“先攻表往下走了一位”
- 不等于新单位已经正式开始回合

### `EndTurn`

用途：

- 结束当前行动者的回合
- 给“回合结束触发”的规则留统一挂点

当前行为：

- 不推进先攻顺序
- 不重置下一位资源
- 可选地追加一条 `turn_ended` 事件
- 若当前实体身上有 `turn_effects`，这里会结算 `end_of_turn` 触发效果

适用时机：

- 当前单位明确说“结束回合”时
- 怪物或玩家完成本回合全部行动时

典型调用：

```python
result = EndTurn(encounter_repository).execute_with_state("enc_preview_demo")
```

返回后：

- 当前行动者仍然是原来的单位
- 这一步只代表“当前人的回合结束了”
- 若有回合结束触发效果，结果会额外出现在 `result.turn_effect_resolutions`

### `StartTurn`

用途：

- 正式开始当前行动者的回合
- 在这一刻统一刷新该单位的回合资源

当前会自动重置：

- `action_economy.action_used`
- `action_economy.bonus_action_used`
- `action_economy.reaction_used`
- `action_economy.free_interaction_used`
- `speed.remaining`
- `combat_flags.movement_spent_feet`

适用时机：

- `EndTurn` + `AdvanceTurn` 之后
- 或 encounter 初始化后第一次开始当前单位回合时

LLM 不需要做的事：

- 不自己手动重置动作经济
- 不自己手动重置移动力

典型调用：

```python
result = StartTurn(encounter_repository).execute_with_state("enc_preview_demo")
```

返回后：

- 直接把 `result.encounter_state` 交给前端全量刷新
- 若当前实体身上有 `turn_effects`，这里也会结算 `start_of_turn` 触发效果
- 结果会额外出现在 `result.turn_effect_resolutions`

推荐顺序：

1. `EndTurn`
2. `AdvanceTurn`
3. `StartTurn`

### `turn_effects`

用途：

- 在实体身上描述“开始回合 / 结束回合自动触发什么”

当前最小模型：

```json
{
  "effect_id": "effect_hold_person_001",
  "name": "定身术持续效果",
  "source_entity_id": "ent_enemy_vampire_mage_001",
  "trigger": "end_of_turn",
  "save": {
    "ability": "wis",
    "dc": 15,
    "on_success_remove_effect": true
  },
  "on_trigger": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "on_save_success": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": ["paralyzed"]
  },
  "on_save_failure": {
    "damage_parts": [],
    "apply_conditions": [],
    "remove_conditions": []
  },
  "remove_after_trigger": false
}
```

说明：

- `conditions` 继续表示“当前状态”
- `turn_effects` 表示“开始/结束回合时要结算的效果”
- 当前只支持单实体挂载的最小持续效果
- `AdvanceTurn` 不会触发它，只有 `StartTurn` / `EndTurn` 会触发

---

## 6.3 阻塞式移动

### `MoveEncounterEntity`

用途：

- 执行一次不会被 reaction 中断的完整移动
- 更适合底层规则测试或明确不需要阻塞反应窗口的场景

当前已实现的移动规则要点：

- 按逐格路径检查
- 上下左右一格消耗 5 尺
- 斜线按 5/10 交替计费
- 中间插入直线后，斜线计数重置
- 会检查墙体、困难地形、占位和整块体型合法性
- 同伴可穿过，敌人不可穿过
- 小型 / 微型实体允许共享中心点判定规则下的合法占位
- 会自动读取实体 `conditions` 并附加移动限制：
  - `grappled` / `paralyzed` / `petrified` / `restrained` / `stunned` / `unconscious` 会直接阻止自愿移动
  - `frightened:<source_id>` 会阻止任何让自己更接近恐惧源的路径
  - `prone` 当前按匍匐移动处理，路径合法但每一步移动成本翻倍
  - `exhaustion:<level>` 会把当前速度上限减少 `level * 5` 尺，并影响本回合剩余可用移动力
- 旧存档里格式错误的 condition 字符串会在移动判定里被忽略，不会让 tool 直接崩溃

典型调用：

```python
result = MoveEncounterEntity(encounter_repository, append_event).execute_with_state(
    encounter_id="enc_preview_demo",
    entity_id="ent_ally_wizard_001",
    target_position={"x": 6, "y": 9},
    count_movement=True,
    use_dash=False,
)
```

返回后：

- 如果结果里带 `encounter_state`，直接交给 `window.applyToolResult(result)`

LLM 需要做的事：

- 理解玩家说的目标位置或方向
- 决定是否 `use_dash`
- 把最终目标坐标传给 tool

LLM 不需要做的事：

- 不自己扣移动力
- 不自己根据 condition 解释移动限制
- 不自己判路径是否合法
- 不自己改 token 坐标

### `BeginMoveEncounterEntity`

用途：

- 开启一段可能被 reaction 中断的真实移动
- 第一版主要给借机攻击使用

行为：

- 先校验整段路径是否合法
- 若途中没有 reaction，直接完成整段移动
- 若途中触发 reaction：
  - 停在触发点
  - 写入 `reaction_requests`
  - 写入 `pending_movement`
  - 返回 `movement_status = "waiting_reaction"`

典型调用：

```python
result = BeginMoveEncounterEntity(encounter_repository, append_event).execute_with_state(
    encounter_id="enc_preview_demo",
    entity_id="ent_enemy_orc_001",
    target_position={"x": 10, "y": 4},
    count_movement=True,
    use_dash=False,
)
```

LLM 必须关注：

- `movement_status`
- `reaction_requests`
- `encounter_state.reaction_requests`
- `encounter_state.pending_movement`

如果 `movement_status == "waiting_reaction"`：

- 若 `ask_player = true`，LLM 必须立刻询问玩家是否使用该反应
- 不能先把角色描述成已经到达终点

### `ContinuePendingMovement`

用途：

- 在 reaction 处理完后继续剩余移动
- 玩家不使用该 reaction 时，也调用它

行为：

- 当前阻塞 request 若仍为 `pending`，会先标记为 `expired`
- 若移动者已被打到 0 HP 或已无法继续移动，返回 `movement_status = "interrupted"`
- 若剩余路径上再次触发 reaction，会再次暂停并返回 `movement_status = "waiting_reaction"`
- 若后续没有新的 reaction，则完成剩余移动并返回 `movement_status = "completed"`

典型调用：

```python
result = ContinuePendingMovement(encounter_repository, append_event).execute_with_state(
    encounter_id="enc_preview_demo",
)
```

### `ResolveReactionRequest`

用途：

- 结算一个已生成的 reaction request
- 第一版只支持 `opportunity_attack`

当前行为：

- 校验 request 仍可执行
- 调用现有攻击链结算借机攻击
- 只消耗 `reaction_used`
- 不消耗 `action_used`
- 结算后把 request 标记为 `resolved`

典型调用：

```python
result = ResolveReactionRequest(encounter_repository, append_event, execute_attack).execute(
    encounter_id="enc_preview_demo",
    request_id="react_001",
    final_total=17,
    dice_rolls={"base_rolls": [12], "modifier": 5},
    damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
)
```

---

## 6.4 攻击

### `ExecuteAttack`

用途：

- 收口一次武器 / 攻击动作的完整结算

当前链路：

- 命中判定
- 命中后按 `damage_parts` 结算伤害
- 自动调用 `UpdateHp`
- 目标若正在专注且实际受伤，自动生成 `concentration_check_request`

LLM 需要提供的核心信息：

- 谁攻击
- 攻击谁
- 使用什么武器或攻击方式
- 攻击掷骰结果
- 每个伤害段的掷骰结果 `damage_rolls`

LLM 可从返回中读取：

- 是否命中
- 是否暴击
- `damage_resolution`
- `hp_update`
- 是否生成 `concentration_check_request`

这很重要，因为 LLM 要拿这些结果做 RP 描述。

---

## 6.5 豁免型法术

### `ExecuteSaveSpell`

用途：

- 收口一次单目标豁免型法术

当前链路：

- `EncounterCastSpell`
- `SavingThrowRequest`
- `ResolveSavingThrow`
- `SavingThrowResult`
- 需要时自动串 `UpdateHp`
- 需要时自动串 `UpdateConditions`
- 需要时自动串 `UpdateEncounterNotes`

### 当前主路径

豁免法术优先走法术模板：

- `spell_definition.failed_save_outcome`
- `spell_definition.successful_save_outcome`

当前 outcome 已实现字段：

- `damage_parts`
- `damage_parts_mode`
- `damage_multiplier`
- `conditions`
- `note`

### 伤害输入约定

法术伤害仍由外部 / LLM 提供 `damage_rolls`，系统负责：

- 校验 `source`
- 应用戏法成长
- 应用高环追加伤害
- 走 `ResolveDamageParts`
- 返回结构化 `damage_resolution`

### 当前边界规则

- 只传 `damage_reason` / `damage_type` 时，仍然走新模板主路径
- 只有旧的效果字段才算兼容旧路径：
  - `hp_change_on_failed_save`
  - `hp_change_on_success`
  - `conditions_on_failed_save`
  - `conditions_on_success`
  - `note_on_failed_save`
  - `note_on_success`
- 如果 `spell_definition` 和这些旧效果字段混用，应直接报错

### LLM 需要读的结果

- `success`
- `selected_outcome`
- `damage_resolution`
- `hp_update`
- `condition_updates`
- `note_update`

这些结果既用于规则判断，也用于 RP 描述。

---

## 5.6 标记转移

### `RetargetMarkedSpell`

用途：

- 把已经获得转移资格的单目标标记法术改挂到新目标
- 当前用于：
  - `Hex`
  - `Hunter's Mark`

输入重点：

- `encounter_id`
- `spell_instance_id`
- `new_target_id`

当前行为：

- 不重新施法
- 不消耗法术位
- 会消耗施法者本回合的附赠动作
- 会给新目标挂上新的标记 effect
- 会更新原 `spell_instance` 的当前目标
- 会把 `retarget_available` 改回 `false`

适用时机：

- 某个标记目标已经掉到 `0 HP`
- `GetEncounterState` 或上一条 tool 结果已经表明该法术实例进入可转移待命

LLM 判断信号：

- 如果上一条 `UpdateHp` 结果里出现 `retarget_updates`
- 或最新 `GetEncounterState` 里的 `retargetable_spell_actions` 非空
- 这时应该优先考虑 `RetargetMarkedSpell`
- 不要再调用一次 `EncounterCastSpell` 重新施法

推荐判断顺序：

1. 先看最新 `encounter_state.retargetable_spell_actions`
2. 如果其中有玩家正在操作的那条标记法术，就直接拿它的 `spell_instance_id`
3. 再根据玩家指定的新目标调用 `RetargetMarkedSpell`

和重新施法的区别：

- `EncounterCastSpell`
  - 是第一次施法
  - 会正常消耗法术位
- `RetargetMarkedSpell`
  - 是沿用现有持续中的同一个法术实例
  - 不消耗法术位
  - 只消耗附赠动作

典型调用：

```python
result = RetargetMarkedSpell(
    encounter_repository,
    append_event,
).execute(
    encounter_id="enc_preview_demo",
    spell_instance_id="spell_hex_001",
    new_target_id="ent_enemy_orc_001",
    include_encounter_state=True,
)
```

返回后：

- 直接把 `result.encounter_state` 交给前端刷新
- 新目标会出现新的标记 effect
- 原法术实例会继续存在，但目标改成新单位

---

## 5.7 共享更新 Tool

### `UpdateHp`

用途：

- 处理伤害 / 治疗并写回 encounter

约定：

- `hp_change > 0` 表示受到伤害
- `hp_change < 0` 表示受到治疗

系统会自动处理：

- 临时 HP
- 抗性 / 免疫 / 易伤
- 专注检定请求
- 可转移标记法术的待转移状态

### `UpdateConditions`

用途：

- 对目标应用或移除 condition

当前 condition 只做字符串层：

- 例如 `blinded`
- 例如 `incapacitated`

复杂持续时间、来源追踪、结束条件以后再补。

### `UpdateEncounterNotes`

用途：

- 记录战场备注或实体相关备注

适用场景：

- 特殊区域说明
- 法术遗留效果说明
- 一次性提醒文本

---

## 5.8 专注检定

### `ExecuteConcentrationCheck`

用途：

- 结算一次专注检定

通常情况：

- LLM 不需要主动手搓整条链
- 目标受到真实伤害后，`UpdateHp` 会自动生成 `concentration_check_request`
- 如果目标正被活动中的可转移标记法术影响，且这次伤害把目标打到 `0 HP`
- `UpdateHp` 会自动把该法术实例切换为“可转移待命”
- 并清掉旧目标身上的旧标记 effect
- 后续再对该请求进行专注结算

LLM 需要知道：

- 专注请求由系统自动生成
- 不要在目标没受伤时额外手动补一份

---

## 6. Map Notes 的定位

玩家一直看大地图。

LLM 额外拿一份结构化 `map_notes`，用于全局判断：

- 哪些区域是墙
- 哪些区域是困难地形
- 哪些区域是高台
- 哪些区域有特殊效果

这份信息给 LLM 做全局战场理解，不要求玩家直接阅读。

---

## 7. LLM 应该如何理解返回值

## 7.1 状态由系统维护

以下内容不应由 LLM 自己手工维护：

- 实体位置
- HP
- 条件列表
- 资源消耗
- 回合顺序
- 专注请求

LLM 只读 tool 返回结果，或重新读取 `GetEncounterState`。

## 7.2 描述信息给 RP 用

以下结构非常适合 LLM 做战斗描述：

- `damage_resolution.parts`
- `damage_resolution.total_damage`
- `hp_update.damage_adjustment`
- `condition_updates`
- `note_update`

例如：

- 暴击时可描述“重击”
- 额外火焰伤害可单独描述
- 目标因失败豁免而 `blinded` 时可单独描述

---

## 8. 不要这样做

不要：

- 不读 `encounter_state` 就猜当前状态
- 自己计算并直接改前端 token 位置
- 命中后只改 HP 文本，不刷新整页
- 自己把 condition 写进前端，但不调用 `UpdateConditions`
- 自己在前端拼一份假的当前回合信息
- 在 tool 已经自动处理专注请求时，再手动补一条

---

## 9. 最短示例

### 9.1 阻塞式移动

```python
state = GetEncounterState(encounter_repository).execute("enc_preview_demo")

result = BeginMoveEncounterEntity(encounter_repository, append_event).execute_with_state(
    encounter_id="enc_preview_demo",
    entity_id=state["current_turn_entity"]["id"],
    target_position={"x": 6, "y": 9},
    count_movement=True,
    use_dash=False,
)
```

```js
window.applyToolResult(result)
```

如果返回 `movement_status == "waiting_reaction"`，推荐流程：

1. 读取 `result.reaction_requests[0]`
2. 若 `ask_player == true`，立刻询问玩家是否使用该 reaction
3. 玩家不用时，调用 `ContinuePendingMovement`
4. 玩家要用时，先调用 `ResolveReactionRequest`，再调用 `ContinuePendingMovement`

### 9.2 豁免法术

```python
result = ExecuteSaveSpell(
    encounter_cast_spell,
    saving_throw_request,
    resolve_saving_throw,
    saving_throw_result,
).execute(
    encounter_id="enc_preview_demo",
    target_id="ent_enemy_iron_duster_001",
    spell_id="burning_hands",
    base_roll=6,
    damage_rolls=[
        {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
    ],
    damage_reason="燃烧之手火焰灼烧",
    damage_type="fire",
    include_encounter_state=True,
)
```

```js
window.applyToolResult(result)
```

---

## 10. 更新规则

今后凡是下面这些内容变化，都优先改这份文档：

- LLM 标准工作流
- 前端刷新契约
- 核心 tool 入口
- tool 返回结构
- 新增的自动规则链
- 需要 LLM 读取的关键字段

旧文档如果只覆盖其中一个局部主题，应尽量改成引用这份总手册，避免说明分叉。
