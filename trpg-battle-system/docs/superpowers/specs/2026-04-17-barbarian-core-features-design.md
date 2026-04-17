# 野蛮人核心战斗特性设计

日期：2026-04-17

## 目标

在现有 `trpg-battle-system` 的职业特性框架上，补齐 Barbarian / 野蛮人 的战斗核心能力，并与 Fighter / Monk / Rogue 保持同一层级的接线方式。

本轮覆盖：

- `Rage` / 狂暴
- `Unarmored Defense` / 无甲防御
- `Weapon Mastery` / 武器精通
- `Danger Sense` / 危机感应
- `Reckless Attack` / 鲁莽攻击
- `Primal Knowledge` / 原初学识
- `Extra Attack` / 额外攻击
- `Fast Movement` / 快速移动
- `Feral Instinct` / 野性直觉
- `Instinctive Pounce` / 莽驰
- `Brutal Strike` / 凶蛮打击
- `Relentless Rage` / 坚韧狂暴
- `Persistent Rage` / 持久狂暴
- `Indomitable Might` / 不屈勇武

本轮不覆盖：

- 子职
- 属性值提升
- 传奇恩惠
- 原初斗士
- 其他不直接影响当前战斗主链的高阶延伸内容

## 设计原则

### 1. 继续沿用职业 runtime 模板

野蛮人数据继续挂在：

`entity.class_features["barbarian"]`

不额外引入平行的职业系统。

### 2. 主动能力做成独立 command，被动能力挂回既有主链

主动声明的能力：

- `use_rage` / 进入狂暴、延长狂暴
- `Reckless Attack` / 鲁莽攻击
- `Brutal Strike` / 凶蛮打击

其中：

- `use_rage` 新增独立 command
- `Reckless Attack` 与 `Brutal Strike` 继续作为攻击链参数声明，而不是拆成独立 command

被动能力分别挂回：

- 护甲计算链
- 攻击请求链
- 攻击结算链
- 豁免链
- 属性检定链
- 先攻链
- 回合开始 / 结束链
- HP 更新链

### 3. 新增 command 对外统一使用 `entity_id`

现有仓库对外命令层大量使用 `actor_id`，但本质上传的仍是执行者的 `entity_id`。

本轮新加的野蛮人 command 统一使用：

- `entity_id`

内部若要复用旧 service，可在 command handler 内部映射到既有 `actor_id` 风格。

### 4. 狂暴优先做成可预测的状态机

野蛮人最复杂的是 `Rage` / 狂暴 的生命周期。

本轮以“状态机可验证、事件可投影、LLM 易理解”为优先，明确：

- 何时开始
- 何时延长
- 何时结束
- 15级后如何变成持久狂暴

## 一、数据结构

建议野蛮人 runtime 结构如下：

```jsonc
{
  "barbarian": {
    "level": 9,
    "rage": {
      "max": 4,
      "remaining": 3,
      "active": false,
      "ends_at_turn_end_of": null,
      "persistent_rage": false,
      "restored_on_initiative_this_long_rest": false
    },
    "rage_damage_bonus": 3,
    "weapon_mastery_count": 3,
    "danger_sense": { "enabled": true },
    "reckless_attack": {
      "enabled": true,
      "declared_this_turn": false,
      "active_until_turn_start_of": null
    },
    "primal_knowledge": { "enabled": true },
    "feral_instinct": { "enabled": true },
    "instinctive_pounce": { "enabled": true },
    "brutal_strike": {
      "enabled": true,
      "extra_damage_dice": "1d10",
      "max_effects": 1
    },
    "relentless_rage": {
      "enabled": false,
      "current_dc": 10
    },
    "indomitable_might": { "enabled": false }
  }
}
```

说明：

- `rage.max / remaining`：狂暴资源
- `rage.active`：当前是否狂暴中
- `rage.ends_at_turn_end_of`：当前狂暴会在谁的回合结束时到期
- `rage.persistent_rage`：15级后是否免延长检查
- `restored_on_initiative_this_long_rest`：记录 15级先攻恢复是否已用过
- `reckless_attack.declared_this_turn`：本回合是否已经声明鲁莽攻击
- `reckless_attack.active_until_turn_start_of`：敌人对其攻击获得优势的持续边界
- `relentless_rage.current_dc`：坚韧狂暴当前 DC，初始 10，每次成功后 +5

## 二、主动 command

## 1. `use_rage` / 进入狂暴、延长狂暴

新增 command：

`use_rage(encounter_id, entity_id, extend_only=false, pounce_path=null)`

参数：

- `encounter_id`：遭遇战 ID
- `entity_id`：执行者实体 ID
- `extend_only`：是否仅延长已激活的狂暴
- `pounce_path`：进入狂暴时配套的 `Instinctive Pounce` / 莽驰 路径

### 正常进入狂暴

条件：

- 当前是自身回合
- `bonus_action_used == false`
- 未着重甲
- 还有 `rage.remaining`

结算：

