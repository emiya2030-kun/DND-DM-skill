# Paladin Radiant Strikes And Restoring Touch Design

## Goal

在现有 `trpg-battle-system` 战斗 runtime 中，补上第二批圣武士核心战斗能力：

- `Radiant Strikes`｜光耀打击
- `Restoring Touch`｜复原之触

同时明确：

- `Divine Sense`｜神圣感知 本轮不做后端 rule service，由 LLM 按剧情信息自行裁定与叙述

本轮只做稳定、可测试、可接入现有主链的最小正确版，不扩展到完整长休恢复、坐骑、子职引导神力等系统。

## Scope

本轮完成：

1. paladin runtime 增加 `radiant_strikes` 摘要
2. `Radiant Strikes` 接入 `ExecuteAttack` 命中后结构化伤害链
3. `Restoring Touch` 接入现有 `UseLayOnHands`
4. `GetEncounterState` 投影新增对应 paladin 摘要
5. 对应测试

本轮不做：

- `Divine Sense` 后端 service
- `Abjure Foes`
- `Aura of Courage`
- `Aura Expansion`
- `Faithful Steed`
- 长休恢复这些职业资源

## Divine Sense Handling

`Divine Sense` 本轮不进入后端。

原因：

1. 它更接近剧情侦测与信息裁定，而不是战斗内确定性规则结算
2. 当前后端没有完整“哪些目标对角色可感知、哪些地点受祝福/亵渎”的结构化事实源
3. 若强行做后端扫描，容易给出伪精确结果

因此本轮策略是：

- 后端不提供 `use_divine_sense` service
- 不往 `GetEncounterState` 塞伪扫描结果
- 只在 skill / 协议层说明其可由 LLM 作为剧情能力自行叙述

## Radiant Strikes

### Rule

当满足以下条件时，攻击命中后自动追加 `1d8 radiant`：

1. paladin level `>= 11`
2. 攻击是 `melee weapon attack` 或 `unarmed strike`
3. 攻击命中

### Runtime Shape

统一挂在：

```python
entity.class_features["paladin"]["radiant_strikes"]
```

最小结构：

```python
{
  "enabled": True
}
```

等级驱动默认值：

- `level >= 11` 时 `enabled = True`
- 否则 `enabled = False`

### Execution Shape

接到 `ExecuteAttack._prepare_structured_damage(...)` 的 damage part 追加链。

追加项：

```python
{
  "source": "paladin_radiant_strikes",
  "formula": "1d8",
  "damage_type": "radiant"
}
```

### Behavior Notes

1. 不需要 LLM 额外声明
2. 不消耗动作、附赠动作、反应
3. 不消耗法术位
4. 可与 `Divine Smite` 同次命中同时存在
5. 暴击时随现有结构化伤害链一起翻倍骰子

## Restoring Touch

### Rule

`Restoring Touch` 不是独立 service，而是对 `Lay on Hands` 的扩展：

当圣武士使用 `Lay on Hands` 时，可以额外移除目标身上的下列状态：

- `blinded`
- `charmed`
- `deafened`
- `frightened`
- `paralyzed`
- `stunned`

每成功移除一个状态，额外消耗 5 点治疗池。

### Entry Shape

扩展现有入口：

```python
UseLayOnHands.execute(
    encounter_id: str,
    actor_id: str,
    target_id: str,
    heal_amount: int = 0,
    cure_poison: bool = False,
    remove_conditions: list[str] | None = None,
    allow_out_of_turn_actor: bool = False,
)
```

### Cost Rule

总消耗：

```python
heal_amount
+ (5 if cure_poison and target_has_poisoned else 0)
+ 5 * 实际被移除的合法状态数量
```

更精确地说：

1. `heal_amount` 始终按声明值消耗
2. `cure_poison=True` 且目标当前有 `poisoned` 时，消耗 5
3. `remove_conditions` 中每个合法且当前实际存在的状态，各消耗 5
4. 不存在的状态不收费

