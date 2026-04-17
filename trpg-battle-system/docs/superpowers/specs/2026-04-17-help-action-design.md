# 协助动作设计

日期：2026-04-17

## 目标

为 `trpg-battle-system` 增加基础战斗动作 `Help`，覆盖其两种战斗内用法：

- 辅助一次属性检定
- 辅助一次攻击检定

本次目标是做“最小正确版”：

- LLM 能稳定把玩家自然语言转成标准 tool 调用
- 后端独立完成规则生效，不依赖 LLM 手工记状态
- 与现有 `turn_effects`、攻击链、属性检定链、开始回合清理链自然接合
- 为后续 `Help` 的职业变体、战斗外扩展与更多短时辅助效果保留扩展点

## 本次范围

本次只覆盖：

- 普通动作版 `Help`
- `Help(ability)` 对技能 / 工具检定的单次优势辅助
- `Help(attack)` 对敌方目标的单次攻击优势辅助
- `GetEncounterState` 对 `Help` 状态的摘要投影
- LLM skill 中的调用规则更新

本次明确不覆盖：

- 战斗外完整 `Help` 协议
- “DM 是否允许此帮助成立”的复杂语义判定
- 复杂可见性 / 口头距离 / 物理接触建模
- `Ready` 动作配合 `Help`
- 多层叠加 `Help` 的复杂优先级系统

## 设计原则

### 1. `Help` 是显式动作，不应隐式塞进攻击或检定请求

玩家说“我协助他攻击”或“我帮他调查”时，本质是在当前回合执行标准动作。

因此 `Help` 应有独立 service / runtime command，而不是：

- 在攻击请求里偷偷附加标记
- 在属性检定请求里临时传一个 `helped: true`

本次采用两个显式入口：

- `use_help_attack`
- `use_help_ability_check`

这样调用顺序清楚：

- 先执行 `Help`
- 后续攻击或检定链自动读取其效果
- LLM 不需要自己维持“这个优势还在不在”

### 2. 一律复用 `turn_effects`，不新建平行 help 容器

`Help` 本质上是“短持续、可消费、可过期”的运行时战斗效果。

它与现有：

- `Dodge`
- `Disengage`
- 法术持续效果
- 武器精通短时效果

在运行态性质上是一类问题。

因此本次不额外引入 `pending_help_effects` 或独立仓库，而是继续使用 `EncounterEntity.turn_effects`。

### 3. `Help(attack)` 挂在被干扰的敌人身上

用户已确认：

- `Help(attack)` 不预先绑定某个具体盟友
- 任意盟友对该目标的下一次攻击都可消耗它

因此最自然的模型是：

- 对敌人使用 `Help(attack)` 时，把 effect 挂在“被帮助攻击的目标”身上
- 任意合法盟友之后攻击该目标时，自动获得优势并消耗该 effect

这样比把 effect 挂在施助者身上更直观，查询成本也更低。

### 4. `Help(ability)` 挂在受助盟友身上

`Help(ability)` 的受益者是某个明确盟友，且只对某个明确的技能 / 工具检定生效。

因此 effect 应直接挂在该盟友身上：

- 查询路径最短
- 结算点明确
- 与 `execute_ability_check` 最容易接合

### 5. 后端只做最小硬规则校验，不替代 DM 的语义裁定

`Help(ability)` 规则里明确：

- DM 对“你是否真的能帮助这个检定”拥有最终解释权

因此本次后端只校验：

- 是否当前回合
- 是否有动作
- 是否盟友
- 是否提供了标准化的 `check_type` / `check_key`

而不在后端硬编码：

- 一定距离内才可口头帮助
- 某些技能绝对不能帮
- 是否必须有相同熟练

这些留给 LLM / DM 先判断，再决定是否调用 tool。

## 一、服务结构

### 新增 service

- `tools/services/combat/actions/use_help_attack.py`
- `tools/services/combat/actions/use_help_ability_check.py`

### 新增 runtime command

- `runtime/commands/use_help_attack.py`
- `runtime/commands/use_help_ability_check.py`

### 复用的既有主链

- `AttackRollRequest`
- `execute_ability_check`
- `StartTurn` / 开始回合清理链
- `GetEncounterState`

## 二、运行态模型

