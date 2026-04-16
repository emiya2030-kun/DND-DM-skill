# Forced Movement State Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `GetEncounterState` 投影最近一次强制位移摘要，并让 localhost 地图页面通过 `RenderBattlemapView` 显示对应轨迹高亮。

**Architecture:** `GetEncounterState` 通过事件仓储读取最近一条 `forced_movement_resolved`，整理出 `recent_forced_movement` 结构和中文摘要。`RenderBattlemapView` 只消费这个投影字段，给地图格子和图例添加高亮，不直接读取事件日志。

**Tech Stack:** Python 3、unittest、TinyDB 事件仓储、现有 encounter state 与 battlemap HTML 渲染服务

---

### Task 1: 强制位移状态投影

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_projects_recent_forced_movement_summary(self) -> None:
    state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")
    forced = state["recent_forced_movement"]
    self.assertEqual(forced["moved_feet"], 10)
    self.assertEqual(forced["summary"], "Goblin被 Push 推离 10 尺，移动到 (5,2)。")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_projects_recent_forced_movement_summary`

Expected: FAIL，缺少 `recent_forced_movement` 字段或摘要不匹配

- [ ] **Step 3: Write minimal implementation**

```python
class GetEncounterState:
    def __init__(..., event_repository: EventRepository | None = None):
        self.event_repository = event_repository or EventRepository()

    def execute(...):
        return {
            ...,
            "recent_forced_movement": self._build_recent_forced_movement(encounter),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_projects_recent_forced_movement_summary`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  tools/services/encounter/get_encounter_state.py \
  test/test_get_encounter_state.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: project recent forced movement in encounter state"
```

### Task 2: 地图轨迹高亮

**Files:**
- Modify: `tools/services/map/render_battlemap_view.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_highlights_recent_forced_movement_cells(self) -> None:
    payload = RenderBattlemapView().execute(encounter, recent_forced_movement={
        "start_position": {"x": 5, "y": 4},
        "resolved_path": [{"x": 6, "y": 4}],
        "final_position": {"x": 6, "y": 4},
        "blocked": False,
    })
    self.assertIn("tile--forced-origin", payload["html"])
    self.assertIn("tile--forced-path", payload["html"])
    self.assertIn("tile--forced-destination", payload["html"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_render_battlemap_view.RenderBattlemapViewTests.test_render_highlights_recent_forced_movement_cells`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def execute(self, encounter: Encounter, recent_forced_movement: dict[str, object] | None = None) -> dict[str, object]:
    ...

def _tile_classes(...):
    if current_cell == origin:
        classes.append("tile--forced-origin")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_render_battlemap_view.RenderBattlemapViewTests.test_render_highlights_recent_forced_movement_cells`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  tools/services/map/render_battlemap_view.py \
  tools/services/encounter/get_encounter_state.py \
  test/test_render_battlemap_view.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: render forced movement highlight on battlemap"
```

### Task 3: 保留最近一次高亮直到被下一次强制位移覆盖

**Files:**
- Modify: `test/test_get_encounter_state.py`
- Modify: `tools/services/encounter/get_encounter_state.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_uses_latest_forced_movement_event_only(self) -> None:
    state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")
    forced = state["recent_forced_movement"]
    self.assertEqual(forced["final_position"], {"x": 6, "y": 2})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_uses_latest_forced_movement_event_only`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
events = self.event_repository.list_by_encounter(encounter.encounter_id)
forced_events = [event for event in events if event.event_type == "forced_movement_resolved"]
latest = forced_events[-1] if forced_events else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_get_encounter_state.GetEncounterStateTests.test_execute_uses_latest_forced_movement_event_only`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  tools/services/encounter/get_encounter_state.py \
  test/test_get_encounter_state.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "test: keep latest forced movement projection stable"
```

### Task 4: 回归验证

**Files:**
- Modify: `test/test_get_encounter_state.py`
- Modify: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Run focused regression**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_get_encounter_state test.test_render_battlemap_view`

Expected: PASS

- [ ] **Step 2: Run full regression**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest discover -s test -p 'test_*.py'`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  test/test_get_encounter_state.py \
  test/test_render_battlemap_view.py \
  tools/services/encounter/get_encounter_state.py \
  tools/services/map/render_battlemap_view.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "test: verify forced movement state projection"
```
