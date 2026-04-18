# Player Summon Shared Turn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让玩家控制、带有 `summoner_entity_id` 的召唤物并入宿主回合，允许在同一个玩家回合中交错操纵宿主与召唤物。

**Architecture:** 通过一个共享回合判定 helper 统一识别“玩家共享回合召唤物”，并把“当前行动者是否合法”从单一 `current_entity_id` 判定提升为“当前回合编组成员”判定。召唤物实体本身、地图占位和动作经济保持独立，但不再单独占据 `turn_order`，`GetEncounterState` 负责把当前回合编组摘要稳定投影给 LLM 和前端。

**Tech Stack:** Python 3, unittest/pytest, runtime command layer, encounter services, battlemap projection

---

### Task 1: 建立共享回合判定与召唤物插入规则

**Files:**
- Create: `tools/services/encounter/shared_turns.py`
- Modify: `tools/services/spells/summons/create_summoned_entity.py`
- Modify: `tools/services/spells/summons/find_familiar_builder.py`
- Modify: `tools/services/spells/summons/find_steed_builder.py`
- Test: `test/test_player_shared_turns.py`
- Test: `test/test_use_pact_of_the_chain.py`

- [ ] **Step 1: 写失败测试，锁定共享回合召唤物不再插入 `turn_order`**

```python
def test_player_controlled_summon_with_summoner_id_does_not_insert_into_turn_order() -> None:
    encounter = build_encounter_with_warlock_and_enemy()
    summon = build_player_summon(
        entity_id="ent_familiar_001",
        summoner_entity_id="ent_warlock_001",
        initiative=14,
    )

    result = create_summoned_entity_by_initiative(encounter=encounter, summon=summon)

    assert summon.entity_id in encounter.entities
    assert summon.entity_id not in encounter.turn_order
    assert result["shared_turn_owner_id"] == "ent_warlock_001"
```

- [ ] **Step 2: 跑测试，确认当前实现确实失败**

Run: `python3 -m pytest test/test_player_shared_turns.py::test_player_controlled_summon_with_summoner_id_does_not_insert_into_turn_order -q`

Expected: `FAILED`，因为当前 `create_summoned_entity_by_initiative()` 会直接把召唤物插入 `turn_order`。

- [ ] **Step 3: 实现共享回合 helper，集中封装判定逻辑**

```python
def get_shared_turn_owner_id(entity: EncounterEntity, encounter: Encounter) -> str | None:
    if entity.category != "summon":
        return None
    if entity.controller != "player":
        return None
    source_ref = entity.source_ref if isinstance(entity.source_ref, dict) else {}
    owner_id = source_ref.get("summoner_entity_id")
    if not isinstance(owner_id, str) or not owner_id:
        return None
    owner = encounter.entities.get(owner_id)
    if owner is None or owner.controller != "player":
        return None
    return owner_id


def is_shared_turn_summon(entity: EncounterEntity, encounter: Encounter) -> bool:
    return get_shared_turn_owner_id(entity, encounter) is not None
```

- [ ] **Step 4: 让召唤物插入逻辑识别共享回合召唤物**

```python
shared_turn_owner_id = get_shared_turn_owner_id(summon, encounter)
encounter.entities[summon.entity_id] = summon
if shared_turn_owner_id is not None:
    return {
        "entity_id": summon.entity_id,
        "shared_turn_owner_id": shared_turn_owner_id,
        "inserted_into_turn_order": False,
    }
```

- [ ] **Step 5: 回归 `find_familiar` / `find_steed` builder，确保 source_ref 满足共享回合判定**

```python
source_ref = {
    "summoner_entity_id": caster.entity_id,
    "source_spell_id": "find_familiar",
    "summon_template": "find_familiar",
    "familiar": True,
}
```

```python
source_ref = {
    "summoner_entity_id": caster.entity_id,
    "source_spell_id": "find_steed",
    "summon_template": "otherworldly_steed",
    "controlled_mount": True,
    "shares_initiative_with_summoner": True,
}
```

- [ ] **Step 6: 运行测试，确认共享回合插入行为通过**

Run: `python3 -m pytest test/test_player_shared_turns.py test/test_use_pact_of_the_chain.py -q`

Expected: 相关测试 `PASS`，并且旧的“召唤物必进 turn_order”断言要改成“共享回合召唤物不进 turn_order，但实体仍存在”。

- [ ] **Step 7: Commit**

```bash
git add tools/services/encounter/shared_turns.py tools/services/spells/summons/create_summoned_entity.py tools/services/spells/summons/find_familiar_builder.py tools/services/spells/summons/find_steed_builder.py test/test_player_shared_turns.py test/test_use_pact_of_the_chain.py
git commit -m "feat: group player summons into owner turns"
```

### Task 2: 提升动作合法性到“当前回合编组”

