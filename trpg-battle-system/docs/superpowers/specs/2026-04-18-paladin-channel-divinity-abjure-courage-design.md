# Paladin Channel Divinity, Abjure Foes, And Aura Of Courage Design

## Goal

在现有 `trpg-battle-system` 战斗 runtime 中，补上第三批圣武士核心战斗能力：

- `Channel Divinity`｜引导神力资源框架
- `Abjure Foes`｜弃绝众敌
- `Aura of Courage`｜勇气灵光

本轮目标是让圣武士从“单体强化职业”继续推进到“有职业资源、有群体压制能力、有抗恐 aura”的可运行形态。

## Scope

本轮完成：

1. paladin `channel_divinity` runtime
2. `Abjure Foes` 独立 service
3. `Aura of Courage` 被动 aura 规则接入
4. `GetEncounterState` paladin 摘要补充
5. 对应测试

本轮不做：

- `Divine Sense` 后端 service
- 子职额外 `Channel Divinity` 选项
- `Aura Expansion`｜灵光增效
- 完整短休 / 长休入口
- 战斗外剧情类神圣侦测

## Remaining Paladin Features Status

### 已完成

- `Lay on Hands`｜圣疗
- `Aura of Protection`｜守护灵光
- `Divine Smite`｜至圣斩
- `Radiant Strikes`｜光耀打击
- `Restoring Touch`｜复原之触
- `Fighting Style`｜战斗风格
- `Extra Attack`｜额外攻击

### 本轮完成后将新增

- `Channel Divinity`｜引导神力资源框架
- `Abjure Foes`｜弃绝众敌
- `Aura of Courage`｜勇气灵光

### 仍未实现

- `Divine Sense`｜神圣感知
- `Aura Expansion`｜灵光增效
- `Faithful Steed`｜信实坐骑
- `Blessed Warrior`｜受祝福的勇士
- 子职能力
- 长休 / 短休驱动的职业资源恢复入口

## Channel Divinity

### Purpose

`Channel Divinity` 本轮只作为职业资源底座存在。

它本身不是一个单独动作入口，而是供：

- `Abjure Foes`
- 后续子职 `Channel Divinity` 选项

共同消耗的统一资源。

### Runtime Shape

统一挂在：

```python
entity.class_features["paladin"]["channel_divinity"]
```

最小结构：

```python
{
  "enabled": True,
  "max_uses": 2,
  "remaining_uses": 2
}
```

### Level Defaults

- `level < 3`：
  - `enabled = False`
  - `max_uses = 0`
- `3 <= level <= 10`：
  - `enabled = True`
  - `max_uses = 2`
- `level >= 11`：
  - `enabled = True`
  - `max_uses = 3`

若 runtime 显式给了 `remaining_uses`，优先保留；否则默认等于 `max_uses`。

### Out Of Scope

本轮不做：

- 短休自动恢复 1 次
- 长休恢复全部
- 统一休息入口

本轮只要求：

- 能正确初始化
- 能被 `Abjure Foes` 消耗
- `GetEncounterState` 可见剩余次数

## Abjure Foes

### Purpose

`Abjure Foes` 是 9 级圣武士的群体压制能力。

它是本轮第一个真正消耗 `Channel Divinity` 的主动职业能力，用来验证：

1. paladin 资源是否接线正确
2. 多目标豁免是否能稳定落地
3. 恐慌与行动受限是否能挂到现有持续效果框架

### Entry Shape

建议入口：

```python
UseAbjureFoes.execute(
    encounter_id: str,
    actor_id: str,
    target_ids: list[str],
    save_rolls: dict[str, int] | None = None,
)
```

### Activation Rule

1. paladin level `>= 9`
2. actor 必须是当前行动者
3. 消耗 1 次动作
4. 消耗 1 次 `channel_divinity`

### Targeting Rule

1. 目标必须是施法者 60 尺内可见生物
2. 目标数量上限 = `max(1, actor.ability_mods["cha"])`
3. 本轮只允许选择明确的 `target_ids`，不做自动选敌

### Save Rule

每个目标进行一次 `wis` 豁免，对抗 paladin 的法术豁免 DC：

```python
8 + proficiency_bonus + cha_mod
```

### On Fail

目标豁免失败时：

1. 添加 `frightened`
2. 再挂一个 turn effect，表示：
   - 持续 1 分钟
   - 若目标受到任何伤害则提前结束
   - 持续期间，该目标每回合只能执行下列行为之一：
     - 移动
     - 一个动作
     - 一个附赠动作

### On Success

无效果。

### Duration Modeling

本轮建议拆成两层：

1. `frightened` condition
2. `abjure_foes_restriction` turn effect

这样做的原因：

1. `frightened` 仍复用现有 condition 语义
2. “每回合只能做一类事”的特殊限制不应塞进通用 `frightened`
3. 后续若 `Aura of Courage` 进入范围，可只压制 `frightened` 部分，而不误删 restriction 来源

