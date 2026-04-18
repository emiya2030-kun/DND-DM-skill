# Metamagic Batch 1 Design

## 目标

在现有术士与施法主链上，补上第一批可战斗落地的超魔法：

- `Quickened Spell / 瞬发法术`
- `Distant Spell / 远程法术`
- `Heightened Spell / 升阶法术`
- `Careful Spell / 谨慎法术`

这批实现继续复用现有 `metamagic_options` 入口，不引入独立的“超魔施法”服务，也不提前实现第二批超魔。

## 当前上下文

系统已经具备以下基础：

- 术士核心资源与运行时
  - `sorcery_points`
  - `UseInnateSorcery`
  - `ConvertSpellSlotToSorceryPoints`
  - `CreateSpellSlotFromSorceryPoints`
- 施法声明入口
  - `SpellRequest`
  - `EncounterCastSpell`
- 反应窗口与 `Counterspell / 反制法术`
- `Subtle Spell / 精妙法术`
  - 已经通过 `metamagic_options.selected = ["subtle_spell"]` 接入
  - 已经支持术法点扣除、事件写入、`noticeability` 元数据与反制法术跳过

本轮设计目标是让新的超魔继续挂在同一条主链，而不是发展出第二套规则入口。

## 范围

### 本轮包含

- 统一扩展 `metamagic_options`
- 在 `SpellRequest` 中做声明期校验与结构化结果生成
- 在 `EncounterCastSpell` 中做术法点消耗、动作经济改写、失败回滚、事件载荷写入
- 在射程校验中接入 `Distant Spell`
- 在豁免链中接入 `Heightened Spell`
- 在豁免链中接入 `Careful Spell`
- 在文档中为 LLM 补充新的调用规则

### 本轮不包含

- `Empowered Spell / 强效法术`
- `Seeking Spell / 追踪法术`
- `Transmuted Spell / 转化法术`
- `Extended Spell / 延效法术`
- `Twinned Spell / 孪生法术`
- 7 级 `Sorcery Incarnate / 术法化身` 带来的“一次法术可挂两个超魔”
- `Empowered Spell` 与其他超魔叠加的特例
- 将超魔抽成独立 service 层

## 方案选择

本轮采用“沿现有主链分点接入”的方案。

原因：

- 现有施法系统已经分为声明、施法、豁免、反应几条清晰主链
- 每个超魔影响的规则位置不同，硬做统一大入口会增加额外抽象
- 当前最需要的是战斗闭环，而不是超魔框架美观度

因此实现策略为：

- `SpellRequest` 负责“是否允许声明这个超魔”
- `EncounterCastSpell` 负责“是否扣资源、是否改动作、是否写事件”
- 射程 / 豁免等后续规则链只消费结构化 `metamagic` 数据

## 输入契约

继续统一使用：

```json
{
  "metamagic_options": {
    "selected": ["quickened_spell"],
    "heightened_target_id": "ent_enemy_001",
    "careful_target_ids": ["ent_ally_001", "ent_ally_002"]
  }
}
```

### 字段语义

- `selected`
  - 字符串数组
  - 本轮合法值：
    - `subtle_spell`
    - `quickened_spell`
    - `distant_spell`
    - `heightened_spell`
    - `careful_spell`
- `heightened_target_id`
  - 仅 `heightened_spell` 使用
  - 必须是本次法术的一个目标
- `careful_target_ids`
  - 仅 `careful_spell` 使用
  - 必须是本次法术影响范围内、且数量不超过 `max(1, cha_mod)` 的生物

## 组合规则

本轮一次法术只能声明一个超魔。

原因：

- 现有系统只有 `subtle_spell` 单超魔状态
- 如果这轮直接允许多超魔，会连带引入：
  - 排他校验
  - 资源累加
  - `Sorcery Incarnate` 例外
  - 各效果之间的先后级联

因此本轮规则明确为：

- `selected` 长度只能为 `0` 或 `1`
- 若大于 `1`，直接报错

## 术法点消耗

- `subtle_spell`: 1
- `distant_spell`: 1
- `careful_spell`: 1
- `quickened_spell`: 2
- `heightened_spell`: 2