## 1. `Help(attack)` effect

成功使用 `Help(attack)` 后，在目标敌人身上追加一个 `turn_effect`：

```json
{
  "effect_id": "effect_help_attack_001",
  "effect_type": "help_attack",
  "name": "Help Attack",
  "source_entity_id": "ent_ally_sabur_001",
  "source_name": "萨布尔",
  "source_side": "ally",
  "trigger": "manual_state",
  "source_ref": "action:help_attack",
  "expires_on": "source_next_turn_start",
  "remaining_uses": 1
}
```

语义：

- 这个目标正被 `source` 虚晃干扰
- 在 `source` 下个回合开始前，任意同阵营盟友对它的下一次攻击获得优势
- 一旦被合法攻击消费，移除 effect

## 2. `Help(ability)` effect

成功使用 `Help(ability)` 后，在受助盟友身上追加一个 `turn_effect`：

```json
{
  "effect_id": "effect_help_ability_001",
  "effect_type": "help_ability_check",
  "name": "Help Ability Check",
  "source_entity_id": "ent_ally_miren_001",
  "source_name": "米伦",
  "trigger": "manual_state",
  "source_ref": "action:help_ability_check",
  "expires_on": "source_next_turn_start",
  "remaining_uses": 1,
  "help_check": {
    "check_type": "skill",
    "check_key": "investigation"
  }
}
```

语义：

- 受助者的下一次指定检定具有优势
- 到来源者下个回合开始前未用掉则失效
- 真正消费发生在该盟友完成对应检定时

## 为什么统一使用 `source_next_turn_start`

规则文本是：

- 若到你的下个回合开始前还没用掉，效果消失

这里的“你”是施助者，而不是受助者或目标。

因此两种 `Help` 都应绑定：

- `source_entity_id`
- `expires_on = source_next_turn_start`

而不是简单写成：

- `start_of_target_turn`
- `one_round`

## 三、`use_help_attack` 设计

### 输入

`use_help_attack.execute(...)`

- `encounter_id`
- `actor_id`
- `target_id`

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `action_economy.action_used == false`
- actor 未失能到无法执行动作
- `target` 存在
- `target` 是敌人
- `target` 在 `actor` 5 尺内

### 结算

成功时：

- 消耗 `action_economy.action_used`
- 清理该目标身上由同一 `source_entity_id` 生成的旧 `help_attack` effect
- 写入新的 `help_attack` effect
- 返回最新 `encounter_state`

### 为什么不限制“指定某个盟友”

用户已明确选择：

- `Help(attack)` 供任意盟友使用

因此本次不接收：

- `ally_id`

也不在 effect 中绑定：

- 指定受益者

## 四、`use_help_ability_check` 设计

### 输入

`use_help_ability_check.execute(...)`

- `encounter_id`
- `actor_id`
- `ally_id`
- `check_type`
- `check_key`

其中：

- `check_type` 取值：`skill` / `tool`
- `check_key` 例如：`investigation` / `perception` / `thieves_tools`

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `action_economy.action_used == false`
- actor 未失能到无法执行动作
- `ally` 存在
- `ally` 与 `actor` 同阵营
- 提供合法的 `check_type`
- `check_key` 非空

### 结算

成功时：

- 消耗 `action_economy.action_used`
- 清理该 `ally` 身上由同一 `source_entity_id` + 同一 `check_type/check_key` 生成的旧 `help_ability_check`
- 写入新的 `help_ability_check`
- 返回最新 `encounter_state`

### 为什么不在后端判断“你是否真的帮得上”

这是 DM 裁定层，不适合后端一刀切。

例如：

- 调查桌面文件时，米伦可以口头提醒关键痕迹
- 盗贼工具拆锁时，旁边的法师未必帮得上
- 某些场景下，即使盟友不熟练，也可能能提供简单协助

这些都应由 LLM 先理解场景后决定是否调用 `use_help_ability_check`。

## 五、攻击链接入

`help_attack` 接入 `AttackRollRequest`。

当攻击者对目标发起攻击时：

1. 读取目标身上的 `turn_effects`
2. 找出所有有效的 `help_attack`
3. 过滤出来源阵营与攻击者同阵营的 effect
4. 若存在，则该次攻击获得优势
5. 在请求上下文中记录“本次命中了哪个 help effect”