### Early End On Damage

本轮直接接入现有受伤 / HP 更新链：

- 目标受到任何伤害时，移除：
  - `abjure_foes_restriction` turn effect
  - 与该 effect 绑定的 `frightened`

这要求 effect 带清晰 `source_ref`，例如：

```python
{
  "effect_type": "abjure_foes_restriction",
  "source_ref": "paladin:abjure_foes",
  "ends_on_damage": True,
}
```

## Aura Of Courage

### Purpose

`Aura of Courage` 是 10 级圣武士的被动 aura，主要解决：

1. 自己与盟友在 aura 范围内免疫 `frightened`
2. 已恐慌角色进入 aura 后，恐慌效果暂时失效

### Runtime Shape

统一挂在：

```python
entity.class_features["paladin"]["aura_of_courage"]
```

最小结构：

```python
{
  "enabled": True,
  "radius_feet": 10
}
```

等级驱动默认值：

- `level >= 10` 时启用
- 默认半径 `10`

### Rule Choice

本轮采用：

- **不删除 `frightened` condition**
- **只在规则结算阶段压制其效果**

原因：

1. `frightened` 可能有来源、持续时间、后续豁免，直接删掉会丢失语义
2. “进入 aura 暂时无效”更适合做 suppression，而不是状态移除

### Practical Effect

在 aura 覆盖内：

1. 新的 `frightened` 不应生效
2. 已存在的 `frightened` 其行为与检定惩罚应被压制

### Integration Points

本轮只接入最关键两条链：

1. `Abjure Foes` 添加 `frightened` 时：
   - 若目标正处于勇气灵光内，则不添加 `frightened`
   - 也不添加其伴随的行动限制 effect
2. 攻击 / d20 判定中若未来已有 `frightened` 惩罚链，则统一检查 suppression

如果当前仓库里还没有完整的 `frightened` 通用惩罚实现，本轮至少先确保：

- `Abjure Foes` 不会对勇气灵光覆盖内目标生效

### Aura Source Selection

与 `Aura of Protection` 一样：

- 只要任意一个符合条件的 paladin 覆盖到目标，就视为获得 `Aura of Courage`
- 不需要多来源叠加

## GetEncounterState Projection

本轮 paladin 摘要建议扩展为：

```python
"paladin": {
  "level": 10,
  "divine_smite": {"enabled": True},
  "lay_on_hands": {"pool_remaining": 32, "pool_max": 50},
  "channel_divinity": {"enabled": True, "remaining_uses": 2, "max_uses": 2},
  "aura_of_protection": {"enabled": True, "radius_feet": 10},
  "aura_of_courage": {"enabled": True, "radius_feet": 10},
  "available_features": [
    "divine_smite",
    "lay_on_hands",
    "channel_divinity",
    "abjure_foes",
    "aura_of_protection",
    "aura_of_courage"
  ]
}
```

可见性规则：

- `channel_divinity`：`level >= 3`
- `abjure_foes`：`level >= 9`
- `aura_of_courage`：`level >= 10`

## Files To Touch

预计修改：

- `tools/services/class_features/shared/runtime.py`
- `tools/services/class_features/shared/__init__.py`
- `tools/services/encounter/get_encounter_state.py`
- `tools/services/combat/shared/update_hp.py`
- `tools/services/combat/save_spell/resolve_saving_throw.py`（如需复用 aura 判定工具则最小补丁）

预计新增：

- `tools/services/class_features/paladin/use_abjure_foes.py`

预计测试：

- `test/test_use_abjure_foes.py`
- `test/test_get_encounter_state.py`
- `test/test_update_hp.py`

## Testing

至少覆盖：

### Channel Divinity

1. 3 级 paladin 自动得到 `2/2`
2. 11 级 paladin 自动得到 `3/3`
3. 显式写入 `remaining_uses` 时不会被默认值覆盖

### Abjure Foes

1. 9 级 paladin 可消耗 1 次 `channel_divinity`
2. 会消耗动作
3. 目标数量不能超过 `max(1, cha_mod)`
4. 超过 60 尺或不可见目标拒绝
5. 失败目标获得 `frightened` + restriction effect
6. 成功目标不受影响
7. 目标受伤后 effect 提前结束

### Aura Of Courage

1. 10 级 paladin 在 `GetEncounterState` 中看到摘要
2. `Abjure Foes` 对勇气灵光范围内盟友 / 自己不应生效
3. 若多个 paladin 覆盖，仍只视为“有勇气灵光”

## Design Notes

本轮刻意不做：

1. 休息入口
2. 子职 channel divinity
3. aura 扩展半径

因为当前最重要的是先把：

- 资源
- 群体主动能力
- 基础抗恐 aura

三者作为一个稳定闭环跑通。
