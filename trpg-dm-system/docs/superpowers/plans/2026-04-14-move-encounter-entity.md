# Move Encounter Entity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 encounter 新增一个带完整规则校验的 `move_encounter_entity` 服务，支持体型占格、逐步路径检查、困难地形、墙体、同伴/敌人占位、斜线 5/10 计费、疾跑与非计费移动。

**Architecture:** 采用“两层拆分”。`movement_rules.py` 只做纯规则计算，不读写仓储；`move_encounter_entity.py` 负责读取 encounter、调用规则层、在通过校验后一次性写回位置和剩余移动力。`EncounterEntity.position` 继续保存左下角锚点，`occupied_cells` 和 `center_position` 由规则层运行时派生。

**Tech Stack:** Python 3、`dataclasses`、现有 `EncounterRepository` / `EncounterService` / `unittest`

---

## 文件结构

- 修改：`tools/models/encounter_entity.py`
  责任：给实体增加 `size` 字段，保证老数据默认按 `medium` 处理，并序列化回仓储。
- 新增：`tools/services/encounter/movement_rules.py`
  责任：纯函数规则层，负责体型尺寸、占格展开、中心点、逐步路径生成、逐步合法性校验、困难地形/墙/占位判断、移动力计算。
- 新增：`tools/services/encounter/move_encounter_entity.py`
  责任：读取 encounter、调用规则层、原子更新位置和 `speed.remaining`、保存仓储。
- 修改：`tools/services/encounter/__init__.py`
  责任：导出新服务。
- 修改：`tools/services/__init__.py`
  责任：把 `MoveEncounterEntity` 聚合到顶层导出。
- 新增：`test/test_movement_rules.py`
  责任：覆盖纯规则层，尤其是斜线计费、占格合法性、同伴/敌人穿越、多格生物逐步校验。
- 新增：`test/test_move_encounter_entity.py`
  责任：覆盖 orchestration，包括保存、扣减移动力、`use_dash`、`count_movement=False`、失败不落盘。
- 修改：`test/test_encounter_service.py`
  责任：把测试实体构造器补上 `size` 兼容断言，防止回归。

### Task 1: 扩展实体模型并锁定序列化兼容

**Files:**
- Modify: `tools/models/encounter_entity.py`
- Modify: `test/test_encounter_service.py`
- Test: `test/test_encounter_service.py`

- [ ] **Step 1: 先写失败测试，锁定 `size` 的默认值和序列化行为**

```python
class EncounterEntitySizeTests(unittest.TestCase):
    def test_entity_defaults_size_to_medium(self) -> None:
        entity = EncounterEntity(
            entity_id="ent_size_default",
            name="Scout",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 2, "y": 3},
            hp={"current": 12, "max": 12, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
        )

        self.assertEqual(entity.size, "medium")
        self.assertEqual(entity.to_dict()["size"], "medium")

    def test_entity_rejects_unknown_size(self) -> None:
        with self.assertRaises(ValueError):
            EncounterEntity(
                entity_id="ent_bad_size",
                name="Weird",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 1, "y": 1},
                hp={"current": 8, "max": 8, "temp": 0},
                ac=10,
                speed={"walk": 30, "remaining": 30},
                initiative=10,
                size="colossal",
            )
```

- [ ] **Step 2: 运行测试，确认当前实现确实失败**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_encounter_service.py -v`

Expected: 新增的 `size` 相关断言失败，报 `EncounterEntity` 没有 `size` 字段或不接受 `size` 参数。

- [ ] **Step 3: 在实体模型中加入 `size`，并保持老数据兼容**

```python
ALLOWED_ENTITY_SIZES = {"tiny", "small", "medium", "large", "huge", "gargantuan"}


