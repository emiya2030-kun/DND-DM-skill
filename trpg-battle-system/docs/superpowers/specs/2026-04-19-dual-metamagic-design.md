# 双超魔与已学超魔设计

日期: 2026-04-19

## 目标

为 `trpg-battle-system` 的术士超魔系统补上 2024 规则里的两块缺口:

- 默认情况下, 每次施法只能应用 1 个超魔法选项
- `Empowered Spell / 强效法术` 与 `Seeking Spell / 追踪法术` 可以作为例外, 与其他超魔同施法
- 当 `Sorcery Incarnate / 术法化身` 处于激活状态, 且术士等级至少 7 级时, 一次施法最多可应用 2 个超魔法选项
- 系统需要追踪术士当前已学会的超魔法选项, 而不是允许任意声明

本轮实现完成后, 术士施法应当具备:

- 已学超魔列表与可学数量上限
- 多超魔组合合法性校验
- 双超魔的总术法点消耗与回滚
- 现有攻击法术、豁免法术、伤害结算、持续时间链路对双超魔的兼容

## 非目标

本轮不做:

- 新增独立的“超魔施法”服务入口
- 角色升级时自动替换或重选超魔选项的 UI / 工具链
- 超过 2 个超魔同时作用于单次施法
- 将 `Sorcery Incarnate` 扩展为除“最多两个超魔”之外的其他新规则
- 对旧数据做一次性迁移脚本

## 规则边界

依据 2024 术士规则, 本轮采用以下边界:

- 2 级获得 `Metamagic / 超魔法` 后, 术士学会 2 个超魔选项
- 到达 10 级与 17 级术士时, 分别再多学会 2 个超魔选项
- 默认每次施法只能应用 1 个超魔
- `Empowered Spell` 可以与其他超魔叠加
- `Seeking Spell` 可以与其他超魔叠加
- 当 `innate_sorcery.active = true` 且术士等级至少 7 级时, 一次施法最多可应用 2 个超魔
- 即使在 `Sorcery Incarnate` 激活期间, 一次施法也不能超过 2 个超魔

### 组合合法性

按规则拆成 3 档:

1. `selected` 为空或只有 1 个选项: 合法
2. `selected` 有 2 个选项:
   - 若术士等级至少 7 且 `innate_sorcery.active = true`: 任意两项都可声明, 前提是各自法术前提满足
   - 否则只允许以下组合:
     - `empowered_spell + X`
     - `seeking_spell + X`
     - `empowered_spell + seeking_spell`
3. `selected` 超过 2 个选项: 直接报错

### 已学超魔

系统必须区分“规则支持的超魔”与“该术士已学会的超魔”:

- 规则支持列表是固定全集
- 已学列表来自术士运行态
- 未学会的超魔不可声明

兼容旧数据时:

- 若运行态显式提供 `known_options`, 严格按它校验
- 若旧数据没有 `known_options`, 运行态 helper 会补兼容结构
- 兼容补全仅用于避免旧存档和旧测试立即失效, 但新写入必须落标准结构

## 数据结构

### 术士运行态

在 `class_features.sorcerer` 下新增:

```json
{
  "metamagic": {
    "known_options": [
      "subtle_spell",
      "quickened_spell"
    ],
    "max_known_options": 2
  }
}
```

规则:

- `max_known_options` 由术士等级自动导出
  - 2-9 级: `2`
  - 10-16 级: `4`
  - 17+ 级: `6`
- `known_options` 为标准化后的字符串数组
- 运行态 helper 会去重、排序并剔除未知值
- 当旧数据缺失 `known_options` 时:
  - 若已有合法 `metamagic.known_options`, 原样保留
  - 若没有, helper 会补成空数组或兼容缺省结构

### 施法输入

继续沿用现有输入:

```json
{
  "metamagic_options": {
    "selected": ["quickened_spell", "heightened_spell"],
    "heightened_target_id": "ent_enemy_001"
  }
}
```

变化点:

- `selected` 现在允许 0-2 项
- 需要双超魔时, 参数仍然统一放在同一个对象里
- 各超魔附加字段继续沿用现有命名:
  - `heightened_target_id`
  - `careful_target_ids`
  - `transmuted_damage_type`

### 结构化超魔结果

继续返回统一 `metamagic`, 但语义改为“组合结果”, 例如:

```json
{
  "selected": ["quickened_spell", "heightened_spell"],
  "subtle_spell": false,
  "quickened_spell": true,
  "distant_spell": false,
  "heightened_spell": true,
  "careful_spell": false,
  "empowered_spell": false,
  "extended_spell": false,
  "seeking_spell": false,
  "transmuted_spell": false,
  "twinned_spell": false,
  "sorcery_point_cost": 4,
  "heightened_target_id": "ent_enemy_001",
  "careful_target_ids": [],
  "effective_range_override_feet": null,
  "transmuted_damage_type": null,
  "effective_target_scaling_bonus_levels": 0
}
```

要求:

- 布尔字段继续保留, 以兼容现有下游逻辑
- `selected` 是标准化后的最终列表
- `sorcery_point_cost` 为总消耗, 不再是假定单选

## 架构策略

本轮不再让 `SpellRequest` 与 `EncounterCastSpell` 各自维护一份多超魔校验规则。

采用一个共享超魔解析器:

- 输入:
  - 术士实体
  - 已知法术
  - 法术定义
  - 当前动作成本
  - 法术目标
  - `metamagic_options`
  - 当前是否处于 `innate_sorcery.active`
- 输出:
  - 结构化 `metamagic`
  - `noticeability`
  - 明确错误码 / 错误消息

共享解析器负责:

1. 标准化 `selected`
2. 校验已学超魔
3. 校验组合合法性
4. 分别校验每个超魔的法术前提
5. 汇总总术法点消耗
6. 生成结构化 `metamagic`

这样可以避免:

- `SpellRequest` 允许但 `EncounterCastSpell` 拒绝
- 两处同时遗漏 `Empowered` / `Seeking` 例外
- 双超魔总消耗在一处按 1 点算, 另一处按总和算

## 链路改动

### 1. 术士运行态初始化

更新术士运行态 helper:

- 计算 `metamagic.max_known_options`
- 标准化 `known_options`
- 保证 `innate_sorcery` 与 `metamagic` 结构同时存在

### 2. SpellRequest

`SpellRequest` 继续作为施法声明期事实源。

改动:

- 删除“长度大于 1 直接报错”的旧逻辑
- 使用共享超魔解析器
- 在返回结果里写入多选后的 `metamagic`
- 对双超魔返回总术法点消耗

新增错误码:

- `too_many_metamagic_options`
- `metamagic_not_known`
- `metamagic_combination_not_allowed`
- `multiple_metamagic_requires_sorcery_incarnate`
- `multiple_metamagic_requires_sorcerer_level_7`

保留已有错误码:

- `heightened_spell_requires_target`
- `careful_spell_too_many_targets`
- `invalid_transmuted_damage_type`
- 其他单个超魔前提错误

### 3. EncounterCastSpell

改动:

- 改为消费共享超魔解析结果
- 一次性扣除总术法点
- 若事件写入失败, 一次性回滚总术法点
- `quickened_spell` 仍改动作经济
- `noticeability` 仍由 `subtle_spell` 决定

### 4. ExecuteSpell

保持现有思路:

- 继续通过布尔字段消费:
  - `seeking_spell`
  - `empowered_spell`
  - `transmuted_spell`
- 不要求了解“这是第一个超魔还是第二个超魔”

### 5. SavingThrowRequest

保持现有消费方式:

- 读取 `heightened_spell`
- 读取 `careful_spell`
- `selected` 允许有两个值, 但下游主要还是靠布尔字段工作

### 6. SavingThrowResult

保持现有处理:

- `careful_spell` 仍把“成功半伤”改为 `0`
- 若同时存在其他超魔, 不影响这一判定

### 7. 持续时间与专注

`extended_spell` 当前行为维持:

- 将法术实例记为默认持续到长休
- 若法术需要专注, 则对应专注检定具有优势

本轮不把它扩到真正的全局持续时间翻倍系统, 因为当前仓库尚无完整长休自动清算。

## 组合示例

### 默认合法

```json
{
  "metamagic_options": {
    "selected": ["empowered_spell", "heightened_spell"],
    "heightened_target_id": "ent_enemy_001"
  }
}
```

原因:

- `Empowered` 明确允许与其他超魔叠加

### 默认非法

```json
{
  "metamagic_options": {
    "selected": ["quickened_spell", "heightened_spell"],
    "heightened_target_id": "ent_enemy_001"
  }
}
```

原因:

- 这组双超魔只有在 `Sorcery Incarnate` 激活且术士等级至少 7 级时才允许

### 术法化身激活时合法

```json
{
  "metamagic_options": {
    "selected": ["quickened_spell", "heightened_spell"],
    "heightened_target_id": "ent_enemy_001"
  }
}
```

前提:

- `class_features.sorcerer.level >= 7`
- `class_features.sorcerer.innate_sorcery.active = true`

## 测试要求

至少补以下测试:

### 声明期

- 默认单超魔仍通过
- 非 `innate_sorcery.active`:
  - `empowered + subtle` 通过
  - `seeking + quickened` 通过
  - `quickened + heightened` 拒绝
- `innate_sorcery.active` 且 7 级:
  - `quickened + heightened` 通过
  - `distant + transmuted` 通过
- 3 个超魔同时声明时报错
- 未学会超魔时报错

### 施法执行

- 双超魔总术法点正确扣除
- 事件写入失败时总术法点正确回滚
- `quickened + heightened` 同时作用:
  - 动作改为附赠动作
  - 目标豁免劣势
- `subtle + twinned` 同时作用:
  - `noticeability` 更新
  - 目标扩展生效

### 结果链

- `empowered + heightened`:
  - 豁免目标劣势
  - 伤害重骰生效
- `seeking + transmuted`:
  - 攻击未命中后自动重骰
  - 命中后伤害类型改写
- `careful + extended`:
  - 受保护目标 0 伤害
  - 法术实例记录延效

## 风险与约束

风险点:

- 现有 `SpellRequest` 与 `EncounterCastSpell` 各自持有一套解析逻辑, 极易出现行为分叉
- 双超魔引入总消耗后, 术法点扣减与回滚最容易写错
- 旧测试与旧数据可能没有 `known_options`

对应策略:

- 提取共享超魔解析 helper
- 总消耗统一集中计算
- 旧数据读取时自动补运行态结构, 新写入统一落标准结构

## 实现顺序

1. 术士运行态补 `metamagic.known_options` 与 `max_known_options`
2. 抽共享多超魔解析 helper
3. 改 `SpellRequest`
4. 改 `EncounterCastSpell`
5. 校正 `ExecuteSpell` / `SavingThrowRequest` / `SavingThrowResult` 的多超魔消费
6. 补单测与回归

## 结论

本轮采用“规则完整 + 最小侵入现有链路”的方案:

- 追踪已学超魔
- 默认单超魔
- `Empowered` / `Seeking` 作为通用叠加例外
- `Sorcery Incarnate` 激活时开放任意双超魔
- 上限始终 2
- 不新增独立施法入口

这样能在不重做整个施法系统的前提下, 把 2024 双超魔规则完整接入现有主链。
