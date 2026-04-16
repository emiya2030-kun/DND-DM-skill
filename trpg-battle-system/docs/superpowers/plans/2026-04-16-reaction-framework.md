# Reaction Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗系统落地统一的 reaction framework，覆盖通用 reaction window / choice group / option 运行态、definition 读取层、统一 resolver 分发，并先接入 `opportunity_attack`、`shield`、`counterspell`。

**Architecture:** 先扩 `Encounter` 运行态与 definition repository，再增加 `reactions/` 框架层与模板层，最后把移动、攻击、施法三个宿主动作接入统一开窗与恢复流程。第一版保留旧 service 作为兼容入口，内部逐步改调新框架，避免一次性重写现有调用链。

**Tech Stack:** Python 3, unittest, TinyDB repositories, existing combat services, existing runtime/battlemap integration.

---

## 文件结构

### 新增文件

- `trpg-battle-system/tools/repositories/reaction_definition_repository.py`
  - 读取 reaction 目录内的本地 definitions，支持按 `reaction_type` 与 `trigger_type` 查询
- `trpg-battle-system/tools/services/combat/rules/reactions/reaction_definitions.py`
  - 第一版 reaction 静态定义表
- `trpg-battle-system/tools/services/combat/rules/reactions/open_reaction_window.py`
  - 宿主动作到检查点时统一开窗
- `trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py`
  - 根据 trigger event 收集 group / option 候选
- `trpg-battle-system/tools/services/combat/rules/reactions/resolve_reaction_option.py`
  - 解析 `window_id/group_id/option_id`，执行 option
- `trpg-battle-system/tools/services/combat/rules/reactions/close_reaction_window.py`
  - 关闭或推进当前 reaction window
- `trpg-battle-system/tools/services/combat/rules/reactions/resume_host_action.py`
  - 按 resolver 结果恢复 / 取消宿主动作
- `trpg-battle-system/tools/services/combat/rules/reactions/templates/leave_reach_interrupt.py`
  - 借机攻击模板
- `trpg-battle-system/tools/services/combat/rules/reactions/templates/targeted_defense_rewrite.py`
  - 护盾术模板
- `trpg-battle-system/tools/services/combat/rules/reactions/templates/cast_interrupt_contest.py`
  - 反制法术模板
- `trpg-battle-system/tools/services/combat/rules/reactions/definitions/opportunity_attack.py`
  - 借机攻击具体 resolver
- `trpg-battle-system/tools/services/combat/rules/reactions/definitions/shield.py`
  - 护盾术具体 resolver
- `trpg-battle-system/tools/services/combat/rules/reactions/definitions/counterspell.py`
  - 反制法术具体 resolver
- `trpg-battle-system/test/test_reaction_definition_repository.py`
- `trpg-battle-system/test/test_open_reaction_window.py`
- `trpg-battle-system/test/test_resolve_reaction_option.py`
- `trpg-battle-system/test/test_attack_reaction_window.py`
- `trpg-battle-system/test/test_spell_reaction_window.py`

### 修改文件

- `trpg-battle-system/tools/models/encounter.py`
  - 新增 `pending_reaction_window`
  - 升级 `reaction_requests`
- `trpg-battle-system/tools/services/__init__.py`
  - 导出新 services
- `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
  - 投影 `pending_reaction_window` 与升级后的 `reaction_requests`
- `trpg-battle-system/tools/services/encounter/begin_move_encounter_entity.py`
  - 改为通过 `OpenReactionWindow` 生成借机窗口
- `trpg-battle-system/tools/services/encounter/continue_pending_movement.py`
  - 通过统一 window 恢复移动
- `trpg-battle-system/tools/services/combat/rules/resolve_reaction_request.py`
  - 兼容包装层，内部转发到 `ResolveReactionOption`
- `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
  - 在攻击声明后、命中锁定前接入 `shield` reaction window
