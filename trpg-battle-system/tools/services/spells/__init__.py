"""施法声明和法术相关 service。

当前这里先放两类法术运行时 service：

1. `encounter_cast_spell.py`
   - 校验当前行动者是否拥有该法术
   - 根据施法等级扣法术位
   - 记录 `spell_declared`

2. `retarget_marked_spell.py`
   - 把已经获得转移资格的单目标标记法术改挂到新目标
   - 不重新施法，不再消耗法术位

注意：

- 这里不负责命中、豁免、伤害或 condition 的最终结算
- 那些逻辑分别在 `combat/save_spell/` 和 `combat/shared/` 里

这样分开以后：

- `spells/` 更像“宣告使用某个法术”
- `combat/save_spell/` 更像“这个法术如何进行规则结算”
"""

from tools.services.spells.execute_spell import ExecuteSpell
from tools.services.spells.spell_request import SpellRequest

__all__ = ["SpellRequest", "ExecuteSpell"]
