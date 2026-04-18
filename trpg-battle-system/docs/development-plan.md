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

### 2026-04-18 补充：飞行移动

已完成：

- `validate_movement_path(...)` 支持 `movement_mode`
- `MoveEncounterEntity.execute(...)` 支持 `movement_mode`
- `BeginMoveEncounterEntity.execute(...)` / `execute_with_state(...)` 支持 `movement_mode`
- `ContinuePendingMovement` 会继承 pending movement 中的 `movement_mode`
- `runtime move_and_attack` 支持透传 `movement_mode`

当前可用值：

- `walk`
- `fly`
- `swim`
- `climb`

当前规则：

- `movement_mode=fly` 时，移动距离按实体的 `speed.fly` 结算
- 飞行移动忽视困难地形额外消耗
- 飞行移动仍然受地图边界、墙体、目标格占位、借机攻击流程约束
- pending movement / 借机打断后续走会继续沿用同一 `movement_mode`

LLM 使用建议：

- 需要明确声明飞行时，在相关移动调用上传 `movement_mode: "fly"`
- 如果不传，默认仍按 `walk` 处理

### 2026-04-18 补充：runtime 纯移动命令

已完成：

- 新增 runtime command：`move_entity`

调用参数：

```json
{
  "command": "move_entity",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "ent_familiar_425418266f7d",
    "target_position": {"x": 11, "y": 4},
    "use_dash": false,
    "movement_mode": "fly"
  }
}
```

字段说明：

- `encounter_id`：遭遇战 id
- `actor_id`：当前要移动的实体 id
- `target_position`：目标格坐标
- `use_dash`：可选；是否冲刺
- `movement_mode`：可选；默认 `walk`

返回语义：

- 如果移动过程中触发借机等反应窗，`result.movement_status = "waiting_reaction"`
- 如果移动成功完成，`result.movement_status = "completed"`
- `encounter_state` 始终返回最新状态

LLM 使用规则：

- 只做纯移动时，优先用 `move_entity`
- 需要移动后立刻攻击时，再用 `move_and_attack`
- 有飞行速度的实体在飞行移动时，显式传 `movement_mode: "fly"`

### 2026-04-18 补充：runtime 启动命令完整性校验

已完成：

- `run_battle_runtime.py` 启动前会执行本地命令注册表自检
- `run_battlemap_localhost.py` 连接远端 runtime 前会校验 `/runtime/health`

当前规则：

- runtime 本地自检会扫描 `runtime/commands/` 下的命令模块
- 若发现存在命令模块但未注册进 `COMMAND_HANDLERS`，runtime 会直接启动失败
- battlemap localhost 连接 runtime 时，默认要求远端 `commands` 覆盖当前仓库里的全部 `COMMAND_HANDLERS`
- 若远端 runtime 少任何一个本地命令，例如 `move_entity`，battlemap localhost 会直接拒绝启动

目的：

- 避免出现“仓库代码里已有命令，但连到的仍是旧 runtime 进程”的假联调
- 把命令集不一致问题前置到启动阶段，而不是拖到战斗操作时才暴露

### 2026-04-18 补充：Metamagic Batch 1 / 超魔法第一批

已完成：

- `SpellRequest.execute(...)` 新增 `metamagic_options`
- `EncounterCastSpell.execute(...)` 新增 `metamagic_options`
- `ExecuteSaveSpell.execute(...)` 新增 `metamagic_options`
- `spell_declared` 事件与施法返回结果新增：
  - `metamagic`
  - `noticeability`
- `SavingThrowRequest` 会读取超魔上下文
- `SavingThrowResult` 会处理 `Careful Spell / 谨慎法术` 的“成功半伤改零”
- `Counterspell / 反制法术` 候选收集会跳过 `subtle_spell`

当前规则：

- 当前一次施法只支持声明一种超魔法
- 当前支持：
  - `subtle_spell`
  - `quickened_spell`
  - `distant_spell`
  - `heightened_spell`
  - `careful_spell`
- 只有术士法术可以使用这些超魔法
- 施法者至少需要 `2` 级术士
- 后端会自动扣除对应术法点：
  - `subtle_spell = 1`
  - `distant_spell = 1`
  - `careful_spell = 1`
  - `quickened_spell = 2`
  - `heightened_spell = 2`