`SpellRequest` 负责校验当前术法点是否足够。

`EncounterCastSpell` 负责实际扣除，并在事件写入失败时回滚。

## SpellRequest 职责

`SpellRequest` 继续作为超魔声明期事实源。

本轮新增职责：

1. 解析 `metamagic_options`
2. 校验 `selected` 数量
3. 校验每个超魔是否满足基础前提：
   - 必须是术士法术
   - 术士等级至少 2
   - 术法点足够
4. 生成统一的 `metamagic` 结构
5. 对需要额外参数的超魔做声明期校验

### 声明期额外校验

#### Quickened Spell

- 本次法术原始施法时间必须是 `action`
- 不能对本来就是 `bonus_action` 或 `reaction` 的法术使用
- 若本回合已经施放过一环或更高法术，则不能使用

#### Distant Spell

- 法术必须满足：
  - 射程至少 `5` 尺；或
  - 射程为 `touch`
- 否则报错

#### Heightened Spell

- 该法术必须强迫目标进行豁免
- 必须提供 `heightened_target_id`
- 该目标必须属于本次法术目标

#### Careful Spell

- 该法术必须强迫目标进行豁免
- 必须提供 `careful_target_ids`
- 保护目标数量不能超过 `max(1, cha_mod)`
- 所有保护目标必须是本次法术会影响到的生物

### SpellRequest 返回结构扩展

继续返回 `metamagic`，但结构扩成通用格式，例如：

```json
{
  "selected": ["heightened_spell"],
  "quickened_spell": false,
  "distant_spell": false,
  "heightened_spell": true,
  "careful_spell": false,
  "subtle_spell": false,
  "sorcery_point_cost": 2,
  "heightened_target_id": "ent_enemy_001",
  "careful_target_ids": []
}
```

对于不涉及的字段，返回安全默认值。

`noticeability` 继续保留，只有 `subtle_spell` 会改成不可感知；其他超魔不改变可见性。

## EncounterCastSpell 职责

`EncounterCastSpell` 本轮新增职责：

1. 消耗本次超魔对应的术法点
2. 将 `Quickened Spell` 的 `action_cost` 改写为 `bonus_action`
3. 将结构化 `metamagic` 写入：
   - `spell_declared` 事件 payload
   - reaction trigger payload
   - 施法返回值
4. 若事件写入失败：
   - 回滚法术位
   - 回滚术法点
   - 回滚动作经济

### Quickened Spell 的动作规则

本轮严格落地以下规则：

- 该法术从 `action` 改为 `bonus_action`
- 如果术士在同一回合里已经施放过一环或更高法术，则不能再瞬发一环或更高法术
- 一旦使用瞬发施放了一环或更高法术，本回合内也不能再施放另一道一环或更高法术

实现方式：

- 在施法者运行态中记录本回合“是否已经施放过一环或更高法术”
- `EncounterCastSpell` 在声明期读取并校验
- 施法成功落库后更新该标记

注意：

- 戏法不受这个“另一道一环或更高法术”限制
- `Quickened Spell` 仍然消耗附赠动作

## Distant Spell 规则

本轮只影响射程校验，不改区域大小，不改 AOE 模板半径。

### 行为

- 若法术射程至少 `5` 尺，则射程翻倍
- 若法术射程为 `touch`，则改为 `30` 尺

### 明确不做

- 不改 `Fireball` 之类的半径
- 不改锥形 / 线形模板尺寸
- 不处理特殊文本例外

### 接入点

- 使用现有目标点 / 目标实体射程校验逻辑
- 由 `metamagic.distant_spell = true` 改写“本次有效射程”

## Heightened Spell 规则

### 行为

- 施法者指定本次法术影响的一名目标
- 该目标对本次法术豁免具有劣势

### 接入点

- 豁免请求或豁免解析阶段读取：
  - `metamagic.heightened_spell`
  - `metamagic.heightened_target_id`
- 仅对该目标附加劣势

### 边界

- 只影响一次法术带来的当前这次豁免
- 不写持久状态
- 不影响其他目标

## Careful Spell 规则

### 行为