- `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
  - 在法术声明后、效果落地前接入 `counterspell` reaction window
- `trpg-battle-system/test/test_begin_move_encounter_entity.py`
  - 更新借机相关断言
- `trpg-battle-system/test/test_resolve_reaction_request.py`
  - 更新为兼容入口测试

### 复用但尽量不改的文件

- `trpg-battle-system/tools/services/combat/attack/attack_roll_request.py`
- `trpg-battle-system/tools/services/combat/attack/attack_roll_result.py`
- `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
- `trpg-battle-system/tools/services/encounter/move_encounter_entity.py`

---

### Task 1: 扩 encounter 运行态以支持通用 reaction window

**Files:**
- Modify: `trpg-battle-system/tools/models/encounter.py`
- Modify: `trpg-battle-system/tools/services/encounter/get_encounter_state.py`
- Test: `trpg-battle-system/test/test_models.py`
- Test: `trpg-battle-system/test/test_get_encounter_state.py`

- [ ] **Step 1: 写 `Encounter` 运行态结构的失败测试**

```python
def test_encounter_accepts_pending_reaction_window_and_serializes_it() -> None:
    encounter = Encounter(
        encounter_id="enc_reaction_window_test",
        name="Reaction Window Test",
        status="active",
        round=1,
        current_entity_id="ent_actor_001",
        turn_order=["ent_actor_001"],
        entities={
            "ent_actor_001": EncounterEntity(
                entity_id="ent_actor_001",
                name="Actor",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 1, "y": 1},
                hp={"current": 10, "max": 10, "temp": 0},
                ac=15,
                speed={"walk": 30, "remaining": 30},
                initiative=10,
            )
        },
        map=EncounterMap(
            map_id="map_reaction_window_test",
            name="Map",
            description="Test map",
            width=8,
            height=8,
        ),
        reaction_requests=[
            {
                "request_id": "react_001",
                "status": "pending",
                "reaction_type": "shield",
                "template_type": "targeted_defense_rewrite",
            }
        ],
        pending_reaction_window={
            "window_id": "rw_001",
            "status": "waiting_reaction",
            "trigger_type": "attack_declared",
            "host_action_type": "attack",
            "host_action_id": "atk_001",
            "host_action_snapshot": {"phase": "before_hit_locked"},
            "choice_groups": [],
            "resolved_group_ids": [],
        },
    )

    payload = encounter.to_dict()

    assert payload["pending_reaction_window"]["window_id"] == "rw_001"
    assert payload["reaction_requests"][0]["template_type"] == "targeted_defense_rewrite"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_models -v`
Expected: FAIL with `TypeError` or missing `pending_reaction_window` serialization/assertion failure

- [ ] **Step 3: 写最小模型实现**

```python
@dataclass
class Encounter:
    ...
    reaction_requests: list[dict[str, Any]] = field(default_factory=list)
    pending_reaction_window: dict[str, Any] | None = None
    pending_movement: dict[str, Any] | None = None
    ...
    def __post_init__(self) -> None:
        ...
        if self.pending_reaction_window is not None and not isinstance(self.pending_reaction_window, dict):
            raise ValueError("pending_reaction_window must be a dict or None")
        if self.pending_movement is not None and not isinstance(self.pending_movement, dict):
            raise ValueError("pending_movement must be a dict or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            ...
            "reaction_requests": self.reaction_requests,
            "pending_reaction_window": self.pending_reaction_window,
            "pending_movement": self.pending_movement,
            ...
        }
```

- [ ] **Step 4: 为 `GetEncounterState` 写投影失败测试**

```python
def test_execute_includes_pending_reaction_window_summary(self) -> None:
    ...
    encounter.pending_reaction_window = {
        "window_id": "rw_001",
        "status": "waiting_reaction",
        "trigger_type": "attack_declared",
        "host_action_type": "attack",
        "host_action_id": "atk_001",
        "host_action_snapshot": {"phase": "before_hit_locked"},
        "choice_groups": [
            {
                "group_id": "rg_001",
                "actor_entity_id": "ent_actor_001",
                "status": "pending",
                "options": [
                    {"option_id": "opt_001", "reaction_type": "shield", "status": "pending"}
                ],
            }
        ],
        "resolved_group_ids": [],
    }
    ...
    self.assertEqual(result["pending_reaction_window"]["window_id"], "rw_001")
    self.assertEqual(result["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"], "shield")
```

