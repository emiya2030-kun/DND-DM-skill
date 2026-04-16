# Session Summary - 2026-04-13

## 目标

这份文档用于记录 2026-04-13 这次开发会话中已经完成的工作、关键设计思路、当前边界和下一步建议，方便下一次新会话直接续上。

## 今天完成了什么

### 1. 攻击链路收口为完整入口

已完成：

- `app/services/combat/attack_roll_request.py`
- `app/services/combat/attack_roll_result.py`
- `app/services/combat/execute_attack.py`
- `app/services/combat/update_hp.py`

当前已经能跑通：

1. 生成攻击请求
2. 接收攻击掷骰最终结果
3. 判定命中 / 未命中 / 暴击
4. 命中后自动扣血
5. 返回结构化数值比较结果给 LLM

攻击结算结果里现在会显式返回：

- `final_total`
- `target_ac`
- `comparison`

其中 `comparison` 的目的是让 LLM 不用自己再口算一次命中判定。

### 2. 豁免型法术链路收口为完整入口

已完成：

- `app/services/spells/encounter_cast_spell.py`
- `app/services/combat/saving_throw_request.py`
- `app/services/combat/resolve_saving_throw.py`
- `app/services/combat/saving_throw_result.py`
- `app/services/combat/execute_save_spell.py`

当前已经能跑通：

1. 声明施法并扣法术位
2. 生成豁免请求
3. 自动计算目标豁免总值
4. 进行 `save_dc` 比较
5. 根据成功 / 失败继续处理伤害、condition、note

豁免结果里现在会显式返回：

- `save_dc`
- `final_total`
- `save_bonus`
- `save_bonus_breakdown`
- `comparison`

这同样是为了让 LLM 直接看到数值对比过程。

### 3. condition / encounter note 已经有基础服务

已完成：

- `app/services/combat/update_conditions.py`
- `app/services/combat/update_encounter_notes.py`

当前已经支持：

- 施加 condition
- 移除 condition
- 添加 / 更新 / 删除 encounter note
- 写入对应事件日志

### 4. 伤害类型修正已接入通用伤害链

已完成：

- 在 `app/services/combat/update_hp.py` 中接入：
  - `resistances`
  - `immunities`
  - `vulnerabilities`

当前规则：

- `immunity`：伤害变为 `0`
- `resistance`：伤害减半，向下取整
- `vulnerability`：伤害翻倍
- 同时有 `resistance` 和 `vulnerability`：互相抵消，按原伤害处理

返回值里现在会显式给出：

- `original_hp_change`
- `adjusted_hp_change`
- `damage_adjustment`

这样 LLM 能知道实际伤害为什么被修正。

### 5. 专注规则模块已建立

已完成：

- `app/services/combat/rules/concentration/request_concentration_check.py`
- `app/services/combat/rules/concentration/resolve_concentration_check.py`
- `app/services/combat/rules/concentration/resolve_concentration_result.py`
- `app/services/combat/rules/concentration/execute_concentration_check.py`

当前已经支持：

1. 目标受到伤害后生成专注检定请求
2. 按 `CON` 豁免计算专注检定总值
3. 支持 `normal / advantage / disadvantage`
4. 比较 `save_dc`
5. 失败后把 `is_concentrating = False`
6. 写入：
   - `concentration_check_resolved`
   - `concentration_broken`

### 6. 自动触发专注检定请求已接入伤害链

已完成：

- `UpdateHp` 在造成实际伤害后，如果目标当前正在专注，会自动生成：
  - `concentration_check_request`

这意味着：

- 攻击链造成伤害后，能自动要求目标过专注检定
- 豁免型法术造成伤害后，也能自动要求目标过专注检定

当前这一步只是“自动生成专注检定请求”，还没有做到“自动帮目标掷骰并直接结算”，因为系统仍然保留“请求 -> 掷骰 -> 结算”的分层。

### 7. services 目录已做轻量整理

已把 `services` 从平铺结构改成分层结构：

- `app/services/encounter/`
- `app/services/events/`
- `app/services/combat/`
- `app/services/spells/`
- `app/services/combat/attack/`
- `app/services/combat/save_spell/`
- `app/services/combat/shared/`
- `app/services/combat/rules/concentration/`

设计目的：

- 后续 service 数量继续增加时，不至于平铺到难以维护
- 让“运行态管理”“事件”“攻击链”“豁免法术链”“共用战斗逻辑”“规则模块”分层更清楚

## 关键设计思路

### 1. 保持“请求 -> 掷骰结果 -> 结算”三段式

当前所有战斗流程都尽量保持这个骨架：

1. request
2. roll result
3. resolution

这样做的好处：