### 为什么不在 request 阶段直接删除 effect

因为 `AttackRollRequest` 只是“构造可执行请求”。

若此时就删除 effect，可能出现：

- 请求成功生成
- 但后续未真正执行攻击
- help 被白白吞掉

因此：

- request 阶段只标记将要消费哪个 effect
- 真正移除应发生在实际攻击结算成功进入执行链时

## 六、属性检定链接入

`help_ability_check` 接入 `execute_ability_check`。

当某实体执行属性检定时：

1. 读取该实体自己的 `turn_effects`
2. 找出有效的 `help_ability_check`
3. 匹配：
   - `check_type`
   - `check_key`
4. 若命中，则本次检定具有优势
5. 检定真正执行后移除该 effect

### 当前版只接技能 / 工具

规则文本明确写的是：

- 技能熟练或工具熟练对应的属性检定

因此当前版不直接支持：

- 纯属性检定 `ability`

后续若要扩展，可单独加：

- `check_type = ability`

但这不在本次范围内。

## 七、过期与清理

两类 `Help` 都在“来源者下个回合开始时”过期。

因此在 `StartTurn` 时，应扫描全场实体的 `turn_effects`，清除：

- `effect_type in ["help_attack", "help_ability_check"]`
- 且 `source_entity_id == 当前开始回合的实体`
- 且 `expires_on == "source_next_turn_start"`

### 为什么要扫全场

因为：

- `help_attack` 挂在敌人身上
- `help_ability_check` 挂在盟友身上

它们都不一定挂在“来源者自己”身上。

因此不能只清理当前实体自己的 `turn_effects`。

## 八、`GetEncounterState` 投影

前端 / LLM 不需要看到完整内部 effect 结构，只需要简洁摘要。

建议投影：

### 对受助盟友

- `受到米伦的 Help（Investigation）`
- `受到米伦的 Help（Thieves' Tools）`

### 对被干扰敌人

- `受到萨布尔的 Help（攻击）`

### 说明

- 只做可读摘要
- 不暴露 `remaining_uses`
- 不暴露内部 `expires_on`

## 九、LLM 调用规则

### `Help(attack)`

当玩家表达：

- “我帮他打这个兽人”
- “我去牵制这个敌人”
- “我协助下一位攻击这个目标”

且意图明确是战斗内帮助攻击时：

1. 调 `use_help_attack`
2. 传 `encounter_id / actor_id / target_id`
3. 后续其他盟友攻击该目标时，不需要 LLM 自己补优势
4. 一律让后端自动读取并结算

### `Help(ability)`

当玩家表达：

- “我帮他调查书桌”
- “我辅助他拆锁”
- “我给他打下手”

且 LLM 判断该帮助在场景上成立时：

1. 先把自然语言标准化成 `check_type + check_key`
2. 调 `use_help_ability_check`
3. 之后当受助者执行对应检定时，不需要 LLM 自己补优势
4. 一律由后端自动读取并消费

### LLM 不该做的事

- 不要自己记“这个 help 还剩没剩”
- 不要自己给攻击口头加优势而不调用 tool
- 不要把 `Help(attack)` 错写成“指定盟友专属 buff”

## 十、错误处理

若不满足前置校验，应返回结构化失败，而不是 transport error。

例如：

- 目标不在 5 尺内
- 不是当前行动者
- 已经使用过动作
- `check_type` 非法
- 目标 / 盟友不存在

LLM 读取失败原因后，应改口或重新选择动作，而不是假装动作已成功。

## 十一、后续扩展点

本次设计为后续留出这些自然扩展位：

- 盗贼 /吟游诗人 / 战术特性的辅助类动作
- `Help(ability)` 支持 `ability` 类型
- 更严格的“是否有足够距离 / 交流条件”判定
- 更细的 effect 可视化投影
- 复杂叠加与优先级规则

## 总结

本次 `Help` 动作采用：

- 两个显式 runtime command
- 两类 `turn_effect`
- `Help(attack)` 挂目标敌人
- `Help(ability)` 挂受助盟友
- 攻击链 / 检定链自动读取并消费
- 在施助者下个回合开始时统一过期

这是当前项目里最小、最清晰、最容易与既有系统对接的实现方案。
