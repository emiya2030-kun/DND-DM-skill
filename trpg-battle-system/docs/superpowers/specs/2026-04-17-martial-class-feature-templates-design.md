# 武力系职业特性模板骨架设计

日期：2026-04-17

## 目标

把当前只覆盖 `fighter` 的战斗内职业特性框架，扩展成一套适用于武力系职业的通用模板骨架。

这轮目标不是把所有职业都做成完整可结算职业，而是先完成三件事：

1. 把武力系职业的战斗内特性统一纳入知识库模板
2. 把这些职业的运行时状态结构统一纳入 `class_features`
3. 只把少量高复用模板接成真实后端能力，作为后续职业扩展样板

## 本轮覆盖范围

本轮纳入的职业：

- `barbarian`
- `fighter`
- `monk`
- `paladin`
- `ranger`
- `rogue`

本轮只覆盖：

- 战斗内职业特性
- 职业资源与本回合状态
- LLM 可见的职业能力摘要
- 少量高复用模板的真实结算接线

本轮明确不覆盖：

- 子职特性
- 战斗外探索 / 社交 / 长休
- 全职业完整数值成长器
- 所有职业能力的一次性完整规则实现

## 设计原则

### 1. 先铺广度骨架，再做少量深度结算

这轮优先建立统一职业模板层与运行时状态层，让系统先认识这些职业能力的存在。

只有少量高复用模板会在这轮直接变成真实可结算能力，其余能力先进入：

- 知识库
- runtime 骨架
- 前端 / LLM 可见摘要

### 2. 知识描述与运行时状态严格分离

知识库负责回答：

- 这个能力是什么
- 什么时候能用
- 消耗什么
- 大致做什么

运行时只负责保存：

- 当前剩余资源
- 本回合是否已使用
- 当前战斗中的临时状态

### 3. 模板优先，专属实现兜底

共性强的职业特性尽量归入模板类型。

规则拧巴或依赖重的能力可以暂时只建模板、不接结算，或者以后单独走专属 service。

## 三层结构

## 一、知识模板层

沿用并扩展现有文件：

- `data/knowledge/class_feature_definitions.json`

每个职业特性继续使用现有字段：

- `id`
- `name`
- `class_id`
- `level_required`
- `template_type`
- `activation`
- `resource_model`
- `trigger`
- `targeting`
- `effect_summary`
- `runtime_support`

### 本轮新增的模板类型

在现有 `fighter` 模板基础上，新增以下高复用模板类型：

- `bonus_attack_grant`
- `damage_rider_once_per_turn`
- `damage_rider_on_hit`
- `stance_or_mode_toggle`
- `defensive_reaction_reduce_damage`
- `defensive_bonus_action`
- `save_on_hit_control`
- `mobility_bonus`
- `conditional_damage_conversion`
- `attack_vantage_tradeoff`
- `save_vantage_passive`

### 典型职业能力映射

#### Barbarian

- `rage`: `stance_or_mode_toggle`
- `reckless_attack`: 暂不接真实结算，可先定义为 `attack_vantage_tradeoff`
- `danger_sense`: 暂不接真实结算，可先定义为 `save_vantage_passive`

#### Monk

- `martial_arts`: `bonus_attack_grant`
- `flurry_of_blows`: `bonus_attack_grant`
- `patient_defense`: `mobility_bonus` 或 `defensive_bonus_action`
- `step_of_the_wind`: `mobility_bonus`
- `deflect_attacks`: `defensive_reaction_reduce_damage`
- `stunning_strike`: `save_on_hit_control`
- `empowered_strikes`: `conditional_damage_conversion`

#### Paladin

- `divine_smite`: `damage_rider_on_hit`
- `lay_on_hands`: 暂不接入本轮

#### Ranger

- `favored_enemy` 风格能力：暂不接入本轮
- `weapon_mastery` 相关：仍由武器系统承担

#### Rogue

- `sneak_attack`: `damage_rider_once_per_turn`
- `cunning_action`: `mobility_bonus`

#### Fighter

保持已有模板：

- `second_wind`
- `action_surge`
- `tactical_shift`
- `indomitable`
- `studied_attacks`
- `extra_attack`
- `tactical_master`

## 二、运行时状态层

统一通过 `EncounterEntity.class_features` 保存职业运行时状态。

建议所有职业都按“职业 bucket + 通用资源字段”组织。

示例：

```json
{
  "class_features": {
    "fighter": {
      "level": 9,
      "second_wind": {"max_uses": 3, "remaining_uses": 2},
      "action_surge": {"max_uses": 1, "remaining_uses": 1, "used_this_turn": false},
      "indomitable": {"max_uses": 1, "remaining_uses": 1}
    },
    "monk": {
      "level": 5,
      "focus_points": {"max": 5, "remaining": 5},
      "martial_arts_die": "1d8",
      "unarmored_movement_bonus_feet": 10,
      "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1}
    },
    "rogue": {
      "level": 5,
      "sneak_attack": {"damage_dice": "3d6", "used_this_turn": false}
    },
    "paladin": {
      "level": 5,
      "divine_smite": {"enabled": true}
    }
  }
}
```