- 如果事件写入失败，后端会回滚本次扣除的术法点
- `noticeability.casting_is_perceptible = false` 主要供 LLM 做剧情判断
- 当前仍允许 `spell_effect_visible = true`，即法术效果本身依然可见
- `quickened_spell` 会把原本的动作施法改为附赠动作施法
- 已实现 2024 施法位规则：
  - 每回合中，通过施法实际消耗法术位的次数最多为一次
  - 这条限制只看“是否实际消耗法术位”，不看是不是附赠动作，也不看法术环阶
  - 戏法、免费施法、物品施法等不消耗法术位的施法，不计入这条限制
- `heightened_spell` 需要传 `heightened_target_id`
- `careful_spell` 需要传 `careful_target_ids`
- `heightened_spell` 会让指定目标对此次法术豁免具有劣势
- `careful_spell` 会让受保护目标自动通过豁免；若该法术“成功豁免仍受半伤”，则该目标改为 `0` 伤害

LLM 使用规则：

- 普通施法仍然调用 `EncounterCastSpell`
- 豁免法术整链调用 `ExecuteSaveSpell` 时，也可以直接透传同一份 `metamagic_options`
- 通用格式：

```json
{
  "metamagic_options": {
    "selected": ["subtle_spell"]
  }
}
```

- `Quickened Spell / 瞬发法术`

```json
{
  "metamagic_options": {
    "selected": ["quickened_spell"]
  }
}
```

- `Distant Spell / 远程法术`

```json
{
  "metamagic_options": {
    "selected": ["distant_spell"]
  }
}
```

- `Heightened Spell / 升阶法术`

```json
{
  "metamagic_options": {
    "selected": ["heightened_spell"],
    "heightened_target_id": "ent_enemy_001"
  }
}
```

- `Careful Spell / 谨慎法术`

```json
{
  "metamagic_options": {
    "selected": ["careful_spell"],
    "careful_target_ids": ["ent_ally_001", "ent_ally_002"]
  }
}
```

### 2026-04-19 补充：Metamagic Batch 2 / 超魔法第二批

已完成：

- `SpellRequest.execute(...)` / `EncounterCastSpell.execute(...)` 现已支持：
  - `empowered_spell`
  - `extended_spell`
  - `seeking_spell`
  - `transmuted_spell`
  - `twinned_spell`
- `ExecuteSpell` 攻击法术链路已支持：
  - `seeking_spell`
  - `empowered_spell`
  - `transmuted_spell`
- `SavingThrowResult` 豁免伤害链路已支持：
  - `empowered_spell`
  - `transmuted_spell`
- `build_spell_instance(...)` 现在会记录本次施法的 `metamagic`
- `extended_spell` 会把法术实例写为默认“持续到长休”，并让该法术的专注检定获得优势
- `UpdateHp` 现在会读取正在维持的延效法术实例，并自动给对应专注检定优势

当前规则：

- 当前一次施法仍只支持声明一种超魔法
- `empowered_spell = 1`
- `extended_spell = 1`
- `seeking_spell = 1`
- `transmuted_spell = 1`
- `twinned_spell = 1`
- `empowered_spell`
  - 只能用于造成伤害的法术
  - 仍然必须在施法声明时提前传 `metamagic_options`
  - 后端会自动按期望收益最高策略重骰低于均值的伤害骰
  - 最多重骰魅力调整值个伤害骰，至少可重骰 1 个
- `extended_spell`
  - 只能用于持续时间至少 1 分钟，或需要专注的法术
  - 当前项目尚无完整长休自动清算，因此运行态表现为“默认持续到长休”
  - 若该法术需要专注，则该法术对应的专注检定具有优势
- `seeking_spell`
  - 只能用于需要攻击检定的法术
  - 若这次法术攻击未命中，后端会自动重骰 1 次 d20
  - 必须使用新结果，不取高
- `transmuted_spell`
  - 只能用于带可转化元素伤害的法术
  - 目前只支持这 6 种类型之间互转：
    - `acid`
    - `cold`
    - `fire`
    - `lightning`
    - `poison`
    - `thunder`
  - 伤害类型会在抗性 / 免疫 / 易伤结算前改写
- `twinned_spell`
  - 只能用于“升环时可额外增加一个目标”的单体法术
  - 后端会把这次施法视为“仅用于目标扩展的等效 +1 环”
  - 不会修改真实 `cast_level`
  - 不会额外消耗更高环位

