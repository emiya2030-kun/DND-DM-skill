"""豁免型法术链路相关 service。

当前豁免型法术的完整实现流程：

1. `spells/encounter_cast_spell.py`
   - 声明施法
   - 扣法术位
   - 记录 `spell_declared`

2. `execute_save_spell.py`
   - 豁免型法术的统一入口
   - 把下面几个步骤按顺序串起来

3. `saving_throw_request.py`
   - 读取法术和目标
   - 生成豁免请求
   - 计算或整理：
     - `save_ability`
     - `save_dc`
     - `vantage`
     - 施法者信息

4. `resolve_saving_throw.py`
   - 根据目标 entity 数据和 d20 结果计算豁免总值
   - 会处理：
     - 属性修正
     - 豁免熟练
     - 优势 / 劣势
     - 额外加值

5. `saving_throw_result.py`
   - 比较 `final_total >= save_dc`
   - 判断成功 / 失败
   - 生成结构化 `comparison`
   - 继续触发：
     - `UpdateHp`
     - `UpdateConditions`
     - `UpdateEncounterNotes`

所以这条链的主路径是：

`EncounterCastSpell -> ExecuteSaveSpell -> SavingThrowRequest -> ResolveSavingThrow -> SavingThrowResult`

如果其中包含实际伤害，最终还会继续流到：

`shared/update_hp.py`
"""
