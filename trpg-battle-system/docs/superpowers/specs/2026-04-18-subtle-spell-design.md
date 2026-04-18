# Subtle Spell Design

日期：2026-04-18

## 目标

为 `Subtle Spell / 精妙法术` 增加第一版稳定实现，满足两个核心目标：

- 战斗层：精妙施法的法术不会触发 `Counterspell / 反制法术`
- 剧情层：LLM 能明确知道“施法动作本身不可被察觉”，但法术效果本身仍可能可见

本设计刻意收窄，不在这一轮实现完整超魔系统，只实现精妙法术这一项。

## 范围

### 本轮包含

- 为施法入口增加超魔声明参数
- 为 `Subtle Spell / 精妙法术` 扣除 1 点术法点
- 为本次施法写入“不可察觉施法声明”标记
- 反应收集层跳过 `counterspell`
- 在返回结果中加入 LLM 可读的可见性字段

### 本轮不包含

- 其他超魔选项
- 完整的“施法可见性系统”
- 对所有反应模板统一做“不可察觉施法”兼容
- 非战斗期的观察/察觉判定自动解析

## 设计原则

- 只给当前最需要的规则开口，不一次性铺满整个超魔框架
- 接口形态从一开始就兼容未来更多超魔
- 战斗规则与叙事提示分开：
  - 战斗规则由后端强制执行
  - 剧情提示通过结构化字段交给 LLM

## 对外接口

在施法相关入口增加可选参数：

```python
metamagic_options={
  "selected": ["subtle_spell"]
}
```

### 设计原因

不使用单独的 `subtle_spell=true`，而使用通用列表结构，原因是未来其他超魔仍可复用同一个入口。

### 当前约束

- 本轮只识别 `subtle_spell`
- 一次施法最多允许传一个当前已实现的超魔
- 若传入未知超魔，直接报错

## 资源与校验

### 前置条件

施法者必须：

- 具有 `sorcerer` 职业等级至少 2
- 具有可用术法点至少 1

否则报错：

- `metamagic_not_available`
- `insufficient_sorcery_points`

### 资源消耗

- 精妙法术消耗 1 点术法点
- 消耗发生在施法声明成功时
- 若后续由于反应或其他异常导致施法整体回滚，则术法点也必须一并回滚

## 运行态与声明态

本轮不要求把“本次施法使用了精妙法术”写入角色长期运行态。

改为写入**本次施法上下文**：

```json
{
  "metamagic": {
    "selected": ["subtle_spell"],
    "subtle_spell": true
  },
  "noticeability": {
    "casting_is_perceptible": false,
    "verbal_visible": false,
    "somatic_visible": false,
    "material_visible": false,
    "spell_effect_visible": true
  }
}
```

### 字段语义

- `casting_is_perceptible: false`
  - 表示施法动作本身不可被直接察觉
- `verbal_visible / somatic_visible / material_visible`
  - 表示本次施法不呈现这些可观察施法成分
- `spell_effect_visible: true`
  - 默认法术效果本身仍可能被看见
  - 例如火焰、闪电、目标突然受控等

## 战斗规则

## 1. 反制法术免疫

当某次施法声明包含 `subtle_spell` 时：

- `Counterspell / 反制法术` 不应进入候选反应列表
- 不应打开 `counterspell` reaction window

### 规则边界

这里只豁免 `counterspell`

本轮不推导：

- 是否还能被其他特殊反应察觉
- 是否完全等于“所有敌人都不知道你施法”

因为你的要求是：

- 系统硬规则上不被反制
- 剧情层把“不可察觉施法声明”交给 LLM

所以本轮只锁定这两个结果。

## 2. 可见性提示

在 `SpellRequest` / `ExecuteSpell` / `EncounterCastSpell` 返回链路中加入可读字段：

- `metamagic`
- `noticeability`

LLM 拿到这些字段后，可以稳定得出：

- 这次施法没有被看到念咒或结印
- 但法术结果仍然可能暴露施法者或效果

## 3. 不改变法术效果

精妙法术不会改变：

- 法术射程
- 法术目标
- 法术伤害
- 法术豁免 DC
- 法术攻击检定

它只改变：

- 是否暴露施法声明
- 是否允许 `counterspell`

## 接入点

## 1. SpellRequest

职责：

- 解析 `metamagic_options`
- 校验是否允许使用 `subtle_spell`
- 生成结构化的 `metamagic` 与 `noticeability`
- 把这些字段返回给后续执行链路

## 2. EncounterCastSpell

职责：

- 在真正扣除资源时，同时扣除 1 点术法点
- 若施法声明失败回滚，术法点也回滚
- 将 `metamagic` / `noticeability` 写入 `spell_declared` payload

## 3. Reaction Candidate Collection

职责：

- 当事件是 `spell_declared`
- 且 payload 标记 `metamagic.subtle_spell = true`
- 则跳过 `counterspell`

## 4. LLM / 前端结果

职责：

- 在 tool 返回里保留 `metamagic` 与 `noticeability`
- 让 LLM 能直接读到这次施法的隐蔽性

## LLM 叙事约定

如果结果中：

```json
{
  "noticeability": {
    "casting_is_perceptible": false
  }
}
```

则 LLM 可以叙述为：

- “你没有看到他念咒或做出施法手势。”
- “这次施法动作本身没有明显征兆。”

但不应自动叙述为：

- “没有人知道发生了法术。”

因为法术效果本身仍可能被看到。

## 测试

至少覆盖：

- 术士可用 `subtle_spell`
- 非术士或 2 级以下术士不可用
- 术法点不足时报错
- 精妙法术会扣 1 点术法点
- 若施法流程回滚，术法点也回滚
- `SpellRequest` 返回 `metamagic.subtle_spell = true`
- `SpellRequest` 返回 `noticeability.casting_is_perceptible = false`
- 敌方有 `counterspell` 时，普通施法会开反应窗
- 敌方有 `counterspell` 时，精妙施法不会开反应窗

## 风险与约束

- 当前只是“对 `counterspell` 特判”，还不是完整的施法可见性系统
- 后续若加入“观察施法”“偷听咒语”“法术辨识”等系统，需要继续复用 `noticeability` 字段，而不是另起一套状态
- 如果后续加入“有价值材料成分仍需显式处理”的更细规则，`material_visible=false` 的语义可能需要细分为：
  - 普通材料成分被抹除
  - 有价值 / 被消耗材料成分仍需外显或至少仍需校验

## 实施顺序

1. 为施法接口补 `metamagic_options`
2. 在 `SpellRequest` 中解析并返回 `subtle_spell` 结构化结果
3. 在 `EncounterCastSpell` 中扣除 / 回滚术法点
4. 在反应候选收集层跳过 `counterspell`
5. 在 LLM 返回中暴露 `noticeability`
6. 补测试与文档
