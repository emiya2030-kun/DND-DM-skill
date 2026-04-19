# 武力系职业特性第二轮设计

日期:2026-04-17

## 目标

在现有 `trpg-battle-system` 已完成的 Fighter / Monk / Rogue 核心战斗能力基础上,继续补齐一批直接影响战斗手感、且适合挂到现有主链的职业特性.

本轮只覆盖:

- Monk
  - `Patient Defense`
  - `Step of the Wind`
  - `Slow Fall`
- Rogue
  - `Cunning Strike` 缺失效果补齐与统一化
- Fighter
  - `Tactical Mind`
  - `Fighting Style` 第一批被动风格

本轮不覆盖:

- 子职
- 战斗外职业能力
- ASI / Epic Boon
- 需要完整装备持握系统才能稳定实现的战斗风格
- 更高阶武僧能力,例如 `Heightened Focus`、`Superior Defense`

## 设计原则

### 1. 主动职业能力走独立 service

与现有:

- `use_second_wind`
- `use_action_surge`

保持一致.

凡是"玩家明确声明使用"的职业能力,优先做成单独 service,而不是塞进通用动作入口.

本轮新增:

- `use_patient_defense`
- `use_step_of_the_wind`

这样做的原因:

- LLM 调用更明确
- 资源扣减集中
- 后续扩展更稳定

### 2. 被动职业能力挂回现有主链

不为被动能力造平行系统.

本轮被动能力分别挂到:

- `ResolveAbilityCheck`
- 攻击请求链
- 伤害结算链
- 坠落伤害结算链

### 3. 范围控制优先于规则全包

本轮目标是把"最常用且结算稳定"的部分做进后端,不追求一次实现全部职业细节.

因此:

- `Fighting Style` 只做第一批简单被动风格
- `Slow Fall` 只做坠落伤害减值
- `Cunning Strike` 先补齐现有规则闭环,不扩额外工具系统

## 一、Monk

## 1. Patient Defense

### 规则

武僧可以用附赠动作执行 `Disengage`.

此外,若额外消耗 1 点功力,则可以在同一个附赠动作中同时获得:

- `Disengage`
- `Dodge`

### 接口

新增 service:

`use_patient_defense(encounter_id, actor_id, spend_focus=false)`

### 结算

基础版:

- 要求当前是自身回合
- 要求附赠动作未使用
- 消耗附赠动作
- 给当前实体挂 `disengage` turn effect

强化版:

- 在基础版前提上
- 还要求武僧 `focus_points.remaining >= 1`
- 消耗 1 点功力
- 额外挂 `dodge` turn effect

### 返回

返回:

- `class_feature_result.patient_defense`
- 最新 `encounter_state`

其中摘要至少包含:

- 是否消耗功力
- 实际授予的效果列表

## 2. Step of the Wind

### 规则

武僧可以用附赠动作执行 `Dash`.

此外,若额外消耗 1 点功力,则可以在同一个附赠动作中同时获得:

- `Disengage`
- `Dash`
- 本回合跳跃距离翻倍

### 接口

新增 service:

`use_step_of_the_wind(encounter_id, actor_id, spend_focus=false)`

### 结算

基础版:

- 要求当前是自身回合
- 要求附赠动作未使用
- 消耗附赠动作
- 授予一次 `Dash`

强化版:

- 在基础版前提上
- 还要求武僧 `focus_points.remaining >= 1`
- 消耗 1 点功力
- 同时授予:
  - `Dash`
  - `Disengage`
  - `jump_distance_multiplier = 2`

### 数据落点

建议沿用现有动作经济和 turn effect 结构:

- `action_economy.dash_available` 或等价 dash 额度字段
- `turn_effects` 中的 `disengage`
- `turn_effects` 中的 `jump_distance_multiplier`

若当前没有显式的跳跃倍率结构,则新增一个简短 turn effect:

```json
{
  "effect_type": "jump_distance_multiplier",
  "multiplier": 2
}
```

### 返回

返回:

- `class_feature_result.step_of_the_wind`
- 最新 `encounter_state`

## 3. Slow Fall

### 规则

