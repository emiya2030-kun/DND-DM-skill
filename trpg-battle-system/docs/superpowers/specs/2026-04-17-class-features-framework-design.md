# 战斗内职业特性框架设计

日期：2026-04-17

## 目标

为战斗系统增加一套可扩展的职业特性框架，先落地战士基础职业特性的第一批真实结算能力，并为后续盗贼、圣武士、野蛮人等职业复用同一套运行时模型。

本次只覆盖：

- 战斗内真实结算
- 基础职业特性，不含子职
- 战士的以下特性：
  - `Second Wind`
  - `Action Surge`
  - `Tactical Shift`
  - `Indomitable`
  - `Studied Attacks`
  - `Extra Attack / Extra Attack (2) / Extra Attack (3)`
  - `Tactical Master`

本次明确不覆盖：

- `Fighting Style`
- `Weapon Mastery` 本体配置系统
- 子职特性
- 战斗外探索 / 社交 / 长休结算
- 复杂法术联动职业能力

## 设计原则

### 1. 不把战士写死进主链

职业特性不能直接散落在攻击、移动、豁免等 service 的条件分支里。要先搭一个通用框架，再让战士成为第一批接入者。

### 2. 模板化优先，专属实现兜底

高共性的职业特性通过模板表达。

例如：

- 主动消耗型
- 失败改判型
- 攻击链修正型
- 回合内额度型
- 临时标记型

但不强求所有职业特性都完全模板化。规则特别拧巴的能力允许专属 service。

### 3. 运行时状态与知识描述分离

LLM 看的知识描述，不直接承担运行时计数。

运行时实体只存：

- 当前遭遇战需要结算的次数
- 当前回合可用额度
- 下次攻击 / 下次豁免等临时标记
- 本回合已使用情况

## 三层结构

### 一、知识模板层

新增职业特性定义仓库，用于提供给 LLM 和部分规则 service 读取。

建议文件：

- `data/knowledge/class_feature_definitions.json`

定义内容只描述规则，不保存当前剩余次数。

每个特性包含：

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

本次战士特性的模板分类：

- `second_wind`: `activated_heal`
- `action_surge`: `extra_action_grant`
- `tactical_shift`: `post_activation_free_movement`
- `indomitable`: `failed_save_reroll`
- `studied_attacks`: `miss_applies_next_attack_advantage_mark`
- `extra_attack`: `attack_action_multi_strike`
- `tactical_master`: `attack_mastery_override`

### 二、运行时状态层

在 `EncounterEntity` 上新增：

- `class_features: dict[str, Any]`

只存运行时状态，不复制整套知识描述。

战士示例结构：

```json
{
  "fighter": {
    "fighter_level": 9,
    "second_wind": {
      "max_uses": 3,
      "remaining_uses": 2
    },
    "action_surge": {
      "max_uses": 1,
      "remaining_uses": 1,
      "used_this_turn": false
    },
    "indomitable": {
      "max_uses": 1,
      "remaining_uses": 1
    },
    "extra_attack_count": 2,
    "tactical_master_enabled": true,
    "studied_attacks": [
      {
        "target_entity_id": "ent_enemy_001",
        "expires_at": "end_of_next_turn",
        "consumed": false
      }
    ],
    "temporary_bonuses": {
      "free_movement_no_oa_feet": 0,
      "extra_non_magic_action_available": 0
    },
    "turn_counters": {
      "attack_action_attacks_used": 0
    }
  }
}
```

### 三、规则执行层

职业特性规则执行分为两类：

#### 独立 service

适合主动宣告并立即产生资源变化的能力。

本次包括：

- `use_second_wind`
- `use_action_surge`

#### 主链 hook

适合依附在攻击 / 豁免 / 回合引擎中的能力。

本次包括：

- `Extra Attack`
- `Studied Attacks`
- `Indomitable`
- `Tactical Master`

## 战士七项特性落地方案

## 1. Second Wind

### 规则

- 附赠动作
- 消耗一次 `Second Wind`
- 恢复 `1d10 + fighter_level`
- 短休恢复 1 次，长休恢复全部

