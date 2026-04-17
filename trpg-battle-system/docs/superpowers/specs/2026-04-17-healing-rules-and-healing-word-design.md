# 2026-04-17 Healing Rules And Healing Word Design

## Goal

把“恢复生命值”的通用规则正式接入战斗系统，并新增一个可在遭遇战中完整执行的治疗法术 `Healing Word`。

本次范围只包含：

- `UpdateHp` 的通用治疗规则
- `Healing Word` 的法术模板与施法结算

本次明确不包含：

- 其他治疗法术（如 `Cure Wounds`）
- 治疗药水
- 休息恢复
- `Second Wind` 等既有职业治疗来源的统一迁移
- 视线系统重做

## Current State

- 系统已经支持 `hp_change < 0` 视为治疗。
- `UpdateHp` 已支持治疗封顶到 `hp.max`，并产出 `healing_applied` 事件。
- 目前尚未阻止“对已死亡目标治疗”。
- `ExecuteSpell` 当前已支持：
  - 攻击型法术
  - 豁免伤害型法术
  - 豁免附状态型法术
  - 无掷骰即时法术
- 当前没有正式的“即时治疗法术”结算分支。

## Rules To Implement

### Healing

- 任何治疗都会把恢复量加到目标当前 HP 上。
- 恢复后的当前 HP 不能超过最大 HP。
- 超出最大 HP 的恢复量直接损失。
- 已死亡生物不能恢复 HP，除非通过专门的复活法术复生。

### Healing Word

- 一环法术
- 施法时间：附赠动作
- 射程：60 尺
- 目标：施法距离内一个你能看见的生物
- 效果：恢复 `2d4 + 施法属性调整值`
- 升环：每比 1 环高 1 环，额外恢复 `2d4`

## Design Overview

采用“统一即时生命变动入口”方案：

- 所有本次新增的治疗仍统一经过 `UpdateHp`
- `Healing Word` 在法术模板中声明为 `resolution.mode = "heal"`
- `ExecuteSpell` 新增一条即时治疗分支，自动掷治疗骰并调用 `UpdateHp`

这样做的原因：

- 底层“能不能治疗”“封顶”“日志怎么写”只保留一份规则
- 法术层只负责目标合法性、资源消耗和治疗量计算
- 后续 `Cure Wounds`、治疗药水、职业治疗都能平移到同一套链路

## UpdateHp Changes

### Existing Convention

- `hp_change > 0`：伤害
- `hp_change < 0`：治疗
- `hp_change == 0`：无变化

### New Treatment Rule

新增“已死亡目标不能接受治疗”的判断。

死亡判断规则：

- 仅当 `target.combat_flags.is_dead == True` 时视为已死亡

这意味着：

- 0 HP 但未死亡的 PC / NPC 仍可被治疗
- 处于 `unconscious`、濒死、死亡豁免中的单位仍可被治疗
- 真正已死亡的单位不能被普通治疗抬起

### Blocked Healing Behavior

当 `hp_change < 0` 且目标已死亡时：

- 不抛异常
- 不改变 HP
- 返回结构化结果
- 事件类型记为 `hp_unchanged`
- 结果增加：
  - `healing_blocked = true`
  - `healing_blocked_reason = "target_is_dead"`

原因：

- LLM 需要看到这是一次合法调用，但规则上无效
- 这比直接抛错更适合战斗协议
- 事件流里也能保留“尝试治疗失败”的记录

### Successful Healing Behavior

当目标未死亡且 `hp_change < 0` 时：

- 维持现有逻辑：
  - `hp_after = min(hp.max, hp_before + heal)`
  - `actual_healing = hp_after - hp_before`
- `event_type = "healing_applied"`
- `applied_change = -actual_healing`

不额外处理：

- 本次不自动清理濒死/昏迷规则状态
- 若现有系统对“被治疗后从 0 HP 恢复”已有逻辑，则保持现状
- 若现状尚未完整处理，该问题留待“0 HP 被治疗后的状态恢复”专题处理

## Healing Word Spell Definition

在 `data/knowledge/spell_definitions.json` 中新增 `healing_word`。

### Required Fields

- `id = "healing_word"`
- `name = "Healing Word"`
- `level = 1`
- 中文名：`治愈真言`
- `targeting.type = "single_target"`
- `targeting.range_feet = 60`
- `targeting.requires_line_of_sight = true`
- `targeting.allowed_target_types = ["creature"]`
- `resolution.mode = "heal"`
- `resolution.activation = "bonus_action"`
- `resolution.healing_mode = "instant"`

### Healing Template Shape

新增一个与伤害模板平行的治疗模板字段：

- `on_cast.healing_parts`

基础结构：

```json
{
  "on_cast": {
    "healing_parts": [
      {
        "source": "spell:healing_word:base",
        "formula": "2d4",
        "include_spellcasting_modifier": true
      }
    ]
  }
}
```

升环结构：

```json
{
  "scaling": {
    "slot_level_bonus": {
      "base_slot_level": 1,
      "additional_healing_parts": [
        {
          "source": "spell:healing_word:slot_scaling",
          "formula_per_extra_level": "2d4"
        }
      ]
    }
  }
}
```

说明：

