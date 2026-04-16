# Spell Area Zones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让范围法术支持“以格子中心为落点”的圆形区域判定，并把瞬时法术区域与持续区域统一接入战斗结算、地图状态和前端圆形投影。

**Architecture:** 新增一个专门的法术区域辅助模块，负责从 `target_point + area_template` 计算命中格与命中实体，再由 `ExecuteSpell` 编排瞬时结算或持续落地区域。`GetEncounterState` 负责把瞬时 overlay 投影给 battlemap 前端，前端继续通过 `applyEncounterState` 自动刷新显示。

**Tech Stack:** Python 3、现有 `unittest`、现有 encounter/service/repository 分层、HTML/CSS/JS battlemap 页面运行时。

---

## File Map

- Create: `tools/services/spells/area_geometry.py`
  - 负责圆形区域格子计算、命中实体收集、区域实例/overlay 构造。
- Create: `test/test_spell_area_geometry.py`
  - 负责法术区域几何与多目标命中测试。
- Modify: `data/knowledge/spell_definitions.json`
  - 给 `fireball` 和首个持续区域法术加入 `area_template`。
- Modify: `tools/services/spells/spell_request.py`
  - 校验区域法术必须提供 `target_point`，并校验落点距离。
- Modify: `tools/services/spells/execute_spell.py`
  - 区域法术走“几何计算 -> 多目标结算 -> overlay/zone 投影”的新链路。
- Modify: `tools/services/spells/encounter_cast_spell.py`
  - 持续区域法术在声明时创建 `spell_instance` 与 `linked_zone_ids`。
- Modify: `tools/services/spells/build_spell_instance.py`
  - 给 `special_runtime` 增加 `linked_zone_ids`。
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 暴露瞬时法术区域 overlay。
- Modify: `tools/services/map/render_battlemap_view.py`
  - 渲染圆形法术 overlay。
- Modify: `tools/services/map/render_battlemap_page.py`
  - 把 overlay 一并写入前端状态。
- Modify: `test/test_spell_request.py`
  - 覆盖 `target_point` 必填、超距等校验。
- Modify: `test/test_execute_spell.py`
  - 覆盖火球术多目标命中、即时区域 overlay。
- Modify: `test/test_encounter_cast_spell.py`
  - 覆盖持续区域 spell instance 与 zone 绑定。
- Modify: `test/test_get_encounter_state.py`
  - 覆盖 overlay 投影。
- Modify: `test/test_render_battlemap_page.py`
  - 覆盖 overlay 写入 client state。
- Modify: `test/test_render_battlemap_view.py`
  - 覆盖圆形 overlay 的 HTML/CSS 标记。

### Task 1: 圆形区域几何与命中实体收集

**Files:**
- Create: `tools/services/spells/area_geometry.py`
- Test: `test/test_spell_area_geometry.py`

- [ ] **Step 1: 写失败测试，锁定圆形命中格与多目标行为**

```python
class SpellAreaGeometryTests(unittest.TestCase):
    def test_circle_area_uses_cell_center_and_returns_covered_cells(self) -> None:
        cells = collect_circle_cells(
            map_width=12,
            map_height=12,
            target_point={"x": 3, "y": 4, "anchor": "cell_center"},
            radius_feet=20,
            grid_size_feet=5,
        )

        self.assertIn((3, 4), cells)
        self.assertIn((7, 4), cells)
        self.assertNotIn((8, 4), cells)

    def test_collects_all_entities_with_any_occupied_cell_inside_area(self) -> None:
        encounter = build_area_test_encounter()

        entity_ids = collect_entities_in_cells(
            encounter=encounter,
            covered_cells={(3, 4), (4, 4), (5, 4), (6, 4)},
        )

        self.assertEqual(
            entity_ids,
            ["ent_enemy_small_001", "ent_enemy_large_001"],
        )
```

- [ ] **Step 2: 跑测试确认当前失败**

