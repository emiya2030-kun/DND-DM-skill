# 属性检定能力链设计

日期：2026-04-17

## 目标

为 `trpg-battle-system` 增加一条独立的“属性检定 / 技能检定”能力链，用于同时支持：

- 战斗内的属性或技能检定
- 战斗外的属性或技能检定
- LLM 高层几乎自动调用
- 后端独立完成掷骰、修正值、优势劣势、DC 成败判断

本次目标是做“最小可用第一版”。

本次只覆盖：

- 单个实体的属性检定
- 单个实体的技能检定
- 明确 DC 的标准 d20 检定
- encounter 内实体
- 高层执行入口 + 底层 request / resolve / result 分层

本次明确不覆盖：

- 对抗检定
- 被动值
- 秘密检定
- 玩家自然语言自动解析
- 复杂职业特性对检定的改写

## 设计原则

### 1. 玩家自然语言由 LLM 理解，tool 不做语义解析

玩家可能会说：

- “我想偷偷绕过去”
- “我看看周围有没有埋伏”
- “我试着把门撞开”

这些话如何理解成“隐匿 / 察觉 / 力量检定”，由 LLM 自己负责。

新 tool 不负责解析原话，不引入一层脆弱的自然语言识别。

tool 只负责接受**已经被 LLM 解释后的检定声明**。

### 2. tool 接受中文 / 英文别名，后端统一标准化

虽然 tool 不负责解析自然语言，但它应该尽量降低 LLM 的调用负担。

因此第一版允许 LLM 传入中文或英文别名，例如：

- `隐匿`
- `stealth`
- `潜行`

后端会统一归一成标准内部 key：

- `stealth`

这样做能兼顾：

- LLM 调用方便
- 后端规则结构统一
- 未来扩展时不需要处理多套内部字段

### 3. 对 LLM 暴露一个高层入口，内部仍保持分层

LLM 不应该每次手动串：

- 生成 request
- 处理 d20
- 结算 final total
- 比较 DC

因此对外新增一个高层入口：

- `ExecuteAbilityCheck`

但内部仍保持和攻击 / 豁免一致的分层结构：

- `AbilityCheckRequest`
- `ResolveAbilityCheck`
- `AbilityCheckResult`
- `ExecuteAbilityCheck`

这样可以同时满足：

- LLM 高层调用简单
- 后端结构稳定
- 以后扩展对抗检定或秘密检定时不需要推翻第一版

### 4. 第一版必须显式传入 DC

本次不做“只掷骰不判定成功失败”的松散模式。

第一版要求 LLM 显式传入：

- `dc`

后端直接返回：

- `final_total`
- `success`
- `failed`
- `comparison`

这样能保证：

- tool 返回的是完整结构化规则结果
- LLM 不需要再自己比较总值与 DC
- 战斗内外都能稳定复用

## 一、服务结构

### 新增服务

- `tools/services/checks/ability_check_request.py`
- `tools/services/checks/resolve_ability_check.py`
- `tools/services/checks/ability_check_result.py`
- `tools/services/checks/execute_ability_check.py`

### 职责划分

#### AbilityCheckRequest

负责：

- 校验 actor 是否存在于 encounter
- 校验 `check_type`
- 校验 `check`
- 校验 `dc`
- 进行别名标准化
- 组装 `RollRequest`

输出仍然使用现有 `RollRequest` 模型。

#### ResolveAbilityCheck

负责：

- 处理 d20 原始点数
- 处理优势 / 劣势
- 读取属性调整值
- 读取技能修正或熟练逻辑
- 处理力竭惩罚
- 输出 `RollResult`

#### AbilityCheckResult

负责：

- 比较 `final_total` 与 `dc`
- 生成 `success / failed`
- 追加事件
- 返回结构化比较结果

#### ExecuteAbilityCheck

负责：

- 串起 request / resolve / result
- 支持后端自动掷骰
- 选择性返回最新 `encounter_state`

这将是 LLM 主要调用的入口。

## 二、调用接口设计

### 对外高层入口

第一版新增：

- `ExecuteAbilityCheck.execute(...)`

建议输入参数：

- `encounter_id`
- `actor_id`
- `check_type`
  - `ability`
  - `skill`
- `check`
  - 支持标准 key 和中英别名
- `dc`
  - 必填
- `vantage`
  - `normal`
  - `advantage`
  - `disadvantage`
- `additional_bonus`
  - 可选
- `reason`
  - 可选
- `include_encounter_state`
  - 可选

### 典型调用

例如：

- 萨布尔做一次隐匿检定，DC 15
- 米伦做一次察觉检定，DC 13
- 某角色做一次力量检定推门，DC 12

LLM 只需要自己先理解玩家原话，然后把结果标准化后传入这个入口。

### 为什么不让 tool 直接吃玩家原话

原因有三个：

1. 语义理解本来就属于 LLM 的强项
2. 把自然语言解析塞进 tool 会让规则边界模糊
3. 后端应该只做可验证、可测试的规则处理，而不是做弱 NLP

## 三、标准化规则

### 属性标准化

第一版支持以下属性别名归一：

- `力量` / `str` / `strength` -> `str`
- `敏捷` / `dex` / `dexterity` -> `dex`
- `体质` / `con` / `constitution` -> `con`
- `智力` / `int` / `intelligence` -> `int`
- `感知` / `wis` / `wisdom` -> `wis`
- `魅力` / `cha` / `charisma` -> `cha`

### 技能标准化