@dataclass
class EncounterEntity:
    entity_id: str
    name: str
    side: str
    category: str
    controller: str
    position: dict[str, int]
    hp: dict[str, int]
    ac: int
    speed: dict[str, int]
    initiative: int
    size: str = "medium"
    entity_def_id: str | None = None
    source_ref: dict[str, Any] = field(default_factory=dict)
    ability_scores: dict[str, int] = field(default_factory=dict)
    ability_mods: dict[str, int] = field(default_factory=dict)
    proficiency_bonus: int = 0
    save_proficiencies: list[str] = field(default_factory=list)
    skill_modifiers: dict[str, int] = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    action_economy: dict[str, Any] = field(default_factory=dict)
    combat_flags: dict[str, Any] = field(default_factory=dict)
    weapons: list[dict[str, Any]] = field(default_factory=list)
    spells: list[dict[str, Any]] = field(default_factory=list)
    resistances: list[str] = field(default_factory=list)
    immunities: list[str] = field(default_factory=list)
    vulnerabilities: list[str] = field(default_factory=list)
    notes: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entity_id = _require_non_empty_string(self.entity_id, "entity_id")
        self.name = _require_non_empty_string(self.name, "name")
        self.side = _require_non_empty_string(self.side, "side")
        self.category = _require_non_empty_string(self.category, "category")
        self.controller = _require_non_empty_string(self.controller, "controller")
        self.initiative = _require_int(self.initiative, "initiative")
        self.size = _require_non_empty_string(self.size, "size").lower()
        if self.size not in ALLOWED_ENTITY_SIZES:
            raise ValueError(f"size must be one of: {', '.join(sorted(ALLOWED_ENTITY_SIZES))}")
        self.proficiency_bonus = _require_int(self.proficiency_bonus, "proficiency_bonus", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_def_id": self.entity_def_id,
            "source_ref": self.source_ref,
            "name": self.name,
            "side": self.side,
            "category": self.category,
            "controller": self.controller,
            "position": self.position,
            "hp": self.hp,
            "ac": self.ac,
            "speed": self.speed,
            "initiative": self.initiative,
            "size": self.size,
            "ability_scores": self.ability_scores,
            "ability_mods": self.ability_mods,
            "proficiency_bonus": self.proficiency_bonus,
            "save_proficiencies": self.save_proficiencies,
            "skill_modifiers": self.skill_modifiers,
            "conditions": self.conditions,
            "resources": self.resources,
            "action_economy": self.action_economy,
            "combat_flags": self.combat_flags,
            "weapons": self.weapons,
            "spells": self.spells,
            "resistances": self.resistances,
            "immunities": self.immunities,
            "vulnerabilities": self.vulnerabilities,
            "notes": self.notes,
        }
```

- [ ] **Step 4: 调整服务层测试构造器，显式允许覆盖 `size`**

```python
def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    initiative: int = 10,
    size: str = "medium",
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        size=size,
    )
```

- [ ] **Step 5: 重新运行模型和服务层测试，确认兼容没破**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_encounter_service.py -v`

Expected: PASS，原有服务测试继续通过，新增 `size` 断言也通过。

- [ ] **Step 6: 提交这一小步**

```bash
git add tools/models/encounter_entity.py test/test_encounter_service.py
git commit -m "feat: add encounter entity size model"
```

### Task 2: 建立纯规则层，先把路径、占格、成本算法做对

**Files:**
- Create: `tools/services/encounter/movement_rules.py`
- Create: `test/test_movement_rules.py`
- Test: `test/test_movement_rules.py`

- [ ] **Step 1: 写规则层失败测试，先锁定最核心的纯函数接口**

```python
class MovementRulesTests(unittest.TestCase):
    def test_get_occupied_cells_for_large_creature(self) -> None:
        entity = build_entity("ent_large", name="Ogre", x=10, y=10, size="large")
        self.assertEqual(
            get_occupied_cells(entity, {"x": 10, "y": 10}),
            {(10, 10), (11, 10), (10, 11), (11, 11)},
        )

    def test_get_center_position_for_large_creature(self) -> None:
        entity = build_entity("ent_large", name="Ogre", x=10, y=10, size="large")
        self.assertEqual(get_center_position(entity), {"x": 10.5, "y": 10.5})

    def test_diagonal_cost_uses_5_10_and_resets_after_orthogonal(self) -> None:
        steps = [(1, 1), (2, 2), (2, 3), (3, 4)]
        self.assertEqual(calculate_step_costs(steps), [5, 10, 5, 5])
```

- [ ] **Step 2: 再补逐步合法性测试，覆盖墙、敌人、同伴和困难地形**

```python
    def test_validate_path_blocks_on_enemy_but_allows_ally_pass_through(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2)
        ally = build_entity("ent_ally", name="Lia", x=3, y=2)
        enemy = EncounterEntity(
            entity_id="ent_enemy",
            name="Goblin",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 4, "y": 2},
            hp={"current": 7, "max": 7, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
        )
        encounter = build_encounter_with_entities(mover, ally, enemy)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 5, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.blocked_reason, "blocked_by_enemy")
        self.assertEqual(result.path[0].anchor, {"x": 3, "y": 2})

    def test_difficult_terrain_doubles_step_cost_when_new_footprint_enters_it(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2)
        encounter = build_encounter_with_terrain(
            mover,
            terrain=[{"x": 3, "y": 2, "type": "difficult_terrain"}],
        )

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 10)
```