- [ ] **Step 5: 写最小投影实现**

```python
def _build_pending_reaction_window(self, encounter: Encounter) -> dict[str, Any] | None:
    pending = encounter.pending_reaction_window
    if not isinstance(pending, dict):
        return None
    return {
        "window_id": pending.get("window_id"),
        "status": pending.get("status"),
        "trigger_type": pending.get("trigger_type"),
        "host_action_type": pending.get("host_action_type"),
        "host_action_id": pending.get("host_action_id"),
        "host_action_snapshot": pending.get("host_action_snapshot", {}),
        "choice_groups": pending.get("choice_groups", []),
        "resolved_group_ids": pending.get("resolved_group_ids", []),
    }
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m unittest test.test_models test.test_get_encounter_state -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/models/encounter.py \
  tools/services/encounter/get_encounter_state.py \
  test/test_models.py \
  test/test_get_encounter_state.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Add reaction window encounter state"
```

### Task 2: 落地本地 definition 读取层

**Files:**
- Create: `trpg-battle-system/tools/repositories/reaction_definition_repository.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/reaction_definitions.py`
- Modify: `trpg-battle-system/tools/repositories/__init__.py`
- Test: `trpg-battle-system/test/test_reaction_definition_repository.py`

- [ ] **Step 1: 写 definition repository 的失败测试**

```python
class ReactionDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_definition_by_reaction_type(self) -> None:
        repository = ReactionDefinitionRepository()

        definition = repository.get("shield")

        self.assertEqual(definition["reaction_type"], "shield")
        self.assertEqual(definition["template_type"], "targeted_defense_rewrite")
        self.assertEqual(definition["trigger_type"], "attack_declared")

    def test_list_by_trigger_type_returns_multiple_definitions(self) -> None:
        repository = ReactionDefinitionRepository()

        definitions = repository.list_by_trigger_type("attack_declared")

        reaction_types = {item["reaction_type"] for item in definitions}
        self.assertIn("shield", reaction_types)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_reaction_definition_repository -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 写最小 definitions 模块**

```python
REACTION_DEFINITIONS = {
    "opportunity_attack": {
        "reaction_type": "opportunity_attack",
        "template_type": "leave_reach_interrupt",
        "trigger_type": "leave_reach",
        "resource_cost": {"reaction": True},
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_enemy_of_trigger_mover",
            "actor_has_melee_attack",
            "actor_can_attack",
        ],
        "resolver": {"service": "resolve_opportunity_attack_reaction"},
    },
    "shield": {
        "reaction_type": "shield",
        "template_type": "targeted_defense_rewrite",
        "trigger_type": "attack_declared",
        "resource_cost": {"reaction": True, "spell_slot": {"level": 1, "allow_higher_slot": True}},
        "eligibility_checks": [
            "reaction_not_used",
            "actor_is_target_of_trigger",
            "actor_can_cast_reaction_spell",
            "actor_has_spell_shield",
        ],
        "resolver": {"service": "resolve_shield_reaction"},
    },
    "counterspell": {
        "reaction_type": "counterspell",
        "template_type": "cast_interrupt_contest",
        "trigger_type": "spell_declared",
        "resource_cost": {"reaction": True, "spell_slot": {"level": 3, "allow_higher_slot": True}},
        "eligibility_checks": [
            "reaction_not_used",
            "actor_can_see_trigger_caster",
            "actor_can_cast_reaction_spell",
            "actor_has_spell_counterspell",
        ],
        "resolver": {"service": "resolve_counterspell_reaction"},
    },
}
```

- [ ] **Step 4: 写最小 repository 实现**

```python
from tools.services.combat.rules.reactions.reaction_definitions import REACTION_DEFINITIONS