- 消耗附赠动作
- `rage.remaining -= 1`
- `rage.active = true`
- 设置 `ends_at_turn_end_of = entity_id`
- 若正在专注，则立刻终止专注
- 返回 `class_feature_result.rage`

### 延长狂暴

`extend_only=true` 时：

- 不扣狂暴次数
- 消耗附赠动作
- 要求当前已经 `rage.active == true`
- 只刷新 `ends_at_turn_end_of`

### 莽驰

若角色具有 `Instinctive Pounce` / 莽驰 且本次传入 `pounce_path`：

- 允许在本次 `use_rage` 中追加一段至多等于当前速度一半的移动
- 这段移动不额外消耗动作或附赠动作
- 建议复用现有移动规则，但给本次调用一个临时 `free_movement_feet` 配额

## 三、被动接线

## 1. `Unarmored Defense` / 无甲防御

挂到 `ArmorProfileResolver`。

规则：

- 未着任何护甲时生效
- 可持用盾牌且仍生效
- AC = `10 + DEX + CON`

优先级：

- 若有护甲，则不生效
- 若同时存在其他无甲防御来源，本轮仍按“已有模式优先做单来源职业特性”，不处理跨职业冲突扩展

## 2. `Weapon Mastery` / 武器精通

挂到现有职业熟练 / 精通模板。

规则：

- 野蛮人自动获得简易与军用近战武器的职业精通使用权限模板
- 可精通武器数随等级增长

不新增单独 command。

## 3. `Danger Sense` / 危机感应

挂到敏捷豁免链。

规则：

- 只要未失能
- `DEX saving throw` 具有优势

挂点：

- `saving_throw_request`
- 或统一保存于 `resolve_saving_throw` 的优势来源整理阶段

## 4. `Primal Knowledge` / 原初学识

挂到属性检定链。

规则：

- 仅在 `rage.active == true` 时可用
- 对以下技能检定可改用力量：
  - `Acrobatics` / 特技
  - `Intimidation` / 威吓
  - `Perception` / 察觉
  - `Stealth` / 隐匿
  - `Survival` / 求生

本轮约定：

- LLM 需要在能力检定请求中显式声明“按原初学识改用力量”
- 后端负责校验：
  - 角色为野蛮人
  - 正在狂暴
  - 技能属于允许列表

## 5. `Extra Attack` / 额外攻击

继续走现有 `Extra Attack` 统一解析。

野蛮人 5 级起：

- `extra_attack_count = 2`

不为野蛮人单独造逻辑。

## 6. `Fast Movement` / 快速移动

挂到回合开始的速度重算。

规则：

- 未着重甲时，速度 `+10 ft`

## 7. `Feral Instinct` / 野性直觉

挂到先攻链。

规则：

- 先攻检定具有优势

挂点：

- `roll_initiative_and_start_encounter`

## 8. `Indomitable Might` / 不屈勇武

挂到力量检定 / 力量豁免结算后。

规则：

- 若最终总值低于力量属性值
- 则改为使用力量属性值作为总值

挂点：

- `resolve_ability_check`
- `resolve_saving_throw`

## 四、攻击链接线

## 1. `Rage Damage` / 狂暴伤害

挂到 `ExecuteAttack` 伤害段生成。

触发条件：

- `rage.active == true`
- 本次攻击使用力量
- 是武器攻击或徒手打击
- 命中并造成伤害

效果：

- 在主伤害段后追加一个平伤段
- 数值来自 `rage_damage_bonus`
- 伤害类型与本次武器或徒手打击的伤害类型一致

## 2. `Reckless Attack` / 鲁莽攻击

继续作为攻击请求参数声明，不新增单独 command。

建议参数：

```jsonc
{
  "class_feature_options": {
    "reckless_attack": true
  }
}
```

规则：

- 只能在自己回合中声明
- 只能在该回合第一次攻击检定前声明
- 仅影响本回合使用力量进行的攻击检定

结算：

- 本回合力量攻击检定具有优势
- 同时给自己挂一个持续到下个回合开始的“敌人对你攻击具有优势”的效果
- 若本回合已声明，再次声明仅视为已启用，不重复挂效果

## 3. `Brutal Strike` / 凶蛮打击

继续作为攻击请求参数声明，不新增单独 command。

建议参数：

```jsonc
{
  "class_feature_options": {
    "brutal_strike": {
      "effects": ["forceful_blow"]
    }
  }
}
```

触发条件：

- 角色具有该特性
- 本回合已声明 `Reckless Attack` / 鲁莽攻击
- 本次是基于力量的攻击
- 本次攻击原本具有优势
- 本次攻击没有劣势

结算方式：

- 放弃这次攻击的优势
- 命中时追加额外伤害骰
- 并附带对应效果

### 9级效果

- `Forceful Blow` / 巨力猛击
  - 目标直线推离 15 尺
  - 攻击者获得一次朝目标方向、至多半速、且不引发借机攻击的追进移动权限
- `Hamstring Blow` / 断筋猛击
  - 目标速度减少 15 尺，持续到攻击者下个回合开始

### 13级新增

- `Staggering Blow` / 震撼猛击
  - 目标下一次豁免具有劣势
  - 直到攻击者下个回合开始前不能发动借机攻击
