# Turn Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 encounter 增加最小可用的 `turn_effects` 运行时模型，并在 `StartTurn` / `EndTurn` 自动结算开始回合与结束回合触发效果。

**Architecture:** 在 `EncounterEntity` 上新增独立 `turn_effects` 字段，避免把未来触发规则塞进 `conditions` 或 `combat_flags`。在 `tools/services/encounter/turns/` 中新增专门的 effect resolver，由 `StartTurn` 和 `EndTurn` 调用；resolver 只编排触发、豁免、伤害和 condition 更新，底层继续复用现有伤害与 condition 服务。

**Tech Stack:** Python 3.9, TinyDB repository, unittest

---

### Task 1: 扩 EncounterEntity 模型并锁定序列化行为

**Files:**
- Modify: `tools/models/encounter_entity.py`
- Test: `test/test_encounter_entity.py`

- [ ] **Step 1: 写失败测试，确认 `turn_effects` 能正常 round-trip**

```python
def test_encounter_entity_round_trips_turn_effects():
    entity = EncounterEntity.from_dict(
        {
            "entity_id": "ent_test",
            "name": "测试角色",
            "side": "ally",
            "category": "pc",
            "controller": "player",
            "position": {"x": 1, "y": 1},
            "hp": {"current": 10, "max": 10, "temp": 0},
            "ac": 15,
            "speed": {"walk": 30, "remaining": 30},
            "initiative": 12,
            "turn_effects": [
                {
                    "effect_id": "effect_hold_person_001",
                    "name": "定身术持续效果",
                    "trigger": "end_of_turn",
                }
            ],
        }
    )

    assert entity.turn_effects == [
        {
            "effect_id": "effect_hold_person_001",
            "name": "定身术持续效果",
            "trigger": "end_of_turn",
        }
    ]
    assert entity.to_dict()["turn_effects"][0]["effect_id"] == "effect_hold_person_001"
```

- [ ] **Step 2: 运行定向测试，确认它先失败**

Run: `python3 -m unittest test.test_encounter_entity -v`
Expected: FAIL because `EncounterEntity` does not accept or serialize `turn_effects`

- [ ] **Step 3: 最小实现 `turn_effects` 字段**

```python
turn_effects: list[dict[str, Any]] = field(default_factory=list)
```

并在 `to_dict()` 中追加：

```python
"turn_effects": self.turn_effects,
```

- [ ] **Step 4: 重跑定向测试**

Run: `python3 -m unittest test.test_encounter_entity -v`
Expected: PASS

### Task 2: 写 turn effects resolver 的失败测试

**Files:**
- Create: `tools/services/encounter/turns/turn_effects.py`
- Create: `test/test_turn_effects.py`

- [ ] **Step 1: 写失败测试，锁定“回合结束再豁免解除状态”**

```python
def test_resolve_turn_effects_removes_condition_and_effect_on_successful_end_of_turn_save():
    encounter = build_encounter_with_turn_effect_target()
    target = encounter.entities["ent_target"]
    target.conditions = ["paralyzed"]
    target.turn_effects = [
        {
            "effect_id": "effect_hold_person_001",
            "name": "定身术持续效果",
            "source_entity_id": "ent_caster",
            "trigger": "end_of_turn",
            "save": {"ability": "wis", "dc": 15, "on_success_remove_effect": True},
            "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
            "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "remove_after_trigger": False,
        }
    ]

    result = resolve_turn_effects(encounter=encounter, entity_id="ent_target", trigger="end_of_turn")

    assert result[0]["save"]["success"] is True
    assert "paralyzed" not in target.conditions
    assert target.turn_effects == []
```

- [ ] **Step 2: 写失败测试，锁定“回合结束持续伤害并移除 effect”**

```python
def test_resolve_turn_effects_applies_damage_and_removes_one_shot_effect():
    encounter = build_encounter_with_turn_effect_target()
    target = encounter.entities["ent_target"]
    target.turn_effects = [
        {
            "effect_id": "effect_acid_001",
            "name": "强酸残留",
            "source_entity_id": "ent_caster",
            "trigger": "end_of_turn",
            "save": None,
            "on_trigger": {
                "damage_parts": [{"source": "effect:acid", "formula": "2d4", "damage_type": "acid"}],
                "apply_conditions": [],
                "remove_conditions": [],
            },
            "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "remove_after_trigger": True,
        }
    ]

    result = resolve_turn_effects(
        encounter=encounter,
        entity_id="ent_target",
        trigger="end_of_turn",
        damage_roll_overrides={"effect:acid": {"rolls": [4, 3], "modifier": 0}},
    )

    assert result[0]["trigger_damage_resolution"]["total_damage"] == 7
    assert target.hp["current"] == 3
    assert target.turn_effects == []
```

- [ ] **Step 3: 运行定向测试，确认失败原因正确**

Run: `python3 -m unittest test.test_turn_effects -v`
Expected: FAIL because `resolve_turn_effects` does not exist yet

### Task 3: 实现最小 resolver

**Files:**
- Create: `tools/services/encounter/turns/turn_effects.py`
- Modify: `tools/services/encounter/turns/__init__.py`

