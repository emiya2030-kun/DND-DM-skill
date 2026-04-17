# 擒抱设计

日期：2026-04-17

## 目标

为 `trpg-battle-system` 增加战斗内的完整最小版擒抱闭环，覆盖：

- 发起擒抱
- 被擒抱者获得 `grappled:来源`
- 被擒抱者速度变为 0，无法自愿移动
- 擒抱者拖着目标移动
- 拖行时擒抱者移动速度减半
- 受擒者主动挣脱
- 擒抱者失能时自动结束擒抱

本次目标是做“最小正确版”：

- LLM 可以把“我擒抱他”“我拖着他走”“我挣脱”稳定转成合法 tool 调用
- 后端独立负责规则结算，不依赖 LLM 手工维护擒抱关系
- 与现有 condition、移动链、状态投影、职业特性扩展位自然接合

## 本次范围

本次只覆盖：

- 单目标主动擒抱
- 单目标主动挣脱
- 拖行时速度减半
- 拖行时被擒抱者随路径逐格被带动
- 擒抱关系的自动释放
- `GetEncounterState` 的擒抱关系摘要

本次明确不覆盖：

- 一个擒抱者同时擒抱多个目标
- 推撞 `Shove`
- 严格空手 / 持物系统
- 更复杂的拖行体型例外
- 战斗外擒抱协议

## 设计原则

### 1. 擒抱是显式动作，不应伪装成攻击或检定附注

玩家说“我擒抱他”时，本质上是执行一种特殊的徒手打击选项，而不是普通伤害攻击。

因此本次不把擒抱塞进：

- `execute_attack`
- `execute_ability_check`

而是使用独立 service / runtime command：

- `use_grapple`
- `escape_grapple`

这样边界清楚：

- 发起擒抱是一种动作
- 挣脱也是一种动作
- 拖行则复用已有移动链自动处理

### 2. 使用 `condition + active_grapple` 双轨，而不是只用一种状态

目标被擒抱这一事实，应继续使用已有条件系统表达：

- `grappled:ent_actor_001`

但“谁正在主动维持这次擒抱、逃脱 DC 是多少、移动时谁拖着谁”这类运行态，单靠 condition 不足够表达。

因此本次采用双轨：

- 被擒抱者：`conditions` 里写 `grappled:来源`
- 擒抱者：`combat_flags["active_grapple"]`

这样分工明确：

- condition 负责规则可见性与既有兼容
- runtime flag 负责拖行与挣脱所需的附加数据

### 3. 本次只支持“一个擒抱者同一时间一个主动擒抱目标”

用户已确认：

- 一个擒抱者同一时间只支持一个主动擒抱目标

因此：

- `combat_flags["active_grapple"]` 只保存单个目标
- 发起第二次擒抱时直接报错

这可以把移动、自动解除、挣脱链路先做稳，而不把多目标手位系统一起拖进来。

### 4. 擒抱 DC 不能写死为力量，必须留职业覆盖扩展点

默认规则下，擒抱豁免 DC 是：

- `8 + 力量调整值 + 熟练加值`

但武僧 `Martial Arts` 可以让徒手打击的擒抱 / 推撞改用敏捷决定 DC。

因此本次不把公式硬编码死，而是抽一个统一 helper：

- `resolve_grapple_save_dc(actor)`

其返回：

- `dc`
- `ability_used`
- `breakdown`

默认：

- `ability_used = str`

若 actor 有武僧覆盖规则：

- `ability_used = dex`

这样未来：

- 推撞
- 其他职业特性
- 专长或特殊怪物能力

都可以复用同一入口。

## 一、服务结构

### 新增 service

- `tools/services/combat/grapple/shared.py`
- `tools/services/combat/grapple/use_grapple.py`
- `tools/services/combat/grapple/escape_grapple.py`

### 新增 runtime command

- `runtime/commands/use_grapple.py`
- `runtime/commands/escape_grapple.py`

### 复用的既有主链

- `BeginMoveEncounterEntity`
- `MoveEncounterEntity`
- `GetEncounterState`
- `UpdateConditions`
- `StartTurn`

## 二、运行态模型

## 1. 被擒抱者 condition

目标若被擒抱，写入：

```json
[
  "grappled:ent_actor_001"
]
```

语义：