当武僧将承受坠落伤害时,可用反应将伤害减少:

`5 * monk level`

### 本轮范围

本轮只做:

- 坠落伤害结算前的减值

不做:

- 复杂地形坠落判定
- 推坠 / 飞行坠落等特殊来源扩展

### 挂接点

新增或扩展坠落伤害结算链:

- `resolve_fall_damage(...)`

若当前仓库还没有正式坠落伤害 service,则本轮先补一个最小 service,并把 `Slow Fall` 挂进去.

### 结算

- 只有武僧可见且可用反应时才允许声明使用
- 使用后消耗 reaction
- 把这次坠落伤害按减值重新计算,最低到 0

### LLM 暴露

不做主动独立 tool.

当发生坠落伤害时:

- 后端应能支持 `use_slow_fall=true` 之类的声明参数
- 或按统一反应框架开窗

推荐本轮直接复用统一 reaction 框架,保持一致性.

## 二、Rogue

## 1. Cunning Strike 总体策略

继续维持:

- 由 `execute_attack.class_feature_options.cunning_strike.effects` 声明

不新增独立 `use_cunning_strike` service.

原因:

- 它天然属于攻击命中后的结算分支
- 必须与偷袭伤害骰扣减紧密绑定

## 2. 支持效果

本轮统一支持以下效果:

- `poison`
- `trip`
- `withdraw`
- `daze`
- `knock_out`
- `obscure`

其中:

- 5 级起可用基础 `Cunning Strike`
- 11 级起允许一次命中两个效果
- 14 级起开放 `daze / knock_out / obscure`

## 3. 效果定义

### poison

- 花费:`1d6`
- 要求角色携带制毒工具
- 目标进行 CON 豁免
- 失败则附加 `poisoned`
- 持续 1 分钟
- 每回合结束可重豁免结束

第一版的"携带制毒工具"实现建议走轻量 runtime 标记,而不是完整物品系统.

### trip

- 花费:`1d6`
- 目标体型必须为 Large 及以下
- 目标进行 DEX 豁免
- 失败则 `prone`

### withdraw

- 花费:`1d6`
- 攻击后立刻获得一次最多半速的移动额度
- 该移动不触发借机攻击

本轮仍不自动替角色移动,只返回结构化结果,让 LLM 继续调移动链.

### daze

- 花费:`2d6`
- 目标进行 CON 豁免
- 失败则附加 `dazed`

本轮把 `dazed` 作为标准化 turn effect / condition 摘要处理,其行为规则只先覆盖:

- 目标下个回合只能执行:
  - 移动
  - 一个动作
  - 一个附赠动作
  三者之一

如果当前没有 `dazed` 的主链行为限制,则本轮一并补上.

### knock_out

- 花费:`6d6`
- 目标进行 CON 豁免
- 失败则 `unconscious`
- 持续 1 分钟或受到任何伤害提前结束
- 每回合结束可重豁免结束

这里不走"0 HP 击晕"那条链,而是单独作为诡诈打击控制效果.

### obscure

- 花费:`3d6`
- 目标进行 DEX 豁免
- 失败则 `blinded`
- 持续到其下个回合结束

## 4. 统一返回结构

`ExecuteAttack` 中所有 `cunning_strike` 结果统一放在:

`resolution.class_features.rogue.cunning_strike`

至少包含:

- 选择了哪些效果
- 扣除了多少偷袭骰
- 每个效果是否生效
- 若需要后续移动,则返回结构化移动授权

例如:

```json
{
  "effects": [
    {
      "effect": "withdraw",
      "applied": true,
      "withdraw_movement": {
        "feet": 15,
        "ignore_opportunity_attacks": true
      }
    }
  ]
}
```

## 三、Fighter

## 1. Tactical Mind

### 规则

当战士一次属性检定失败时,可以消耗一次 `Second Wind` 次数,掷 `1d10` 并加入结果.

若加完仍失败,则此次 `Second Wind` 次数不消耗.

### 挂接点

- `ExecuteAbilityCheck`

### 调用方式

沿用能力检定入口,允许声明:

```json
{
  "class_feature_options": {
    "tactical_mind": true
  }
}
```

### 结算顺序

1. 先正常完成属性检定
2. 若原结果成功,则忽略 `tactical_mind`
3. 若原结果失败,且声明使用:
   - 检查战士 runtime
   - 检查 `second_wind.remaining_uses`
   - 自动掷 `1d10`
   - 用新总值重新比较 DC
4. 仅当新结果成功时,真正扣除一次 `Second Wind`

### 返回

能力检定结果应包含:

- 原始是否成功
- 是否触发 `tactical_mind`
- `1d10` 骰值
- 调整后是否成功
- 是否消耗 `Second Wind`

## 2. Fighting Style

### 总体策略

本轮只做第一批纯被动、易稳定验证的风格:

- `Defense`
- `Archery`
- `Dueling`

不先做:

- `Great Weapon Fighting`
- `Two-Weapon Fighting`
- `Protection`
- `Interception`

因为这些需要更完整的持物、重掷、反应或副武器规则.

### 数据结构

战士 runtime 下新增:

```json
{
  "fighting_style": {
    "style_id": "defense"
  }
}
```

或等价字符串字段.

### Defense

规则:

- 穿着护甲时,AC +1

挂点:

- `ArmorProfileResolver`

### Archery

规则:

- 使用远程武器进行攻击检定时,攻击检定 +2

挂点:

- `AttackRollRequest`

### Dueling

规则:

- 当你单手持用一把近战武器,且另一只手没有持用其他武器时
- 该武器伤害 +2

本轮采用轻量判定:

- 只要求当前攻击为单手近战武器
- 且另一只手未持武器

若未来盾牌要不要算作允许项,再单独细化.

挂点:

- `ExecuteAttack` 的结构化伤害准备阶段

## 四、GetEncounterState 与 Playbook 投影

本轮新增能力应在 `GetEncounterState` 中做简短投影,供前端和 LLM 读取:

- Monk
  - `patient_defense`
  - `step_of_the_wind`
- Rogue
  - `cunning_strike` 可用状态与最大效果数
- Fighter
  - `tactical_mind`
  - `fighting_style`

投影原则:

- 只给可用摘要
- 不暴露过多内部临时字段

并同步更新:

- [fighter.md](/Users/runshi.zhang/DND-DM-skill/trpg-battle-system/docs/skill-playbooks/fighter.md)
- [rogue.md](/Users/runshi.zhang/DND-DM-skill/trpg-battle-system/docs/skill-playbooks/rogue.md)
- [monk.md](/Users/runshi.zhang/DND-DM-skill/trpg-battle-system/docs/skill-playbooks/monk.md)

让 LLM 协议与后端调用保持一致.

## 五、测试要求

至少补以下测试:

### Monk

- `use_patient_defense` 基础版:只给 `Disengage`
- `use_patient_defense` 强化版:额外给 `Dodge` 并扣 1 点功力
- `use_step_of_the_wind` 基础版:授予 `Dash`
- `use_step_of_the_wind` 强化版:授予 `Dash + Disengage + jump_distance_multiplier`
- `Slow Fall`:反应后坠落伤害减少 `5 * level`

### Rogue

- `poison` 会附加 `poisoned` 与回合末重豁免
- `daze` 会附加行为限制效果
- `knock_out` 会附加 `unconscious` 且受伤提前结束
- `obscure` 会附加 `blinded` 至下回合结束
- 11 级双效果与 14 级高阶效果门槛回归

### Fighter

- `Tactical Mind` 失败转成功时消耗 `Second Wind`
- `Tactical Mind` 失败仍失败时不消耗 `Second Wind`
- `Defense` 穿甲时 AC +1
- `Archery` 远程武器攻击 +2
- `Dueling` 满足条件时伤害 +2,不满足时不加

## 六、非目标

本轮明确不做:

- `Monk` 的 `Heightened Focus`、`Self-Restoration`、`Superior Defense`
- `Rogue` 子职与 `Stroke of Luck`
- `Fighter` 更复杂战斗风格
- 完整坠落、跳跃、攀爬、液面移动系统
