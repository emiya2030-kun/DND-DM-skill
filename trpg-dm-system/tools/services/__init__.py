"""service 总入口。

当前 service 分层遵循一个固定原则：

1. 先看完整入口 `execute_*`
2. 再看该入口下面的 request / resolve / update 子 service
3. 最后再看 shared 和 rules 这类横向复用模块

目前最重要的几条实现流程：

1. 攻击链
   - `ExecuteAttack`
   - `AttackRollRequest`
   - `AttackRollResult`
   - `UpdateHp`
   - 如果目标正在专注，`UpdateHp` 会继续生成 `concentration_check_request`
   - 如果目标正被活动中的可转移标记法术影响且掉到 0 HP，`UpdateHp` 会把该实例改成可转移待命

2. 豁免型法术链
   - `EncounterCastSpell`
   - `ExecuteSaveSpell`
   - `SavingThrowRequest`
   - `ResolveSavingThrow`
   - `SavingThrowResult`
   - `UpdateHp`
   - `UpdateConditions`
   - `UpdateEncounterNotes`
   - 如果目标正在专注且实际受伤，`UpdateHp` 会继续生成 `concentration_check_request`
   - 如果目标正被活动中的可转移标记法术影响且掉到 0 HP，`UpdateHp` 也会同步更新该实例运行时状态

3. 标记法术转移链
   - `RetargetMarkedSpell`
   - 只负责把已有法术实例改挂到新目标
   - 不重新施法，不消耗法术位，但会占用附赠动作

4. 专注检定链
   - `ExecuteConcentrationCheck`
   - `RequestConcentrationCheck`
   - `ResolveConcentrationCheck`
   - `ResolveConcentrationResult`
   - 如果专注失败，系统会自动结束该施法者仍在生效的专注法术实例
   - 并同步清掉这些实例挂到目标上的 `conditions` 与 `turn_effects`

5. 遭遇战移动链
   - `MoveEncounterEntity`
   - 内部使用 `movement_rules` 做逐步路径、占格、地形、condition 和移动力校验

6. 遭遇战回合链
   - `EndTurn`
   - `AdvanceTurn`
   - `StartTurn`
   - `EndTurn` 结束当前人回合
   - `AdvanceTurn` 只推进先攻顺序
   - `StartTurn` 才重置当前单位回合资源

这份 `__init__` 主要负责聚合对外常用 service，方便上层按统一入口导入。
"""

from tools.services.events.append_event import AppendEvent
from tools.services.spells.encounter_cast_spell import EncounterCastSpell
from tools.services.spells.execute_spell import ExecuteSpell
from tools.services.spells.retarget_marked_spell import RetargetMarkedSpell
from tools.services.spells.spell_request import SpellRequest
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.combat.save_spell.execute_save_spell import ExecuteSaveSpell
from tools.services.combat.attack.attack_roll_result import AttackRollResult
from tools.services.combat.attack.attack_roll_request import AttackRollRequest
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.rules.resolve_reaction_request import ResolveReactionRequest
from tools.services.combat.save_spell.saving_throw_request import SavingThrowRequest
from tools.services.combat.save_spell.saving_throw_result import SavingThrowResult
from tools.services.combat.rules.concentration.execute_concentration_check import ExecuteConcentrationCheck
from tools.services.combat.rules.concentration.request_concentration_check import RequestConcentrationCheck
from tools.services.combat.rules.concentration.resolve_concentration_check import ResolveConcentrationCheck
from tools.services.combat.rules.concentration.resolve_concentration_result import ResolveConcentrationResult
from tools.services.combat.shared.update_conditions import UpdateConditions
from tools.services.combat.shared.update_encounter_notes import UpdateEncounterNotes
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.manage_encounter_entities import EncounterService
from tools.services.encounter.begin_move_encounter_entity import BeginMoveEncounterEntity
from tools.services.encounter.continue_pending_movement import ContinuePendingMovement
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement
from tools.services.encounter.turns import AdvanceTurn, EndTurn, StartTurn
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity
from tools.services.map.build_map_notes import BuildMapNotes
from tools.services.map.render_battlemap_page import RenderBattlemapPage
from tools.services.map.render_battlemap_view import RenderBattlemapView

__all__ = [
    "AppendEvent",
    "EncounterCastSpell",
    "ExecuteSpell",
    "SpellRequest",
    "RetargetMarkedSpell",
    "ExecuteAttack",
    "ExecuteSaveSpell",
    "ExecuteConcentrationCheck",
    "AttackRollRequest",
    "AttackRollResult",
    "ResolveDamageParts",
    "ResolveReactionRequest",
    "AdvanceTurn",
    "BeginMoveEncounterEntity",
    "ContinuePendingMovement",
    "ResolveForcedMovement",
    "EndTurn",
    "StartTurn",
    "EncounterService",
    "GetEncounterState",
    "MoveEncounterEntity",
    "RequestConcentrationCheck",
    "ResolveSavingThrow",
    "ResolveConcentrationCheck",
    "ResolveConcentrationResult",
    "SavingThrowRequest",
    "SavingThrowResult",
    "UpdateConditions",
    "UpdateEncounterNotes",
    "UpdateHp",
    "BuildMapNotes",
    "RenderBattlemapPage",
    "RenderBattlemapView",
]