- [ ] **Step 3: 用失败用例锁定“严格占格判定”，避免只检查终点**

```python
    def test_large_creature_checks_full_footprint_on_every_intermediate_step(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_large",
            name="Ogre",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 2, "y": 2},
            hp={"current": 59, "max": 59, "temp": 0},
            ac=11,
            speed={"walk": 40, "remaining": 40},
            initiative=8,
            size="large",
        )
        encounter = build_encounter_with_terrain(
            mover,
            terrain=[{"x": 4, "y": 3, "type": "wall"}],
        )

        with self.assertRaisesRegex(ValueError, "blocked_by_wall"):
            validate_movement_path(
                encounter=encounter,
                entity_id=mover.entity_id,
                target_position={"x": 3, "y": 2},
                count_movement=True,
                use_dash=False,
            )
```

- [ ] **Step 4: 运行规则层测试，确认是红灯**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_movement_rules.py -v`

Expected: FAIL，提示缺少 `movement_rules.py` 或函数未定义。

- [ ] **Step 5: 编写规则层最小实现，先给出稳定的数据结构**

```python
from __future__ import annotations

from dataclasses import dataclass


SIZE_TO_FOOTPRINT = {
    "tiny": (1, 1),
    "small": (1, 1),
    "medium": (1, 1),
    "large": (2, 2),
    "huge": (3, 3),
    "gargantuan": (4, 4),
}


@dataclass(frozen=True)
class MovementStep:
    anchor: dict[str, int]
    occupied_cells: set[tuple[int, int]]
    feet_cost: int
    movement_kind: str


@dataclass(frozen=True)
class MovementValidationResult:
    path: list[MovementStep]
    feet_cost: int
    used_dash: bool
    movement_counted: bool
    blocked_reason: str | None = None


def get_footprint_size(entity: EncounterEntity) -> tuple[int, int]:
    return SIZE_TO_FOOTPRINT[entity.size]


def get_occupied_cells(entity: EncounterEntity, anchor: dict[str, int] | None = None) -> set[tuple[int, int]]:
    anchor_position = entity.position if anchor is None else anchor
    width, height = get_footprint_size(entity)
    origin_x = anchor_position["x"]
    origin_y = anchor_position["y"]
    return {
        (origin_x + delta_x, origin_y + delta_y)
        for delta_x in range(width)
        for delta_y in range(height)
    }


def get_center_position(entity: EncounterEntity, anchor: dict[str, int] | None = None) -> dict[str, float]:
    anchor_position = entity.position if anchor is None else anchor
    width, height = get_footprint_size(entity)
    return {
        "x": anchor_position["x"] + (width - 1) / 2,
        "y": anchor_position["y"] + (height - 1) / 2,
    }


def validate_movement_path(
    encounter: Encounter,
    entity_id: str,
    target_position: dict[str, int],
    *,
    count_movement: bool,
    use_dash: bool,
) -> MovementValidationResult:
    mover = encounter.entities[entity_id]
    path_anchors = iter_anchor_path(mover.position, target_position)
    steps: list[MovementStep] = []
    total_cost = 0
    diagonal_run_count = 0
    previous_anchor = (mover.position["x"], mover.position["y"])

    for current_anchor in path_anchors:
        movement_kind = classify_step(previous_anchor, current_anchor)
        diagonal_run_count = diagonal_run_count + 1 if movement_kind == "diagonal" else 0
        occupied_cells = get_occupied_cells(mover, {"x": current_anchor[0], "y": current_anchor[1]})
        enters_difficult = footprint_enters_difficult_terrain(encounter, mover, previous_anchor, current_anchor)
        step_cost = calculate_step_cost(movement_kind, diagonal_run_count, enters_difficult)
        ensure_step_is_legal(encounter, mover, occupied_cells, is_final_step=current_anchor == path_anchors[-1])
        steps.append(
            MovementStep(
                anchor={"x": current_anchor[0], "y": current_anchor[1]},
                occupied_cells=occupied_cells,
                feet_cost=step_cost,
                movement_kind=movement_kind,
            )
        )
        total_cost += step_cost
        previous_anchor = current_anchor

    return MovementValidationResult(
        path=steps,
        feet_cost=total_cost,
        used_dash=use_dash,
        movement_counted=count_movement,
        blocked_reason=None,
    )