LLM 使用规则：

- 这 5 个超魔都仍然只需要通过 `metamagic_options` 声明
- LLM 不需要手动指定重骰哪几个伤害骰
- LLM 不需要手动在攻击失手后再追加调用“追踪法术”
- LLM 不需要手动改写伤害类型结算
- LLM 不需要手动把 `twinned_spell` 的 `cast_level` 加 1

- `Empowered Spell / 强效法术`

```json
{
  "metamagic_options": {
    "selected": ["empowered_spell"]
  }
}
```

- `Extended Spell / 延效法术`

```json
{
  "metamagic_options": {
    "selected": ["extended_spell"]
  }
}
```

- `Seeking Spell / 追踪法术`

```json
{
  "metamagic_options": {
    "selected": ["seeking_spell"]
  }
}
```

- `Transmuted Spell / 转化法术`

```json
{
  "metamagic_options": {
    "selected": ["transmuted_spell"],
    "transmuted_damage_type": "cold"
  }
}
```

- `Twinned Spell / 孪生法术`

```json
{
  "metamagic_options": {
    "selected": ["twinned_spell"]
  }
}
```

### 2026-04-18 补充：玩家召唤物共享宿主回合

已完成：

- 新增共享回合判定 helper
- 玩家控制、且 `source_ref.summoner_entity_id` 指向玩家实体的 `summon`
  - 不再插入 `turn_order`
  - 保留实体本身、地图占位与独立动作经济
- 动作合法性从“必须等于 `current_entity_id`”提升为“当前回合编组成员可行动”
- `GetEncounterState` 新增 `current_turn_group`
- 旧遭遇战若先攻表里仍残留玩家召唤物节点，读取时会自动标准化移除

当前语义：

- 玩家可以在同一回合里交错操纵宿主与召唤物
- 例如：角色移动 -> 魔宠协助 -> 角色攻击
- 召唤物继续使用自己的 `actor_id` 调用现有动作接口
- 共享回合召唤物不会再单独开始 / 结束自己的独立回合

LLM 使用规则：

- 先读取 `current_turn_group`
- 若目标召唤物出现在 `controlled_members` 中，则本回合可以直接操作它
- 对外命令参数不变，仍然传该召唤物自己的 `actor_id`

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

## Warlock LLM 调用约定

### Armor of Shadows / 幽影护甲

用途：

- 以动作对自己施放 `Mage Armor / 法师护甲`
- 不消耗法术位

服务：

- `UseArmorOfShadows`

调用参数：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001"
}
```

参数说明：

- `encounter_id`：当前遭遇战 ID
- `actor_id`：要使用幽影护甲的术士实体 ID

调用前提：

- 当前必须轮到 `actor_id`
- `actor_id` 需要拥有 `Armor of Shadows / 幽影护甲`
- `actor_id` 的动作尚未使用
- `actor_id` 不能穿着护甲；若已穿护甲，后端会报 `mage_armor_requires_unarmored_target`

成功后后端会写入：

- `warlock.armor_of_shadows.enabled = true`
- 在 `actor.turn_effects` 中写入一个 `effect_type = "mage_armor"` 的持续效果
- 刷新实体 AC 为 `13 + 敏捷调整值`

LLM 使用规则：

- 这是一个主动声明能力，直接调用 `UseArmorOfShadows`
- 不需要传法术位参数，后端不会扣 `spell_slots` 或 `pact_magic_slots`
- 如果目标已经穿着护甲，不要调用
- 如果角色已经有 `mage_armor`，后端会刷新该效果，不会重复叠加

持续时间规则：

- 当前系统把这类 `8 小时` 防护统一建模为 `持续到长休`
- 对 `Mage Armor / 法师护甲`，额外保留“穿上护甲则提前结束”的规则
- 目前长休自动清理器还没实现，所以这个时长规则先记录在运行态和文档里，由后续长休系统统一收口

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "armor_of_shadows": {
          "enabled": true
        },
        "available_features": [
          "eldritch_invocations",
          "pact_magic",
          "armor_of_shadows",
          "magical_cunning"
        ]
      }
    }
  }
}
```

### Fiendish Vigor / 邪魔活力

用途：