### Action Rule

即使本次没有实际治疗、没有解毒成功、也没有成功移除任何状态：

- 这次 `Lay on Hands` 仍视为一次已声明能力
- 仍消耗附赠动作
- 但治疗池不减少

### Multi-Effect Rule

允许一次结算中同时包含：

- 治疗
- `cure_poison`
- 多个 `remove_conditions`

只要池子足够支付全部实际成本，就允许一次性完成结算。

例如同一次可以同时：

- 恢复 HP
- 移除 `poisoned`
- 移除 `paralyzed`
- 移除 `stunned`
- 移除更多合法状态

### Validation Rule

`remove_conditions` 的处理：

1. 去重后再处理
2. 仅接受白名单中的 6 个状态
3. 非白名单项不收费、不移除，但会显式记录到 `invalid_requested_conditions`

建议返回：

```python
{
  "conditions_requested": [...],
  "conditions_removed": [...],
  "conditions_not_present": [...],
  "invalid_requested_conditions": [...],
  "pool_spent_on_condition_removal": 10,
}
```

## GetEncounterState Projection

`GetEncounterState` 中 paladin 摘要增加：

```python
"paladin": {
  "level": 14,
  "divine_smite": {"enabled": True},
  "lay_on_hands": {"pool_remaining": 37, "pool_max": 70},
  "aura_of_protection": {"enabled": True, "radius_feet": 10},
  "radiant_strikes": {"enabled": True},
  "available_features": [
    "divine_smite",
    "lay_on_hands",
    "aura_of_protection",
    "radiant_strikes",
    "restoring_touch"
  ]
}
```

`restoring_touch` 本身不一定需要单独 runtime bucket，因为它是 `Lay on Hands` 的增强规则；但 `available_features` 应体现它可用。

可用性规则：

- `restoring_touch` 在 `paladin level >= 14` 时加入 `available_features`

## Files To Touch

预计修改：

- `tools/services/class_features/shared/runtime.py`
- `tools/services/class_features/shared/__init__.py`
- `tools/services/class_features/paladin/use_lay_on_hands.py`
- `tools/services/combat/attack/attack_roll_request.py`（如需把 paladin 选项透传则最小补丁）
- `tools/services/combat/attack/execute_attack.py`
- `tools/services/encounter/get_encounter_state.py`

预计新增 / 更新测试：

- `test/test_use_lay_on_hands.py`
- `test/test_execute_attack.py`
- `test/test_get_encounter_state.py`

## Testing

至少覆盖：

### Radiant Strikes

1. 11 级圣武士近战命中自动追加 `1d8 radiant`
2. 11 级圣武士徒手命中自动追加 `1d8 radiant`
3. 非 11 级不追加
4. 与 `Divine Smite` 同次命中可并存
5. 暴击时 damage part 正常翻倍骰子

### Restoring Touch

1. `Lay on Hands` 可同时治疗并移除多个状态
2. 每个成功移除的状态额外消耗 5 点池子
3. 请求移除不存在的状态不收费
4. 请求移除不存在的状态时仍消耗附赠动作
5. `cure_poison` 与 `remove_conditions` 可同次一起结算
6. 池子不足时拒绝整个结算

### Projection

1. 11 级 paladin 能看到 `radiant_strikes.enabled = True`
2. 14 级 paladin 的 `available_features` 包含 `restoring_touch`

## Design Notes

这轮设计刻意不把 `Restoring Touch` 拆成新 service，也不把 `Radiant Strikes` 做成 LLM 主动声明能力。

原因：

1. 两者都自然落在现有主链：
   - `Radiant Strikes` 落在命中后伤害链
   - `Restoring Touch` 落在 `Lay on Hands`
2. 这样能避免新增平行入口
3. LLM 使用协议更稳定，不需要额外记忆新的调用方式
