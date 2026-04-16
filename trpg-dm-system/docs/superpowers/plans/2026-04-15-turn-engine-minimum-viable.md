# Turn Engine Minimum Viable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 encounter 增加最小可用的回合推进层，在切换到新行动者时统一重置动作经济与移动资源，并通过 `encounter_state` 暴露最新结果。

**Architecture:** 在 `tools/services/encounter/turns/` 中新增纯回合规则层和 service 入口层。纯规则层只负责“下一位是谁、是否进入新 round、如何重置当前单位回合资源”；service 层负责读写仓储并返回最新 `encounter_state`。旧的 `EncounterService.advance_turn*` 直接委托给新层，避免出现两套推进逻辑。

**Tech Stack:** Python 3.9, TinyDB repository, unittest

---

### Task 1: 建 turn engine 纯规则层与测试

**Files:**
- Create: `tools/services/encounter/turns/__init__.py`
- Create: `tools/services/encounter/turns/turn_engine.py`
- Create: `test/test_turn_engine.py`

- [ ] **Step 1: 写失败测试，锁定最小回合规则**

```python
def test_advance_turn_switches_to_next_entity_and_resets_turn_resources():
    encounter = build_encounter_with_two_entities()
    current = encounter.entities["ent_ally_eric_001"]
    current.action_economy = {"action_used": True, "bonus_action_used": True, "reaction_used": True}
    current.speed["remaining"] = 5
    current.combat_flags["movement_spent_feet"] = 25

    next_entity = encounter.entities["ent_ally_lia_001"]
    next_entity.action_economy = {"action_used": True, "bonus_action_used": True, "reaction_used": True}
    next_entity.speed["remaining"] = 0
    next_entity.combat_flags["movement_spent_feet"] = 30

    updated = advance_turn(encounter)

    assert updated.current_entity_id == "ent_ally_lia_001"
    assert updated.round == 1
    assert updated.entities["ent_ally_lia_001"].action_economy == {
        "action_used": False,
        "bonus_action_used": False,
        "reaction_used": False,
        "free_interaction_used": False,
    }
    assert updated.entities["ent_ally_lia_001"].speed["remaining"] == 30
    assert updated.entities["ent_ally_lia_001"].combat_flags["movement_spent_feet"] == 0
```

- [ ] **Step 2: 补 wrap round 与 `current_entity_id is None` 的失败测试**

```python
def test_advance_turn_wraps_to_first_entity_and_increments_round():
    encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_lia_001")
    updated = advance_turn(encounter)
    assert updated.current_entity_id == "ent_ally_eric_001"
    assert updated.round == 2


def test_advance_turn_with_no_current_entity_selects_first_and_resets_it():
    encounter = build_encounter_with_two_entities(current_entity_id=None)
    updated = advance_turn(encounter)
    assert updated.current_entity_id == "ent_ally_eric_001"
    assert updated.round == 1
```

- [ ] **Step 3: 实现最小 turn engine**

```python
def reset_turn_resources(entity: EncounterEntity) -> None:
    entity.action_economy = {
        "action_used": False,
        "bonus_action_used": False,
        "reaction_used": False,
        "free_interaction_used": False,
    }
    entity.speed["remaining"] = entity.speed["walk"]
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    combat_flags["movement_spent_feet"] = 0
    entity.combat_flags = combat_flags


def advance_turn(encounter: Encounter) -> Encounter:
    if not encounter.turn_order:
        raise ValueError("cannot advance turn without turn_order")
    if encounter.current_entity_id is None:
        encounter.current_entity_id = encounter.turn_order[0]
        reset_turn_resources(encounter.entities[encounter.current_entity_id])
        return encounter
    current_index = encounter.turn_order.index(encounter.current_entity_id)
    next_index = current_index + 1
    if next_index >= len(encounter.turn_order):
        encounter.current_entity_id = encounter.turn_order[0]
        encounter.round += 1
    else:
        encounter.current_entity_id = encounter.turn_order[next_index]
    reset_turn_resources(encounter.entities[encounter.current_entity_id])
    return encounter
```

- [ ] **Step 4: 运行定向测试**

Run: `python3 -m unittest test.test_turn_engine -v`
Expected: PASS

### Task 2: 建 service 入口并接回 EncounterService

**Files:**
- Create: `tools/services/encounter/turns/advance_turn.py`
- Modify: `tools/services/encounter/__init__.py`
- Modify: `tools/services/__init__.py`
- Modify: `tools/services/encounter/manage_encounter_entities.py`
- Create: `test/test_advance_turn.py`
- Modify: `test/test_encounter_service.py`

- [ ] **Step 1: 写 service 级失败测试**

```python
def test_advance_turn_service_returns_latest_state():
    repo.save(build_encounter_with_two_entities())
    result = AdvanceTurn(repo).execute_with_state("enc_service_test")
    assert result["encounter_state"]["current_turn_entity"]["id"] == "ent_ally_lia_001"
    assert result["encounter_state"]["current_turn_entity"]["movement_remaining"] == "30 feet"
    assert result["encounter_state"]["current_turn_entity"]["actions"]["action_used"] is False
```

- [ ] **Step 2: 让 `EncounterService.advance_turn*` 委托给新 service**

```python
def advance_turn(self, encounter_id: str) -> Encounter:
    return AdvanceTurn(self.repository).execute(encounter_id)


def advance_turn_with_state(self, encounter_id: str) -> dict[str, object]:
    return AdvanceTurn(self.repository).execute_with_state(encounter_id)
```

- [ ] **Step 3: 实现 service 入口与导出**

```python
class AdvanceTurn:
    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(self, encounter_id: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        updated = advance_turn(encounter)
        return self.repository.save(updated)

    def execute_with_state(self, encounter_id: str) -> dict[str, object]:
        updated = self.execute(encounter_id)
        return {
            "encounter_id": updated.encounter_id,
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }
```

- [ ] **Step 4: 运行 service 相关测试**

Run: `python3 -m unittest test.test_advance_turn test.test_encounter_service -v`
Expected: PASS

### Task 3: 补 LLM 运行说明并做回归

**Files:**
- Modify: `docs/llm-runtime-tool-guide.md`

- [ ] **Step 1: 在运行手册中新增回合推进说明**

补充：

- `AdvanceTurn` 是回合切换入口
- 切到新单位时会自动重置：
  - `action_economy`
  - `speed.remaining`
  - `combat_flags.movement_spent_feet`
- `GetEncounterState` 仍然是前端刷新事实源

- [ ] **Step 2: 跑全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 3: 检查差异**

Run: `git diff -- tools/services/encounter tools/services/__init__.py test docs/llm-runtime-tool-guide.md`
Expected: only turn engine, service wiring, tests, and runtime guide changes