### 实现

新增 service：

- `tools/services/class_features/fighter/use_second_wind.py`

输入：

- `encounter_id`
- `actor_id`
- 可选 `healing_roll`

行为：

- 校验当前实体或允许的越回合声明
- 校验附赠动作可用
- 校验 `remaining_uses > 0`
- 结算治疗
- 消耗 `bonus_action`
- 扣减 `remaining_uses`
- 若拥有 `Tactical Shift`，在结果里返回一次免费移动额度

返回结构中新增：

- `class_feature_result`
- `encounter_state`

## 2. Tactical Shift

### 规则

- 使用 `Second Wind` 后触发
- 可移动不超过速度一半
- 不引发借机攻击

### 实现

不做单独按钮 service。

由 `use_second_wind` 返回：

```json
{
  "free_movement_after_second_wind": {
    "feet": 15,
    "ignore_opportunity_attacks": true
  }
}
```

之后 LLM 再决定是否调用移动工具。

移动工具需要支持一个临时 flag：

- `ignore_opportunity_attacks_for_this_move = true`

该 flag 只对这次免费移动生效。

## 3. Action Surge

### 规则

- 自己回合内使用
- 获得一个额外动作
- 该动作不能是 `Magic action`
- 每回合最多使用一次

### 实现

新增 service：

- `tools/services/class_features/fighter/use_action_surge.py`

行为：

- 校验在自己回合
- 校验本回合未用过
- 校验仍有剩余次数
- 增加 `extra_non_magic_action_available += 1`
- 标记 `used_this_turn = true`

该额度由后续动作请求消费。

## 4. Extra Attack 系列

### 规则

- 执行 `Attack action` 时，一次动作内可攻击多次
- 5级为 2 次
- 11级为 3 次
- 20级为 4 次
- 若来自多个职业或来源的 `Extra Attack` 同时存在，这些来源不叠加
- 运行时只取“当前可用的最高攻击次数”

### 实现

不做独立 service。

在攻击主链增加概念：

- 一次 `Attack action` 的攻击额度

运行时计数：

- `attack_action_attacks_used`
- `extra_attack_count`
- `extra_attack_sources`

行为：

- 第一次普通武器攻击时，若本回合尚未开启攻击动作序列，则开启
- 每次攻击消耗序列中的一个攻击位
- 当攻击位耗尽，才真正视为这次攻击动作完成
- `extra_attack_count` 由所有来源中的最大值决定，而不是求和

示例：

- 战士5 / 牧师不会因为只有一份 `Extra Attack` 以外的来源而额外增加攻击次数
- 战士5 / 其他同样提供 `Extra Attack` 的职业，也仍然只取更高的一档，不叠加成 3 次或更多
- 战士11 若已有 `Three attacks per Attack action`，其他来源的 `Extra Attack` 不再增加次数

这意味着：

- 不再把一次普通攻击简单等同于“整个动作用完”

本次只改武器攻击，不把复杂法术动作混进来。

## 5. Studied Attacks

### 规则

- 你对某生物攻击失手后
- 直到你下个回合结束前
- 你对其的下次攻击检定具有优势

### 实现

挂在攻击结算后：

- 若本次武器攻击失手
- 给目标写入一条临时标记

示例：

```json
{
  "target_entity_id": "ent_enemy_001",
  "expires_at": "end_of_next_turn",
  "consumed": false
}
```

攻击请求阶段读取该标记：

- 若目标匹配且未消费
- 自动给予优势
- 结算后立刻消费

## 6. Indomitable

### 规则

- 当一次豁免失败时
- 可重骰，并加战士等级
- 必须使用新结果

### 实现

接入统一 reaction framework。

触发点：

- `saving_throw_failed`

新增 reaction 定义：

- `indomitable`

结算行为：

- 消耗一次 `indomitable.remaining_uses`
- 重投 d20
- 加上原豁免修正
- 再额外加 `fighter_level`
- 使用新结果覆盖旧结果

