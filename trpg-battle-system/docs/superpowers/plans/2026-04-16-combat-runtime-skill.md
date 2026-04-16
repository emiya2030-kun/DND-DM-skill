# Combat Runtime Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated combat runtime skill plus the missing encounter initialization and initiative-start services so a real LLM can set up a battle, roll initiative, and run turns against the current backend safely.

**Architecture:** Keep rules and encounter state in backend services. Extend `EncounterService` with a high-level `initialize_encounter(...)` entrypoint for “布场”, add a separate `RollInitiativeAndStartEncounter` service for “开战”, and generate a dedicated `combat-runtime` skill directory that documents how LLMs should orchestrate the existing tools. Tests stay in `test/` beside the current encounter service coverage.

**Tech Stack:** Python, unittest, TinyDB-backed repositories, markdown skill files

---

## File Structure

- Modify: `tools/services/encounter/manage_encounter_entities.py`
  - Add `initialize_encounter(...)` and `initialize_encounter_with_state(...)`
  - Keep encounter creation/runtime entity management in the same service class
- Create: `tools/services/encounter/roll_initiative_and_start_encounter.py`
  - New combat-start service that rolls initiative, sorts turn order, sets current actor, and calls `StartTurn`
- Modify: `tools/services/encounter/__init__.py`
  - Export `RollInitiativeAndStartEncounter`
- Modify: `tools/services/__init__.py`
  - Export `RollInitiativeAndStartEncounter`
- Modify: `test/test_encounter_service.py`
  - Add coverage for `initialize_encounter(...)`
- Create: `test/test_roll_initiative_and_start_encounter.py`
  - Cover initiative formula, tie-breaking, and `StartTurn` reset behavior
- Create: `combat-runtime/SKILL.md`
  - Entry point for the new combat runtime skill
- Create: `combat-runtime/references/runtime-protocol.md`
  - Hard runtime rules and combat loop
- Create: `combat-runtime/references/tool-catalog.md`
  - Tool-by-tool orchestration catalog
- Create: `combat-runtime/references/monster-turn-flow.md`
  - Minimum monster AI behavior contract
- Create: `combat-runtime/references/companion-npc-turn-flow.md`
  - Companion-NPC autonomous combat behavior contract
- Create: `combat-runtime/references/intent-examples.md`
  - Legal orchestration examples for common combat utterances

### Task 1: Add `initialize_encounter(...)` to `EncounterService`

**Files:**
- Modify: `tools/services/encounter/manage_encounter_entities.py`
- Test: `test/test_encounter_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
    def test_initialize_encounter_replaces_map_and_entities_and_resets_runtime_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter.reaction_requests = [{"request_id": "req_old"}]
            encounter.pending_movement = {"entity_id": "ent_ally_eric_001"}
            encounter.round = 3
            service.create_encounter(encounter)

            initialized = service.initialize_encounter(
                encounter.encounter_id,
                map_setup={
                    "map_id": "map_new",
                    "name": "New Battle Map",
                    "description": "Fresh battle map",
                    "width": 12,
                    "height": 12,
                    "terrain": [],
                    "zones": [],
                    "map_notes": [{"title": "北侧高台", "cells": ["(3,3)"]}],
                    "battlemap_details": ["高台在北侧"],
                },
                entity_setups=[
                    {
                        "entity_instance_id": "ent_pc_miren",
                        "template_ref": {
                            "source_type": "pc",
                            "template_id": "pc_miren",
                        },
                        "runtime_overrides": {
                            "name": "米伦",
                            "side": "ally",
                            "controller": "player",
                            "category": "pc",
                            "position": {"x": 4, "y": 6},
                            "hp": {"current": 18, "temp": 0},
                            "initiative": 0,
                        },
                    },
                    {
                        "entity_instance_id": "ent_enemy_sabur",
                        "template_ref": {
                            "source_type": "monster",
                            "template_id": "monster_sabur",
                        },
                        "runtime_overrides": {
                            "name": "萨布尔",
                            "side": "enemy",
                            "controller": "gm",
                            "category": "monster",
                            "position": {"x": 8, "y": 6},
                            "hp": {"current": 30, "temp": 0},
                            "initiative": 0,
                        },
                    },
                ],
            )

            self.assertEqual(initialized.map.map_id, "map_new")
            self.assertEqual(set(initialized.entities.keys()), {"ent_pc_miren", "ent_enemy_sabur"})
            self.assertEqual(initialized.turn_order, [])
            self.assertIsNone(initialized.current_entity_id)
            self.assertEqual(initialized.round, 1)
            self.assertEqual(initialized.reaction_requests, [])
            self.assertIsNone(initialized.pending_movement)
            repo.close()

    def test_initialize_encounter_with_state_returns_full_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            service.create_encounter(encounter)

            result = service.initialize_encounter_with_state(
                encounter.encounter_id,
                map_setup={
                    "map_id": "map_initialized",
                    "name": "Initialized Map",
                    "description": "State projection test",
                    "width": 10,
                    "height": 10,
                    "terrain": [],
                    "zones": [],
                    "map_notes": [],
                    "battlemap_details": [],
                },
                entity_setups=[
                    {
                        "entity_instance_id": "ent_pc_miren",
                        "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                        "runtime_overrides": {
                            "name": "米伦",
                            "side": "ally",
                            "controller": "player",
                            "category": "pc",
                            "position": {"x": 2, "y": 2},
                            "hp": {"current": 20, "temp": 0},
                            "initiative": 0,
                        },
                    }
                ],
            )

            self.assertEqual(result["encounter_id"], encounter.encounter_id)
            self.assertEqual(result["status"], "initialized")
            self.assertIsNone(result["encounter_state"]["current_turn_entity"])
            repo.close()
```