**Files:**
- Modify: `tools/services/combat/actions/use_help_attack.py`
- Modify: `tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/class_features/warlock/use_pact_of_the_chain.py`
- Create: `tools/services/encounter/shared_turn_access.py`
- Test: `test/test_use_help_attack.py`
- Test: `test/test_runtime_move_entity.py`
- Test: `test/test_runtime_cast_spell.py`

- [ ] **Step 1: 写失败测试，锁定宿主回合内允许召唤物行动**

```python
def test_use_help_attack_allows_shared_turn_summon_on_owner_turn() -> None:
    encounter = build_encounter_with_kael_and_sphinx()
    encounter.current_entity_id = "ent_kael_001"

    result = UseHelpAttack(repo).execute(
        encounter_id=encounter.encounter_id,
        actor_id="ent_sphinx_001",
        target_id="ent_goblin_001",
    )

    assert result["actor_id"] == "ent_sphinx_001"
```

- [ ] **Step 2: 跑测试，确认当前校验失败在 `not_actor_turn`**

Run: `python3 -m pytest test/test_use_help_attack.py::test_use_help_attack_allows_shared_turn_summon_on_owner_turn -q`

Expected: `FAILED`，错误原因为 `not_actor_turn`。

- [ ] **Step 3: 抽出统一访问校验 helper**

```python
def ensure_actor_can_act_in_current_turn(encounter: Encounter, actor_id: str) -> None:
    current_id = encounter.current_entity_id
    if current_id is None:
        raise ValueError("no_current_turn_entity")
    if actor_id == current_id:
        return
    actor = encounter.entities.get(actor_id)
    if actor is None:
        raise ValueError("actor_not_found")
    if get_shared_turn_owner_id(actor, encounter) == current_id:
        return
    raise ValueError("not_actor_turn")
```

- [ ] **Step 4: 把现有单点 `current_entity_id == actor_id` 校验替换为共享回合访问校验**

```python
from tools.services.encounter.shared_turn_access import ensure_actor_can_act_in_current_turn

ensure_actor_can_act_in_current_turn(encounter, actor_id)
```

需要优先替换这些主链：

- `UseHelpAttack`
- 移动入口
- 攻击入口
- 施法入口

- [ ] **Step 5: 补测试，锁定宿主和召唤物动作经济独立**

```python
def test_shared_turn_summon_action_does_not_consume_owner_action() -> None:
    encounter = build_encounter_with_kael_and_sphinx()
    encounter.current_entity_id = "ent_kael_001"

    UseHelpAttack(repo).execute(
        encounter_id=encounter.encounter_id,
        actor_id="ent_sphinx_001",
        target_id="ent_goblin_001",
    )

    updated = repo.get(encounter.encounter_id)
    assert updated.entities["ent_sphinx_001"].action_economy["action_used"] is True
    assert updated.entities["ent_kael_001"].action_economy.get("action_used") is not True
```

- [ ] **Step 6: 运行主链测试，确认共享回合访问已经打通**

Run: `python3 -m pytest test/test_use_help_attack.py test/test_runtime_move_entity.py test/test_runtime_cast_spell.py -q`

Expected: 相关测试 `PASS`，且没有把真正的非当前回合敌方单位放开。

- [ ] **Step 7: Commit**

```bash
git add tools/services/encounter/shared_turn_access.py tools/services/combat/actions/use_help_attack.py tools/services/encounter/begin_move_encounter_entity.py tools/services/combat/attack/execute_attack.py tools/services/spells/encounter_cast_spell.py tools/services/class_features/warlock/use_pact_of_the_chain.py test/test_use_help_attack.py test/test_runtime_move_entity.py test/test_runtime_cast_spell.py
git commit -m "feat: allow shared-turn summons to act on owner turns"
```

### Task 3: 把共享回合编组投影到 `GetEncounterState`

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `scripts/run_battlemap_localhost.py`
- Test: `test/test_use_pact_of_the_chain.py`
- Test: `test/test_get_encounter_state_shared_turns.py`
- Test: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: 写失败测试，锁定 `current_turn_group` 投影结构**

```python
def test_get_encounter_state_projects_current_turn_group_for_owner_and_summon() -> None:
    encounter = build_encounter_with_kael_and_sphinx()
    encounter.current_entity_id = "ent_kael_001"

    state = GetEncounterState(repo).execute(encounter.encounter_id)

    assert state["current_turn_group"]["owner_entity_id"] == "ent_kael_001"
    assert [item["name"] for item in state["current_turn_group"]["controlled_members"]] == [
        "Kael",
        "Sphinx of Wonder",
    ]
```

- [ ] **Step 2: 跑测试，确认当前状态对象还没有该字段**

Run: `python3 -m pytest test/test_get_encounter_state_shared_turns.py::test_get_encounter_state_projects_current_turn_group_for_owner_and_summon -q`

Expected: `FAILED`，因为 `current_turn_group` 尚未投影。

- [ ] **Step 3: 在 `GetEncounterState` 里增加统一编组摘要构建**

