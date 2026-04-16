"""战斗规则模块。

这里放的是更偏“规则域”的模块，而不是单纯某一条攻击或法术链的子步骤。

当前已落地：

1. `concentration/`
   - 专注检定请求
   - 专注检定总值计算
   - 专注结果结算
   - 完整入口 `execute_concentration_check.py`

后续适合继续放在这里的模块包括：

- `conditions/`
- `death_saves/`
- `opportunity_attacks/`
- `grapple/`

也就是说，这里更像“规则专题区”。
"""

from . import conditions  # noqa: F401
from . import opportunity_attacks  # noqa: F401

__all__ = ["conditions", "opportunity_attacks"]
