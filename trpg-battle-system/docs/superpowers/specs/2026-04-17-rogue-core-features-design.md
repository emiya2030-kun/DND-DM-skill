# 盗贼核心战斗特性设计

日期：2026-04-17

## 目标

为 `trpg-battle-system` 接入盗贼的核心战斗特性，并且优先走“共用 runtime 支撑 + 主链挂接”的设计，而不是把规则零散写进攻击、豁免、检定代码中。

本轮覆盖：

- 专精 Expertise
- 偷袭 Sneak Attack（含按等级自动成长）
- 灵巧动作 Cunning Action
- 稳定瞄准 Steady Aim
- 直觉闪避 Uncanny Dodge
- 可靠才能 Reliable Talent
- 圆滑心智 Slippery Mind
- 飘忽不定 Elusive
- 诡诈打击 Cunning Strike
- 进阶诡诈打击 Improved Cunning Strike
- 凶狡打击 Devious Strike

本轮不覆盖：

- 盗贼黑话
- 子职
- 属性值提升
- 传奇恩惠
- 幸运一击
- 工具熟练的完整系统化支持

## 设计原则

### 1. 统一放进 rogue runtime bucket

盗贼相关战斗运行时状态全部放在：

- `entity.class_features["rogue"]`

至少保存：

- `level`
- `expertise`
- `sneak_attack`
- `steady_aim`
- `cunning_strike`
- `uncanny_dodge`
- `reliable_talent`
- `slippery_mind`
- `elusive`

### 2. 已有主链只做“挂接点”，不重造系统

各能力按性质挂到现有链路：

- 属性 / 技能检定链
- 攻击请求链
- 攻击结算链
- reaction framework
- start turn / end turn
- encounter state projection

### 3. 偷袭伤害骰必须按等级自动推导

当前系统依赖：

- `rogue.sneak_attack.damage_dice`

但还是手写字符串。

本轮改为：

- 如果 `rogue.level` 存在，则后端自动计算并刷新 `damage_dice`
- LLM 不需要再手填 `3d6`、`4d6`

成长表：

- 1-2: `1d6`
- 3-4: `2d6`
- 5-6: `3d6`
- 7-8: `4d6`
- 9-10: `5d6`
- 11-12: `6d6`
- 13-14: `7d6`
- 15-16: `8d6`
- 17-18: `9d6`
- 19-20: `10d6`

### 4. 诡诈打击是“命中后消耗偷袭骰换效果”

诡诈打击不单独造平行服务。

它属于：

- 命中
- 确认可以偷袭
- 在投伤害前扣除若干 `d6`
- 伤害结算后立刻附加控制或移动效果

因此本轮把它设计为：

- 作为 `ExecuteAttack` 中的“偷袭后处理层”
- 由 `class_feature_options` 显式声明想用哪种诡诈打击

## 一、rogue runtime 结构

推荐结构：

```json
{
  "rogue": {
    "level": 7,
    "expertise": {
      "skills": ["stealth", "sleight_of_hand"]
    },
    "sneak_attack": {
      "damage_dice": "4d6",
      "used_this_turn": false
    },
    "steady_aim": {
      "enabled": true,
      "used_this_turn": false,
      "grants_advantage_on_next_attack": false
    },
    "cunning_strike": {
      "enabled": true,
      "max_effects_per_hit": 1
    },
    "uncanny_dodge": {
      "enabled": true
    },
    "reliable_talent": {
      "enabled": true
    },
    "slippery_mind": {
      "enabled": false
    },
    "elusive": {
      "enabled": false
    }
  }
}
```

### 运行时约束

- `damage_dice` 由后端按等级刷新
- `used_this_turn` 在每次自己回合开始时重置
- `steady_aim.used_this_turn` 在每次自己回合开始时重置
- `steady_aim.grants_advantage_on_next_attack` 在一次攻击请求消费后清除
- `cunning_strike.max_effects_per_hit`
  - 5-10级：1
  - 11级以上：2

## 二、各特性挂接点

### 1. 专精 Expertise

挂到：

- `ResolveAbilityCheck`

规则：

- 如果本次是技能检定
- 且该技能在 `rogue.expertise.skills`
- 且角色对该技能熟练
- 则把熟练加值翻倍

第一版不扩工具专精，因为工具检定链还未正式建模。

### 2. 偷袭 Sneak Attack

挂到：

- `AttackRollRequest`
- `ExecuteAttack`
- `StartTurn`

规则：

- 维持现有触发条件校验
- 命中后若声明 `sneak_attack: true`
- 则自动读取当前等级对应的 `damage_dice`
- 每回合一次
- 借机攻击仍可触发

