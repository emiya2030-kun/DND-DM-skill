"""encounter 运行态管理和视图投影 service。

这一层负责遭遇战本身，而不是具体的攻击或法术规则。

当前主要包含两类能力：

1. `manage_encounter_entities.py`
   - 管理 encounter 中有哪些实体
   - 推进回合
   - 更新位置、当前行动者、HP 快照等

2. `get_encounter_state.py`
   - 把底层运行态投影成给 LLM / UI 读取的视图对象

3. `move_encounter_entity.py`
   - 对实体移动执行路径、地形、占位和移动力规则校验
   - 在需要时追加 `movement_resolved` 事件

4. `turns/`
   - 统一处理回合切换与回合资源重置
   - `EndTurn` / `AdvanceTurn` / `StartTurn` 是对外 service 入口

可以把这一层理解成：

- “战场当前是什么状态”
- “现在轮到谁”
- “给上层读的一份整理后的快照”
"""

from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.begin_move_encounter_entity import BeginMoveEncounterEntity
from tools.services.encounter.continue_pending_movement import ContinuePendingMovement
from tools.services.encounter.manage_encounter_entities import EncounterService
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity
from tools.services.encounter.roll_initiative_and_start_encounter import RollInitiativeAndStartEncounter
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement
from tools.services.encounter.turns import AdvanceTurn, EndTurn, StartTurn

__all__ = [
    "AdvanceTurn",
    "BeginMoveEncounterEntity",
    "ContinuePendingMovement",
    "EndTurn",
    "StartTurn",
    "EncounterService",
    "GetEncounterState",
    "MoveEncounterEntity",
    "RollInitiativeAndStartEncounter",
    "ResolveForcedMovement",
]