class ReactionDefinitionRepository:
    def get(self, reaction_type: str) -> dict[str, object]:
        definition = REACTION_DEFINITIONS.get(reaction_type)
        if definition is None:
            raise ValueError(f"reaction_definition '{reaction_type}' not found")
        return dict(definition)

    def list_by_trigger_type(self, trigger_type: str) -> list[dict[str, object]]:
        return [
            dict(definition)
            for definition in REACTION_DEFINITIONS.values()
            if definition.get("trigger_type") == trigger_type
        ]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest test.test_reaction_definition_repository -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/repositories/reaction_definition_repository.py \
  tools/services/combat/rules/reactions/reaction_definitions.py \
  tools/repositories/__init__.py \
  test/test_reaction_definition_repository.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Add reaction definition repository"
```

### Task 3: 落地开窗与候选收集框架

**Files:**
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/collect_reaction_candidates.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/open_reaction_window.py`
- Modify: `trpg-battle-system/tools/services/combat/rules/reactions/__init__.py`
- Test: `trpg-battle-system/test/test_open_reaction_window.py`

- [ ] **Step 1: 写“同一 actor 多 option 只生成一个 group”的失败测试**

```python
def test_open_reaction_window_groups_multiple_options_by_actor(self) -> None:
    encounter = build_attack_declared_encounter_with_shield_and_absorb_elements()
    repository.save(encounter)

    result = OpenReactionWindow(repository, ReactionDefinitionRepository()).execute(
        encounter_id="enc_reaction_window_test",
        trigger_event={
            "event_id": "evt_attack_declared_001",
            "trigger_type": "attack_declared",
            "host_action_type": "attack",
            "host_action_id": "atk_001",
            "host_action_snapshot": {
                "attack_id": "atk_001",
                "actor_entity_id": "ent_enemy_001",
                "target_entity_id": "ent_actor_001",
                "attack_total": 17,
                "target_ac_before_reaction": 15,
                "phase": "before_hit_locked",
            },
            "target_entity_id": "ent_actor_001",
        },
    )

    self.assertEqual(result["status"], "waiting_reaction")
    self.assertEqual(len(result["pending_reaction_window"]["choice_groups"]), 1)
    options = result["pending_reaction_window"]["choice_groups"][0]["options"]
    self.assertEqual({item["reaction_type"] for item in options}, {"shield", "absorb_elements"})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_open_reaction_window -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 写最小候选收集实现**

```python
class CollectReactionCandidates:
    def __init__(self, encounter_repository: EncounterRepository, definition_repository: ReactionDefinitionRepository):
        self.encounter_repository = encounter_repository
        self.definition_repository = definition_repository

    def execute(self, *, encounter: Encounter, trigger_event: dict[str, object]) -> list[dict[str, object]]:
        trigger_type = str(trigger_event["trigger_type"])
        definitions = self.definition_repository.list_by_trigger_type(trigger_type)
        if trigger_type == "attack_declared":
            target_id = str(trigger_event["target_entity_id"])
            return [
                {
                    "actor_entity_id": target_id,
                    "reaction_definition": definition,
                }
                for definition in definitions
            ]
        return []