Run: `python3 -m unittest test.test_spell_area_geometry -v`  
Expected: FAIL，提示 `collect_circle_cells` / `collect_entities_in_cells` 未定义

- [ ] **Step 3: 写最小实现，建立几何辅助模块**

```python
def collect_circle_cells(
    *,
    map_width: int,
    map_height: int,
    target_point: dict[str, Any],
    radius_feet: int,
    grid_size_feet: int,
) -> set[tuple[int, int]]:
    radius_tiles = radius_feet / grid_size_feet
    center_x = float(target_point["x"])
    center_y = float(target_point["y"])
    covered: set[tuple[int, int]] = set()
    for y in range(1, map_height + 1):
        for x in range(1, map_width + 1):
            dx = x - center_x
            dy = y - center_y
            if (dx * dx + dy * dy) ** 0.5 <= radius_tiles:
                covered.add((x, y))
    return covered


def collect_entities_in_cells(
    *,
    encounter: Encounter,
    covered_cells: set[tuple[int, int]],
) -> list[str]:
    matched: list[str] = []
    for entity_id, entity in encounter.entities.items():
        occupied = get_occupied_cells(entity)
        if any((cell_x, cell_y) in covered_cells for cell_x, cell_y in occupied):
            matched.append(entity_id)
    return matched
```

- [ ] **Step 4: 补区域实例和 overlay 构造器**

```python
def build_spell_area_overlay(
    *,
    overlay_id: str,
    spell_id: str,
    spell_name: str,
    target_point: dict[str, Any],
    radius_feet: int,
    grid_size_feet: int,
    persistence: str,
) -> dict[str, Any]:
    return {
        "overlay_id": overlay_id,
        "kind": "spell_area_circle",
        "source_spell_id": spell_id,
        "source_spell_name": spell_name,
        "target_point": dict(target_point),
        "radius_feet": radius_feet,
        "radius_tiles": radius_feet / grid_size_feet,
        "persistence": persistence,
    }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m unittest test.test_spell_area_geometry -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add test/test_spell_area_geometry.py tools/services/spells/area_geometry.py
git commit -m "feat: add spell area geometry helpers"
```

### Task 2: 区域法术请求校验

**Files:**
- Modify: `data/knowledge/spell_definitions.json`
- Modify: `tools/services/spells/spell_request.py`
- Test: `test/test_spell_request.py`

- [ ] **Step 1: 写失败测试，锁定 `target_point` 校验**

```python
def test_area_spell_requires_target_point(self) -> None:
    result = self.service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="fireball",
        cast_level=3,
    )

    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "missing_target_point")


def test_area_spell_rejects_target_point_beyond_range(self) -> None:
    result = self.service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="fireball",
        cast_level=3,
        target_point={"x": 40, "y": 40, "anchor": "cell_center"},
    )

    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "target_point_out_of_range")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_spell_request -v`  
Expected: FAIL，当前 `SpellRequest` 不会要求 `target_point`

- [ ] **Step 3: 给法术知识库补 `area_template`**

```json
"fireball": {
  "targeting": {
    "type": "area_sphere",
    "range_feet": 150,
    "radius_feet": 20,
    "requires_line_of_sight": true,
    "allowed_target_types": ["creature"]
  },
  "area_template": {
    "shape": "sphere",
    "radius_feet": 20,
    "render_mode": "circle_overlay",
    "persistence": "instant"
  }
}
```

- [ ] **Step 4: 在 `SpellRequest` 增加区域模板校验**

```python
def _validate_target_point(
    self,
    *,
    encounter: Any,
    actor: Any,
    spell_definition: dict[str, Any],
    target_point: dict[str, Any] | None,
) -> dict[str, Any] | None:
    area_template = spell_definition.get("area_template")
    if not isinstance(area_template, dict):
        return None
    if not isinstance(target_point, dict):
        return {
            "ok": False,
            "error_code": "missing_target_point",
            "message": "该法术需要指定落点坐标。",
        }
    if target_point.get("anchor") != "cell_center":
        return {
            "ok": False,
            "error_code": "invalid_target_point",
            "message": "当前只支持以格子中心为法术落点。",
        }
    if not self._point_within_range(actor=actor, target_point=target_point, spell_definition=spell_definition):
        return {
            "ok": False,
            "error_code": "target_point_out_of_range",
            "message": "该落点超出法术施法距离。",
        }
    return None
```

