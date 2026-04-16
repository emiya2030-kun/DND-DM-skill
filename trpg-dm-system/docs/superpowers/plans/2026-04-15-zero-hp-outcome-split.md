# Zero HP Outcome Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `HP=0` 的结果按实体类别分流：`monster` 删除并留骷髅、`summon` 直接消失、`pc/npc` 进入昏迷并在页面上显示红色高亮。

**Architecture:** 以 `UpdateHp` 作为唯一的 0 HP 分流入口，负责修改 encounter 运行态；地图残骸通过 `EncounterMap` 上的新字段投影到 battlemap；页面高亮只基于实体当前 `HP/condition/category` 渲染，不额外引入前端状态。

**Tech Stack:** Python dataclass models, service-layer rules, unittest, HTML string rendering in `RenderBattlemapView`

---

### Task 1: 锁定 0 HP 分流测试

**Files:**
- Modify: `test/test_update_hp.py`
- Modify: `test/test_opportunity_attack_player_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_zero_hp_monster_is_removed_and_leaves_skeleton_remains(self) -> None:
    result = service.execute(
        encounter_id="enc_update_hp_test",
        target_id="ent_enemy_goblin_001",
        hp_change=99,
        reason="massive damage",
        include_encounter_state=True,
    )

    updated = repo.get("enc_update_hp_test")
    assert updated is not None
    self.assertNotIn("ent_enemy_goblin_001", updated.entities)
    self.assertNotIn("ent_enemy_goblin_001", updated.turn_order)
    self.assertEqual(updated.map.remains[0]["icon"], "💀")
    self.assertEqual(updated.map.remains[0]["position"], {"x": 5, "y": 4})
    self.assertEqual(result["zero_hp_outcome"]["outcome"], "monster_removed_with_remains")


def test_zero_hp_summon_is_removed_without_remains(self) -> None:
    result = service.execute(
        encounter_id="enc_update_hp_test",
        target_id="ent_summon_wolf_001",
        hp_change=99,
        reason="dismissed by damage",
        include_encounter_state=True,
    )

    updated = repo.get("enc_update_hp_test")
    assert updated is not None
    self.assertNotIn("ent_summon_wolf_001", updated.entities)
    self.assertEqual(updated.map.remains, [])
    self.assertEqual(result["zero_hp_outcome"]["outcome"], "summon_removed")


def test_zero_hp_player_becomes_unconscious_and_stays_on_map(self) -> None:
    result = service.execute(
        encounter_id="enc_update_hp_test",
        target_id="ent_ally_eric_001",
        hp_change=99,
        reason="dropped to zero",
        include_encounter_state=True,
    )

    updated = repo.get("enc_update_hp_test")
    assert updated is not None
    self.assertIn("ent_ally_eric_001", updated.entities)
    self.assertIn("unconscious", updated.entities["ent_ally_eric_001"].conditions)
    self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 0)
    self.assertEqual(result["zero_hp_outcome"]["outcome"], "entity_unconscious")


def test_opportunity_attack_drop_to_zero_leaves_player_unconscious_at_trigger_position(self) -> None:
    continue_result = continue_move.execute_with_state(encounter_id="enc_opportunity_flow_test")
    updated = encounter_repo.get("enc_opportunity_flow_test")
    assert updated is not None
    self.assertEqual(continue_result["movement_status"], "interrupted")
    self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 5, "y": 4})
    self.assertIn("unconscious", updated.entities["ent_enemy_orc_001"].conditions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_update_hp test.test_opportunity_attack_player_flow`
Expected: FAIL because `EncounterMap` has no `remains`, `UpdateHp` does not remove entities or add `unconscious`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/services/combat/shared/update_hp.py
if target.hp["current"] == 0:
    zero_hp_outcome = self._resolve_zero_hp_outcome(encounter, target)


def _resolve_zero_hp_outcome(self, encounter: Encounter, target: EncounterEntity) -> dict[str, Any]:
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test.test_update_hp test.test_opportunity_attack_player_flow`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_update_hp.py test/test_opportunity_attack_player_flow.py tools/services/combat/shared/update_hp.py tools/models/map.py
git commit -m "feat: split zero hp outcomes by entity category"
```

### Task 2: 投影地图残骸到 battlemap

**Files:**
- Modify: `tools/models/map.py`
- Modify: `tools/services/map/render_battlemap_view.py`
- Test: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_battlemap_view_shows_skeleton_remains_on_empty_tile(self) -> None:
    encounter.map.remains = [
        {"remains_id": "remains_goblin_001", "icon": "💀", "position": {"x": 6, "y": 4}, "label": "哥布林尸骸"}
    ]

    payload = RenderBattlemapView().execute(encounter)

    self.assertIn("💀", payload["html"])
    self.assertIn("tile__remains", payload["html"])
    self.assertIn("哥布林尸骸", payload["html"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_render_battlemap_view`
Expected: FAIL because remains are not modeled or rendered.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/models/map.py
remains: list[dict[str, Any]] = field(default_factory=list)

# tools/services/map/render_battlemap_view.py
remains = self._find_remains_at(encounter, x, y)
if entity is None and remains is not None:
    occupant = f'<span class="tile__remains" title="{remains["label"]}">{remains["icon"]}</span>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_render_battlemap_view`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/models/map.py tools/services/map/render_battlemap_view.py test/test_render_battlemap_view.py
git commit -m "feat: render monster remains on battlemap"
```

### Task 3: 玩家/NPC 0 HP 红色高亮

**Files:**
- Modify: `tools/services/map/render_battlemap_view.py`
- Test: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_battlemap_view_marks_zero_hp_player_with_red_outline(self) -> None:
    player = encounter.entities["ent_ally_eric_001"]
    player.hp["current"] = 0
    player.conditions = ["unconscious"]

    payload = RenderBattlemapView().execute(encounter)

    self.assertIn("token--downed", payload["html"])
    self.assertIn("character-card--downed", payload["html"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_render_battlemap_view`
Expected: FAIL because no downed CSS class exists.

- [ ] **Step 3: Write minimal implementation**

```python
def _is_downed_entity(self, entity: EncounterEntity) -> bool:
    return entity.category in {"pc", "npc"} and entity.hp.get("current", 0) == 0


def _occupant_class(self, entity: EncounterEntity) -> str:
    classes = ["token", ...]
    if self._is_downed_entity(entity):
        classes.append("token--downed")
    return " ".join(classes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest test.test_render_battlemap_view`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/map/render_battlemap_view.py test/test_render_battlemap_view.py
git commit -m "feat: highlight downed players on battlemap"
```

### Task 4: 全量验证

**Files:**
- No code changes required

- [ ] **Step 1: Run focused regression**

Run: `python3 -m unittest test.test_update_hp test.test_opportunity_attack_player_flow test.test_render_battlemap_view`
Expected: PASS

- [ ] **Step 2: Run full regression**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 3: Review diff**

Run: `git diff -- tools/models/map.py tools/services/combat/shared/update_hp.py tools/services/map/render_battlemap_view.py test/test_update_hp.py test/test_opportunity_attack_player_flow.py test/test_render_battlemap_view.py`
Expected: only zero-HP split and render changes

- [ ] **Step 4: Commit**

```bash
git add tools/models/map.py tools/services/combat/shared/update_hp.py tools/services/map/render_battlemap_view.py test/test_update_hp.py test/test_opportunity_attack_player_flow.py test/test_render_battlemap_view.py docs/superpowers/plans/2026-04-15-zero-hp-outcome-split.md
git commit -m "feat: split zero hp outcomes and render remains"
```