它不是动作，不消耗 action / bonus action / reaction。
但它属于“失败后插入的改判窗口”，所以沿用 reaction window 作为统一询问机制。

## 7. Tactical Master

### 规则

- 使用你已掌握精通的武器攻击时
- 可把该次攻击的精通改为：
  - `push`
  - `sap`
  - `slow`

### 实现

不做单独 service。

攻击入口新增可选参数：

- `mastery_override`

只有满足以下条件时才合法：

- 实体拥有 `tactical_master_enabled`
- 本次武器原本可使用精通
- override 值属于 `push / sap / slow`

攻击命中后按 override 结算精通效果。

## 与现有系统的衔接

## 与 action economy 的关系

保留现有：

- `action_used`
- `bonus_action_used`
- `reaction_used`

职业特性不替代动作经济，只在其上叠加职业资源。

## 与 reaction framework 的关系

以下能力直接复用 reaction window：

- `Indomitable`
- 后续其他“失败后改判”类职业特性

这样未来可以统一接：

- 圣武士 / 牧师 / 法师的失败后响应能力

## 与移动系统的关系

`Tactical Shift` 不改移动主规则。

只是给一次“带免借机 flag 的免费移动额度”，由后续移动 service 消费。

## 与攻击系统的关系

攻击主链需要增加三个 hook：

- 攻击前：读取 `Studied Attacks` 优势标记
- 攻击中：支持 `Tactical Master` 的 `mastery_override`
- 攻击后：失手时写入 `Studied Attacks`

同时把一次 `Attack action` 与“单次攻击”解耦，接入 `Extra Attack` 序列。

## 运行时初始化

需要有一个统一初始化入口，把角色静态等级信息转为战斗运行时职业特性状态。

建议两种来源兼容：

- encounter 初始化时由 LLM / 上层传入 `class_features`
- 若上层只传职业与等级，则由 `initialize_encounter` 补齐默认运行时结构

本次优先支持：

- 显式传入完整 `class_features`

## 测试策略

按功能分层测试：

### 单元测试

- `use_second_wind`
- `use_action_surge`
- `studied_attacks` 标记写入与消费
- `tactical_master` override 合法性

### 攻击链测试

- `Extra Attack` 不会第一击就把整次攻击动作锁死
- `Studied Attacks` 失手后给下次对同目标优势
- `Tactical Master` 改写精通效果生效

### 失败改判测试

- 失败豁免后开 `Indomitable` 窗口
- 使用后重骰并加战士等级
- 新结果覆盖旧结果

### 移动联动测试

- `Second Wind` 后返回 `Tactical Shift` 免费移动额度
- 该次移动不触发借机攻击

## 推荐实现顺序

1. `class_features` 运行时数据结构
2. `Second Wind + Tactical Shift`
3. `Action Surge`
4. `Extra Attack`
5. `Studied Attacks`
6. `Indomitable`
7. `Tactical Master`
8. 职业特性知识库

## 风险与边界

### 1. Extra Attack 是最容易污染主链的点

如果继续把“一次攻击”视作“整个动作结束”，后续战士、武僧、双武器、怪物多重攻击都会互相冲突。

因此必须尽早拆开“动作额度”和“攻击次数额度”。

### 2. Tactical Shift 不能偷偷自动移动

它只授予免费移动资格，不替玩家自动决定位置。

### 3. Indomitable 复用 reaction window 只是运行协议复用

它不是规则意义上的 Reaction，不消耗 `reaction_used`。
这里只复用“失败后暂停并改判”的宿主机制。

### 4. Tactical Master 依赖现有武器精通链

如果未来精通系统结构变化，需要同步调整 override 校验逻辑。

## 本次产出范围结论

这次不是“只把战士七个特性做掉”，而是：

- 先搭一个战斗内职业特性通用框架
- 再用战士七个特性作为第一批实现

这样后续加入其他职业时，只需要：

- 增加知识定义
- 增加运行时初始化
- 在少数 hook 点接入对应模板或专属 service

而不需要重写整套系统。