- [ ] **Step 1: 实现最小入口与触发筛选**

```python
def resolve_turn_effects(
    *,
    encounter: Encounter,
    entity_id: str,
    trigger: str,
    damage_roll_overrides: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    entity = encounter.entities[entity_id]
    matching_effects = [
        effect for effect in entity.turn_effects
        if effect.get("trigger") == trigger
    ]
    ...
```

- [ ] **Step 2: 实现 `on_trigger` 伤害与 condition 更新**

核心最小代码应包含：

```python
damage_resolution = _resolve_effect_damage(
    target=entity,
    damage_parts=outcome.get("damage_parts", []),
    damage_roll_overrides=damage_roll_overrides,
)
_apply_condition_changes(entity, apply=outcome.get("apply_conditions", []), remove=outcome.get("remove_conditions", []))
```

- [ ] **Step 3: 实现最小豁免判断**

使用目标实体现有属性直接算：

```python
save_bonus = int(entity.ability_mods.get(save_ability, 0))
if save_ability in entity.save_proficiencies:
    save_bonus += int(entity.proficiency_bonus)
total = base_roll + save_bonus
success = total >= save_dc
```

并约定默认 `base_roll = 20` 仅用于当前 resolver 单元测试，通过 `save_roll_overrides` 显式覆盖；这样可以让测试稳定，不引入骰子依赖。

- [ ] **Step 4: 实现 effect 自身移除规则**

```python
if effect.get("remove_after_trigger"):
    remove_effect = True
if save_success and bool(save_config.get("on_success_remove_effect")):
    remove_effect = True
```

最后从 `entity.turn_effects` 中删除对应 `effect_id`。

- [ ] **Step 5: 重跑定向测试**

Run: `python3 -m unittest test.test_turn_effects -v`
Expected: PASS

### Task 4: 把 resolver 接进 StartTurn / EndTurn

**Files:**
- Modify: `tools/services/encounter/turns/start_turn.py`
- Modify: `tools/services/encounter/turns/end_turn.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Create: `test/test_start_turn.py`
- Create: `test/test_end_turn.py`

- [ ] **Step 1: 写 service 级失败测试，锁定 `StartTurn.execute_with_state()` 回传 effect 结果**

```python
def test_start_turn_execute_with_state_returns_turn_effect_resolutions():
    repo.save(build_encounter_with_start_of_turn_effect())
    result = StartTurn(repo).execute_with_state("enc_start_turn")
    assert len(result["turn_effect_resolutions"]) == 1
    assert result["turn_effect_resolutions"][0]["trigger"] == "start_of_turn"
```

- [ ] **Step 2: 写 service 级失败测试，锁定 `EndTurn.execute_with_state()` 回传 effect 结果**

```python
def test_end_turn_execute_with_state_returns_turn_effect_resolutions():
    repo.save(build_encounter_with_end_of_turn_effect())
    result = EndTurn(repo).execute_with_state("enc_end_turn")
    assert len(result["turn_effect_resolutions"]) == 1
    assert result["turn_effect_resolutions"][0]["trigger"] == "end_of_turn"
```

- [ ] **Step 3: 修改 service 返回结构**

```python
return {
    "encounter_id": updated.encounter_id,
    "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
    "turn_effect_resolutions": resolutions,
}
```

- [ ] **Step 4: 在 turn engine 接 resolver**

`start_turn(encounter)` 改为返回：

```python
tuple[Encounter, list[dict[str, object]]]
```

流程：

1. 选定当前实体
2. 刷新资源
3. 调 `resolve_turn_effects(..., trigger="start_of_turn")`
4. 返回更新后的 encounter 和 resolutions

`end_turn(encounter)` 同理，只是不刷新资源，trigger 改为 `end_of_turn`。

- [ ] **Step 5: 跑 service 相关测试**

Run: `python3 -m unittest test.test_turn_effects test.test_start_turn test.test_end_turn -v`
Expected: PASS

### Task 5: 补回归测试与运行手册

**Files:**
- Modify: `test/test_turn_engine.py`
- Modify: `test/test_encounter_service.py`
- Modify: `docs/llm-runtime-tool-guide.md`

- [ ] **Step 1: 回归已有 turn engine 测试**

补充断言：

- `AdvanceTurn` 仍然不触发 `turn_effects`
- `StartTurn` 才触发 `start_of_turn`
- `EndTurn` 才触发 `end_of_turn`

- [ ] **Step 2: 更新 LLM runtime 手册**

新增说明：

- `turn_effects` 是开始/结束回合触发效果的运行时字段
- `StartTurn.execute_with_state()` / `EndTurn.execute_with_state()` 会额外返回 `turn_effect_resolutions`
- 前端仍以 `encounter_state` 作为刷新事实源

- [ ] **Step 3: 运行全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 4: 检查最终差异**

Run: `git diff -- tools/models/encounter_entity.py tools/services/encounter/turns test docs/llm-runtime-tool-guide.md`
Expected: only `turn_effects` model, resolver, turn service wiring, tests, and runtime guide changes