- 以动作施放一次无需法术位的 `False Life / 虚假生命`
- 当前实现按该法术的最大值直接给予临时生命值

服务：

- `UseFiendishVigor`

调用参数：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001"
}
```

参数说明：

- `encounter_id`：当前遭遇战 ID
- `actor_id`：要使用邪魔活力的术士实体 ID

调用前提：

- 当前必须轮到 `actor_id`
- `actor_id` 需要拥有 `Fiendish Vigor / 邪魔活力`
- `actor_id` 的动作尚未使用

成功后后端会写入：

- 通过 `GrantTemporaryHp` 给自身结算临时生命值
- 当前实现固定按 `False Life / 虚假生命` 最大值处理，即 `12` 点临时生命值
- 不会消耗 `spell_slots` 或 `pact_magic_slots`

LLM 使用规则：

- 这是一个主动声明能力，直接调用 `UseFiendishVigor`
- 如果角色当前没有更高的临时生命值，就会替换成 12
- 如果角色当前已有更高的临时生命值，后端会保留原值

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "fiendish_vigor": {
          "enabled": true
        },
        "available_features": [
          "eldritch_invocations",
          "pact_magic",
          "fiendish_vigor",
          "magical_cunning"
        ]
      }
    }
  }
}
```

### Gaze of Two Minds / 共视感官

用途：

- 以附赠动作与一个自愿生物建立感官连接。

服务：

- `UseGazeOfTwoMinds`

调用参数：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001",
  "target_id": "ent_ally_001"
}
```

参数说明：

- `encounter_id`：当前遭遇战 ID
- `actor_id`：施放共视感官的术士实体 ID
- `target_id`：要建立连接的目标实体 ID

调用前提：

- 当前必须轮到 `actor_id`
- `actor_id` 需要拥有 `Gaze of Two Minds / 共视感官`
- `actor_id` 的附赠动作尚未使用
- `target_id` 必须位于触及范围内，也就是 5 尺内

成功后后端会写入术士运行态：

- `linked_entity_id`
- `linked_entity_name`
- `remaining_source_turn_ends`
- `special_senses`

LLM 使用规则：

- 先用 `UseGazeOfTwoMinds` 建立连接。
- 后续施法时不用额外传新参数，后端会自动读取当前连接状态。
- 如果 `can_cast_via_link = true`，则单体攻击法术会按连接目标的位置做射程与视线校验。
- 如果目标超出 60 尺，后端会自动退回施法者自身位置，不会继续借位施法。

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "gaze_of_two_minds": {
          "enabled": true,
          "linked_entity_id": "ent_ally_001",
          "linked_entity_name": "Scout",
          "remaining_source_turn_ends": 2,
          "special_senses": {
            "darkvision": 60
          },
          "can_cast_via_link": true,
          "distance_to_link_feet": 5
        }
      }
    }
  }
}
```

### Pact of the Chain / 链之魔契

用途：

- 以一个魔法动作无耗位召唤或替换你的特殊魔宠
- 当前实现直接走职业特性服务，不依赖通用 `EncounterCastSpell`

服务：

- `UsePactOfTheChain`

调用参数：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001",
  "familiar_form": "pseudodragon",
  "creature_type": "celestial",
  "target_point": {
    "x": 3,
    "y": 2,
    "anchor": "cell_center"
  }
}
```

参数说明：

- `encounter_id`：当前遭遇战 ID
- `actor_id`：使用链之魔契的术士实体 ID
- `familiar_form`：当前支持的魔宠形态之一
  - `slaad_tadpole`
  - `pseudodragon`
  - `owl`
  - `skeleton`
  - `zombie`
  - `sprite`
  - `quasit`
  - `imp`
  - `sphinx_of_wonder`
- `creature_type`：可选；当 `familiar_form = owl` 时可传，例如 `celestial / fey / fiend`
- `target_point`：可选；若不传，后端会自动把魔宠放在施法者身边最近的合法未占据格

调用前提：

- 当前必须轮到 `actor_id`
- `actor_id` 需要拥有 `Pact of the Chain / 链之魔契`
- `actor_id` 的动作尚未使用
- 如果传了 `target_point`，则必须在施法者 `10 尺` 内且是合法未占据格

后端行为：

- 召唤物会加入地图与遭遇战实体表
- 召唤物会自己掷先攻，并按先攻插入 `turn_order`
- 若术士已有旧魔宠，后端会先移除旧魔宠，再放入新魔宠
- 不消耗 `spell_slots` 或 `pact_magic_slots`
- 会写入术士运行态：
  - `warlock.pact_of_the_chain.familiar_entity_id`
  - `warlock.pact_of_the_chain.familiar_name`
  - `warlock.pact_of_the_chain.familiar_form_id`

LLM 使用规则：

- 这是一个主动声明能力，直接调用 `UsePactOfTheChain`
- 若玩家没有指定落点，可以省略 `target_point`
- 若玩家明确指定落点，就把格点传给后端校验
- 若玩家想更换魔宠形态，直接再次调用；后端会自动替换旧魔宠

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "pact_of_the_chain": {
          "enabled": true,
          "familiar_entity_id": "ent_familiar_001",
          "familiar_name": "Pseudodragon",
          "familiar_form_id": "pseudodragon"
        },
        "available_features": [
          "eldritch_invocations",
          "pact_magic",
          "pact_of_the_chain",
          "magical_cunning"
        ]
      }
    }
  }
}
```