- [ ] **Step 5: 在成功返回里保留 `area_template`**

```python
return {
    "ok": True,
    "actor_id": actor_id,
    "spell_id": spell_id,
    "target_point": target_point,
    "spell_definition": spell_definition,
    "area_template": spell_definition.get("area_template"),
    ...
}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m unittest test.test_spell_request -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add data/knowledge/spell_definitions.json test/test_spell_request.py tools/services/spells/spell_request.py
git commit -m "feat: validate spell area target points"
```

### Task 3: 即时范围法术结算接入 `ExecuteSpell`

**Files:**
- Modify: `tools/services/spells/execute_spell.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_execute_spell.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: 写失败测试，锁定火球术多目标命中与 overlay**

```python
def test_execute_fireball_hits_all_entities_inside_circle_and_returns_overlay(self) -> None:
    result = self.service.execute(
        encounter_id="enc_execute_fireball_save_damage_test",
        actor_id="ent_fireball_caster_001",
        spell_id="fireball",
        cast_level=3,
        target_point={"x": 6, "y": 6, "anchor": "cell_center"},
        save_rolls={
            "ent_fireball_target_failed_001": {"base_roll": 4},
            "ent_fireball_target_success_001": {"base_roll": 17},
        },
        damage_rolls=[6, 6, 6, 6, 6, 6, 6, 6],
    )

    self.assertEqual(result["spell_resolution"]["mode"], "save_damage")
    self.assertEqual(len(result["spell_resolution"]["targets"]), 2)
    self.assertEqual(result["encounter_state"]["spell_area_overlays"][0]["kind"], "spell_area_circle")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_execute_spell test.test_get_encounter_state -v`  
Expected: FAIL，当前结果里没有 `spell_area_overlays`，也不会从区域几何自动挑目标

- [ ] **Step 3: 在 `ExecuteSpell` 中增加区域法术分支**

```python
if self._is_area_spell(spell_definition):
    area_resolution = self._prepare_area_spell_resolution(
        encounter_id=encounter_id,
        actor_id=request_result["actor_id"],
        spell_definition=spell_definition,
        target_point=request_result["target_point"],
    )
    if not area_resolution.get("ok"):
        return area_resolution
```

- [ ] **Step 4: 用命中格自动推导目标列表**

```python
covered_cells = collect_circle_cells(
    map_width=encounter.map.width,
    map_height=encounter.map.height,
    target_point=target_point,
    radius_feet=area_template["radius_feet"],
    grid_size_feet=encounter.map.grid_size_feet,
)
target_ids = collect_entities_in_cells(
    encounter=encounter,
    covered_cells=covered_cells,
)
overlay = build_spell_area_overlay(
    overlay_id=f"overlay_{uuid4().hex[:12]}",
    spell_id=spell_definition["id"],
    spell_name=spell_definition["localization"]["name_zh"],
    target_point=target_point,
    radius_feet=area_template["radius_feet"],
    grid_size_feet=encounter.map.grid_size_feet,
    persistence="instant",
)
```

- [ ] **Step 5: 把瞬时 overlay 写入 encounter 运行态并投影到 `get_encounter_state`**

```python
combat_state = encounter.encounter_notes
combat_state.append(
    {
        "type": "spell_area_overlay",
        "payload": overlay,
    }
)
```

```python
def _build_spell_area_overlays(self, encounter: Encounter) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for note in encounter.encounter_notes:
        if isinstance(note, dict) and note.get("type") == "spell_area_overlay":
            payload = note.get("payload")
            if isinstance(payload, dict):
                overlays.append(payload)
    return overlays[-1:]
