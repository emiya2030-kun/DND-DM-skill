# Paladin Core Combat Design

## Goal

在现有 `trpg-battle-system` 战斗 runtime 中，接入第一批圣武士核心战斗能力：

- `Lay on Hands`｜圣疗
- `Aura of Protection`｜守护灵光
- `Divine Smite`｜至圣斩 / 圣武斩

本轮只做战斗内可稳定落地的闭环，不扩展到圣武士子职、坐骑、引导神力或战斗外法术准备系统。

## Scope

本轮完成：

1. 圣武士 runtime 资源结构与最小投影
2. `Lay on Hands` 独立 service
3. `Aura of Protection` 自动接入豁免链
4. `Divine Smite` 接入攻击命中后伤害追加链
5. 对应测试、状态投影与运行时摘要

本轮不做：

- `Faithful Steed`｜信实坐骑
- `Channel Divinity`｜引导神力
- `Abjure Foes`｜弃绝众敌
- `Aura of Courage`｜勇气灵光
- `Radiant Strikes`｜光耀打击
- `Restoring Touch`｜复原之触
- 圣武士准备法术系统
- battlemap 上的灵光圆形展示

## Runtime Shape

圣武士运行时统一挂在 `entity.class_features["paladin"]`。

建议本轮最小结构：

```python
{
  "paladin": {
    "level": 6,
    "lay_on_hands": {
      "pool_max": 30,
      "pool_remaining": 22
    },
    "divine_smite": {
      "enabled": True
    },
    "aura_of_protection": {
      "enabled": True,
      "radius_feet": 10
    }
  }
}
```

规则推导：

- `lay_on_hands.pool_max = paladin level * 5`
- `aura_of_protection.enabled = paladin level >= 6`
- `aura_of_protection.radius_feet = 10`
- `divine_smite.enabled = paladin level >= 2`

若 runtime 已显式写入这些字段，则优先保留显式值；若只给了 `level`，则按等级自动补全默认值。

## Lay on Hands

### 形态

`Lay on Hands` 作为单独 service 落地，不塞进通用施法链。

建议入口：

```python
UseLayOnHands.execute(
    encounter_id: str,
    actor_id: str,
    target_id: str,
    heal_amount: int = 0,
    cure_poison: bool = False,
    allow_out_of_turn_actor: bool = False,
)
```

### 规则

1. 这是一次附赠动作。
2. 目标可以是自己或触及范围内的一个生物。
3. `heal_amount` 必须为正整数或 0。
4. `cure_poison=True` 时必须额外消耗 5 点治疗池。
5. 若同时治疗与解毒，则总消耗为 `heal_amount + 5`。
6. 消耗不能超过剩余治疗池。
7. 治疗遵循现有通用治疗规则：
   - 不能超过最大生命值
   - 死亡生物不能被治疗
8. `cure_poison=True` 时移除目标身上的 `poisoned` 条件；若目标没有中毒，仍允许消耗并返回 `changed=False`。

### 返回

返回结构应至少包含：

```python
{
  "status": "resolved",
  "pool_spent": 8,
  "pool_remaining": 22,
  "hp_restored": 3,
  "poison_removed": True,
  "encounter_state": ...
}
```

## Aura of Protection

### 形态

`Aura of Protection` 不需要独立 action service。

它应直接接入现有豁免请求 / 豁免结算链，作为被动加值来源。

### 规则

1. 只有圣武士等级 `>= 6` 时启用。
2. 灵光覆盖源自圣武士自身 10 尺内区域。
3. 灵光对自己与盟友生效。
4. 加值为圣武士魅力调整值，最少 `+1`。
5. 圣武士若处于 `incapacitated`，该灵光失效。
6. 多个圣武士同时覆盖同一目标时，只取一个灵光。
7. 本轮采用“取最高加值”的确定性规则。

### 接入点

优先接到保存豁免加值计算的共享链路，而不是在最终结果阶段临时修正。

这样：

- `SavingThrowRequest` 的 `context` 能看到灵光来源
- `ResolveSavingThrow` / `SavingThrowResult` 不需要再补丁式改写
- concentration、法术豁免、职业特性豁免都能复用同一逻辑

### 元数据

豁免请求中应保留类似字段：

