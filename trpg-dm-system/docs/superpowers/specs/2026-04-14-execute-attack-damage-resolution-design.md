# Execute Attack Damage Resolution 设计说明

## 目标

把 `execute_attack` 从“外部手传总伤害值 `hp_change`”推进到“系统内部按结构化伤害段结算”。

这次设计要求：

- 继续保留当前攻击命中判定主链路
- 命中后由系统从武器定义生成 `damage_parts`
- 外部按 `source` 提供对应的 `damage_rolls`
- 系统调用 `ResolveDamageParts` 结算多段伤害
- 系统再把 `total_damage` 交给 `UpdateHp`
- 返回结构化 `damage_resolution` 给 LLM，支持 RP 描述

这次只覆盖：

- 武器攻击
- 一次命中后的立即伤害
- 暴击倍骰
- 抗性 / 免疫 / 易伤

明确不覆盖：

- 法术伤害
- `Hex` / `Hunter's Mark`
- 运行时附伤效果收集
- 持续伤害 / 区域伤害 / 延迟伤害

## 为什么要做

当前 `execute_attack` 还是这套模式：

1. 外部先判定攻击掷骰
2. 外部自己算出一个 `hp_change`
3. 再把这个总值传回系统扣血

这会带来三个问题：

- 系统不知道伤害是怎么组成的，LLM 也拿不到可描述的 breakdown
- 多段伤害、暴击倍骰、不同类型抗性无法稳定统一处理
- 一旦来源复杂起来，上层容易“看起来能跑，实际算错”

所以需要把“攻击后的伤害结算”收回系统内部。

## 方案比较

### 方案 A：继续手传 `hp_change`

优点：

- 改动最小
- 现有接口几乎不用动

缺点：

- 系统看不到伤害构成
- LLM 无法可靠拿到逐段伤害信息
- 多段伤害与暴击规则仍然分散在外部

结论：

- 不推荐

### 方案 B：传 `damage_rolls`，由系统生成 `damage_parts` 并完成结算

优点：

- 系统重新掌握伤害规则主导权
- LLM 可以拿到结构化 breakdown
- 能平滑接入已完成的 `ResolveDamageParts`
- 后续扩展法术和附伤时不需要推倒重来

缺点：

- `execute_attack` 接口需要改造
- 需要补一层武器数据到 `damage_parts` 的映射

结论：

- 推荐

### 方案 C：外部直接传完整 `damage_parts`

优点：

- `execute_attack` 内部逻辑更薄
- 理论上最灵活

缺点：

- 把系统已有武器定义绕开了
- 上层更容易构造出与武器不一致的数据
- 会把知识库实例化问题提前暴露出来

结论：

- 当前阶段不推荐

## 推荐方案

采用方案 B：

- `execute_attack` 继续负责完整攻击编排
- 武器定义仍然是伤害段的事实来源
- 外部只需要按 `source` 传对应的伤害骰值
- 系统内部生成 `damage_parts`
- 系统内部调用 `ResolveDamageParts`
- 再把 `damage_resolution.total_damage` 传给 `UpdateHp`

这样可以同时满足两件事：

- 规则校验留在系统内
- LLM 拿到可叙述的结构化伤害结果

## 数据来源与边界

### 现有武器数据

当前武器结构已经足够支撑这一轮：

```json
{
  "weapon_id": "rapier",
  "name": "Rapier",
  "damage": [
    {"formula": "1d8+3", "type": "piercing"}
  ]
}
```

本轮不改武器知识库字段名，不新增复杂 effect 层字段。

### 内部 damage_parts 结构

`execute_attack` 命中后，从武器 `damage` 列表生成内部 `damage_parts`：

```json
[
  {
    "source": "weapon:rapier:part_0",
    "formula": "1d8+3",
    "damage_type": "piercing"
  }
]
```

如果武器有多段伤害，例如：

```json
{
  "weapon_id": "infernal_rapier",
  "damage": [
    {"formula": "1d8+3", "type": "piercing"},
    {"formula": "1d8", "type": "fire"}
  ]
}
```

则生成：

```json
[
  {
    "source": "weapon:infernal_rapier:part_0",
    "formula": "1d8+3",
    "damage_type": "piercing"
  },
  {
    "source": "weapon:infernal_rapier:part_1",
    "formula": "1d8",
    "damage_type": "fire"
  }
]
```

### 为什么 `source` 要系统生成

原因：

- 保证与武器定义一一对应
- 保证测试和 LLM 调用时都有稳定键名
- 后续加入命中附伤时，可以继续往同一命名体系扩展

## ExecuteAttack 新接口

### 输入

保留现有攻击判定相关输入：

- `encounter_id`
- `target_id`
- `weapon_id`
- `final_total`
- `dice_rolls`
- `vantage`
- `description`

伤害输入改为：

```json
{
  "damage_rolls": [
    {
      "source": "weapon:infernal_rapier:part_0",
      "rolls": [6, 3]
    },
    {
      "source": "weapon:infernal_rapier:part_1",
      "rolls": [5, 2]
    }
  ]
}
```

说明：

- `source` 必须对应系统生成的某一段 `damage_part`
- `rolls` 只放该段实际骰出的每颗骰子结果
- 暴击时，骰子数量增加；固定值不在 `rolls` 里重复传

### 移除的输入

新主流程不再依赖：

- `hp_change`
- `damage_reason`
- `damage_type`