```

- [ ] **Step 6: 在规则层实现关键算法，按这个拆分顺序逐个补齐**

```python
def iter_anchor_path(start: dict[str, int], target: dict[str, int]) -> list[tuple[int, int]]:
    path: list[tuple[int, int]] = []
    current_x = start["x"]
    current_y = start["y"]
    while current_x != target["x"] or current_y != target["y"]:
        delta_x = 0 if current_x == target["x"] else (1 if target["x"] > current_x else -1)
        delta_y = 0 if current_y == target["y"] else (1 if target["y"] > current_y else -1)
        current_x += delta_x
        current_y += delta_y
        path.append((current_x, current_y))
    return path


def classify_step(previous: tuple[int, int], current: tuple[int, int]) -> str:
    return "diagonal" if previous[0] != current[0] and previous[1] != current[1] else "orthogonal"


def calculate_step_cost(base_kind: str, diagonal_run_count: int, enters_difficult: bool) -> int:
    base_cost = 10 if base_kind == "diagonal" and diagonal_run_count % 2 == 0 else 5
    return base_cost * 2 if enters_difficult else base_cost
```

- [ ] **Step 7: 把“同伴可穿过、敌人不可穿过、终点共享例外”写成独立判定函数**

```python
def can_pass_through(entity: EncounterEntity, other: EncounterEntity) -> bool:
    if other.side == entity.side:
        return True
    return False


def can_end_on(entity: EncounterEntity, other: EncounterEntity) -> bool:
    if other.side != entity.side:
        return False
    return other.size in {"tiny", "small"}
```

- [ ] **Step 8: 重新运行纯规则测试，确认全部转绿**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_movement_rules.py -v`

Expected: PASS，覆盖体型占格、中心点、5/10 斜线、困难地形、墙和占位阻挡。

- [ ] **Step 9: 提交规则层**

```bash
git add tools/services/encounter/movement_rules.py test/test_movement_rules.py
git commit -m "feat: add encounter movement rules"
```

### Task 3: 加入 orchestration 服务，真正更新 encounter 状态

**Files:**
- Create: `tools/services/encounter/move_encounter_entity.py`
- Create: `test/test_move_encounter_entity.py`
- Test: `test/test_move_encounter_entity.py`

- [ ] **Step 1: 写失败测试，先锁定成功移动会更新位置和剩余移动力**

```python
class MoveEncounterEntityTests(unittest.TestCase):
    def test_move_entity_updates_anchor_and_remaining_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = service.repository.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 5, "y": 2},
            )

            entity = updated.entities["ent_ally_eric_001"]
            self.assertEqual(entity.position, {"x": 5, "y": 2})
            self.assertEqual(entity.speed["remaining"], 15)
```

- [ ] **Step 2: 补充 `use_dash` 和 `count_movement=False` 的行为测试**

```python
    def test_move_entity_with_dash_uses_extra_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = service.repository.save(build_service_encounter())
        updated = service.execute(
            encounter_id=encounter.encounter_id,
            entity_id="ent_ally_eric_001",
            target_position={"x": 8, "y": 2},
            use_dash=True,
        )
        self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 0)

    def test_move_entity_without_counting_movement_keeps_remaining_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = service.repository.save(build_service_encounter())
        updated = service.execute(
            encounter_id=encounter.encounter_id,
            entity_id="ent_ally_eric_001",
            target_position={"x": 4, "y": 2},
            count_movement=False,
        )
        self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
```

- [ ] **Step 3: 再写失败测试，锁定“非法移动不落盘”**

```python
    def test_illegal_move_does_not_mutate_repository_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = service.repository.save(
                build_service_encounter(
                    terrain=[{"x": 4, "y": 2, "type": "wall"}],
                )
            )

            with self.assertRaisesRegex(ValueError, "blocked_by_wall"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 5, "y": 2},
                )

            reloaded = repo.get(encounter.encounter_id)
            self.assertEqual(reloaded.entities["ent_ally_eric_001"].position, {"x": 2, "y": 2})
            self.assertEqual(reloaded.entities["ent_ally_eric_001"].speed["remaining"], 30)
```

- [ ] **Step 4: 运行 orchestration 测试，确认当前为红灯**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_move_encounter_entity.py -v`

Expected: FAIL，提示 `MoveEncounterEntity` 模块不存在。

- [ ] **Step 5: 实现服务入口，只在规则通过后一次性更新并保存**

```python
from tools.services.encounter.movement_rules import validate_movement_path