```python
"aura_of_protection_bonus": 3,
"aura_of_protection_source": "ent_ally_paladin_001"
```

### GetEncounterState

本轮 `GetEncounterState` 只需要返回 aura 摘要，不做 battlemap overlay。

建议投影：

```python
"paladin": {
  "level": 6,
  "divine_smite": {"enabled": True},
  "lay_on_hands": {"pool_remaining": 22, "pool_max": 30},
  "aura_of_protection": {
    "enabled": True,
    "radius_feet": 10
  },
  "available_features": ["divine_smite", "lay_on_hands", "aura_of_protection"]
}
```

## Divine Smite

### 形态

`Divine Smite` 接到 `ExecuteAttack` 的命中后结构化伤害链，不单独建 action service。

建议入口：

```python
ExecuteAttack.execute(
    ...,
    class_feature_options={
      "divine_smite": {
        "slot_level": 1
      }
    }
)
```

### 触发条件

1. 该次攻击必须命中。
2. 攻击必须是近战武器攻击或徒手打击。
3. 角色必须有可用圣武斩能力：
   - `paladin level >= 2`
   - 且存在足够法术位

### 伤害规则

基础伤害：

- `2d8 radiant`

升环：

- 每高于 1 环 1 级，额外 `+1d8`

目标为 `fiend` 或 `undead` 时：

- 再额外 `+1d8`

因此：

- 1 环普通目标：`2d8`
- 1 环邪魔 / 亡灵：`3d8`
- 2 环普通目标：`3d8`
- 2 环邪魔 / 亡灵：`4d8`

### 目标分类识别

本轮用实体现有运行时类别 / 来源信息做最小识别：

1. 若 `entity.source_ref["creature_type"]` 存在，则优先用它
2. 否则可读取 `entity.category`
3. 只有明确为 `fiend` 或 `undead` 时才追加额外 `1d8`
4. 不做模糊推断

### 结算方式

圣武斩应作为额外 damage part 追加到结构化伤害中，例如：

```python
{
  "source": "paladin_divine_smite",
  "formula": "3d8",
  "damage_type": "radiant"
}
```

法术位在 damage part 成功挂入本次命中后立即扣除。

未命中时不得消耗法术位。

### 动作经济

规则文本将其视为“附赠动作，当命中后立即执行”。
本轮后端实现不额外占用独立 bonus action 标记，而将其建模为命中后追加能力。

原因：

- 它必须与命中事件强绑定
- 现有 `ExecuteAttack` 最适合承载该时机
- LLM 的调用也更稳定

## Testing

至少覆盖以下测试：

### Lay on Hands

1. 正常治疗并扣池
2. 治疗不超过最大生命
3. 解毒消耗 5 点并移除 `poisoned`
4. 治疗与解毒同时进行
5. 剩余池不足时报错
6. 附赠动作已用时报错

### Aura of Protection

1. 自身豁免获得魅力加值
2. 10 尺内盟友获得加值
3. 超出 10 尺不生效
4. `incapacitated` 时失效
5. 两个圣武士覆盖时取最高值
6. `GetEncounterState` 正确投影 aura 摘要

### Divine Smite

1. 近战命中追加 `2d8`
2. 高环位增加伤害骰
3. 对 `fiend` / `undead` 额外 `+1d8`
4. 未命中不消耗法术位
5. 远程攻击不能触发
6. 法术位不足时报错

## File Boundaries

建议新增或修改以下边界：

- `tools/services/class_features/paladin/`
  - 放 `UseLayOnHands`
  - 放 paladin runtime helper
- `tools/services/class_features/shared/runtime.py`
  - 增加 paladin runtime 自动补全
- `tools/services/combat/attack/execute_attack.py`
  - 接入 `Divine Smite`
- `tools/services/combat/save_spell/...` 或共享 saving throw 链
  - 接入 `Aura of Protection`
- `tools/services/encounter/get_encounter_state.py`
  - 增加 paladin 资源摘要细节

## Out of Scope Follow-ups

下一批自然扩展项：

- `Aura of Courage`｜勇气灵光
- `Radiant Strikes`｜光耀打击
- `Restoring Touch`｜复原之触
- `Faithful Steed`｜信实坐骑
- `Abjure Foes`｜弃绝众敌
