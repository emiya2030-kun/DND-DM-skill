# 护甲受训与盾牌接入战斗运行时设计

## 目标

把护甲和盾牌像武器一样接入战斗系统，覆盖当前战斗内真正会影响结算的部分：

- 静态护甲/盾牌知识库
- entity 运行时装备字段
- 战士自动护甲受训
- 基础 AC 自动重算
- 力量不达标的速度惩罚
- 未受训护甲对力量/敏捷 D20 检定的劣势
- 未受训护甲禁止施法
- 盾牌只有受训时才给 AC
- 同时只能一套护甲、一面盾牌
- `GetEncounterState` 对外投影这些信息

本轮不做：

- 护甲穿脱时长
- 盾牌占手与更细持物系统
- 全通用能力检定链
- 潜行检定真正结算，只先投影“隐匿劣势来源”

## 现状问题

当前系统只有 `entity.ac` 这个最终值，没有“AC 来源”。武器已经有知识库 + repository + runtime 合并链，但护甲还是手写死值，导致：

- AC 不能从装备自动算
- 盾牌术等临时 AC 加值和基础 AC 没有清晰边界
- 职业护甲受训无法真正进入规则结算
- 未受训护甲的攻击/豁免/施法限制无处落地

## 设计总览

这轮采用“静态模板 + 运行时解析 + 写回最终值”的方式，不把 `entity.ac` 改成动态属性。

### 1. 静态知识库

新增 `data/knowledge/armor_definitions.json`，只保留战斗规则字段：

- `armor_id`
- `name`
- `category`
  - `light` / `medium` / `heavy` / `shield`
- `ac`
  - 护甲：基础 AC 与敏捷上限规则
  - 盾牌：`bonus`
- `strength_requirement`
- `stealth_disadvantage`

不保存价格、重量、穿脱时间。

### 2. Entity 运行时字段

`EncounterEntity` 新增：

- `equipped_armor: dict[str, Any] | None`
- `equipped_shield: dict[str, Any] | None`

运行时装备结构只保留最小字段：

- `armor_id`
- 可选展示名覆盖
- 可选显式受训覆盖

护甲和盾牌继续允许 entity 写最少信息，具体战斗规则由 repository + resolver 补全。

### 3. 护甲解析器

新增集中规则模块，职责是：

- 读取护甲/盾牌模板
- 解析 actor 的护甲受训
- 计算基础 AC
- 判断盾牌 AC 是否生效
- 计算力量需求导致的速度惩罚
- 标记是否存在隐匿劣势来源
- 标记未受训护甲状态

这里不直接处理临时 AC 改写。护盾术仍然继续在最终 AC 上叠加 +5，并在回合开始移除。

### 4. 规则落点

#### 攻击链

`AttackRollRequest` 在生成 request 时读取护甲解析结果：

- 如果 actor 穿着未受训护甲，且这次攻击使用 `str` 或 `dex`，则加入 `armor_untrained` 劣势来源
- 其余逻辑不变

#### 豁免链

`SavingThrowRequest` 在生成 request 时读取目标护甲解析结果：

- 如果目标穿着未受训护甲，且豁免属性是 `str` 或 `dex`，则 `context.vantage` 变为 `disadvantage`
- 同时记录劣势来源，给后续日志和前端使用

#### 施法链

`EncounterCastSpell` 在声明施法时先检查护甲解析结果：

- 如果 caster 穿着未受训护甲，则直接抛错 `armor_training_required_for_spellcasting`

### 5. AC 与速度更新

提供统一刷新函数，在以下时机写回实体：

- 初始化/读取测试实体时显式调用
- `GetEncounterState` 投影前兜底刷新
- 未来装备变更 service 复用

刷新结果：

- `entity.ac = 基础护甲 AC + 受训盾牌 AC + 现有临时 AC 修正之前的基础值`
- `speed.walk` 不直接被改写
- 速度惩罚通过状态投影给出 `effective_speed`

为了避免和护盾术冲突，这轮不重写“临时 AC bonus 的存储方式”。基础 AC 刷新只负责“无临时加成时应有的 AC”，护盾术继续在当前值上加减。

实现上采用：

- 先从护甲解析器得到 `base_ac`
- 如果实体身上有 `shield_ac_bonus` 这类 turn effect，不在刷新函数里重复计算
- 视图层单独投影 `base_ac`、`current_ac`、`shield_bonus_active`

## 受训来源

先支持两层来源：

1. 显式配置
   - `class_features.<class>.armor_training`
2. 职业自动绑定
   - fighter 自动获得 `["light", "medium", "heavy", "shield"]`

这保证后续别的职业可以沿同一结构扩展。

## 对外投影

`GetEncounterState` 新增护甲相关视图：

- 当前角色卡与先攻列表都能看到：
  - `armor`
  - `shield`
  - `armor_training`
  - `ac_breakdown`
  - `speed_penalty_feet`
  - `effective_speed`
  - `stealth_disadvantage_sources`
  - `untrained_armor_penalties`

其中：

- `ac_breakdown.base_armor_ac`
- `ac_breakdown.shield_bonus`
- `ac_breakdown.current_ac`
- `ac_breakdown.shield_spell_bonus_active`

## 错误语义

- 非法施法：`armor_training_required_for_spellcasting`
- 装备多套护甲：模型层拒绝
- 多面盾牌：模型层拒绝
- 缺失模板：如果运行时装备引用了不存在的 `armor_id`，直接抛错

## 测试策略

优先覆盖：

1. repository 能读取护甲知识库
2. 护甲解析器能正确算 AC、速度惩罚、隐匿劣势、未受训状态
3. 战士自动获得护甲/盾牌受训
4. 攻击检定受未受训护甲影响
5. 豁免检定受未受训护甲影响
6. 未受训护甲禁止施法
7. `GetEncounterState` 能正确投影

## 风险与规避

### 风险 1：和护盾术 AC 加减冲突

规避：保留 `entity.ac` 为最终值，不把全部 AC 动态化；基础护甲解析和临时 AC bonus 分层处理。

### 风险 2：测试里很多实体只写死 `ac`

规避：护甲字段为空时，继续兼容旧实体，`ac` 保持原样。

### 风险 3：未受训护甲的“所有力量/敏捷 D20 检定劣势”目前没有通用检定链

规避：本轮先覆盖攻击检定和豁免检定；能力检定链以后直接复用同一解析结果。