- 结构统一
- LLM 更容易理解
- 测试也更容易拆开写

### 2. 把“长期状态”和“即时上下文”分开

长期状态放在 entity / encounter 快照中，例如：

- `hp`
- `position`
- `conditions`
- `resources`
- `combat_flags`

即时上下文放在 request / result 中，例如：

- `distance_to_target`
- `save_dc`
- `target_ac`
- `comparison`

这样可以避免把临时计算值塞回底层存储结构。

### 3. 让 LLM 直接拿到数值比较结果

本次开发明确坚持了一个方向：

- 不只返回“成功 / 失败”
- 还返回“左值 vs 右值”的结构化结果

例如：

- 攻击：`attack_total >= target_ac`
- 豁免：`saving_throw_total >= save_dc`
- 专注：`concentration_total >= save_dc`

这样 LLM 不需要自己再还原判定过程。

### 4. 通用伤害结算尽量收口到 `update_hp`

因为攻击链、豁免链、以后可能还有环境伤害链，最终都会走到 HP 更新。

所以把这些共通规则放在 `update_hp` 最划算：

- temp hp
- 抗性 / 免疫 / 易伤
- 自动触发专注检定请求

### 5. 规则模块单独放子目录

当前已经开始把“规则类”单独收进：

- `app/services/combat/rules/`

现在第一个模块是：

- `concentration/`

后面如果继续扩，可以按这个方式放：

- `death_saves/`
- `opportunity_attacks/`
- `grapple/`
- `conditions/`

### 6. service 结构按 “execute 入口 -> 下游子 service” 分层

后续 service 目录继续整理时，优先按这个思路组织：

1. 最上层放完整入口
   - 例如：
     - `execute_attack.py`
     - `execute_save_spell.py`
     - `execute_concentration_check.py`
2. 下一层放该入口依赖的 request / resolve / update service
   - 例如专注规则下：
     - `request_concentration_check.py`
     - `resolve_concentration_check.py`
     - `resolve_concentration_result.py`
3. 再往下才是规则子模块
   - 例如：
     - `combat/rules/concentration/`

这样做的目的不是为了形式，而是为了让目录本身就能表达依赖关系：

- 先看到“完整入口是什么”
- 再看到“它下面拆了哪些步骤”

这样比单纯按文件功能平铺更容易理解。

## 当前依赖的数据字段

### 施法者最低建议准备

如果实体要参与豁免型法术结算，当前最低建议准备：

- `source_ref.spellcasting_ability`
- `ability_mods`
- `proficiency_bonus`
- `spells`

### 豁免目标最低建议准备

如果实体要被系统自动计算豁免总值，当前最低建议准备：

- `ability_mods`
- `proficiency_bonus`
- `save_proficiencies`

### 专注目标最低建议准备

如果实体要参与专注检定，当前最低建议准备：

- `combat_flags.is_concentrating`
- `ability_mods["con"]`
- `proficiency_bonus`
- `save_proficiencies`

## 当前还没做的内容

以下内容还没有做，下一轮开发时要注意：

1. 专注失败后自动清理专注产生的效果
   - 现在只会把 `is_concentrating = False`
   - 还不会自动移除由专注维持的 note / condition / effect
2. condition 持续时间和自动移除
   - 目前 condition 还是字符串列表，没有持续时间结构
   - 优势 / 劣势来源后续优先也放进 condition 体系里，而不是单独再起一套平行结构
   - 目标是让 condition 后面既能表达“状态本身”，也能表达“它影响哪些检定/攻击”
3. 多目标 AoE
   - 目前 `execute_save_spell.py` 只收口了单目标版本
4. 法术库驱动效果
   - 当前法术效果参数仍有一部分由调用方传入
   - 后续会由法术库统一提供
5. 非魔法武器伤害等更细粒度伤害标签
   - 当前抗性 / 免疫 / 易伤按简单伤害类型字符串处理

## 下一步建议

下一轮建议优先做下面两个中的一个：

### 方案 A：专注断开后的效果清理

目标：

- 当专注检定失败时，不只是改 `is_concentrating = False`
- 还要自动清除该专注维持的 note / effect / condition

适合继续补“真实战斗闭环”。

### 方案 B：condition 生命周期

目标：

- 给 condition 增加持续时间
- 绑定回合开始 / 结束触发移除
- 把自动移除和事件日志接起来
- 把优势 / 劣势来源逐步收进 condition 结构里

适合继续补“状态系统”。

如果要优先贴近实际战斗体验，建议先做 **方案 A**。

## 测试状态

本次会话结束时，全量测试结果为：

```bash
python3 -m unittest discover -s test -p 'test_*.py'
```

结果：

- `Ran 69 tests`
- `OK`