```python
def _build_current_turn_group(self, encounter: Encounter, current_entity: EncounterEntity | None) -> dict[str, Any] | None:
    if current_entity is None:
        return None
    members = [{"entity_id": current_entity.entity_id, "name": current_entity.name, "relation": "owner"}]
    for entity in encounter.entities.values():
        if entity.entity_id == current_entity.entity_id:
            continue
        if get_shared_turn_owner_id(entity, encounter) == current_entity.entity_id:
            members.append({"entity_id": entity.entity_id, "name": entity.name, "relation": "summon"})
    return {
        "owner_entity_id": current_entity.entity_id,
        "owner_name": current_entity.name,
        "controlled_members": members,
    }
```

- [ ] **Step 4: 把 battlemap localhost 首屏也对齐共享回合状态**

```python
initial_state = fetch_runtime_encounter_state(self.runtime_base_url, encounter_id)
html = render_localhost_battlemap_page(
    encounter_id=encounter_id,
    initial_state=initial_state,
    page_title=self.page_title,
)
```

这里不需要新增新参数协议，只需要确保页面首屏和轮询都能看到 `current_turn_group`。

- [ ] **Step 5: 跑状态投影和 localhost 页面测试**

Run: `python3 -m pytest test/test_get_encounter_state_shared_turns.py test/test_run_battlemap_localhost.py -q`

Expected: `PASS`

- [ ] **Step 6: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py scripts/run_battlemap_localhost.py test/test_use_pact_of_the_chain.py test/test_get_encounter_state_shared_turns.py test/test_run_battlemap_localhost.py
git commit -m "feat: project shared turn groups in encounter state"
```

### Task 4: 共享回合回归与联调验证

**Files:**
- Modify: `test/test_runtime_http_server.py`
- Modify: `docs/development-plan.md`
- Modify: `docs/llm-runtime-tool-guide.md`
- Test: `test/test_runtime_use_help_attack.py`
- Test: `test/test_battlemap_runtime_integration.py`

- [ ] **Step 1: 补 runtime 级联测试，锁定“Kael 回合里 Sphinx 协助 -> Kael 攻击”可走通**

```python
def test_runtime_shared_turn_allows_summon_help_then_owner_attack() -> None:
    help_result = dispatch("use_help_attack", {
        "encounter_id": "enc_shared_turn_test",
        "actor_id": "ent_sphinx_001",
        "target_id": "ent_goblin_001",
    })
    attack_result = dispatch("execute_attack", {
        "encounter_id": "enc_shared_turn_test",
        "actor_id": "ent_kael_001",
        "target_id": "ent_goblin_001",
        "weapon_id": "eldritch_blast",
    })

    assert help_result["encounter_state"]["current_turn_entity"]["name"] == "Kael"
    assert attack_result["encounter_state"]["recent_activity"]
```

- [ ] **Step 2: 跑失败测试，确认当前 runtime 链路至少一处仍按旧回合规则拦截**

Run: `python3 -m pytest test/test_runtime_use_help_attack.py test/test_battlemap_runtime_integration.py -q`

Expected: 至少一个用例 `FAILED`，原因应是共享回合行为尚未完全贯通。

- [ ] **Step 3: 修正文档，明确 LLM 调用不变，只是“合法 actor”范围扩大**

```markdown
- 玩家共享回合召唤物继续使用原有动作命令。
- 仍然传自己的 `actor_id`。
- 当前回合若属于其宿主，则该召唤物可合法行动。
- `GetEncounterState.current_turn_group` 可用于判断本回合可操纵成员。
```

- [ ] **Step 4: 运行最终回归测试集**

Run: `python3 -m pytest test/test_player_shared_turns.py test/test_use_pact_of_the_chain.py test/test_use_help_attack.py test/test_runtime_use_help_attack.py test/test_runtime_move_entity.py test/test_runtime_cast_spell.py test/test_get_encounter_state_shared_turns.py test/test_run_battlemap_localhost.py test/test_battlemap_runtime_integration.py test/test_runtime_http_server.py -q`

Expected: 全部 `PASS`

- [ ] **Step 5: 本地重启联调服务并做一次真实战斗验证**

Run: `python3 scripts/run_battlemap_localhost.py --port 8782 --runtime-base-url http://127.0.0.1:8771 --encounter-id enc_warlock_lv5_test`

Expected:
- 页面打开仍指向 `enc_warlock_lv5_test`
- `GetEncounterState.current_turn_group` 显示 `Kael / Sphinx of Wonder`
- 可先用 `Sphinx` 执行 `use_help_attack`
- 再用 `Kael` 执行 `execute_attack` 或 `cast_spell`

- [ ] **Step 6: Commit**

```bash
git add test/test_runtime_http_server.py test/test_runtime_use_help_attack.py test/test_battlemap_runtime_integration.py docs/development-plan.md docs/llm-runtime-tool-guide.md
git commit -m "feat: support shared turns for player summons"
```