### 3. 灵巧动作 Cunning Action

挂到：

- `GetEncounterState`
- 高层 runtime 行为约束

第一版最小实现：

- 在 `current_turn_entity.available_actions` 或职业摘要里明确显示盗贼可用：
  - `dash`
  - `disengage`
  - `hide`
  作为附赠动作

后端不需要新建专门 tool。
LLM 继续使用既有移动或检定链，但必须知道这些动作可作为 bonus action 执行。

### 4. 稳定瞄准 Steady Aim

挂到：

- `AttackRollRequest`
- `StartTurn`
- `GetEncounterState`

规则：

- 只能在本回合尚未移动时使用
- 使用时消耗附赠动作
- 立刻把本回合速度变为 0
- 为本回合下一次攻击提供优势
- 下一次攻击请求会消费这次优势

### 5. 直觉闪避 Uncanny Dodge

挂到：

- reaction definition repository
- attack reaction window
- reaction resolution

规则：

- 当一个你能看见的攻击者用一次攻击检定命中你时
- 你可用反应把这次攻击伤害减半（向下取整）

它和 Shield / Deflect Attacks 一样，属于防御反应模板。

### 6. 可靠才能 Reliable Talent

挂到：

- `ResolveAbilityCheck`

规则：

- 当进行属性检定
- 且这次检定能运用你已熟练的技能
- 若 d20 结果为 1-9，则按 10 处理

本轮只覆盖技能检定，不扩工具检定。

### 7. 圆滑心智 Slippery Mind

挂到：

- `resolve_entity_save_proficiencies`

规则：

- 盗贼 15 级获得感知和魅力豁免熟练

### 8. 飘忽不定 Elusive

挂到：

- `AttackRollRequest`

规则：

- 只要目标拥有 `elusive.enabled`
- 且目标未失能
- 则以其为目标的攻击检定不能因为任何来源而具有优势

第一版实现为：

- 在最终 advantage / disadvantage 归并前
- 清空对该目标的 advantage 来源
- 但不清掉 disadvantage

### 9. 诡诈打击 / 进阶诡诈打击 / 凶狡打击

挂到：

- `ExecuteAttack`
- `UpdateConditions`
- `ResolveForcedMovement`
- turn effects

#### 支持的效果

- `poison`：消耗 1d6，附加中毒与回合末重豁免
- `trip`：消耗 1d6，目标大型及以下，失败则倒地
- `withdraw`：消耗 1d6，攻击后立刻无借机移动至多一半速度
- `daze`：消耗 2d6，失败则下一回合只能移动 / 动作 / 附赠动作三选一
- `knock_out`：消耗 6d6，失败则昏迷，受到伤害结束，回合末重豁免
- `obscure`：消耗 3d6，失败则目盲至其下回合结束

#### 规则约束

- 必须先成功触发偷袭
- 先从偷袭伤害骰里扣除对应 `d6`
- 才投剩余偷袭伤害
- 5-10级每次命中最多 1 种效果
- 11级以上每次命中最多 2 种效果

#### 豁免 DC

- `8 + 熟练加值 + 敏捷调整值`

## 三、LLM / runtime 暴露方式

### attack 的 `class_feature_options`

当前已有：

- `sneak_attack: true`

本轮扩展为支持：

```json
{
  "sneak_attack": true,
  "steady_aim": true,
  "cunning_strike": {
    "effects": ["trip"]
  }
}
```

或：

```json
{
  "sneak_attack": true,
  "cunning_strike": {
    "effects": ["poison", "withdraw"]
  }
}
```

### ability check

不新增新 tool。

只是在 `ExecuteAbilityCheck` 中自动应用：

- 专精
- 可靠才能

## 四、测试要求

至少覆盖：

1. 盗贼等级自动推导偷袭骰
2. 偷袭仍保持每回合一次
3. 专精使技能熟练加值翻倍
4. 可靠才能把技能检定 d20 低于 10 提到 10
5. 稳定瞄准要求未移动、消耗附赠动作、给下一击优势并把速度归零
6. 直觉闪避反应能把伤害减半
7. 圆滑心智会增加 `wis` / `cha` 豁免熟练
8. 飘忽不定会压制攻击优势
9. 诡诈打击会扣偷袭骰并附加对应效果
10. 11级以上允许一次命中使用两种诡诈打击

## 五、范围控制

本轮仍然不做：

- 子职
- 工具熟练与工具专精的完整系统
- 躲藏动作本身的完整规则判定
- 幸运一击
- 战斗外完整盗贼互动系统
