# Reaction Requests 与最小借机攻击 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗系统增加通用 `reaction_requests` / `pending_movement` 运行时结构，并实现最小借机攻击链：移动途中触发、阻塞移动、结算反应、再继续移动。

**Architecture:** 在 `Encounter` 顶层新增 `reaction_requests` 和 `pending_movement`，由新的移动入口 `BeginMoveEncounterEntity` / `ContinuePendingMovement` 管理分段移动。`ResolveReactionRequest` 作为通用反应执行入口，第一版只支持 `opportunity_attack`，内部复用现有攻击判定与伤害链，但只消耗 `reaction_used`，不消耗 `action_used`。

**Tech Stack:** Python 3.9, unittest, dataclass models, TinyDB-style repositories, existing encounter/combat services

---

### Task 1: 扩 Encounter 模型支持 `reaction_requests` 与 `pending_movement`

**Files:**
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/models/encounter.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
def test_encounter_roundtrip_preserves_reaction_requests_and_pending_movement(self) -> None:
    entity = build_entity()
    encounter = Encounter(
        encounter_id="enc_test",
        name="Test",
        status="active",
        round=1,
        current_entity_id=entity.entity_id,
        turn_order=[entity.entity_id],
        entities={entity.entity_id: entity},
        map=build_map(),
        reaction_requests=[
            {
                "request_id": "react_001",
                "reaction_type": "opportunity_attack",
                "trigger_type": "leave_melee_reach",
                "status": "pending",
                "actor_entity_id": entity.entity_id,
                "actor_name": entity.name,
                "target_entity_id": "ent_enemy_001",
                "target_name": "Enemy",
                "ask_player": True,
                "auto_resolve": False,
                "source_event_type": "movement_trigger_check",
                "source_event_id": None,
                "payload": {
                    "weapon_id": "rapier",
                    "weapon_name": "Rapier",
                    "trigger_position": {"x": 5, "y": 4},
                    "reason": "目标离开了你的近战触及",
                },
            }
        ],
        pending_movement={
            "movement_id": "move_001",
            "entity_id": entity.entity_id,
            "start_position": {"x": 4, "y": 4},
            "target_position": {"x": 8, "y": 4},
            "current_position": {"x": 5, "y": 4},
            "remaining_path": [{"x": 6, "y": 4}],
            "count_movement": True,
            "use_dash": False,
            "status": "waiting_reaction",
            "waiting_request_id": "react_001",
        },
    )
    payload = encounter.to_dict()
    roundtrip = Encounter.from_dict(payload)
    self.assertEqual(roundtrip.reaction_requests[0]["request_id"], "react_001")
    self.assertEqual(roundtrip.pending_movement["movement_id"], "move_001")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_models.EncounterModelTests.test_encounter_roundtrip_preserves_reaction_requests_and_pending_movement -v`

Expected: FAIL with `TypeError` or missing `reaction_requests` / `pending_movement`

- [ ] **Step 3: 写最小实现**

```python
@dataclass
class Encounter:
    ...
    spell_instances: list[dict[str, Any]] = field(default_factory=list)
    reaction_requests: list[dict[str, Any]] = field(default_factory=list)
    pending_movement: dict[str, Any] | None = None
    ...
    def __post_init__(self) -> None:
        ...
        if not isinstance(self.reaction_requests, list):
            raise ValueError("reaction_requests must be a list")
        if self.pending_movement is not None and not isinstance(self.pending_movement, dict):
            raise ValueError("pending_movement must be a dict or None")
    ...
    def to_dict(self) -> dict[str, Any]:
        return {
            ...
            "spell_instances": self.spell_instances,
            "reaction_requests": self.reaction_requests,
            "pending_movement": self.pending_movement,
            ...
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_models.EncounterModelTests.test_encounter_roundtrip_preserves_reaction_requests_and_pending_movement -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/models/encounter.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_models.py
git commit -m "feat: add reaction request runtime fields"
```

### Task 2: 提取借机触发检测辅助层

**Files:**
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/opportunity_attacks/build_opportunity_request.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/__init__.py`
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_build_opportunity_request.py`

- [ ] **Step 1: 写失败测试**

```python
def test_build_request_marks_player_prompt_for_enemy_leaving_reach(self) -> None:
    attacker = build_player_melee()
    target = build_enemy_mover()
    request = build_opportunity_request(
        actor=attacker,
        target=target,
        trigger_position={"x": 5, "y": 4},
        weapon={"weapon_id": "rapier", "name": "Rapier"},
    )
    assert request["reaction_type"] == "opportunity_attack"
    assert request["ask_player"] is True
    assert request["auto_resolve"] is False
    assert request["payload"]["weapon_id"] == "rapier"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_build_opportunity_request -v`

Expected: FAIL with `ModuleNotFoundError` or `NameError`

- [ ] **Step 3: 写最小实现**

```python
from uuid import uuid4

def build_opportunity_request(*, actor, target, trigger_position, weapon):
    return {
        "request_id": f"react_{uuid4().hex[:12]}",
        "reaction_type": "opportunity_attack",
        "trigger_type": "leave_melee_reach",
        "status": "pending",
        "actor_entity_id": actor.entity_id,
        "actor_name": actor.name,
        "target_entity_id": target.entity_id,
        "target_name": target.name,
        "ask_player": actor.controller == "player",
        "auto_resolve": actor.controller != "player",
        "source_event_type": "movement_trigger_check",
        "source_event_id": None,
        "payload": {
            "weapon_id": weapon["weapon_id"],
            "weapon_name": weapon["name"],
            "trigger_position": trigger_position,
            "reason": "目标离开了你的近战触及",
        },
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_build_opportunity_request -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/opportunity_attacks/build_opportunity_request.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_build_opportunity_request.py
git commit -m "feat: add opportunity reaction request builder"
```

### Task 3: 实现 `BeginMoveEncounterEntity` 的最小阻塞移动

**Files:**
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/__init__.py`
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_begin_move_encounter_entity.py`

- [ ] **Step 1: 写失败测试，覆盖生成 pending movement**

```python
def test_execute_creates_pending_movement_and_reaction_request_when_enemy_leaves_player_reach(self) -> None:
    repo, event_repo = make_repositories()
    encounter = build_encounter_with_player_and_moving_enemy()
    repo.save(encounter)
    service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
    result = service.execute_with_state(
        encounter_id="enc_begin_move_test",
        entity_id="ent_enemy_orc_001",
        target_position={"x": 8, "y": 4},
    )
    updated = repo.get("enc_begin_move_test")
    assert updated.pending_movement["status"] == "waiting_reaction"
    assert updated.reaction_requests[0]["reaction_type"] == "opportunity_attack"
    assert result["movement_status"] == "waiting_reaction"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_begin_move_encounter_entity -v`

Expected: FAIL with missing service import

- [ ] **Step 3: 写最小实现**

```python
class BeginMoveEncounterEntity:
    def execute_with_state(...):
        encounter = self.repository.get(encounter_id)
        entity = encounter.entities[entity_id]
        full_result = validate_movement_path(...)
        first_trigger = self._find_first_opportunity_trigger(encounter, entity, full_result.path)
        if first_trigger is None:
            MoveEncounterEntity(self.repository, self.append_event).execute(...)
            return {
                "encounter_id": encounter_id,
                "entity_id": entity_id,
                "movement_status": "completed",
                "reaction_requests": [],
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }
        entity.position.update(first_trigger["trigger_position"])
        encounter.pending_movement = {
            "movement_id": f"move_{uuid4().hex[:12]}",
            "entity_id": entity_id,
            "start_position": first_trigger["start_position"],
            "target_position": target_position,
            "current_position": first_trigger["trigger_position"],
            "remaining_path": first_trigger["remaining_path"],
            "count_movement": count_movement,
            "use_dash": use_dash,
            "status": "waiting_reaction",
            "waiting_request_id": first_trigger["request"]["request_id"],
        }
        encounter.reaction_requests.append(first_trigger["request"])
        self.repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "entity_id": entity_id,
            "movement_status": "waiting_reaction",
            "reaction_requests": [first_trigger["request"]],
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_begin_move_encounter_entity -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/begin_move_encounter_entity.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_begin_move_encounter_entity.py
git commit -m "feat: add blocking move start for reaction prompts"
```

### Task 4: 实现 `ResolveReactionRequest`，第一版只支持借机攻击

**Files:**
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/resolve_reaction_request.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py`
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_resolve_reaction_request.py`

- [ ] **Step 1: 写失败测试，覆盖只消耗 reaction 不消耗 action**

```python
def test_execute_resolves_opportunity_attack_and_spends_reaction_only(self) -> None:
    repo, event_repo = make_repositories()
    encounter = build_pending_opportunity_encounter()
    repo.save(encounter)
    service = ResolveReactionRequest(
        repo,
        AppendEvent(event_repo),
        ExecuteAttack(
            AttackRollRequest(repo),
            AttackRollResult(repo, AppendEvent(event_repo), UpdateHp(repo, AppendEvent(event_repo))),
        ),
    )
    result = service.execute(
        encounter_id="enc_react_test",
        request_id="react_001",
        final_total=17,
        dice_rolls={"base_rolls": [12], "modifier": 5},
        damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
    )
    updated = repo.get("enc_react_test")
    assert updated.entities["ent_ally_eric_001"].action_economy["reaction_used"] is True
    assert updated.entities["ent_ally_eric_001"].action_economy.get("action_used", False) is False
    assert updated.reaction_requests[0]["status"] == "resolved"
    assert result["reaction_type"] == "opportunity_attack"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_resolve_reaction_request -v`

Expected: FAIL with missing service import

- [ ] **Step 3: 写最小实现**

```python
class ResolveReactionRequest:
    def execute(self, *, encounter_id, request_id, final_total, dice_rolls, damage_rolls=None):
        encounter = self.repository.get(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        if request["reaction_type"] != "opportunity_attack":
            raise ValueError("unsupported_reaction_type")
        actor = encounter.entities[request["actor_entity_id"]]
        actor.action_economy["reaction_used"] = True
        attack_result = self.execute_attack.execute(
            encounter_id=encounter_id,
            target_id=request["target_entity_id"],
            weapon_id=request["payload"]["weapon_id"],
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls or [],
            consume_action=False,
        )
        request["status"] = "resolved"
        self.repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "request_id": request_id,
            "reaction_type": "opportunity_attack",
            "attack_result": attack_result,
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_resolve_reaction_request -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/rules/resolve_reaction_request.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_resolve_reaction_request.py
git commit -m "feat: resolve opportunity reaction requests"
```

### Task 5: 给攻击链补“借机不消耗 action”的入口

**Files:**
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/attack/execute_attack.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_can_consume_reaction_without_action_for_opportunity_attack(self) -> None:
    with make_repositories() as (encounter_repo, event_repo):
        encounter = build_encounter()
        encounter.entities["ent_ally_eric_001"].action_economy = {
            "action_used": False,
            "reaction_used": False,
        }
        encounter_repo.save(encounter)
        service = ExecuteAttack(
            AttackRollRequest(encounter_repo),
            AttackRollResult(encounter_repo, AppendEvent(event_repo), UpdateHp(encounter_repo, AppendEvent(event_repo))),
        )
        result = service.execute(
            encounter_id="enc_execute_attack_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="rapier",
            final_total=17,
            dice_rolls={"base_rolls": [12], "modifier": 5},
            consume_action=False,
            consume_reaction=True,
        )
        updated = encounter_repo.get("enc_execute_attack_test")
        self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy.get("action_used", False))
        self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["reaction_used"])
        self.assertTrue(result["resolution"]["hit"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_can_consume_reaction_without_action_for_opportunity_attack -v`

Expected: FAIL with unexpected keyword or wrong action state

- [ ] **Step 3: 写最小实现**

```python
def execute(..., consume_action: bool = True, consume_reaction: bool = False, ...):
    ...
    if consume_action:
        actor.action_economy["action_used"] = True
    if consume_reaction:
        if actor.action_economy.get("reaction_used"):
            raise ValueError("reaction_already_used")
        actor.action_economy["reaction_used"] = True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_can_consume_reaction_without_action_for_opportunity_attack -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/combat/attack/execute_attack.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_execute_attack.py
git commit -m "feat: support reaction-based attack consumption"
```

### Task 6: 实现 `ContinuePendingMovement`，支持“跳过借机”与“中断停点”

**Files:**
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/continue_pending_movement.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/__init__.py`
- Create: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_continue_pending_movement.py`

- [ ] **Step 1: 写失败测试，覆盖不借机时继续移动**

```python
def test_execute_expires_pending_request_and_finishes_move_when_player_skips_reaction(self) -> None:
    repo, event_repo = make_repositories()
    encounter = build_waiting_reaction_encounter()
    repo.save(encounter)
    service = ContinuePendingMovement(repo, AppendEvent(event_repo))
    result = service.execute_with_state(encounter_id="enc_continue_move_test")
    updated = repo.get("enc_continue_move_test")
    assert updated.pending_movement is None
    assert updated.reaction_requests[0]["status"] == "expired"
    assert updated.entities["ent_enemy_orc_001"].position == {"x": 8, "y": 4}
    assert result["movement_status"] == "completed"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_continue_pending_movement -v`

Expected: FAIL with missing service import

- [ ] **Step 3: 写最小实现**

```python
class ContinuePendingMovement:
    def execute_with_state(self, *, encounter_id):
        encounter = self.repository.get(encounter_id)
        pending = encounter.pending_movement
        request = self._get_request_or_raise(encounter, pending["waiting_request_id"])
        if request["status"] == "pending":
            request["status"] = "expired"
        mover = encounter.entities[pending["entity_id"]]
        if mover.hp["current"] <= 0 or mover.combat_flags.get("is_defeated"):
            pending["status"] = "interrupted"
            encounter.pending_movement = None
            self.repository.save(encounter)
            return {..., "movement_status": "interrupted", "encounter_state": GetEncounterState(self.repository).execute(encounter_id)}
        mover.position = dict(pending["target_position"])
        encounter.pending_movement = None
        self.repository.save(encounter)
        return {..., "movement_status": "completed", "encounter_state": GetEncounterState(self.repository).execute(encounter_id)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_continue_pending_movement -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/continue_pending_movement.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/__init__.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_continue_pending_movement.py
git commit -m "feat: continue pending movement after reaction window"
```

### Task 7: 给 `GetEncounterState` 投影 `reaction_requests` / `pending_movement`

**Files:**
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/get_encounter_state.py`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_get_encounter_state.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_projects_pending_reaction_requests_and_pending_movement(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.reaction_requests = [
            {
                "request_id": "react_001",
                "reaction_type": "opportunity_attack",
                "trigger_type": "leave_melee_reach",
                "status": "pending",
                "actor_entity_id": "ent_ally_eric_001",
                "actor_name": "Eric",
                "target_entity_id": "ent_enemy_goblin_001",
                "target_name": "Goblin",
                "ask_player": True,
                "auto_resolve": False,
                "source_event_type": "movement_trigger_check",
                "source_event_id": None,
                "payload": {"weapon_id": "rapier", "weapon_name": "Rapier", "trigger_position": {"x": 5, "y": 4}, "reason": "目标离开了你的近战触及"},
            }
        ]
        encounter.pending_movement = {
            "movement_id": "move_001",
            "entity_id": "ent_enemy_goblin_001",
            "start_position": {"x": 4, "y": 4},
            "target_position": {"x": 8, "y": 4},
            "current_position": {"x": 5, "y": 4},
            "remaining_path": [{"x": 6, "y": 4}],
            "count_movement": True,
            "use_dash": False,
            "status": "waiting_reaction",
            "waiting_request_id": "react_001",
        }
        repo.save(encounter)
        state = GetEncounterState(repo).execute("enc_view_test")
        self.assertEqual(state["reaction_requests"][0]["status"], "pending")
        self.assertEqual(state["pending_movement"]["status"], "waiting_reaction")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_projects_pending_reaction_requests_and_pending_movement -v`

Expected: FAIL with missing `reaction_requests`

- [ ] **Step 3: 写最小实现**

```python
def execute(self, encounter_id: str) -> dict[str, Any]:
    ...
    return {
        ...
        "reaction_requests": encounter.reaction_requests,
        "pending_movement": encounter.pending_movement,
        ...
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_projects_pending_reaction_requests_and_pending_movement -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/encounter/get_encounter_state.py /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_get_encounter_state.py
git commit -m "feat: project pending reactions in encounter state"
```

### Task 8: 更新运行时文档并做全量回归

**Files:**
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/docs/llm-runtime-tool-guide.md`
- Modify: `/Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py`

- [ ] **Step 1: 补文档**

```markdown
### `BeginMoveEncounterEntity`
- 可能返回 `movement_status = "waiting_reaction"`
- 这表示 LLM 必须先处理 `reaction_requests`

### `ResolveReactionRequest`
- 第一版只支持 `opportunity_attack`
- 借机攻击消耗 `reaction`，不消耗 `action`

### `ContinuePendingMovement`
- 玩家不借机时，直接调用这个 tool
- 它会把当前未处理 request 标成 `expired` 后继续移动
```

- [ ] **Step 2: 跑定向回归**

Run: `python3 -m unittest test.test_begin_move_encounter_entity test.test_resolve_reaction_request test.test_continue_pending_movement test.test_get_encounter_state -v`

Expected: PASS

- [ ] **Step 3: 跑全量回归**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`

Expected: `Ran ... tests ... OK`

- [ ] **Step 4: 提交**

```bash
git add /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/docs/llm-runtime-tool-guide.md /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/tools/services/__init__.py
git commit -m "docs: add reaction request runtime workflow"
```

---

## Self-Review

- Spec coverage: 覆盖了 `reaction_requests`、`pending_movement`、`BeginMoveEncounterEntity`、`ResolveReactionRequest`、`ContinuePendingMovement`、路径顺序借机、阻塞移动、玩家跳过借机继续移动、`GetEncounterState` 投影与文档更新。没有覆盖撤离、强制位移、长柄武器、法术反应，符合 spec 的“本次不做”。
- Placeholder scan: 计划中没有 `TODO`、`TBD` 或“稍后实现”这类占位描述。每个任务都给了目标文件、测试、命令和最小代码片段。
- Type consistency: 统一使用 `reaction_requests`、`pending_movement`、`movement_status`、`request_id`、`spell_instance_id` 等命名；执行入口固定为 `BeginMoveEncounterEntity` / `ResolveReactionRequest` / `ContinuePendingMovement`。