第一版支持现有 DND 常见技能的中英别名归一，内部统一成标准 key，例如：

- `运动` / `athletics` -> `athletics`
- `隐匿` / `潜行` / `stealth` -> `stealth`
- `察觉` / `perception` -> `perception`
- `特技` / `acrobatics` -> `acrobatics`
- `驯兽` / `animal handling` -> `animal_handling`
- `奥秘` / `arcana` -> `arcana`
- `历史` / `history` -> `history`
- `洞悉` / `insight` -> `insight`
- `威吓` / `intimidation` -> `intimidation`
- `调查` / `investigation` -> `investigation`
- `医药` / `medicine` -> `medicine`
- `自然` / `nature` -> `nature`
- `宗教` / `religion` -> `religion`
- `求生` / `survival` -> `survival`
- `游说` / `persuasion` -> `persuasion`
- `欺瞒` / `deception` -> `deception`
- `表演` / `performance` -> `performance`
- `巧手` / `sleight_of_hand` / `sleight of hand` -> `sleight_of_hand`

### 错误策略

若 LLM 传入未知检定名称，后端应直接报错：

- `unknown_ability_check`
- `unknown_skill_check`

不做模糊匹配，不在后端猜测。

## 四、结算规则

### 共同规则

属性检定与技能检定都走 d20 主链：

- 原始 d20
- 优势 / 劣势
- 检定加值
- 力竭惩罚

最终得到：

- `final_total`

### 属性检定

属性检定的加值为：

- 对应属性调整值
- 再加 `additional_bonus`

第一版不加熟练。

### 技能检定

技能检定优先读取实体已有的：

- `skill_modifiers[skill]`

若存在且是整数，则直接使用它作为该技能基础修正值。

若不存在，则退回为：

- 该技能对应属性调整值
- 若实体对该技能熟练，再加熟练加值

其中技能对应属性映射在后端固定表中维护。

### 优势 / 劣势

第一版只处理显式传入的：

- `normal`
- `advantage`
- `disadvantage`

不自动从太多职业特性中推导额外优势来源。

### 力竭惩罚

沿用现有 condition runtime：

- `exhaustion:n`

对应的 d20 惩罚继续生效。

### 自动失败

第一版不引入“属性检定自动失败”的额外规则。

也就是说：

- 只要是属性检定或技能检定
- 都不会因为特定 condition 自动变成 0

这和豁免不同。

## 五、结果结构

### RollResult

底层仍然复用现有 `RollResult`。

新增允许的 `roll_type`：

- `ability_check`

### AbilityCheckResult 输出

建议输出结构包括：

- `encounter_id`
- `actor_id`
- `check_type`
- `check`
- `normalized_check`
- `dc`
- `final_total`
- `success`
- `failed`
- `comparison`
- `vantage`
- `chosen_roll`
- `bonus_breakdown`
- `event_id`

其中 `comparison` 风格应和现有 saving throw 结果一致，例如：

- 左值：`ability_check_total`
- 右值：`dc`
- 比较符：`>=`

### 事件日志

第一版新增事件类型建议为：

- `ability_check_resolved`

payload 至少包含：

- 谁在检定
- 检定类型
- 检定项
- DC
- 最终总值
- 是否成功

## 六、战斗内外的适用方式

### 战斗内

战斗内允许任意实体发起属性检定或技能检定。

第一版不强行要求：

- 必须是当前行动者

因为很多检定本质上是叙事 / 环境交互，而不是标准攻击动作。

如果未来需要更严的战斗内动作经济约束，可以在高层入口追加一个：

- 是否消耗动作
- 是否校验当前行动者

但第一版不加。

### 战斗外

战斗外也通过当前 encounter 执行。

也就是说：

- 只要 actor 在 encounter 中存在
- 就可以执行属性检定或技能检定

这样无需另起一套“非战斗检定系统”。

## 七、LLM 调用约束

为了满足“几乎自动调用”的目标，给 LLM 的约束应该是：

1. 先理解玩家原话是在要求什么检定
2. 再把检定标准化为 `ability` 或 `skill`
3. 显式传入 `dc`
4. 优势 / 劣势若有规则来源，则显式传入
5. 一般直接调用 `ExecuteAbilityCheck`

LLM 不应该：

- 自己手动掷 d20
- 自己手动算属性调整值
- 自己手动比较 `final_total` 与 `dc`

这些都应该由后端完成。

## 八、为什么现在不做对抗检定

对抗检定虽然和属性检定相近，但它天然多出：

- 双 actor
- 双请求
- 双结果
- 比较规则
- ties 处理

如果在第一版一起做，会明显拉大范围。

因此更合理的路径是：

1. 先把单人属性 / 技能检定链做稳定
2. 再在下一轮扩展：
   - contest request
   - contest resolve
   - contest result

## 九、测试要求

第一版至少应覆盖：

1. 属性检定 request 构造
2. 技能检定 request 构造
3. 中文 / 英文别名标准化
4. 优势检定
5. 劣势检定
6. 技能修正优先于属性推导
7. 无 `skill_modifier` 时按属性 + 熟练推导
8. 力竭惩罚
9. `ExecuteAbilityCheck` 全链路
10. `include_encounter_state` 投影
11. 非法 `check_type`
12. 非法 `check`
13. 缺失 `dc`

## 十、第一版之后的自然扩展

第一版完成后，最自然的扩展顺序是：

1. 对抗检定
2. 被动值
3. 秘密检定
4. 更复杂的职业特性改写
5. 更高层的 LLM 调用规范文档