### Eldritch Mind / 魔能意志

用途：

- 被动强化专注维持
- 使角色进行“保持专注”的体质豁免时具有优势

触发方式：

- 不单独调用服务
- 后端在 `RequestConcentrationCheck` 时自动读取该祈唤

后端行为：

- 如果术士拥有 `Eldritch Mind / 魔能意志`，专注检定请求默认会变为 `advantage`
- 如果外部已经给了 `disadvantage`，当前实现会先与该优势抵消，结果变为 `normal`

LLM 使用规则：

- 不需要额外声明
- 只要角色已选择该祈唤，专注检定链会自动生效

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "eldritch_mind": {
          "enabled": true
        },
        "available_features": [
          "eldritch_invocations",
          "pact_magic",
          "eldritch_mind",
          "magical_cunning"
        ]
      }
    }
  }
}
```

### Devil's Sight / 魔鬼视界

用途：

- 被动提供 120 尺特殊视觉
- 目前只作为 LLM 可读规则摘要，不直接改战斗判定

触发方式：

- 不单独调用服务
- 后端在 `warlock` 运行态与 `GetEncounterState` 中自动投影

后端行为：

- 若术士拥有 `Devil's Sight / 魔鬼视界`，运行态会写入：
  - `enabled = true`
  - `range_feet = 120`
  - `sees_magical_darkness = true`

当前限制：

- 现在还没有把 `魔法黑暗 / magical darkness` 正式接入视线判定
- 所以这项能力当前主要是给 LLM 读取，并在如 `Darkness / 黑暗术` 之类配合中手动参考

LLM 使用规则：

- 不需要主动声明
- 当战场上存在普通黑暗或魔法黑暗相关描述时，优先查看施法者是否有 `devils_sight`
- 目前后端不会自动因为该能力修改命中、视线或可见性结果

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "class_features": {
      "warlock": {
        "devils_sight": {
          "enabled": true,
          "range_feet": 120,
          "sees_magical_darkness": true
        },
        "available_features": [
          "eldritch_invocations",
          "pact_magic",
          "devils_sight",
          "magical_cunning"
        ]
      }
    }
  }
}
```

### Eldritch Smite / 魔能斩

用途：

- 当术士以契约武器命中目标后，消耗一个契约法术位，附加力场伤害，并可选择将目标击倒。

触发方式：

- 不单独调用服务。
- 通过 `ExecuteAttack` 的 `class_feature_options.eldritch_smite` 显式声明触发。

调用参数：

```json
{
  "encounter_id": "enc_xxx",
  "target_id": "ent_enemy_001",
  "weapon_id": "longsword",
  "final_total": 19,
  "dice_rolls": {
    "base_rolls": [13],
    "modifier": 6
  },
  "damage_rolls": [
    {
      "source": "weapon:longsword:part_0",
      "rolls": [3]
    },
    {
      "source": "warlock_eldritch_smite",
      "rolls": [1, 2, 3, 4]
    }
  ],
  "class_feature_options": {
    "eldritch_smite": {
      "enabled": true,
      "slot_level": 3,
      "knock_prone": true
    }
  }
}
```

## Spell Notes For LLM

### Disguise Self / 易容术

用途：

- 标准一环自我幻术
- 当前实现目标是“可施放、可投影、可让 LLM 看到识破规则”

调用方式：

- 通过 `ExecuteSpell`
- 当前推荐直接把它当作普通自我法术使用

调用参数示例：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001",
  "spell_id": "disguise_self",
  "cast_level": 1,
  "declared_action_cost": "action"
}
```