- `Sundering Blow` / 破势猛击
  - 直到攻击者下个回合开始前，其他生物下一次攻击该目标时获得 `+5`

### 17级强化

- 额外伤害骰提升到 `2d10`
- 一次可同时声明两种不同效果

## 五、狂暴生命周期

## 1. 狂暴期间自动效果

激活期间：

- 对钝击、穿刺、挥砍具有抗性
- 力量检定具有优势
- 力量豁免具有优势
- 不能保持专注
- 不能施法

## 2. 回合结束的延长检查

15级前，在当前狂暴者自己的回合结束时检查：

若本轮满足以下任一条件，则狂暴延长到下个自己的回合结束：

- 对敌人做过一次攻击检定
- 迫使敌人做过一次豁免检定
- 用附赠动作执行了“仅延长狂暴”

否则狂暴结束。

建议用简单的 runtime 标记记录本轮是否满足：

- `rage_extended_by_attack_this_turn`
- `rage_extended_by_forced_save_this_turn`
- 或统一放在 `turn_counters`

## 3. 提前结束条件

15级前：

- 穿上重甲
- 陷入失能
- 回合结束未满足延长条件

15级后：

- 穿上重甲
- 陷入昏迷

## 4. `Persistent Rage` / 持久狂暴

15级：

- 投先攻时可重获所有已消耗狂暴次数
- 这一恢复在每次长休之间只可触发一次
- 狂暴总是持续 10 分钟，无需每轮延长判定

挂点：

- `roll_initiative_and_start_encounter`
- 回合结束链中的狂暴结束检查

## 六、掉到 0 HP 的 `Relentless Rage` / 坚韧狂暴

挂到 `UpdateHp`。

触发条件：

- 野蛮人等级 11+
- `rage.active == true`
- 即将掉到 0 HP
- 不是立即死亡

结算：

- 进行一次 `CON save`
- 当前 DC = `relentless_rage.current_dc`
- 成功：
  - 不进入 0 HP 流程
  - HP 改为 `barbarian level * 2`
  - `current_dc += 5`
- 失败：
  - 正常进入 0 HP 流程

重置：

- 完成短休或长休后，`current_dc` 重置为 10

本轮实现方式：

- 后端自动掷骰
- 不要求外部传入体质豁免骰

## 七、投影到 `GetEncounterState`

当前回合实体资源中新增或补齐：

- `barbarian.level`
- `barbarian.rage`
- `barbarian.rage_damage_bonus`
- `barbarian.reckless_attack`
- `barbarian.brutal_strike`
- `barbarian.relentless_rage`
- `barbarian.available_features`

其中 `available_features` 至少包含：

- `rage`
- `reckless_attack`
- `danger_sense`

高等级满足时再出现：

- `brutal_strike`
- `relentless_rage`
- `persistent_rage`
- `indomitable_might`

仍不向前端投影完整职业熟练底表。

## 八、Playbook 暴露

新增：

- `docs/skill-playbooks/barbarian.md`

至少写明：

- 如何进入狂暴
- 如何延长狂暴
- 如何声明鲁莽攻击
- 如何声明凶蛮打击
- 哪些能力为自动生效

## 九、测试计划

本轮按 TDD 分批覆盖：

1. `use_rage`
   - 进入狂暴
   - 仅延长狂暴
   - 莽驰移动
   - 无次数时报错
   - 重甲时报错
2. `ArmorProfileResolver`
   - 野蛮人无甲防御
   - 允许持盾
3. 敏捷豁免
   - 危机感应提供优势
   - 失能时失效
4. 先攻
   - 野性直觉提供优势
   - 15级持久狂暴的先攻恢复
5. 攻击请求
   - 鲁莽攻击给予优势
   - 被攻击时敌人对其有优势
   - 凶蛮打击合法性校验
6. 攻击结算
   - 狂暴伤害追加
   - 凶蛮打击四种效果
   - 17级双效果与 `2d10`
7. 检定与豁免
   - 狂暴中的力量检定 / 力量豁免优势
   - 原初学识可改用力量
   - 不屈勇武下限生效
8. HP 更新
   - 坚韧狂暴成功保留生命
   - 失败则正常倒地
   - DC 成功后递增
9. 回合结束
   - 狂暴正常延长
   - 狂暴未满足条件时结束
   - 15级持久狂暴跳过延长判定
10. `GetEncounterState`
    - 野蛮人资源与可用特性投影

## 十、范围外说明

本轮刻意不做：

- 子职扩展
- 战斗外技能熟练选择界面
- 长休 / 短休总资源管理重构
- 跨职业无甲防御冲突裁定框架
- 更复杂的“进入狂暴同时位移并触发中断反应”的特例优化

若后续要继续扩展 Barbarian，应优先顺序为：

1. `Rage` / 狂暴 的完整 runtime command 与状态投影
2. `Reckless Attack` / `Brutal Strike` 攻击链闭环
3. `Relentless Rage` / `Persistent Rage`
4. 再进入子职
