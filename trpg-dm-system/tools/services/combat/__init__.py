"""战斗结算相关 service。

当前 `combat/` 下的目录按“完整入口 -> 子步骤 -> 横向共享 / 规则模块”组织：

1. `attack/`
   - 单体攻击链路
   - 入口是 `execute_attack.py`

2. `save_spell/`
   - 豁免型法术链路
   - 入口是 `execute_save_spell.py`

3. `shared/`
   - 攻击链和法术链都会共用的基础 service
   - 例如：
     - `update_hp.py`
     - `update_conditions.py`
     - `update_encounter_notes.py`

4. `rules/`
   - 更偏规则模块的独立逻辑
   - 当前第一个模块是 `concentration/`

这样分层的目的，是让目录本身就能表达“从哪里进入”和“下面拆了哪些实现步骤”。
"""