后端行为：

- 若法术定义的 `targeting.type = self`，后端会自动把施法者自己补成目标
- 会生成一个活动中的 `spell_instance`
- 会给施法者写入一个 `effect_type = disguise_self` 的持续效果

当前限制：

- 当前系统不做“研究动作识破幻术”的自动规则执行
- 但可以在效果元数据中记录：
  - 外观描述
  - 身高变化
  - 体态描述
  - “物理检查会穿过去”
  - “可通过 Investigation vs spell DC 识破”
- 这些信息主要给 LLM 读取并用于叙事判断

持续时间规则：

- 按当前统一约定，`1 小时` 类效果先按“持续到长休”处理
- 后续等长休系统与更完整时长系统补上后，再统一收口

参数说明：

- `class_feature_options.eldritch_smite.enabled`：是否声明本次攻击命中后触发魔能斩
- `class_feature_options.eldritch_smite.slot_level`：本次要消耗的契约法术位环级
- `class_feature_options.eldritch_smite.knock_prone`：命中后是否尝试将目标击倒

调用前提：

- `actor_id` 必须拥有 `Eldritch Smite / 魔能斩`
- 当前攻击必须使用已绑定的 `Pact of the Blade / 刃之魔契` 武器
- 本回合尚未使用过魔能斩
- 必须有一个与 `slot_level` 完全一致且仍可用的 `pact_magic_slots`

后端行为：

- 只有命中时才会生效
- 额外伤害公式为 `1d8 + 每法术位环级 1d8`
- 后端实现为 `(slot_level + 1)d8` 力场伤害
- 只消耗 `pact_magic_slots`，不会消耗普通 `spell_slots`
- 若 `knock_prone = true`，则对 `Huge / 巨型` 及以下目标附加 `prone`
- 若目标体型超过 `Huge / 巨型`，则不会击倒，但仍正常造成额外伤害

成功后后端会写入：

- `warlock.eldritch_smite.used_this_turn = true`
- `resources.pact_magic_slots.remaining`

LLM 使用规则：

- 只有在“契约武器已经命中”且“本回合还没用过魔能斩”时，才声明 `eldritch_smite`
- `slot_level` 必须与当前可用的契约法术位环级一致
- 如果想附带击倒效果，再传 `knock_prone = true`
- 若攻击未命中，不要声明魔能斩

`GetEncounterState` 里建议 LLM 重点读取：

```json
{
  "resources": {
    "pact_magic_slots": {
      "slot_level": 3,
      "max": 2,
      "remaining": 2
    },
    "class_features": {
      "warlock": {
        "eldritch_smite": {
          "enabled": true,
          "used_this_turn": false
        }
      }
    }
  }
}
```

### Find Familiar Special Forms / 寻获魔宠特殊形态数据

用途：

- 为 `Find Familiar / 寻获魔宠` 与后续 `Pact of the Chain / 链之魔契` 提前补齐特殊形态的数据底座
- 当前先提供召唤实体 builder 与结构化资料，不直接开放新的玩家动作服务

当前已内置的特殊形态：

- `slaad_tadpole`
- `pseudodragon`
- `owl`
- `skeleton`
- `zombie`
- `sprite`
- `quasit`
- `imp`
- `sphinx_of_wonder`

当前数据落点：

- 可直接用于攻击链的动作写入 `EncounterEntity.weapons`
- 不进入当前自动战斗结算的特殊能力写入 `source_ref`
  - `traits_metadata`
  - `actions_metadata`
  - `reactions_metadata`
  - `special_senses`
  - `languages`
  - `condition_immunities`

当前限制：

- 这一层只是数据 builder，不负责把魔宠正式召入战斗
- `链之魔契 / Pact of the Chain` 的控制逻辑、魔宠独立先攻、特殊动作按钮、变形/隐形/真心视界等主动能力还没接服务
- 因此这些特殊能力当前主要给 LLM 读取，用于叙事与规则判断