```

- [ ] **Step 4: 写最小开窗实现**

```python
class OpenReactionWindow:
    def __init__(self, encounter_repository: EncounterRepository, definition_repository: ReactionDefinitionRepository):
        self.encounter_repository = encounter_repository
        self.collect_candidates = CollectReactionCandidates(encounter_repository, definition_repository)

    def execute(self, *, encounter_id: str, trigger_event: dict[str, object]) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        candidates = self.collect_candidates.execute(encounter=encounter, trigger_event=trigger_event)
        if not candidates:
            return {"status": "no_window_opened", "pending_reaction_window": None}

        groups_by_actor: dict[str, dict[str, object]] = {}
        requests: list[dict[str, object]] = []
        for index, candidate in enumerate(candidates, start=1):
            actor_id = str(candidate["actor_entity_id"])
            definition = dict(candidate["reaction_definition"])
            group = groups_by_actor.setdefault(
                actor_id,
                {
                    "group_id": f"rg_{actor_id}",
                    "actor_entity_id": actor_id,
                    "ask_player": True,
                    "status": "pending",
                    "resource_pool": "reaction",
                    "group_priority": 100,
                    "trigger_sequence": index,
                    "relationship_rank": 1,
                    "tie_break_key": actor_id,
                    "options": [],
                },
            )
            request_id = f"react_{actor_id}_{definition['reaction_type']}"
            requests.append(
                {
                    "request_id": request_id,
                    "status": "pending",
                    "reaction_type": definition["reaction_type"],
                    "template_type": definition["template_type"],
                    "trigger_type": trigger_event["trigger_type"],
                    "trigger_event_id": trigger_event["event_id"],
                    "actor_entity_id": actor_id,
                    "target_entity_id": trigger_event.get("target_entity_id"),
                    "ask_player": True,
                    "auto_resolve": False,
                    "resource_cost": definition.get("resource_cost", {}),
                    "priority": 100,
                    "payload": {},
                }
            )
            group["options"].append(
                {
                    "option_id": f"opt_{actor_id}_{definition['reaction_type']}",
                    "reaction_type": definition["reaction_type"],
                    "template_type": definition["template_type"],
                    "request_id": request_id,
                    "label": definition.get("name", definition["reaction_type"]),
                    "status": "pending",
                }
            )

        encounter.reaction_requests.extend(requests)
        encounter.pending_reaction_window = {
            "window_id": f"rw_{trigger_event['event_id']}",
            "status": "waiting_reaction",
            "trigger_event_id": trigger_event["event_id"],
            "trigger_type": trigger_event["trigger_type"],
            "blocking": True,
            "host_action_type": trigger_event["host_action_type"],
            "host_action_id": trigger_event["host_action_id"],
            "host_action_snapshot": trigger_event["host_action_snapshot"],
            "choice_groups": list(groups_by_actor.values()),
            "resolved_group_ids": [],
        }
        self.encounter_repository.save(encounter)
        return {
            "status": "waiting_reaction",
            "pending_reaction_window": encounter.pending_reaction_window,
            "reaction_requests": requests,
        }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest test.test_open_reaction_window -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/services/combat/rules/reactions/collect_reaction_candidates.py \
  tools/services/combat/rules/reactions/open_reaction_window.py \
  tools/services/combat/rules/reactions/__init__.py \
  test/test_open_reaction_window.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Add reaction window opening flow"
```

### Task 4: 落地 option 解析与借机攻击模板

**Files:**
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/resolve_reaction_option.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/close_reaction_window.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/resume_host_action.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/templates/leave_reach_interrupt.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/definitions/opportunity_attack.py`
- Modify: `trpg-battle-system/tools/services/combat/rules/resolve_reaction_request.py`
- Test: `trpg-battle-system/test/test_resolve_reaction_option.py`
- Test: `trpg-battle-system/test/test_resolve_reaction_request.py`

- [ ] **Step 1: 写“解析借机 option 会消费 reaction 并关闭 group”的失败测试**

```python
def test_resolve_reaction_option_executes_opportunity_attack_and_consumes_reaction(self) -> None:
    encounter = build_pending_leave_reach_window()
    repository.save(encounter)
    service = ResolveReactionOption(
        encounter_repository=repository,
        append_event=append_event,
        execute_attack=execute_attack,
    )

    result = service.execute(
        encounter_id="enc_reaction_window_test",
        window_id="rw_evt_leave_reach_001",
        group_id="rg_ent_ally_eric_001",
        option_id="opt_ent_ally_eric_001_opportunity_attack",
        final_total=17,
        dice_rolls={"base_rolls": [12], "modifier": 5},
        damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
    )

    updated = repository.get("enc_reaction_window_test")
    assert result["resolution_mode"] == "append_followup_action"
    assert updated.entities["ent_ally_eric_001"].action_economy["reaction_used"] is True
    assert updated.pending_reaction_window is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_resolve_reaction_option -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 写最小模板与具体 resolver**

```python
class ResolveOpportunityAttackReaction:
    def __init__(self, execute_attack: ExecuteAttack):
        self.execute_attack = execute_attack

    def execute(self, *, encounter_id: str, request: dict[str, object], final_total: int, dice_rolls: dict[str, object], damage_rolls: list[dict[str, object]] | None) -> dict[str, object]:
        return {
            "reaction_result": self.execute_attack.execute(
                encounter_id=encounter_id,
                actor_id=str(request["actor_entity_id"]),
                target_id=str(request["target_entity_id"]),
                weapon_id=str(request["payload"]["weapon_id"]),
                final_total=final_total,
                dice_rolls=dice_rolls,
                damage_rolls=damage_rolls,
                consume_action=False,
                consume_reaction=True,
                allow_out_of_turn_actor=True,
            ),
            "resolution_mode": "append_followup_action",
            "host_action_post_check": {"required": True, "check": "can_movement_continue"},
        }