- [ ] **Step 2: Run the focused tests to confirm failure**

Run:

```bash
pytest test/test_encounter_service.py -k initialize_encounter -v
```

Expected:

```text
FAILED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_replaces_map_and_entities_and_resets_runtime_fields
FAILED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_with_state_returns_full_encounter_state
```

- [ ] **Step 3: Implement the minimal `initialize_encounter(...)` behavior**

Add these methods to `EncounterService` in `tools/services/encounter/manage_encounter_entities.py`:

```python
    def initialize_encounter(
        self,
        encounter_id: str,
        *,
        map_setup: dict[str, object],
        entity_setups: list[dict[str, object]],
    ) -> Encounter:
        encounter = self._get_encounter_or_raise(encounter_id)

        encounter.map = EncounterMap(
            map_id=str(map_setup["map_id"]),
            name=str(map_setup["name"]),
            description=str(map_setup.get("description", "")),
            width=int(map_setup["width"]),
            height=int(map_setup["height"]),
            terrain=list(map_setup.get("terrain", [])),
            zones=list(map_setup.get("zones", [])),
        )

        initialized_entities: dict[str, EncounterEntity] = {}
        for entity_setup in entity_setups:
            runtime_overrides = dict(entity_setup["runtime_overrides"])
            entity = EncounterEntity(
                entity_id=str(entity_setup["entity_instance_id"]),
                name=str(runtime_overrides["name"]),
                side=str(runtime_overrides["side"]),
                category=str(runtime_overrides["category"]),
                controller=str(runtime_overrides["controller"]),
                position=dict(runtime_overrides["position"]),
                hp={
                    "current": int(runtime_overrides["hp"]["current"]),
                    "max": int(runtime_overrides["hp"].get("max", runtime_overrides["hp"]["current"])),
                    "temp": int(runtime_overrides["hp"].get("temp", 0)),
                },
                ac=int(runtime_overrides.get("ac", 10)),
                speed=dict(runtime_overrides.get("speed", {"walk": 30, "remaining": 30})),
                initiative=int(runtime_overrides.get("initiative", 0)),
                size=str(runtime_overrides.get("size", "medium")),
                conditions=list(runtime_overrides.get("conditions", [])),
                notes=list(runtime_overrides.get("notes", [])),
                combat_flags=dict(runtime_overrides.get("combat_flags", {})),
                resources=dict(runtime_overrides.get("resources", {})),
            )
            self._validate_position_within_map(encounter, entity.position["x"], entity.position["y"])
            initialized_entities[entity.entity_id] = entity

        encounter.entities = initialized_entities
        encounter.turn_order = []
        encounter.current_entity_id = None
        encounter.round = 1
        encounter.reaction_requests = []
        encounter.pending_movement = None
        encounter.spell_instances = []
        encounter.encounter_notes = list(map_setup.get("battlemap_details", []))

        return self.repository.save(encounter)

    def initialize_encounter_with_state(
        self,
        encounter_id: str,
        *,
        map_setup: dict[str, object],
        entity_setups: list[dict[str, object]],
    ) -> dict[str, object]:
        updated = self.initialize_encounter(
            encounter_id,
            map_setup=map_setup,
            entity_setups=entity_setups,
        )
        return {
            "encounter_id": updated.encounter_id,
            "status": "initialized",
            "initialized_entities": list(updated.entities.keys()),
            "map_summary": {
                "map_id": updated.map.map_id,
                "width": updated.map.width,
                "height": updated.map.height,
            },
            "encounter_state": GetEncounterState(self.repository).execute(updated.encounter_id),
        }
```

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
pytest test/test_encounter_service.py -k initialize_encounter -v
```

Expected:

```text
PASSED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_replaces_map_and_entities_and_resets_runtime_fields
PASSED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_with_state_returns_full_encounter_state
```

- [ ] **Step 5: Commit the initialization service**

```bash
git add test/test_encounter_service.py tools/services/encounter/manage_encounter_entities.py
git commit -m "feat: add encounter initialization service"
```

### Task 2: Add `RollInitiativeAndStartEncounter`

**Files:**
- Create: `tools/services/encounter/roll_initiative_and_start_encounter.py`
- Modify: `tools/services/encounter/__init__.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_roll_initiative_and_start_encounter.py`

- [ ] **Step 1: Write the failing initiative tests**

```python
class RollInitiativeAndStartEncounterTests(unittest.TestCase):
    def test_rolls_initiative_sorts_turn_order_and_starts_first_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            entity_a = build_entity("ent_a", name="米伦", x=2, y=2, initiative=0)
            entity_a.ability_mods = {"dex": 3}
            entity_a.action_economy = {"action_used": True}
            entity_a.speed["remaining"] = 0

            entity_b = build_entity("ent_b", name="萨布尔", x=4, y=2, initiative=0)
            entity_b.ability_mods = {"dex": 1}

            encounter = Encounter(
                encounter_id="enc_initiative_test",
                name="Initiative Test",
                status="active",
                round=1,
                current_entity_id=None,
                turn_order=[],
                entities={"ent_a": entity_a, "ent_b": entity_b},
                map=EncounterMap(
                    map_id="map_init",
                    name="Map",
                    description="Map",
                    width=10,
                    height=10,
                ),
            )
            repo.save(encounter)

            with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[12, 12]):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.25, 0.10]):
                    result = RollInitiativeAndStartEncounter(repo).execute_with_state("enc_initiative_test")

            self.assertEqual(result["turn_order"], ["ent_a", "ent_b"])
            self.assertEqual(result["current_entity_id"], "ent_a")
            self.assertFalse(result["encounter_state"]["current_turn_entity"]["action_economy"]["action_used"])
            repo.close()

    def test_initiative_results_hide_internal_decimal_from_public_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            entity = build_entity("ent_a", name="米伦", x=2, y=2, initiative=0)
            entity.ability_mods = {"dex": 2}
            encounter = Encounter(
                encounter_id="enc_initiative_hidden_decimal",
                name="Hidden Decimal Test",
                status="active",
                round=1,
                current_entity_id=None,
                turn_order=[],
                entities={"ent_a": entity},
                map=EncounterMap(
                    map_id="map_init",
                    name="Map",
                    description="Map",
                    width=10,
                    height=10,
                ),
            )
            repo.save(encounter)

            with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", return_value=11):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", return_value=0.42):
                    result = RollInitiativeAndStartEncounter(repo).execute_with_state("enc_initiative_hidden_decimal")

            self.assertEqual(result["initiative_results"][0]["initiative_roll"], 11)
            self.assertEqual(result["initiative_results"][0]["initiative_modifier"], 2)
            self.assertEqual(result["initiative_results"][0]["initiative_total"], 13)
            self.assertNotIn("initiative_tiebreak_decimal", result["initiative_results"][0])
            repo.close()