LLM 使用规则：

- 如果战场上已经存在这类魔宠实体，优先从该实体的 `source_ref` 读取其特殊感官、特质与动作说明
- 若看到 `weapons` 中存在可攻击条目，可以按普通攻击链使用这些攻击
- 若是 `source_ref.actions_metadata` 或 `source_ref.reactions_metadata` 中的能力，当前默认视为“规则已记录、系统未自动化”，由 LLM 判断是否可叙述或暂不触发

### Find Familiar / 寻获魔宠

用途：

- 通过 `EncounterCastSpell` 正式把魔宠召入战斗
- 当前已支持一只普通形态：`owl`

调用方式：

- `EncounterCastSpell.execute(...)`

调用参数示例：

```json
{
  "encounter_id": "enc_xxx",
  "actor_id": "ent_warlock_001",
  "spell_id": "find_familiar",
  "cast_level": 1,
  "target_point": {
    "x": 3,
    "y": 2,
    "anchor": "cell_center"
  },
  "spell_options": {
    "familiar_form": "owl",
    "creature_type": "celestial"
  }
}
```

参数说明：

- `spell_options.familiar_form` 为必填
- 当前支持值：
  - `slaad_tadpole`
  - `pseudodragon`
  - `owl`
  - `skeleton`
  - `zombie`
  - `sprite`
  - `quasit`
  - `imp`
  - `sphinx_of_wonder`
- 当 `spell_options.familiar_form = owl` 时，可额外传 `spell_options.creature_type`
  - 可省略；当前后端省略时默认按 `fey` 记录
- `target_point` 可省略；省略时后端会自动找施法者身边最近的合法未占据格

调用前提：

- 必须掌握 `find_familiar`
- 必须提供 `spell_options.familiar_form`
- 若提供 `target_point`，则必须位于施法者 `10 尺` 内且是合法未占据格

后端行为：

- 会创建 `spell_instance`
- 会创建对应特殊形态召唤物实体并加入地图
- 召唤物会自己掷先攻，并按先攻插入 `turn_order`
- 同一施法者再次施放时，会先移除旧魔宠，再放入新魔宠

当前限制：

- 目前普通动物形态只支持 `owl`
- 暂不支持通过通用 `ExecuteSpell` 传 `spell_options`
- 这一轮只保证 `EncounterCastSpell` 直调稳定可用
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
- [x] GrantTemporaryHp 基础服务
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
- [ ] 临时生命值的长休清空尚未接入
  - 当前已支持临时生命值吸收伤害与通用授予服务
  - 但由于长休系统尚未实现，"无持续时间的临时生命值在长休结束时清空" 这条规则仍未落地
- [ ] 更完整的装备持握与弹药管理
- [ ] 更完整的 LLM 战斗协议文档拆分
- [ ] 术士 `Font of Magic / 魔力泉涌` 造出的临时法术位，尚未接入真正的长休自动清空
  - 当前底层已经支持记录 `created_spell_slots`
  - 但由于统一长休系统尚未实现，暂时不会自动在长休结算时移除这些临时法术位

## 玩家可见层中文化约定

- `GetEncounterState` 属于玩家可见投影层，默认应输出中文展示文案。
- 内部 runtime / repository / event payload 继续保留稳定英文 id。
  - 例如：`spell_id`、`weapon_id`、`entity_id`、`effect_type`、`damage_type` 不因展示层中文化而改变。
- 中文化优先放在投影层完成，不在底层状态里回写中文。
- 当前已在投影层中文化的典型内容包括：
  - 生命状态摘要
  - 条件与持续效果标签
  - 距离 / 网格 / 移动力单位
  - 法术位与契约魔法摘要
  - 常见武器 / 法术展示名与伤害类型
- 后续新增对外动作调用接口时，除参数协议外，必须同步补充一段面向 LLM 的中文调用说明，写入本文件或相邻开发文档，避免调用层与展示层脱节。

## 维护方式

这份文档不是最初阶段的“计划草稿”，而是当前开发现状文档。

后续维护规则：

1. 每次完成一组稳定能力后，更新对应阶段状态与能力清单。
2. 若某个系统从“基础版”提升为“完整规则版”，应同步更新“暂未完成”部分。
3. 若测试总量显著变化，可同步更新“当前总览”中的测试统计。