- 施法者指定最多 `max(1, cha_mod)` 名生物
- 这些生物自动通过本次法术豁免
- 若法术在成功豁免后仍然只造成半伤，则这些被保护目标改为 `0` 伤害

### 接入点

- 豁免请求或豁免解析阶段读取：
  - `metamagic.careful_spell`
  - `metamagic.careful_target_ids`
- 对被保护目标：
  - 直接标记豁免成功
  - 若后续成功豁免伤害倍率为 `0.5`，额外覆盖为 `0`

### 边界

- 只处理“自动成功且半伤改零伤”
- 不追加额外免疫状态
- 对非伤害类豁免法术，仍然只表现为自动成功

## 事件与 LLM 可见数据

这批超魔继续走和 `subtle_spell` 相同的暴露策略。

`spell_declared` 事件 payload 与施法返回值中都应保留：

- `metamagic`
- `noticeability`

补充原则：

- `Quickened Spell` 让 LLM 能知道本次是附赠动作施法
- `Heightened Spell` 让 LLM 能知道哪个目标吃到劣势
- `Careful Spell` 让 LLM 能知道哪些目标被保护
- `Distant Spell` 让 LLM 能知道本次射程被改写

## 错误语义

本轮错误需要保持具体，不使用模糊总报错。

建议新增以下错误码：

- `multiple_metamagic_not_supported`
- `metamagic_requires_sorcerer_spell`
- `metamagic_requires_sorcerer_level_2`
- `insufficient_sorcery_points`
- `quickened_spell_requires_action_cast_time`
- `quickened_spell_conflicts_with_same_turn_leveled_spell`
- `distant_spell_requires_range_or_touch_spell`
- `heightened_spell_requires_saving_throw_spell`
- `heightened_spell_requires_target`
- `heightened_target_not_in_spell_targets`
- `careful_spell_requires_saving_throw_spell`
- `careful_spell_requires_targets`
- `careful_spell_too_many_targets`
- `careful_target_not_in_spell_targets`

`Subtle Spell` 现有错误语义若与这些命名不一致，可以在实现中做一次统一。

## 测试策略

### SpellRequest

至少覆盖：

- `Quickened` 合法声明
- `Quickened` 非 `action` 法术时报错
- 多超魔同时声明时报错
- `Distant` 射程法术合法
- `Distant` 非触碰/非远程时报错
- `Heightened` 缺目标时报错
- `Careful` 超过魅调上限时报错

### EncounterCastSpell

至少覆盖：

- `Quickened` 会扣 2 点术法点并改成 `bonus_action`
- `Quickened` 与同回合高环法术冲突时报错
- 事件写入失败会回滚术法点
- 结果与事件都会带 `metamagic`

### 射程链

至少覆盖：

- `Distant` 让原本超距目标变合法
- `touch -> 30 尺`

### 豁免链

至少覆盖：

- `Heightened` 指定目标的豁免带劣势
- `Careful` 保护目标自动成功
- `Careful` 在半伤法术下改为 0 伤
- 非保护目标仍按正常规则结算

## 文档更新

需要更新：

- `docs/llm-runtime-tool-guide.md`
- `docs/development-plan.md`

文档必须明确写出：

- 新的 `metamagic_options` 输入格式
- 每个已实现超魔的可用条件
- `Quickened Spell` 的动作经济限制
- 当前仍然只支持“单超魔”

## 实现顺序

推荐顺序：

1. 扩 `SpellRequest` 的通用超魔解析和校验
2. 接 `EncounterCastSpell` 的资源与动作经济
3. 接 `Distant Spell` 到射程校验
4. 接 `Heightened` / `Careful` 到豁免链
5. 更新文档与测试

## 未来兼容性

虽然本轮不做统一大框架，但这份结构应为后续超魔预留空间：

- `selected` 保持数组
- `metamagic` 保持结构化字典
- 允许未来继续加：
  - `empowered_spell`
  - `seeking_spell`
  - `transmuted_spell`
  - `extended_spell`
  - `twinned_spell`

同时保留一个明确限制：

- 在正式支持 `Sorcery Incarnate` 之前，任何一次法术都只能声明一个超魔