- 伤害仍走 `damage_parts`
- 治疗单独走 `healing_parts`
- 本次只给 `Healing Word` 使用，但结构允许后续复用

## SpellRequest Changes

`SpellRequest` 不需要为治疗法术单独加特殊规则，只需沿用现有框架完成：

- 已知法术校验
- `cast_level` 合法性校验
- 单目标数量校验
- 60 尺距离校验
- 视线校验
- 附赠动作可用性校验

本次只需要确保：

- `resolution.mode = "heal"` 的法术可以像其他法术一样通过 `SpellRequest`

## ExecuteSpell Changes

### New Branch

在 `ExecuteSpell.execute()` 中新增 `heal` 分支。

触发条件：

- `spell_definition.resolution.mode == "heal"`

### Flow

1. 调 `SpellRequest`
2. 调 `EncounterCastSpell` 扣法术位、消耗附赠动作、写 `spell_declared`
3. 解析治疗模板
4. 若调用方未提供治疗骰，则后端自动掷骰
5. 计算总治疗量
6. 调 `UpdateHp(hp_change = -healing_total, reason = spell_name)`
7. 返回结构化法术结算结果与最新 `encounter_state`

### Healing Total Calculation

治疗总值由以下部分组成：

- 基础 `2d4`
- 施法属性调整值
- 升环额外 `2d4 * upcast_delta`

其中施法属性调整值来源沿用现有施法体系已有字段：

- 不在本次设计中重做施法属性来源规则
- 直接复用当前系统计算法术 DC / 豁免时使用的施法属性来源

如果当前实体缺少可解析的施法属性调整值：

- 默认视为 0

### Response Shape

`ExecuteSpell` 的治疗分支返回：

- `encounter_id`
- `actor_id`
- `spell_id`
- `cast_level`
- `resource_update`
- `spell_resolution.mode = "heal"`
- `spell_resolution.target_id`
- `spell_resolution.healing_rolls`
- `spell_resolution.healing_total`
- `spell_resolution.hp_update`
- `encounter_state`

`hp_update` 保留 `UpdateHp` 的完整回包，便于：

- LLM 读取实际恢复量
- 区分“治疗成功”与“目标已死亡，治疗被阻止”

## Automatic Rolling

`Healing Word` 与现有自动攻击/自动伤害/自动豁免保持一致：

- 默认由后端自动掷骰
- 不依赖外部先给治疗骰

本次在 `ExecuteSpell` 内部增加一个小型治疗骰解析器即可，不新增单独公共 service。

原因：

- 当前只支持一个即时治疗法术
- 抽象成通用治疗骰 service 的收益不足
- 等第二个治疗法术进入时再决定是否抽公共模块

## Event Projection

本次不新增新的事件类型。

使用已有事件流：

- `spell_declared`
- `healing_applied`
- `hp_unchanged`（若目标已死亡）

前端和 `GetEncounterState` 无需为 `Healing Word` 单独加展示协议，只要沿用已有：

- 最近活动
- HP 变化
- 法术声明

## Error Handling

### Structured Non-error Outcome

以下情况不是 transport error，也不是 service exception：

- 对已死亡目标施放 `Healing Word`

结果应是：

- 法术照常施放
- 资源照常消耗
- `UpdateHp` 返回 `healing_blocked_reason = "target_is_dead"`

### True Validation Errors

以下仍应按现有方式报错或返回失败：

- 目标不存在
- 超出射程
- 没有视线
- 目标数量不合法
- 附赠动作已用
- 法术位不合法
- 施法者未掌握法术

## Testing Plan

先写失败测试，再补实现。

### UpdateHp Tests

新增测试：

- 已死亡目标接受治疗时不恢复 HP
- 已死亡目标治疗返回 `hp_unchanged`
- 已死亡目标治疗结果包含 `healing_blocked_reason = "target_is_dead"`
- 0 HP 但未死亡的目标仍可接受治疗

### SpellRequest Tests

新增测试：

- `Healing Word` 被识别为附赠动作单目标法术
- `Healing Word` 超出 60 尺时报错
- `Healing Word` 被墙阻挡视线时报错

### ExecuteSpell Tests

新增测试：

- `Healing Word` 自动掷治疗骰并恢复 HP
- `Healing Word` 会消耗附赠动作和法术位
- `Healing Word` 治疗封顶到最大 HP
- `Healing Word` 升环时额外增加 `2d4`
- `Healing Word` 对已死亡目标施放时返回治疗被阻止
- `Healing Word` 对 0 HP 未死亡目标施放时可恢复 HP

## Out Of Scope Notes

以下问题刻意留到后续专题：

- 被治疗后自动移除 `unconscious` / 濒死状态的完整规则
- 死亡与复活法术体系
- `Second Wind` 改为统一走 `UpdateHp`
- 通用治疗公式 service
- 掩蔽与更精细的视线系统

## Acceptance Criteria

满足以下条件即算完成：

- `UpdateHp` 严格禁止对已死亡目标恢复 HP
- `Healing Word` 能作为附赠动作法术完整施放
- 后端可自动掷 `Healing Word` 的治疗骰
- 升环治疗量正确
- 治疗结果统一走 `UpdateHp`
- 已死亡目标被 `Healing Word` 指向时，不报 transport error，但不会恢复 HP
- 新增测试覆盖并通过