```

- [ ] **Step 2: Run the focused tests to confirm failure**

Run:

```bash
pytest test/test_roll_initiative_and_start_encounter.py -v
```

Expected:

```text
ERROR file or directory not found: test/test_roll_initiative_and_start_encounter.py
```

- [ ] **Step 3: Implement the new initiative-start service and exports**

Create `tools/services/encounter/roll_initiative_and_start_encounter.py`:

```python
from __future__ import annotations

from random import random, randint

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.start_turn import StartTurn


class RollInitiativeAndStartEncounter:
    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(self, encounter_id: str) -> dict[str, object]:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        rolled_rows: list[dict[str, object]] = []
        for entity_id, entity in encounter.entities.items():
            modifier = int(entity.ability_mods.get("dex", 0))
            roll = randint(1, 20)
            tiebreak = round(random(), 2)
            total = roll + modifier
            rolled_rows.append(
                {
                    "entity_id": entity_id,
                    "name": entity.name,
                    "initiative_roll": roll,
                    "initiative_modifier": modifier,
                    "initiative_total": total,
                    "initiative_tiebreak_decimal": tiebreak,
                }
            )

        rolled_rows.sort(
            key=lambda row: (
                row["initiative_total"],
                row["initiative_modifier"],
                row["initiative_tiebreak_decimal"],
            ),
            reverse=True,
        )
        encounter.turn_order = [row["entity_id"] for row in rolled_rows]
        encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
        self.repository.save(encounter)
        StartTurn(self.repository).execute(encounter_id)

        return {
            "encounter_id": encounter_id,
            "turn_order": encounter.turn_order,
            "current_entity_id": encounter.current_entity_id,
            "initiative_results": [
                {
                    "entity_id": row["entity_id"],
                    "name": row["name"],
                    "initiative_roll": row["initiative_roll"],
                    "initiative_modifier": row["initiative_modifier"],
                    "initiative_total": row["initiative_total"],
                }
                for row in rolled_rows
            ],
        }

    def execute_with_state(self, encounter_id: str) -> dict[str, object]:
        result = self.execute(encounter_id)
        result["encounter_state"] = GetEncounterState(self.repository).execute(encounter_id)
        return result