其中：

- `damage_reason` 可以改由系统基于武器名或攻击名自动生成
- `damage_type` 不需要单独传，因为逐段类型来自 `damage_parts`

## 执行流程

推荐 `execute_attack` 内部固定为：

1. 用 `AttackRollRequest` 生成攻击请求
2. 用 `AttackRollResult` 判定是否命中、是否暴击
3. 如果未命中：
   - 直接返回攻击结果
   - 不结算伤害
   - 不调用 `UpdateHp`
4. 如果命中：
   - 从武器定义生成 `damage_parts`
   - 校验 `damage_rolls` 与 `damage_parts.source` 是否完全匹配
   - 读取目标的 `resistances` / `immunities` / `vulnerabilities`
   - 调用 `ResolveDamageParts`
   - 把 `damage_resolution.total_damage` 交给 `UpdateHp`
   - 把完整 `damage_resolution` 一并写回返回结果

这个顺序保证：

- 命中判定职责不变
- 伤害规则集中在 `ResolveDamageParts`
- HP 变动仍然统一走 `UpdateHp`

## 返回结构

推荐把伤害结果挂在 `resolution.damage_resolution` 下：

```json
{
  "resolution": {
    "hit": true,
    "is_critical_hit": true,
    "damage_resolution": {
      "is_critical_hit": true,
      "parts": [
        {
          "source": "weapon:infernal_rapier:part_0",
          "formula": "1d8+3",
          "resolved_formula": "2d8+3",
          "damage_type": "piercing",
          "rolled_total": 12,
          "adjusted_total": 12,
          "adjustment_rule": "normal"
        },
        {
          "source": "weapon:infernal_rapier:part_1",
          "formula": "1d8",
          "resolved_formula": "2d8",
          "damage_type": "fire",
          "rolled_total": 7,
          "adjusted_total": 3,
          "adjustment_rule": "resistance"
        }
      ],
      "total_damage": 15
    },
    "hp_update": {
      "...": "..."
    }
  }
}
```

### 为什么保留两层结构

因为：

- `resolution` 表示“这次攻击结果”
- `damage_resolution` 表示“命中后伤害如何结算”

这样后续扩法术、豁免、半伤时，结构仍然清楚，不会把“命中判定结果”和“伤害拆解结果”揉成一层。

同时，LLM 也能直接拿来做 RP：

- 是否命中
- 是否暴击
- 每段伤害是什么
- 哪段被抗性 / 免疫 / 易伤修改了
- 最终总伤害是多少

## 关于 `needs_damage_roll`

当前 `AttackRollResult` 里已有 `needs_damage_roll` 字段。

它的原始含义是：

- 这次攻击命中了
- 但流程还停在“等待下一步掷伤害骰”

在新的 `execute_attack` 完整链路里，这个字段不再是核心判断依据。

因为：

- 新主流程会在一次调用里直接完成命中与伤害结算
- 不再依赖这个字段提示外部“下一步该掷伤害”

结论：

- 可以在低层保留该字段，兼容旧流程或调试用途
- 新主流程不应依赖它驱动逻辑

## 严格校验规则

这一轮采用严格校验，不做静默兜底。

### 必须报错的情况

- 武器不存在
- 武器没有 `damage`
- 生成后的 `damage_parts` 为空
- `damage_rolls` 缺少某个应有的 `source`
- `damage_rolls` 多出未知 `source`
- `damage_rolls` 中同一 `source` 重复出现
- 某一段 `rolls` 数量与该段实际骰子数量不匹配
- 某个骰值非法

### 可以宽松处理的情况

如果攻击未命中，即使外部同时传了 `damage_rolls`：

- 系统可以直接忽略
- 不进入伤害结算
- 不因此让整次攻击失败

原因：

- 未命中时本来就不会消费伤害结果
- 允许上层先准备好完整调用包，不需要为了未命中再重发一次不同结构

## 错误信息原则

错误应尽量可直接用于 LLM 自我修正。

推荐优先做到：

- 能区分“缺失 source”与“未知 source”
- 能指出冲突的具体 `source`
- 能指出是哪一段骰子数量不对

不要求这轮先做非常复杂的错误对象，但至少不要只返回笼统的 `ValueError` 文本。

## 测试范围

本轮只补武器攻击链测试，不扩法术链。

至少覆盖：

- 命中时会从武器生成 `damage_parts`
- 命中时会按 `source` 调用 `ResolveDamageParts`
- `damage_resolution.total_damage` 会被传给 `UpdateHp`
- 返回里保留完整 `damage_resolution`
- 暴击时 `resolved_formula` 正确翻倍
- 目标有抗性时，逐段结果和总伤害正确
- 缺少 `source` / 多余 `source` / 重复 `source` 时会报错
- 未命中时不结算伤害，也不扣血

## 与后续系统的关系

这次设计是“攻击命中后结构化伤害结算”的中间层。

后续可以在此基础上继续接入：

- 法术攻击伤害
- 豁免型法术伤害
- 命中触发的运行时附伤
- 更细的叙事日志与前端展示

但这一轮不提前引入这些复杂度。

## 实施建议

实现顺序建议：

1. 先给 `execute_attack` 写红灯测试
2. 先接最小武器单段伤害
3. 再接多段伤害
4. 再接暴击与抗性
5. 最后删掉旧测试里对 `hp_change` 的主路径依赖

这样能保证迁移过程始终可验证。