### 运行时字段约束

#### Fighter

保持现有结构兼容，不做破坏性重构。

#### Monk

至少预留：

- `level`
- `focus_points`
- `martial_arts_die`
- `unarmored_movement_bonus_feet`
- `stunning_strike`

#### Rogue

至少预留：

- `level`
- `sneak_attack`

#### Paladin

至少预留：

- `level`
- `divine_smite`

#### Barbarian

至少预留：

- `level`
- `rage`

#### Ranger

本轮先只留最小 bucket：

- `level`

### Runtime 规则

- 只存战斗中会变化的数据
- 不在 entity 中复制整段规则描述
- 所有 `used_this_turn` / `uses_this_turn` 字段都必须在回合引擎中有明确刷新点

## 三、规则执行层

### 本轮真实接入的模板类型

本轮只建议打通这几类：

#### 1. `damage_rider_once_per_turn`

首个使用者：

- `rogue.sneak_attack`

接入点：

- 攻击命中后伤害组装阶段

最低实现目标：

- 满足条件时可追加一段额外伤害
- 每回合只触发一次

#### 2. `bonus_attack_grant`

首个使用者：

- `monk.martial_arts`
- `monk.flurry_of_blows`

接入点：

- 动作经济 / 攻击入口

最低实现目标：

- 允许附赠动作徒手打击
- `Flurry of Blows` 扣除 `focus`
- 返回结构化攻击次数信息

#### 3. `save_on_hit_control`

首个使用者：

- `monk.stunning_strike`

接入点：

- 攻击命中后可选追加效果

最低实现目标：

- 每回合最多一次
- 扣除 `focus`
- 目标进行体质豁免
- 失败附加 `stunned`
- 成功附加速度减半与“下一次攻击对其优势”的结构化标记或 turn effect

### 本轮只建模板、不接真实结算的能力

这些能力先进入知识库与 runtime 骨架，但本轮不强行打通：

- `barbarian.rage`
- `monk.deflect_attacks`
- `paladin.divine_smite`
- `rogue.cunning_action`
- `monk.patient_defense`
- `monk.step_of_the_wind`
- `monk.empowered_strikes`

原因：

- 这些能力要么依赖反应框架进一步扩展
- 要么会改写宿主动作上下文
- 要么会牵涉更复杂的资源/目标/伤害重写

本轮若强行全接，会把范围拉爆

## GetEncounterState 投影要求

`GetEncounterState` 需要继续遵守“不给 LLM 暴露过底层内部细节”的原则。

但本轮要新增职业能力摘要，让 LLM 知道当前有哪些职业资源和可声明能力。

建议新增 / 扩展的投影内容：

- `resources.class_features.<class_id>`
- 每个职业只投影摘要字段

例如：

```json
{
  "class_features": {
    "monk": {
      "level": 5,
      "focus_points": {"remaining": 5, "max": 5},
      "martial_arts_die": "1d8",
      "unarmored_movement_bonus_feet": 10,
      "available_features": [
        "martial_arts",
        "flurry_of_blows",
        "patient_defense",
        "step_of_the_wind",
        "stunning_strike"
      ]
    }
  }
}
```

不直接暴露：

- 模板全文
- 内部 hook 配置
- 纯后端控制字段

## 边界与兼容性

### 1. 不破坏现有 Fighter

现有 `fighter` 相关：

- `Second Wind`
- `Action Surge`
- `Indomitable`
- `Extra Attack`
- `Studied Attacks`
- `Tactical Master`

都必须保持现状可用

### 2. 不要求一次性全职业可战斗

这轮完成后，系统应达到：

- 所有武力系职业都“进入系统”
- LLM 能看到这些职业的战斗能力摘要
- 部分通用模板能真实结算

但不要求：

- 六个职业都完整可玩

### 3. 模板与 runtime 命名统一

统一约定：

- 知识库特性 ID：`class.feature_name`
- runtime bucket：`class_features[class_id]`
- runtime 内部能力字段：使用 snake_case

## 测试要求

本轮测试分三类：

### 1. 模板仓库测试

- 新职业特性能够被 repository 正确读取
- `template_type` / `activation` / `resource_model` 正确

### 2. Runtime 投影测试

- `GetEncounterState` 能正确投影 monk / rogue / paladin / barbarian / ranger 摘要
- 不暴露不该给前端 / LLM 看的底层字段

### 3. 最小真实结算测试

至少覆盖：

- `rogue.sneak_attack`
- `monk.martial_arts`
- `monk.flurry_of_blows`
- `monk.stunning_strike`

## 本轮完成标准

本轮完成后，应满足：

1. 武力系职业特性进入统一知识库模板层
2. 武力系职业 runtime 骨架进入统一 `class_features`
3. `GetEncounterState` 能投影这些职业的战斗能力摘要
4. 至少三类高复用模板开始真实结算：
   - `damage_rider_once_per_turn`
   - `bonus_attack_grant`
   - `save_on_hit_control`
5. 现有 fighter 流程、熟练系统、攻击链、反应链不回退