```

Update `tools/services/encounter/__init__.py`:

```python
from tools.services.encounter.roll_initiative_and_start_encounter import RollInitiativeAndStartEncounter

__all__ = [
    "AdvanceTurn",
    "BeginMoveEncounterEntity",
    "ContinuePendingMovement",
    "EndTurn",
    "StartTurn",
    "EncounterService",
    "GetEncounterState",
    "MoveEncounterEntity",
    "ResolveForcedMovement",
    "RollInitiativeAndStartEncounter",
]
```

Update `tools/services/__init__.py`:

```python
from tools.services.encounter.roll_initiative_and_start_encounter import RollInitiativeAndStartEncounter

__all__ = [
    "AppendEvent",
    "EncounterCastSpell",
    "ExecuteSpell",
    "SpellRequest",
    "RetargetMarkedSpell",
    "ExecuteAttack",
    "ExecuteSaveSpell",
    "ExecuteConcentrationCheck",
    "AttackRollRequest",
    "AttackRollResult",
    "ResolveDamageParts",
    "ResolveReactionRequest",
    "AdvanceTurn",
    "BeginMoveEncounterEntity",
    "ContinuePendingMovement",
    "ResolveForcedMovement",
    "EndTurn",
    "StartTurn",
    "RollInitiativeAndStartEncounter",
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

- [ ] **Step 4: Run the initiative tests**

Run:

```bash
pytest test/test_roll_initiative_and_start_encounter.py -v
```

Expected:

```text
PASSED test/test_roll_initiative_and_start_encounter.py::RollInitiativeAndStartEncounterTests::test_rolls_initiative_sorts_turn_order_and_starts_first_turn
PASSED test/test_roll_initiative_and_start_encounter.py::RollInitiativeAndStartEncounterTests::test_initiative_results_hide_internal_decimal_from_public_payload
```

- [ ] **Step 5: Commit the initiative-start service**

```bash
git add test/test_roll_initiative_and_start_encounter.py tools/services/encounter/roll_initiative_and_start_encounter.py tools/services/encounter/__init__.py tools/services/__init__.py
git commit -m "feat: add initiative start service"
```

### Task 3: Write the `combat-runtime` skill files

**Files:**
- Create: `combat-runtime/SKILL.md`
- Create: `combat-runtime/references/runtime-protocol.md`
- Create: `combat-runtime/references/tool-catalog.md`
- Create: `combat-runtime/references/monster-turn-flow.md`
- Create: `combat-runtime/references/companion-npc-turn-flow.md`
- Create: `combat-runtime/references/intent-examples.md`

- [ ] **Step 1: Write the main skill entry**

Create `combat-runtime/SKILL.md`:

```markdown
# Combat Runtime Skill

这个 skill 只负责战斗期运行协议。

核心原则：

1. 先读 `GetEncounterState`
2. 若战斗尚未开始，先 `initialize_encounter`，再 `RollInitiativeAndStartEncounter`
3. 每次 mutation 后都改用最新 `encounter_state`
4. 任何 `waiting_reaction` 都必须先处理
5. 回合结束固定走 `EndTurn -> AdvanceTurn -> StartTurn`

阅读顺序：

- `references/runtime-protocol.md`
- `references/tool-catalog.md`
- `references/monster-turn-flow.md`
- `references/companion-npc-turn-flow.md`
- `references/intent-examples.md`
```

- [ ] **Step 2: Write the hard protocol and tool catalog**

Create `combat-runtime/references/runtime-protocol.md`:

```markdown
# Runtime Protocol

## 战斗开始

1. LLM 决定战场和参战者
2. 调 `initialize_encounter`
3. 页面刷新
4. 调 `RollInitiativeAndStartEncounter`
5. 向玩家播报 `initiative_results`
6. 宣布 `turn_order` 与当前行动者

## 战斗循环

1. 读 `GetEncounterState`
2. 判断当前行动者
3. 玩家回合时等待玩家明确行动
4. 怪物/NPC 回合时按对应 flow 自主决策
5. 每次状态变更后改用最新 `encounter_state`

## 硬性禁令

- 不手工改 HP、位置、condition、resources、turn order
- 不跳过 `waiting_reaction`
- 不在移动未完成前提前结算后续动作
- 不用旧状态继续推理
```

Create `combat-runtime/references/tool-catalog.md`:

```markdown
# Tool Catalog

## initialize_encounter

- 用途：把 LLM 决定好的地图和参战实体写入 encounter
- 何时调用：战斗开始但尚未开战时
- 下一步：刷新页面，然后调用 `RollInitiativeAndStartEncounter`

## RollInitiativeAndStartEncounter

- 用途：为当前 encounter 中全部参战实体掷先攻并正式开始第一回合
- 何时调用：`initialize_encounter` 完成后
- 下一步：向玩家播报 `initiative_results`

## GetEncounterState

- 用途：读取唯一事实源投影
- 何时调用：任何行动决策前，以及每次 mutation 后需要继续决策时

## BeginMoveEncounterEntity

- 用途：启动一次合法移动判定
- 何时调用：任何主动移动前
- 特殊返回：`waiting_reaction`

## ContinuePendingMovement

- 用途：reaction 处理完后继续未完成移动

## ResolveReactionRequest

- 用途：结算等待中的 reaction request

## ExecuteAttack

- 用途：执行一次攻击动作
- 前提：目标、范围、动作资源都仍合法

## ExecuteSpell

- 用途：执行一次法术动作
- 前提：法术、目标、法术位/资源都仍合法

## EndTurn / AdvanceTurn / StartTurn

- `EndTurn`：结束当前回合
- `AdvanceTurn`：推进先攻顺序
- `StartTurn`：开始下一位回合
```

- [ ] **Step 3: Write the monster, companion, and example references**

Create `combat-runtime/references/monster-turn-flow.md`:

```markdown
# Monster Turn Flow

1. 回合开始先读 `GetEncounterState`
2. 识别当前可合法影响的目标
3. 优先选择能立即击倒、高威胁、或能多目标命中的动作
4. 如需移动，先 `BeginMoveEncounterEntity`
5. 如遇 `waiting_reaction`，先停下处理
6. 移动完成后重新检查目标合法性
7. 攻击或施法
8. 结束回合时走 `EndTurn -> AdvanceTurn -> StartTurn`
```

Create `combat-runtime/references/companion-npc-turn-flow.md`:

```markdown
# Companion NPC Turn Flow

1. 回合开始先读 `GetEncounterState`
2. 若玩家已明确下达战术指令，优先执行
3. 若玩家未明确指挥，自主采取合理行动
4. 优先保护玩家阵营、补位、支援、处理玩家当前威胁
5. 不擅自做高风险剧情决定
6. 仍然严格遵守同一套 runtime-protocol
```

Create `combat-runtime/references/intent-examples.md`:

```markdown
# Intent Examples

## 玩家说：“我移动到 7,10 再砍兽人”

1. 调 `BeginMoveEncounterEntity`
2. 若返回 `waiting_reaction`，先处理 reaction
3. 移动完成后读最新状态
4. 检查兽人是否仍在合法攻击范围
5. 调 `ExecuteAttack`

## 玩家说：“我结束回合”

1. 调 `EndTurn`
2. 调 `AdvanceTurn`
3. 调 `StartTurn`

## 怪物回合：近战怪想接近玩家

1. 读 `GetEncounterState`
2. 选择最近且可合法接近的玩家目标
3. 调 `BeginMoveEncounterEntity`
4. 移动完成后调 `ExecuteAttack`
```

- [ ] **Step 4: Verify the files exist and are readable**

Run:

```bash
find combat-runtime -maxdepth 2 -type f | sort
```

Expected:

```text
combat-runtime/SKILL.md
combat-runtime/references/companion-npc-turn-flow.md
combat-runtime/references/intent-examples.md
combat-runtime/references/monster-turn-flow.md
combat-runtime/references/runtime-protocol.md
combat-runtime/references/tool-catalog.md
```

- [ ] **Step 5: Commit the new combat runtime skill**

```bash
git add combat-runtime
git commit -m "feat: add combat runtime skill docs"
```

### Task 4: Run integration verification and tighten plan/documentation fit

**Files:**
- Modify: `docs/superpowers/specs/2026-04-16-combat-runtime-skill-design.md` (only if the implementation differs)
- Test: `test/test_encounter_service.py`
- Test: `test/test_roll_initiative_and_start_encounter.py`

- [ ] **Step 1: Run the service test slice together**

Run:

```bash
pytest test/test_encounter_service.py test/test_roll_initiative_and_start_encounter.py -v
```

Expected:

```text
PASSED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_replaces_map_and_entities_and_resets_runtime_fields
PASSED test/test_encounter_service.py::EncounterServiceTests::test_initialize_encounter_with_state_returns_full_encounter_state
PASSED test/test_roll_initiative_and_start_encounter.py::RollInitiativeAndStartEncounterTests::test_rolls_initiative_sorts_turn_order_and_starts_first_turn
PASSED test/test_roll_initiative_and_start_encounter.py::RollInitiativeAndStartEncounterTests::test_initiative_results_hide_internal_decimal_from_public_payload
```

- [ ] **Step 2: Run the broader encounter test suite**

Run:

```bash
pytest test/test_start_turn.py test/test_advance_turn.py test/test_get_encounter_state.py test/test_encounter_service.py test/test_roll_initiative_and_start_encounter.py -v
```

Expected:

```text
PASSED test/test_start_turn.py
PASSED test/test_advance_turn.py
PASSED test/test_get_encounter_state.py
PASSED test/test_encounter_service.py
PASSED test/test_roll_initiative_and_start_encounter.py
```

- [ ] **Step 3: If implementation drifted, sync the spec**

If the implementation uses a different return shape from the draft, update `docs/superpowers/specs/2026-04-16-combat-runtime-skill-design.md` so it matches code exactly. Keep the wording concrete, for example:

```markdown
- `initialize_encounter_with_state` returns:
  - `encounter_id`
  - `status`
  - `initialized_entities`
  - `map_summary`
  - `encounter_state`
```

- [ ] **Step 4: Re-run `git diff --stat` and inspect the touched files**

Run:

```bash
git diff --stat HEAD~3..HEAD
```

Expected:

```text
 combat-runtime/SKILL.md                                  | ...
 combat-runtime/references/runtime-protocol.md            | ...
 test/test_encounter_service.py                           | ...
 test/test_roll_initiative_and_start_encounter.py         | ...
 tools/services/encounter/manage_encounter_entities.py    | ...
 tools/services/encounter/roll_initiative_and_start_encounter.py | ...
```

- [ ] **Step 5: Commit the verification / spec sync if needed**

```bash
git add docs/superpowers/specs/2026-04-16-combat-runtime-skill-design.md
git commit -m "docs: sync combat runtime spec to implementation"
```

## Self-Review

- Spec coverage:
  - `initialize_encounter` covered in Task 1
  - `RollInitiativeAndStartEncounter` covered in Task 2
  - `combat-runtime` skill files covered in Task 3
  - integration verification and spec drift handling covered in Task 4
- Placeholder scan:
  - No `TODO`, `TBD`, or “implement later” markers remain
- Type consistency:
  - Plan uses `initialize_encounter`, `initialize_encounter_with_state`, and `RollInitiativeAndStartEncounter` consistently across tasks
