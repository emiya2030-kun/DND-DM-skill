"""专注相关规则 service。

当前专注检定的完整实现流程：

1. `request_concentration_check.py`
   - 当目标受到实际伤害且仍在专注时，生成一次专注检定请求
   - 这里会计算：
     - `save_ability = "con"`
     - `save_dc = max(10, floor(damage_taken / 2))`
     - `vantage`

2. `resolve_concentration_check.py`
   - 根据 d20 原始点数和目标数据计算专注检定最终总值
   - 会处理：
     - `CON` 调整值
     - `CON` 豁免熟练
     - 优势 / 劣势
     - 额外加值

3. `resolve_concentration_result.py`
   - 比较 `final_total >= save_dc`
   - 成功：保持专注
   - 失败：把 `is_concentrating = False`
   - 写：
     - `concentration_check_resolved`
     - `concentration_broken`

4. `execute_concentration_check.py`
   - 专注检定统一入口
   - 串联上述三步

这条链的主路径是：

`RequestConcentrationCheck -> ResolveConcentrationCheck -> ResolveConcentrationResult`

而 `ExecuteConcentrationCheck` 是这条链的完整封装入口。
"""