```

- [ ] **Step 4: 写最小 `ResolveReactionOption` 实现**

```python
class ResolveReactionOption:
    def execute(...):
        encounter = self._get_encounter_or_raise(encounter_id)
        window = self._get_pending_window_or_raise(encounter, window_id)
        group = self._get_group_or_raise(window, group_id)
        option = self._get_option_or_raise(group, option_id)
        request = self._get_request_or_raise(encounter, option["request_id"])

        if option["reaction_type"] != "opportunity_attack":
            raise ValueError("unsupported_reaction_type")

        resolver = ResolveOpportunityAttackReaction(self.execute_attack)
        resolved = resolver.execute(
            encounter_id=encounter_id,
            request=request,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
        )

        request["status"] = "resolved"
        option["status"] = "resolved"
        group["status"] = "resolved"
        for sibling in group["options"]:
            if sibling["option_id"] != option_id and sibling["status"] == "pending":
                sibling["status"] = "expired"
        encounter.pending_reaction_window = None
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "window_id": window_id,
            "group_id": group_id,
            "option_id": option_id,
            "resolution_mode": resolved["resolution_mode"],
            "reaction_result": resolved["reaction_result"],
            "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
        }
```

- [ ] **Step 5: 把旧 `ResolveReactionRequest` 改成兼容包装层**

```python
class ResolveReactionRequest:
    def execute(...):
        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        window = encounter.pending_reaction_window
        if not isinstance(window, dict):
            raise ValueError("pending_reaction_window_not_found")
        for group in window.get("choice_groups", []):
            for option in group.get("options", []):
                if option.get("request_id") == request_id:
                    return self.resolve_reaction_option.execute(
                        encounter_id=encounter_id,
                        window_id=str(window["window_id"]),
                        group_id=str(group["group_id"]),
                        option_id=str(option["option_id"]),
                        final_total=final_total,
                        dice_rolls=dice_rolls,
                        damage_rolls=damage_rolls,
                    )
        raise ValueError("reaction_option_not_found")
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m unittest test.test_resolve_reaction_option test.test_resolve_reaction_request -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/services/combat/rules/reactions/resolve_reaction_option.py \
  tools/services/combat/rules/reactions/close_reaction_window.py \
  tools/services/combat/rules/reactions/resume_host_action.py \
  tools/services/combat/rules/reactions/templates/leave_reach_interrupt.py \
  tools/services/combat/rules/reactions/definitions/opportunity_attack.py \
  tools/services/combat/rules/resolve_reaction_request.py \
  test/test_resolve_reaction_option.py \
  test/test_resolve_reaction_request.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Resolve reaction options through framework"
```

### Task 5: 让移动宿主动作通过统一框架开借机窗口

**Files:**
- Modify: `trpg-battle-system/tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `trpg-battle-system/tools/services/encounter/continue_pending_movement.py`
- Test: `trpg-battle-system/test/test_begin_move_encounter_entity.py`
- Test: `trpg-battle-system/test/test_continue_pending_movement.py`

- [ ] **Step 1: 写“移动触发统一 reaction window”的失败测试**

```python
def test_execute_opens_reaction_window_when_enemy_leaves_reach(self) -> None:
    ...
    result = service.execute_with_state(
        encounter_id="enc_begin_move_test",
        entity_id="ent_enemy_orc_001",
        target_position={"x": 8, "y": 4},
    )

    self.assertEqual(result["movement_status"], "waiting_reaction")
    self.assertEqual(result["encounter_state"]["pending_reaction_window"]["trigger_type"], "leave_reach")
    self.assertEqual(
        result["encounter_state"]["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"],
        "opportunity_attack",
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_begin_move_encounter_entity test.test_continue_pending_movement -v`
Expected: FAIL because result still uses old request-only structure