- 目标被 `ent_actor_001` 擒抱
- 现有 condition runtime 已能识别来源型 condition
- 现有部分攻击判定已能利用 `grappled:来源`

## 2. 擒抱者 runtime flag

擒抱成功后，在擒抱者身上写入：

```json
{
  "target_entity_id": "ent_target_001",
  "escape_dc": 13,
  "dc_ability_used": "str",
  "movement_speed_halved": true,
  "source_condition": "grappled:ent_actor_001"
}
```

保存位置：

```json
combat_flags["active_grapple"]
```

语义：

- 当前主动维持的目标是谁
- 目标挣脱时对抗哪个 DC
- 这次擒抱的 DC 是用哪个能力算出的
- 拖行时应减半速度

## 三、`use_grapple` 设计

### 输入

`use_grapple.execute(...)`

- `encounter_id`
- `actor_id`
- `target_id`

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `actor` 还有动作
- `actor` 未失能到无法执行动作
- `target` 存在
- `target` 是敌人
- `target` 在 5 尺内
- `target` 体型至多比 `actor` 大一级
- `actor` 当前没有 `active_grapple`

本次暂不做严格空手校验。

### 结算

1. 消耗 `actor` 的 `action`
2. 计算擒抱豁免 DC
3. 目标在力量豁免和敏捷豁免中自动取更优者
4. 若目标豁免失败：
   - 给目标加 `grappled:actor_id`
   - 给 `actor` 写入 `active_grapple`
5. 若目标豁免成功：
   - 不建立擒抱关系

### 为什么由后端自动选目标豁免类型

规则写的是：

- 目标必须通过一次力量或敏捷豁免检定（由目标选择）

对怪物和一般自动流程而言，最佳实现是：

- 后端直接计算两者
- 自动取总值更高者

这样 LLM 不需要参与无意义的中间选择，也更稳定。

## 四、擒抱 DC helper

### 统一入口

新增内部 helper：

- `resolve_grapple_save_dc(actor)`

返回结构：

```json
{
  "dc": 14,
  "ability_used": "dex",
  "breakdown": {
    "base": 8,
    "ability_mod": 4,
    "proficiency_bonus": 2
  }
}
```

### 默认行为

默认：

- `ability_used = str`

即：

- `dc = 8 + str_mod + proficiency_bonus`

### 武僧覆盖

若 actor 具有武僧 `Martial Arts` 对应的擒抱 DC 覆盖能力，则：

- `ability_used = dex`

即：

- `dc = 8 + dex_mod + proficiency_bonus`

本次只为武僧留出并接入这个扩展位。

## 五、被擒抱目标的限制

只要目标带有：

- `grappled:来源`

则本次最小规则包括：

- 速度视为 0
- 无法进行自愿移动

接入点：

- `BeginMoveEncounterEntity`
- `MoveEncounterEntity`

实现方式：

- 现有移动链已经把 `grappled` 视作阻止自愿移动的状态之一
- 本次只需保证擒抱成功后正确写入 condition

## 六、拖着目标移动

### 规则目标

若擒抱者正在主动维持擒抱并移动：

- 自身有效移动速度减半
- 被擒抱目标沿路径逐格被拖走

### 本次拖行模型

本次采用“后一格跟随”模型：

- 擒抱者移动到新格
- 被擒抱目标移动到擒抱者刚离开的上一格

也就是：

- 擒抱者在前
- 目标被拖在后面一格

### 为什么不用最终点瞬移

若直接把目标瞬移到擒抱者最终位置：

- 路径展示不自然
- 中途路径阻挡与占格冲突难以解释

逐格拖行更接近你现有地图系统，也方便后续前端表现。

### 速度减半

若 `actor.combat_flags["active_grapple"]` 有效，则：

- 其本次可用移动速度视为 `floor(walk / 2)` 或等价减半处理

这里的“有效”指：

- 目标仍存在
- 目标仍带有 `grappled:actor_id`

### 路径处理

移动链按 path 逐格推进时：

1. 检查擒抱者下一步是否合法
2. 检查目标是否能跟到擒抱者上一格
3. 若两者都合法，更新两者位置
4. 若任何一步不合法，停止并返回非法移动

### 借机攻击

本次不额外给拖行加入特殊借机例外。

即：