```

- [ ] **Step 6: 把 overlay 放进状态返回**

```python
return {
    "encounter_id": encounter.encounter_id,
    ...
    "spell_area_overlays": self._build_spell_area_overlays(encounter),
    "battlemap_view": self.battlemap_view_service.execute(...),
}
```

- [ ] **Step 7: 跑测试确认通过**

Run: `python3 -m unittest test.test_execute_spell test.test_get_encounter_state -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add test/test_execute_spell.py test/test_get_encounter_state.py tools/services/spells/execute_spell.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: execute instant spell area overlays"
```

### Task 4: battlemap 前端圆形 overlay

**Files:**
- Modify: `tools/services/map/render_battlemap_view.py`
- Modify: `tools/services/map/render_battlemap_page.py`
- Test: `test/test_render_battlemap_view.py`
- Test: `test/test_render_battlemap_page.py`

- [ ] **Step 1: 写失败测试，锁定圆形 overlay HTML**

```python
def test_render_shows_spell_area_circle_overlay(self) -> None:
    html = self.service.execute(encounter, spell_area_overlays=[{
        "overlay_id": "overlay_fireball_001",
        "kind": "spell_area_circle",
        "target_point": {"x": 3, "y": 4, "anchor": "cell_center"},
        "radius_tiles": 4,
        "source_spell_name": "火球术",
        "persistence": "instant",
    }])["html"]

    self.assertIn("battlemap-spell-overlay", html)
    self.assertIn("火球术", html)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_render_battlemap_view test.test_render_battlemap_page -v`  
Expected: FAIL，当前 view/page 都没有 overlay 参数

- [ ] **Step 3: 扩展 `RenderBattlemapView.execute` 和 `_render_document` 参数**

```python
def execute(
    self,
    encounter: Encounter,
    recent_forced_movement: dict[str, object] | None = None,
    recent_turn_effects: list[dict[str, object]] | None = None,
    recent_activity: list[dict[str, object]] | None = None,
    spell_area_overlays: list[dict[str, object]] | None = None,
) -> dict[str, object]:
```

- [ ] **Step 4: 在地图表面层叠加圆形 overlay**

```python
def _render_spell_area_overlays(
    self,
    encounter: Encounter,
    spell_area_overlays: list[dict[str, object]] | None,
) -> str:
    if not spell_area_overlays:
        return ""
    items: list[str] = ['<div class="battlemap-spell-overlays">']
    for overlay in spell_area_overlays:
        point = overlay["target_point"]
        radius_tiles = float(overlay["radius_tiles"])
        items.append(
            f'<div class="battlemap-spell-overlay" '
            f'data-spell-name="{overlay["source_spell_name"]}" '
            f'style="--overlay-x:{point["x"]};--overlay-y:{point["y"]};--overlay-radius:{radius_tiles};"></div>'
        )
    items.append("</div>")
    return "".join(items)
```

- [ ] **Step 5: 补 CSS，让圆心对准格中心**

```css
.battlemap-spell-overlays{position:absolute;inset:0;pointer-events:none;z-index:3;}
.battlemap-spell-overlay{
  position:absolute;
  left:calc((var(--overlay-x) - 0.5) * (100% / var(--map-width)));
  top:calc((var(--map-height) - var(--overlay-y) + 0.5) * (100% / var(--map-height)));
  width:calc(var(--overlay-radius) * 2 * (100% / var(--map-width)));
  height:calc(var(--overlay-radius) * 2 * (100% / var(--map-height)));
  transform:translate(-50%, -50%);
  border-radius:999px;
  border:2px solid rgba(255,180,122,.9);
  background:radial-gradient(circle,rgba(255,130,82,.28),rgba(255,130,82,.1) 55%,rgba(255,130,82,0) 72%);
  box-shadow:0 0 36px rgba(255,130,82,.26);
}
```

- [ ] **Step 6: 在 `RenderBattlemapPage` client state 中保留 overlays**

```python
"spell_area_overlays": spell_area_overlays or [],
```

- [ ] **Step 7: 跑测试确认通过**

Run: `python3 -m unittest test.test_render_battlemap_view test.test_render_battlemap_page -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add test/test_render_battlemap_view.py test/test_render_battlemap_page.py tools/services/map/render_battlemap_view.py tools/services/map/render_battlemap_page.py
git commit -m "feat: render spell area circle overlays"
```

### Task 5: 持续区域法术与 spell instance 绑定

**Files:**
- Modify: `data/knowledge/spell_definitions.json`
- Modify: `tools/services/spells/build_spell_instance.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/spells/execute_spell.py`
- Test: `test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写失败测试，锁定持续区域会生成 zone 并绑定到 spell instance**