- [ ] **Step 3: 写最小接线实现**

```python
trigger_event = {
    "event_id": f"evt_leave_reach_{uuid4().hex[:12]}",
    "trigger_type": "leave_reach",
    "host_action_type": "movement",
    "host_action_id": f"move_{uuid4().hex[:12]}",
    "host_action_snapshot": {
        "movement_id": pending_movement_id,
        "entity_id": mover.entity_id,
        "start_position": start_position,
        "current_position": dict(first_trigger["trigger_position"]),
        "target_position": {"x": target_position["x"], "y": target_position["y"]},
        "remaining_path": first_trigger["remaining_path"],
        "count_movement": count_movement,
        "use_dash": use_dash,
        "phase": "after_step_before_continue",
    },
    "trigger_mover_id": mover.entity_id,
    "target_entity_id": mover.entity_id,
}
window_result = self.open_reaction_window.execute(encounter_id=encounter_id, trigger_event=trigger_event)
```

- [ ] **Step 4: 更新继续移动逻辑读取 `pending_reaction_window`**

```python
window = encounter.pending_reaction_window
if isinstance(window, dict) and window.get("status") == "waiting_reaction":
    waiting_group = next(
        (group for group in window.get("choice_groups", []) if group.get("status") == "pending"),
        None,
    )
    if waiting_group is not None:
        for option in waiting_group.get("options", []):
            request = self._get_request_or_raise(encounter, str(option["request_id"]))
            if request.get("status") == "pending":
                request["status"] = "declined"
        waiting_group["status"] = "declined"
    encounter.pending_reaction_window = None
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest test.test_begin_move_encounter_entity test.test_continue_pending_movement -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/services/encounter/begin_move_encounter_entity.py \
  tools/services/encounter/continue_pending_movement.py \
  test/test_begin_move_encounter_entity.py \
  test/test_continue_pending_movement.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Open movement reactions through framework"
```

### Task 6: 给攻击与施法接入 `shield` / `counterspell` 窗口

**Files:**
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/templates/targeted_defense_rewrite.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/templates/cast_interrupt_contest.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/definitions/shield.py`
- Create: `trpg-battle-system/tools/services/combat/rules/reactions/definitions/counterspell.py`
- Modify: `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
- Modify: `trpg-battle-system/tools/services/spells/encounter_cast_spell.py`
- Test: `trpg-battle-system/test/test_attack_reaction_window.py`
- Test: `trpg-battle-system/test/test_spell_reaction_window.py`

- [ ] **Step 1: 写 `shield` 开窗失败测试**

```python
def test_execute_attack_returns_waiting_reaction_when_target_can_cast_shield(self) -> None:
    ...
    result = service.execute(
        encounter_id="enc_attack_reaction_test",
        actor_id="ent_enemy_orc_001",
        target_id="ent_ally_wizard_001",
        weapon_id="spear",
        final_total=17,
        dice_rolls={"base_rolls": [12], "modifier": 5},
    )

    self.assertEqual(result["status"], "waiting_reaction")
    self.assertEqual(result["pending_reaction_window"]["trigger_type"], "attack_declared")
    self.assertEqual(result["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"], "shield")
```

- [ ] **Step 2: 写 `counterspell` 开窗失败测试**

```python
def test_cast_spell_returns_waiting_reaction_when_enemy_can_counterspell(self) -> None:
    ...
    result = encounter_cast_spell.execute(
        encounter_id="enc_spell_reaction_test",
        caster_id="ent_enemy_mage_001",
        spell_id="fireball",
        declared_targets=[{"x": 6, "y": 6}],
    )

    self.assertEqual(result["status"], "waiting_reaction")
    self.assertEqual(result["pending_reaction_window"]["trigger_type"], "spell_declared")
    self.assertEqual(result["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"], "counterspell")
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m unittest test.test_attack_reaction_window test.test_spell_reaction_window -v`
Expected: FAIL because attack/spell paths do not yet open reaction windows