- 是否触发借机攻击，仍按擒抱者自身移动链判断
- 被拖着走的目标不因这次强制式跟随单独生成新的移动声明

## 七、`escape_grapple` 设计

### 输入

`escape_grapple.execute(...)`

- `encounter_id`
- `actor_id`

其中 `actor_id` 必须是受擒者自己。

### 前置校验

必须满足：

- 当前是 `actor` 自己的回合
- `actor` 还有动作
- `actor` 当前处于 `grappled:来源`
- 能从其 condition 中解析出 grappler 来源
- 来源者实体仍存在

### 结算

1. 消耗 `actor` 的 `action`
2. `actor` 在：
   - 力量（运动）
   - 敏捷（特技）
   中自动取更优检定
3. 与 grappler 的 `escape_dc` 比较
4. 成功：
   - 移除 `grappled:来源`
   - 清掉 grappler 的 `active_grapple`
5. 失败：
   - 状态保持不变

### 为什么自动取更优检定

规则是：

- 受擒生物可以进行一次力量（运动）或敏捷（特技）检定

这里同样不需要 LLM 代替角色“选择较差项”，后端直接取更优是最自然的自动化实现。

## 八、自动结束擒抱

以下情况会自动结束擒抱：

### 1. 擒抱者陷入失能

若 grappler 陷入：

- `incapacitated`

则擒抱立刻结束。

### 2. 目标失去对应的 `grappled:来源`

若目标不再带有这条来源型 condition，则 grappler 的 `active_grapple` 也必须同步清掉。

### 3. 任一方离场

若 grappler 或 target 被移除、死亡、消失，则擒抱关系一并结束。

### 建议实现

抽一个统一 helper：

- `release_grapple_if_invalid(encounter, grappler_id)`

并在这些链路里调用：

- `StartTurn`
- `UpdateConditions`
- HP / 移除实体后的关键结算点
- 移动开始前

核心原则：

- 只要一端无效，另一端的擒抱运行态也必须同步清理

## 九、`GetEncounterState` 投影

前端 / LLM 应能直接看出擒抱关系。

### 对被擒抱者

建议展示：

- `grappled`
- `来自 Eric 的 Grappled`

### 对擒抱者

建议展示：

- `正在擒抱 Goblin`

### 说明

- 不暴露内部 `escape_dc`
- 不暴露内部 `dc_breakdown`
- 只做可读摘要

## 十、LLM 调用规则

### 发起擒抱

当玩家表达：

- “我擒抱他”
- “我抓住这个兽人”

时：

1. 调 `use_grapple`
2. 传 `encounter_id / actor_id / target_id`
3. 不要自己手算 DC
4. 不要自己手算目标豁免

### 拖着走

当玩家表达：

- “我拖着他后退”
- “我抓着他往左移动”

时：

1. 直接调用正常移动 tool
2. 后端若检测到 `active_grapple`，自动按减半速度与拖行规则结算
3. 不要自己手动改两人的位置

### 挣脱

当玩家表达：

- “我挣脱”
- “我摆脱他的控制”

时：

1. 调 `escape_grapple`
2. 只传 `encounter_id / actor_id`
3. 后端自动判断来源、自动选更优检定并完成结算

## 十一、错误处理

若不满足前置校验，应返回结构化失败，而不是 transport error。

例如：

- 目标不在 5 尺内
- 目标体型过大
- 当前已有主动擒抱目标
- 不是当前行动者
- 已经使用过动作
- 当前并未处于受擒状态

LLM 读取失败原因后，应改口或改动作，而不是假装擒抱成功。

## 十二、后续扩展点

本次设计为后续保留这些自然扩展位：

- 推撞 `Shove`
- 多目标擒抱
- 严格空手校验
- 武僧擒抱 / 推撞完整联动
- 更多“失能导致自动释放”的统一收口点

## 总结

本次擒抱采用：

- `grappled:来源` condition 表示被擒抱状态
- `combat_flags["active_grapple"]` 表示主动维持关系
- 独立 `use_grapple` / `escape_grapple` 工具
- 移动链自动处理拖行与减半速度
- 目标自愿移动被禁止
- 来源失能或关系失效时自动释放
- 擒抱 DC 通过 helper 统一解析，并保留武僧敏捷替代扩展位

这是当前项目里最稳、最容易和既有 condition / movement / state projection 体系对接的实现方案。
