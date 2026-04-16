"""攻击链路相关 service。

当前攻击链的完整实现流程：

1. `execute_attack.py`
   - 攻击链的统一入口
   - 负责把下面几个步骤按顺序串起来

2. `attack_roll_request.py`
   - 根据当前 encounter、攻击者、目标、武器生成一次攻击请求
   - 这里会计算：
     - 攻击类型
     - 攻击加值
     - 距离
     - 目标 AC

3. `attack_roll_result.py`
   - 接收攻击掷骰的最终结果
   - 比较 `final_total >= target_ac`
   - 判断命中 / 未命中 / 暴击
   - 生成结构化 `comparison`

4. `shared/update_hp.py`
   - 命中后实际处理伤害
   - 这里会统一处理：
     - temp hp
     - 抗性 / 免疫 / 易伤
     - 自动生成专注检定请求

也就是说，攻击链真正的主路径是：

`ExecuteAttack -> AttackRollRequest -> AttackRollResult -> UpdateHp`
"""