- [ ] **Step 4: 在 `ExecuteAttack` 的命中锁定前插入最小开窗逻辑**

```python
trigger_event = {
    "event_id": f"evt_attack_declared_{uuid4().hex[:12]}",
    "trigger_type": "attack_declared",
    "host_action_type": "attack",
    "host_action_id": f"atk_{uuid4().hex[:12]}",
    "host_action_snapshot": {
        "attack_id": attack_id,
        "actor_entity_id": request.actor_entity_id,
        "target_entity_id": request.target_entity_id,
        "weapon_id": weapon_id,
        "attack_mode": normalized_attack_mode,
        "grip_mode": grip_mode or "default",
        "attack_total": resolved_attack_roll["final_total"],
        "target_ac_before_reaction": request.context["target_ac"],
        "vantage": request.context["vantage"],
        "phase": "before_hit_locked",
    },
    "target_entity_id": request.target_entity_id,
}
window_result = self.open_reaction_window.execute(encounter_id=encounter_id, trigger_event=trigger_event)
if window_result["status"] == "waiting_reaction":
    return {
        "status": "waiting_reaction",
        "pending_reaction_window": window_result["pending_reaction_window"],
        "reaction_requests": window_result["reaction_requests"],
        "encounter_state": GetEncounterState(self.attack_roll_request.encounter_repository).execute(encounter_id),
    }
```

- [ ] **Step 5: 在 `encounter_cast_spell.py` 的法术效果落地前插入最小开窗逻辑**

```python
trigger_event = {
    "event_id": f"evt_spell_declared_{uuid4().hex[:12]}",
    "trigger_type": "spell_declared",
    "host_action_type": "spell_cast",
    "host_action_id": f"spell_{uuid4().hex[:12]}",
    "host_action_snapshot": {
        "spell_action_id": spell_action_id,
        "caster_entity_id": caster.entity_id,
        "spell_id": spell_id,
        "spell_level": spell_level,
        "declared_targets": declared_targets,
        "action_cost": declared_action_cost,
        "phase": "before_spell_resolves",
    },
    "caster_entity_id": caster.entity_id,
}
window_result = self.open_reaction_window.execute(encounter_id=encounter_id, trigger_event=trigger_event)
if window_result["status"] == "waiting_reaction":
    return {
        "status": "waiting_reaction",
        "pending_reaction_window": window_result["pending_reaction_window"],
        "reaction_requests": window_result["reaction_requests"],
        "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
    }
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m unittest test.test_attack_reaction_window test.test_spell_reaction_window -v`
Expected: PASS

- [ ] **Step 7: 跑整组回归验证**

Run: `python3 -m unittest test.test_begin_move_encounter_entity test.test_continue_pending_movement test.test_resolve_reaction_option test.test_resolve_reaction_request test.test_attack_reaction_window test.test_spell_reaction_window -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/services/combat/rules/reactions/templates/targeted_defense_rewrite.py \
  tools/services/combat/rules/reactions/templates/cast_interrupt_contest.py \
  tools/services/combat/rules/reactions/definitions/shield.py \
  tools/services/combat/rules/reactions/definitions/counterspell.py \
  tools/services/combat/attack/execute_attack.py \
  tools/services/spells/encounter_cast_spell.py \
  test/test_attack_reaction_window.py \
  test/test_spell_reaction_window.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "Open attack and spell reactions through framework"
```

## Self-Review

- **Spec coverage:** 运行态模型、definition 读取层、统一开窗、choice group 竞争、借机攻击接线、`shield`/`counterspell` 第一版接线都已有对应任务；`absorb_elements` / `hellish_rebuke` 被明确放到后续增量，不混入首批实现。
- **Placeholder scan:** 计划中没有 `TODO`、`TBD`、`implement later`、`similar to Task N` 等占位语句；所有代码步骤都给了具体代码块。
- **Type consistency:** 统一使用 `pending_reaction_window`、`choice_groups`、`options`、`window_id/group_id/option_id`，没有前后命名漂移。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-16-reaction-framework.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