```python
def test_execute_sustained_area_spell_creates_zone_and_links_instance(self) -> None:
    result = self.service.execute(
        encounter_id="enc_cast_spell_test",
        actor_id="ent_ally_eric_001",
        spell_id="moonbeam",
        cast_level=2,
        target_point={"x": 6, "y": 6, "anchor": "cell_center"},
    )

    updated = self.encounter_repo.get("enc_cast_spell_test")
    self.assertEqual(len(updated.map.zones), 1)
    self.assertEqual(updated.spell_instances[0]["special_runtime"]["linked_zone_ids"], [updated.map.zones[0]["zone_id"]])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest test.test_encounter_cast_spell -v`  
Expected: FAIL，当前 spell instance 没有 `linked_zone_ids`

- [ ] **Step 3: 在法术知识库补首个持续区域样板**

```json
"moonbeam": {
  "id": "moonbeam",
  "name": "Moonbeam",
  "level": 2,
  "area_template": {
    "shape": "sphere",
    "radius_feet": 5,
    "render_mode": "circle_overlay",
    "persistence": "sustained",
    "zone_definition_id": "fire_burn_area"
  }
}
```

- [ ] **Step 4: 扩展 `build_spell_instance` 的 `special_runtime`**

```python
def _build_special_runtime(...):
    runtime: dict[str, Any] = {}
    ...
    runtime["linked_zone_ids"] = []
    return runtime
```

- [ ] **Step 5: 在施法声明时创建持续区域实例**

```python
zone = build_spell_zone_instance(
    spell_definition=spell_definition,
    caster=caster,
    cast_level=resolved_cast_level,
    target_point=target_point,
    encounter=encounter,
)
encounter.map.zones.append(zone)
spell_instance["special_runtime"]["linked_zone_ids"] = [zone["zone_id"]]
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m unittest test.test_encounter_cast_spell -v`  
Expected: PASS

- [ ] **Step 7: 跑整组回归**

Run: `python3 -m unittest test.test_spell_area_geometry test.test_spell_request test.test_execute_spell test.test_encounter_cast_spell test.test_get_encounter_state test.test_render_battlemap_view test.test_render_battlemap_page -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add data/knowledge/spell_definitions.json test/test_encounter_cast_spell.py tools/services/spells/build_spell_instance.py tools/services/spells/encounter_cast_spell.py tools/services/spells/execute_spell.py
git commit -m "feat: link sustained spell areas to spell instances"
```

## Self-Review

- Spec coverage:
  - 圆形格心判定：Task 1
  - 多目标同时命中：Task 1 + Task 3
  - `target_point` 校验：Task 2
  - 瞬时区域 overlay：Task 3 + Task 4
  - 持续区域与 `map.zones` / `spell_instance` 绑定：Task 5
- Placeholder scan:
  - 本计划没有使用 `TODO` / `TBD` / “自行补充测试” 这类占位描述
- Type consistency:
  - 统一使用 `target_point = {"x", "y", "anchor": "cell_center"}`
  - 统一使用 `spell_area_overlays`
  - 统一使用 `linked_zone_ids`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-spell-area-zones.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
