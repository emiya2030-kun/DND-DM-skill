# Damage Parts 多段伤害结算设计说明

## 目标

新增一套独立的多段伤害结算基础设施,用来支持:

- 武器自身多段伤害
- 法术自身多段伤害
- 暴击时所有骰子类伤害倍骰
- 不同伤害类型分别应用抗性 / 免疫 / 易伤

这期设计只覆盖:

- 一次命中
- 一次法术命中或豁免结算
- 在这次结算里立即生效的伤害段

明确不覆盖:

- 持续伤害
- 回合开始 / 回合结束伤害
- 区域停留伤害
- 延迟触发伤害
- `damage_modifiers`
- `Hex` / `Hunter's Mark`
- 直接改造 `execute_attack`

## 为什么要做

当前系统已经能"应用伤害",但还不能"结构化结算伤害组成".

现状是:

- 上层先算出一个总伤害值 `hp_change`
- 再调用 `UpdateHp`
- `UpdateHp` 负责扣血、临时生命、抗性 / 免疫 / 易伤、专注检定触发

这套方式足够处理单一伤害值,但一旦进入下面这些场景就会不够用:

- `1d8 piercing + 1d8 fire`
- 法术本体伤害 + 附加伤害
- 暴击时只倍骰,不倍固定值
- 同一次结算中不同伤害类型分别吃抗性

所以需要在 `UpdateHp` 之前增加一层"多段伤害结算器".

## 推荐方案

采用方案 A:

- 先做一个独立的多段伤害结算 service
- 先把伤害规则和测试做稳
- 暂时不直接接入 `execute_attack` 主流程

原因:

- 边界清楚
- 最适合单元测试
- 出问题时更容易定位
- 不会一次把攻击链和伤害链同时改复杂

## 范围

本期包含:

- `damage_part` 标准结构
- `ResolveDamageParts` service
- 逐段掷骰
- 暴击倍骰
- 逐段伤害类型修正
- 结构化 breakdown 输出

本期不包含:

- 运行时附伤效果收集
- 攻击链自动收集武器 / 法术的 `damage_parts`
- 前端展示伤害分解详情
- effect instance / target marker 设计

## 核心概念

### damage_part

单段伤害的最小结构:

```json
{
  "formula": "1d8+4",
  "damage_type": "piercing",
  "source": "weapon_base"
}
```

字段解释:

- `formula`
  - 原始伤害公式
  - 这期只要求支持当前项目里已经常见的掷骰表达式
- `damage_type`
  - 用于逐段应用抗性 / 免疫 / 易伤
- `source`
  - 用于日志、调试和后续区分伤害来源

### 为什么只保留这三个字段

因为这期只做基础设施,不做运行时附伤收集.

当前真正必须回答的问题只有三个:

1. 这段伤害掷什么
2. 它是什么类型
3. 它来自哪里

其他字段例如:

- `label`
- `crit_behavior`
- `applies_on`
- `target_scope`

都属于后续更复杂的 effect 层,本期先不引入.

## 暴击规则

本期直接固定采用当前 DND 规则前提:

- 只要是骰子类伤害,暴击时都倍骰
- 固定值不倍

例子:

- `1d8+4` 暴击后变成 `2d8+4`
- `2d6` 暴击后变成 `4d6`
- `1d8 fire` 暴击后变成 `2d8 fire`

这个规则放在结算器里统一处理,不在 `damage_part` 上重复写配置.

原因:

- 当前范围里没有必要给每一段伤害再写 `crit_rule`
- 数据层越简单,未来接主流程时越稳定

## 伤害类型修正规则

每一段伤害都独立应用目标的:

- `immunities`
- `resistances`
- `vulnerabilities`

逐段规则:

- 免疫:该段变 `0`
- 抗性:该段减半,向下取整
- 易伤:该段翻倍
- 抗性和易伤同时存在:互相抵消,按原值
- 没有 `damage_type`:该段不做属性修正

关键点:

- 修正是**逐段**做,不是先汇总再统一修正
- 这样才能正确支持不同类型混合伤害

## Service 设计

建议新增:

- `tools/services/combat/damage/resolve_damage_parts.py`
- `tools/services/combat/damage/__init__.py`

### ResolveDamageParts

职责:

- 接收一组 `damage_parts`
- 根据 `is_critical_hit` 决定是否倍骰
- 逐段掷骰
- 逐段应用抗性 / 免疫 / 易伤
- 返回完整 breakdown 和总伤害

建议输入:

```python
resolve_damage_parts(
    damage_parts: list[dict[str, object]],
    *,
    is_critical_hit: bool,
    resistances: list[str] | None = None,
    immunities: list[str] | None = None,
    vulnerabilities: list[str] | None = None,
)
```

说明:

- 当前先不直接传 `EncounterEntity`
- 只传结算真正需要的伤害 trait 数据
- 让这个 service 保持纯规则层,不绑 encounter 仓储

## 输出结构

建议输出:

```json
{
  "is_critical_hit": true,
  "parts": [
    {
      "source": "weapon_base",
      "formula": "1d8+4",
      "resolved_formula": "2d8+4",
      "damage_type": "piercing",
      "rolled_total": 11,
      "adjusted_total": 11,
      "adjustment_rule": "normal"
    },
    {
      "source": "weapon_bonus",
      "formula": "1d8",
      "resolved_formula": "2d8",
      "damage_type": "fire",
      "rolled_total": 7,
      "adjusted_total": 3,
      "adjustment_rule": "resistance"
    }
  ],
  "total_damage": 14
}
```

字段解释:

- `resolved_formula`
  - 暴击后实际用于掷骰的公式
- `rolled_total`
  - 掷骰后的原始结果
- `adjusted_total`
  - 吃完属性修正后的最终结果
- `adjustment_rule`
  - 解释该段为什么变化
- `total_damage`
  - 给 `UpdateHp` 或后续主流程直接使用

## 与现有系统的关系

当前系统关系建议保持为:

1. 未来攻击 / 法术入口负责收集 `damage_parts`
2. 调用 `ResolveDamageParts`
3. 取 `total_damage`
4. 再把结果交给 `UpdateHp`

也就是说:

- `ResolveDamageParts` 负责"算伤害"
- `UpdateHp` 负责"应用伤害"

这两层不要混.

## 为什么不直接改 UpdateHp

因为 `UpdateHp` 当前职责已经很明确:

- 临时生命
- 扣血 / 治疗
- 伤害类型修正
- 专注检定请求
- 事件日志

如果把多段掷骰、暴击倍骰、分段 breakdown 也塞进去,它会变成一层同时负责:

- 规则解析
- 数值结算
- 状态应用

职责会过重.

因此更合理的拆法是:

- `ResolveDamageParts`
- `UpdateHp`

前者纯结算,后者纯应用.

## 第一阶段测试要求

至少覆盖:

1. 单段普通伤害
2. 多段不同类型伤害
3. 暴击倍骰但不倍固定值
4. 抗性逐段减半
5. 免疫逐段归零
6. 易伤逐段翻倍
7. 同一次结算里不同段分别吃不同修正

建议新增测试文件:

- `test/test_resolve_damage_parts.py`

## 后续扩展方向

等第一期稳定后,再进入下一阶段:

- 把武器 / 法术的静态 `damage_parts` 接进攻击链
- 引入 `damage_modifiers`
- 支持 `Hex` / `Hunter's Mark`
- 让事件日志和前端展示 breakdown

但这些都不属于本期.

## 结论

这期的正确切入点不是直接改攻击主流程,而是先补一个独立、纯规则的多段伤害结算器.

它的职责很单纯:

- 输入一组 `damage_parts`
- 处理暴击
- 处理逐段抗性 / 免疫 / 易伤
- 输出总伤害和分段明细

这样等后面真正把武器附伤、法术附伤、`damage_modifiers` 接进来时,就有一层稳定的基础设施可复用.
