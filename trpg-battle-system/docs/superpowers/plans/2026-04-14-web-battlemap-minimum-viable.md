# Web Battlemap Minimum Viable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimum viable web battlemap renderer that turns encounter data into a player-facing HTML grid plus LLM-facing `map_notes`, and expose both through `get_encounter_state`.

**Architecture:** Keep `EncounterMap` as the single fact source. Add a dedicated `app/services/map/` slice with one renderer for battlemap HTML and one builder for structured `map_notes`, then compose them into `GetEncounterState` without pushing rendering logic into the existing projector.

**Tech Stack:** Python, dataclass-backed domain models, unittest, inline HTML/CSS generation

---

### Task 1: Add Map Service Tests First

**Files:**
- Create: `test/test_render_battlemap_view.py`
- Modify: `test/test_get_encounter_state.py`
- Test: `test/test_render_battlemap_view.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing renderer test**

```python
def test_render_returns_html_with_grid_layers_and_sidebar(self) -> None:
    encounter = build_encounter_with_battlemap_features()

    payload = RenderBattlemapView().execute(encounter)

    self.assertEqual(payload["title"], "Battlemap Demo")
    self.assertIn("battlemap-shell", payload["html"])
    self.assertIn("grid-template-columns: repeat(6, 56px);", payload["html"])
    self.assertIn("tile tile--wall", payload["html"])
    self.assertIn("tile tile--difficult", payload["html"])
    self.assertIn("tile tile--high-ground", payload["html"])
    self.assertIn("tile tile--zone", payload["html"])
    self.assertIn("tile__occupant", payload["html"])
    self.assertIn("🛡", payload["html"])
    self.assertIn("current-turn", payload["html"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_render_battlemap_view.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `RenderBattlemapView`

- [ ] **Step 3: Write the failing map notes integration assertion**

```python
def test_execute_includes_battlemap_view_and_map_notes(self) -> None:
    state = GetEncounterState(repo).execute("enc_view_test")

    self.assertIn("battlemap_view", state)
    self.assertIn("map_notes", state)
    self.assertIn("terrain_summary", state["map_notes"])
    self.assertIn("html", state["battlemap_view"])
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_get_encounter_state.py -v`
Expected: FAIL because `GetEncounterState` does not return those keys

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills add test/test_render_battlemap_view.py test/test_get_encounter_state.py
git -C /Users/runshi.zhang/trpg-module-skills commit -m "test: add battlemap view expectations"
```

### Task 2: Implement Dedicated Map Services

**Files:**
- Create: `app/services/map/__init__.py`
- Create: `app/services/map/render_battlemap_view.py`
- Create: `app/services/map/build_map_notes.py`
- Modify: `app/services/__init__.py`
- Test: `test/test_render_battlemap_view.py`

- [ ] **Step 1: Create the smallest `map` service package**

```python
from app.services.map.build_map_notes import BuildMapNotes
from app.services.map.render_battlemap_view import RenderBattlemapView

__all__ = ["BuildMapNotes", "RenderBattlemapView"]
```

- [ ] **Step 2: Implement minimal `BuildMapNotes`**

```python
class BuildMapNotes:
    def execute(self, encounter: Encounter) -> dict[str, Any]:
        return {
            "terrain_summary": self._build_terrain_summary(encounter),
            "zone_summary": self._build_zone_summary(encounter),
            "landmarks": self._build_landmarks(encounter),
            "tactical_warnings": [],
        }
```

- [ ] **Step 3: Implement minimal `RenderBattlemapView`**

```python
class RenderBattlemapView:
    TILE_SIZE_PX = 56

    def execute(self, encounter: Encounter) -> dict[str, Any]:
        html = self._render_document(encounter)
        return {
            "title": encounter.name,
            "html": html,
            "dimensions": {
                "width": encounter.map.width,
                "height": encounter.map.height,
                "grid_size_feet": encounter.map.grid_size_feet,
            },
        }
```

- [ ] **Step 4: Render the grid with minimal supported layers**

```python
def _tile_classes(self, x: int, y: int, encounter: Encounter) -> str:
    classes = ["tile"]
    if self._has_terrain_type(encounter.map.terrain, x, y, "wall"):
        classes.append("tile--wall")
    if self._has_terrain_type(encounter.map.terrain, x, y, "difficult_terrain"):
        classes.append("tile--difficult")
    if self._has_terrain_type(encounter.map.terrain, x, y, "high_ground"):
        classes.append("tile--high-ground")
    if self._cell_in_zone(encounter.map.zones, x, y):
        classes.append("tile--zone")
    return " ".join(classes)
```

- [ ] **Step 5: Render occupants and sidebar**

```python
def _occupant_symbol(self, entity: EncounterEntity) -> str:
    if entity.category == "pc":
        return self._class_emoji(entity)
    if entity.entity_id == self._current_entity_id:
        return "C"
    return "E" if entity.side == "enemy" else "N"
```

- [ ] **Step 6: Export the new services**

```python
from app.services.map.build_map_notes import BuildMapNotes
from app.services.map.render_battlemap_view import RenderBattlemapView
```

- [ ] **Step 7: Run the new renderer test**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_render_battlemap_view.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills add app/services/map/__init__.py app/services/map/build_map_notes.py app/services/map/render_battlemap_view.py app/services/__init__.py test/test_render_battlemap_view.py
git -C /Users/runshi.zhang/trpg-module-skills commit -m "feat: add web battlemap rendering services"
```

### Task 3: Integrate Map Services Into `GetEncounterState`

**Files:**
- Modify: `app/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Inject the new services at the state projection boundary**

```python
from app.services.map.build_map_notes import BuildMapNotes
from app.services.map.render_battlemap_view import RenderBattlemapView

class GetEncounterState:
    def __init__(
        self,
        repository: EncounterRepository,
        battlemap_view_service: RenderBattlemapView | None = None,
        map_notes_service: BuildMapNotes | None = None,
    ):
        self.repository = repository
        self.battlemap_view_service = battlemap_view_service or RenderBattlemapView()
        self.map_notes_service = map_notes_service or BuildMapNotes()
```

- [ ] **Step 2: Add `battlemap_view` and `map_notes` to the returned state**

```python
return {
    "encounter_id": encounter.encounter_id,
    "round": encounter.round,
    "current_turn_entity": self._build_current_turn_entity(encounter, current_entity),
    "turn_order": self._build_turn_order(encounter, current_entity),
    "battlemap_details": self._build_battlemap_details(encounter),
    "battlemap_view": self.battlemap_view_service.execute(encounter),
    "map_notes": self.map_notes_service.execute(encounter),
    "encounter_notes": encounter.encounter_notes,
}
```

- [ ] **Step 3: Run the state projection tests**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_get_encounter_state.py -v`
Expected: PASS

- [ ] **Step 4: Run the full suite**

Run: `python3 -m unittest discover -s /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test -p 'test_*.py'`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/trpg-module-skills add app/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git -C /Users/runshi.zhang/trpg-module-skills commit -m "feat: expose battlemap view in encounter state"
```

## Self-Review

- Spec coverage: the plan covers the first-phase web battlemap, `map_notes`, current-turn highlighting, right sidebar, and `get_encounter_state` integration. It does not include interaction, drag-and-drop, fog of war, or large creatures by design.
- Placeholder scan: no `TODO` or unspecified steps remain.
- Type consistency: the plan consistently uses `RenderBattlemapView`, `BuildMapNotes`, `battlemap_view`, and `map_notes`.