class MoveEncounterEntity:
    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(
        self,
        encounter_id: str,
        entity_id: str,
        target_position: dict[str, int],
        *,
        count_movement: bool = True,
        use_dash: bool = False,
    ) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")

        result = validate_movement_path(
            encounter=encounter,
            entity_id=entity_id,
            target_position=target_position,
            count_movement=count_movement,
            use_dash=use_dash,
        )

        entity.position["x"] = target_position["x"]
        entity.position["y"] = target_position["y"]
        if count_movement:
            entity.speed["remaining"] = max(0, entity.speed["remaining"] - result.feet_cost)
        return self.repository.save(encounter)
```

- [ ] **Step 6: 补上输入保护和移动额度校验**

```python
        if not isinstance(target_position, dict) or "x" not in target_position or "y" not in target_position:
            raise ValueError("target_position must contain integer x and y")
        if not isinstance(target_position["x"], int) or not isinstance(target_position["y"], int):
            raise ValueError("target_position must contain integer x and y")

        available_movement = entity.speed["remaining"] + (entity.speed["walk"] if use_dash else 0)
        if result.feet_cost > available_movement:
            raise ValueError("insufficient_movement")
```

- [ ] **Step 7: 重新运行 orchestration 测试，确认成功/失败路径都正确**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_move_encounter_entity.py -v`

Expected: PASS，成功移动会更新位置，非法移动会保持仓储原状。

- [ ] **Step 8: 提交服务层**

```bash
git add tools/services/encounter/move_encounter_entity.py test/test_move_encounter_entity.py
git commit -m "feat: add move encounter entity service"
```

### Task 4: 接入导出层并做整体验证

**Files:**
- Modify: `tools/services/encounter/__init__.py`
- Modify: `tools/services/__init__.py`
- Modify: `test/test_move_encounter_entity.py`
- Test: `test/test_movement_rules.py`
- Test: `test/test_move_encounter_entity.py`
- Test: `test/test_encounter_service.py`

- [ ] **Step 1: 把新服务导出到 encounter 子层和顶层 services**

```python
# tools/services/encounter/__init__.py
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity


__all__ = [
    "MoveEncounterEntity",
]
```

```python
# tools/services/__init__.py
from tools.services.events.append_event import AppendEvent
from tools.services.spells.encounter_cast_spell import EncounterCastSpell
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.combat.save_spell.execute_save_spell import ExecuteSaveSpell
from tools.services.combat.attack.attack_roll_result import AttackRollResult
from tools.services.combat.attack.attack_roll_request import AttackRollRequest
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
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
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity
from tools.services.map.build_map_notes import BuildMapNotes
from tools.services.map.render_battlemap_page import RenderBattlemapPage
from tools.services.map.render_battlemap_view import RenderBattlemapView

__all__ = [
    "AppendEvent",
    "EncounterCastSpell",
    "ExecuteAttack",
    "ExecuteSaveSpell",
    "ExecuteConcentrationCheck",
    "AttackRollRequest",
    "AttackRollResult",
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
```

- [ ] **Step 2: 给顶层导出补一个最小回归测试，防止以后漏挂**

```python
from tools.services import MoveEncounterEntity


class MoveEncounterEntityExportTests(unittest.TestCase):
    def test_services_package_exports_move_encounter_entity(self) -> None:
        self.assertIsNotNone(MoveEncounterEntity)
```

- [ ] **Step 3: 跑规则层、服务层和现有 encounter 测试**

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_movement_rules.py -v`

Expected: PASS

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_move_encounter_entity.py -v`

Expected: PASS

Run: `python3 -m unittest /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test/test_encounter_service.py -v`

Expected: PASS

- [ ] **Step 4: 跑全量回归，确认没有打坏地图/法术/状态投影**

Run: `python3 -m unittest discover -s /Users/runshi.zhang/trpg-module-skills/trpg-dm-system/test -p 'test_*.py'`

Expected: PASS，所有测试通过。

- [ ] **Step 5: 提交整合收尾**

```bash
git add tools/services/__init__.py tools/services/encounter/__init__.py
git commit -m "feat: export encounter movement service"
```

## 规格覆盖自检

- `size` 字段与默认 `medium`：由 Task 1 覆盖。
- 左下角锚点 + 运行时派生 `occupied_cells` / `center_position`：由 Task 2 覆盖。
- 上下左右 5 尺、连续斜线 5/10、直线重置：由 Task 2 覆盖。
- 墙、困难地形、多格生物严格逐步判定：由 Task 2 覆盖。
- 同伴可穿过、敌人不可穿过、终点共享例外：由 Task 2 覆盖。
- `count_movement=False` 与 `use_dash=True`：由 Task 3 覆盖。
- 非法移动不得修改 encounter：由 Task 3 覆盖。
- 顶层导出与全量回归：由 Task 4 覆盖。
