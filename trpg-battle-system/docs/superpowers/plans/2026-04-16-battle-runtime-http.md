# Battle Runtime HTTP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗系统增加常驻 HTTP battle runtime，并用 3 个高频命令把随机遭遇、移动后攻击、回合推进收口成稳定入口。

**Architecture:** 新增 `runtime/` 包承载常驻上下文、命令分发与 HTTP 路由，底层规则继续复用现有 `tools/services`。第一版只暴露 `POST /runtime/command`、`GET /runtime/health`、`GET /runtime/encounter-state`，并让 localhost battlemap 可以从 runtime 拉取状态而不是直接碰仓储。

**Tech Stack:** Python 3、unittest、http.server、urllib、现有 TinyDB-style repositories、现有 combat/encounter services

---

### Task 1: 建立 runtime 上下文与命令分发骨架

**Files:**
- Create: `runtime/__init__.py`
- Create: `runtime/context.py`
- Create: `runtime/dispatcher.py`
- Create: `test/test_runtime_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command


class RuntimeDispatcherTests(unittest.TestCase):
    def test_unknown_command_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))

            result = execute_runtime_command(
                context,
                command="unknown_command",
                args={"encounter_id": "enc_test"},
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["command"], "unknown_command")
            self.assertEqual(result["error_code"], "unknown_command")
            self.assertEqual(result["result"], None)

    def test_dispatcher_wraps_success_payload_and_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))

            def fake_handler(ctx, args):
                self.assertIs(ctx, context)
                self.assertEqual(args["encounter_id"], "enc_test")
                return {
                    "encounter_id": "enc_test",
                    "result": {"message": "ok"},
                    "encounter_state": {"encounter_id": "enc_test", "round": 1},
                }

            result = execute_runtime_command(
                context,
                command="test_command",
                args={"encounter_id": "enc_test"},
                handlers={"test_command": fake_handler},
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["message"], "ok")
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_dispatcher -v`

Expected: FAIL，`runtime` 包或 `build_runtime_context` / `execute_runtime_command` 尚不存在

- [ ] **Step 3: Write minimal implementation**

```python
# runtime/context.py
from dataclasses import dataclass
from pathlib import Path

from tools.repositories import EncounterRepository, EventRepository
from tools.repositories.entity_definition_repository import EntityDefinitionRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.services import GetEncounterState


@dataclass
class BattleRuntimeContext:
    encounter_repository: EncounterRepository
    event_repository: EventRepository
    entity_definition_repository: EntityDefinitionRepository
    spell_definition_repository: SpellDefinitionRepository

    def get_encounter_state(self, encounter_id: str) -> dict:
        return GetEncounterState(
            self.encounter_repository,
            event_repository=self.event_repository,
        ).execute(encounter_id)


def build_runtime_context(*, data_dir: Path | None = None) -> BattleRuntimeContext:
    if data_dir is None:
        return BattleRuntimeContext(
            encounter_repository=EncounterRepository(),
            event_repository=EventRepository(),
            entity_definition_repository=EntityDefinitionRepository(),
            spell_definition_repository=SpellDefinitionRepository(),
        )
    return BattleRuntimeContext(
        encounter_repository=EncounterRepository(data_dir / "encounters.json"),
        event_repository=EventRepository(data_dir / "events.json"),
        entity_definition_repository=EntityDefinitionRepository(),
        spell_definition_repository=SpellDefinitionRepository(),
    )
```

```python
# runtime/dispatcher.py
from typing import Any, Callable


RuntimeHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]


def execute_runtime_command(context, *, command: str, args: dict[str, Any], handlers: dict[str, RuntimeHandler] | None = None) -> dict[str, Any]:
    available_handlers = handlers or {}
    handler = available_handlers.get(command)
    if handler is None:
        return {
            "ok": False,
            "command": command,
            "error_code": "unknown_command",
            "message": f"unknown runtime command '{command}'",
            "result": None,
            "encounter_state": None,
        }

    try:
        payload = handler(context, args)
    except ValueError as error:
        encounter_id = args.get("encounter_id")
        encounter_state = None
        if encounter_id:
            try:
                encounter_state = context.get_encounter_state(encounter_id)
            except ValueError:
                encounter_state = None
        return {
            "ok": False,
            "command": command,
            "error_code": str(error),
            "message": str(error),
            "result": None,
            "encounter_state": encounter_state,
        }

    return {
        "ok": True,
        "command": command,
        "result": payload.get("result"),
        "encounter_state": payload.get("encounter_state"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_dispatcher -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  runtime/__init__.py \
  runtime/context.py \
  runtime/dispatcher.py \
  test/test_runtime_dispatcher.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add battle runtime dispatcher core"
```

### Task 2: 实现 `start_random_encounter` 命令

**Files:**
- Create: `runtime/commands/__init__.py`
- Create: `runtime/commands/start_random_encounter.py`
- Create: `runtime/presets/random_encounters.py`
- Create: `test/test_runtime_start_random_encounter.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands.start_random_encounter import start_random_encounter
from runtime.context import build_runtime_context


class RuntimeStartRandomEncounterTests(unittest.TestCase):
    def test_start_random_encounter_initializes_map_rolls_initiative_and_returns_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))

            with patch(
                "runtime.presets.random_encounters.choose_random_encounter_setup",
                return_value={
                    "encounter_name": "林间伏击",
                    "map_setup": {
                        "map_id": "map_forest",
                        "name": "林地小径",
                        "description": "树林中的狭窄道路",
                        "width": 20,
                        "height": 20,
                        "grid_size_feet": 5,
                        "terrain": [],
                        "zones": [],
                        "auras": [],
                        "remains": [],
                        "battlemap_details": [{"title": "树林", "summary": "树木遮挡视线"}],
                    },
                    "entity_setups": [
                        {
                            "entity_instance_id": "ent_ally_wizard_001",
                            "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                            "runtime_overrides": {"name": "米伦", "position": {"x": 4, "y": 4}},
                        },
                        {
                            "entity_instance_id": "ent_enemy_brute_001",
                            "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                            "runtime_overrides": {"name": "荒林掠夺者", "position": {"x": 11, "y": 9}},
                        },
                    ],
                },
            ):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[14, 8]):
                    with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.12, 0.03]):
                        result = start_random_encounter(
                            context,
                            {"encounter_id": "enc_runtime_demo", "theme": "forest_road"},
                        )

            self.assertEqual(result["result"]["encounter_name"], "林间伏击")
            self.assertEqual(result["result"]["map_name"], "林地小径")
            self.assertEqual(result["result"]["current_entity_id"], "ent_ally_wizard_001")
            self.assertEqual(len(result["result"]["initiative_results"]), 2)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_runtime_demo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_start_random_encounter -v`

Expected: FAIL，命令模块与随机预设尚不存在

- [ ] **Step 3: Write minimal implementation**

```python
# runtime/presets/random_encounters.py
import random


RANDOM_ENCOUNTER_SETUPS = {
    "forest_road": [
        {
            "encounter_name": "林间伏击",
            "map_setup": {
                "map_id": "map_forest_road_01",
                "name": "林地小径",
                "description": "树林中的狭窄道路",
                "width": 20,
                "height": 20,
                "grid_size_feet": 5,
                "terrain": [
                    {"x": 9, "y": 6, "type": "wall", "label": "老树"},
                    {"x": 10, "y": 6, "type": "wall", "label": "老树"},
                ],
                "zones": [],
                "auras": [],
                "remains": [],
                "battlemap_details": [{"title": "树林", "summary": "树木遮挡视线"}],
            },
            "entity_setups": [
                {
                    "entity_instance_id": "ent_ally_wizard_001",
                    "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                    "runtime_overrides": {"name": "米伦", "position": {"x": 4, "y": 4}},
                },
                {
                    "entity_instance_id": "ent_ally_ranger_001",
                    "template_ref": {"source_type": "pc", "template_id": "pc_sabur"},
                    "runtime_overrides": {"name": "萨布尔", "position": {"x": 5, "y": 6}},
                },
                {
                    "entity_instance_id": "ent_enemy_raider_001",
                    "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                    "runtime_overrides": {"name": "荒林掠夺者", "position": {"x": 12, "y": 8}},
                },
            ],
        }
    ],
    "swamp_road": [
        {
            "encounter_name": "沼路袭击",
            "map_setup": {
                "map_id": "map_swamp_road_01",
                "name": "沼泽土路",
                "description": "泥泞地面与浅水坑交错",
                "width": 20,
                "height": 20,
                "grid_size_feet": 5,
                "terrain": [
                    {"x": 8, "y": 9, "type": "difficult", "label": "泥潭"},
                    {"x": 9, "y": 9, "type": "difficult", "label": "泥潭"},
                ],
                "zones": [],
                "auras": [],
                "remains": [],
                "battlemap_details": [{"title": "沼地", "summary": "泥潭会拖慢移动"}],
            },
            "entity_setups": [
                {
                    "entity_instance_id": "ent_ally_wizard_001",
                    "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                    "runtime_overrides": {"name": "米伦", "position": {"x": 3, "y": 5}},
                },
                {
                    "entity_instance_id": "ent_enemy_brute_001",
                    "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                    "runtime_overrides": {"name": "泥沼蛮兵", "position": {"x": 13, "y": 11}},
                },
            ],
        }
    ],
}


def choose_random_encounter_setup(theme: str | None = None) -> dict:
    if theme and theme in RANDOM_ENCOUNTER_SETUPS:
        return random.choice(RANDOM_ENCOUNTER_SETUPS[theme])
    all_setups = [item for items in RANDOM_ENCOUNTER_SETUPS.values() for item in items]
    return random.choice(all_setups)
```

```python
# runtime/commands/start_random_encounter.py
from tools.models import Encounter, EncounterMap
from tools.services import RollInitiativeAndStartEncounter
from tools.services.encounter.manage_encounter_entities import EncounterService

from runtime.presets.random_encounters import choose_random_encounter_setup


def start_random_encounter(context, args: dict[str, object]) -> dict[str, object]:
    encounter_id = str(args["encounter_id"])
    setup = choose_random_encounter_setup(args.get("theme"))

    existing = context.encounter_repository.get(encounter_id)
    if existing is None:
        context.encounter_repository.save(
            Encounter(
                encounter_id=encounter_id,
                name=str(setup["encounter_name"]),
                status="active",
                round=1,
                current_entity_id=None,
                turn_order=[],
                entities={},
                map=EncounterMap(map_id="runtime_bootstrap", name="Runtime Bootstrap", description="", width=1, height=1),
            )
        )

    service = EncounterService(
        context.encounter_repository,
        entity_definition_repository=context.entity_definition_repository,
    )
    service.initialize_encounter(
        encounter_id,
        map_setup=setup["map_setup"],
        entity_setups=setup["entity_setups"],
    )
    started = RollInitiativeAndStartEncounter(context.encounter_repository).execute_with_state(encounter_id)
    return {
        "encounter_id": encounter_id,
        "result": {
            "encounter_name": setup["encounter_name"],
            "map_name": setup["map_setup"]["name"],
            "initiative_results": started["initiative_results"],
            "turn_order": started["turn_order"],
            "current_entity_id": started["current_entity_id"],
        },
        "encounter_state": started["encounter_state"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_start_random_encounter -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  runtime/commands/__init__.py \
  runtime/commands/start_random_encounter.py \
  runtime/presets/random_encounters.py \
  test/test_runtime_start_random_encounter.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add start random encounter runtime command"
```

### Task 3: 实现 `move_and_attack` 命令

**Files:**
- Create: `runtime/commands/move_and_attack.py`
- Modify: `runtime/commands/__init__.py`
- Create: `test/test_runtime_move_and_attack.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands.move_and_attack import move_and_attack
from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeMoveAndAttackTests(unittest.TestCase):
    def test_returns_waiting_reaction_without_executing_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            ensure_preview_encounter(context.encounter_repository)

            with patch(
                "runtime.commands.move_and_attack.BeginMoveEncounterEntity.execute_with_state",
                return_value={
                    "encounter_id": "enc_preview_demo",
                    "entity_id": "ent_enemy_brute_001",
                    "movement_status": "waiting_reaction",
                    "reaction_requests": [{"request_id": "react_001"}],
                    "encounter_state": {"encounter_id": "enc_preview_demo", "reaction_requests": [{"request_id": "react_001"}]},
                },
            ):
                result = move_and_attack(
                    context,
                    {
                        "encounter_id": "enc_preview_demo",
                        "actor_id": "ent_enemy_brute_001",
                        "target_position": {"x": 11, "y": 10},
                        "target_id": "ent_ally_ranger_001",
                        "weapon_id": "battleaxe",
                    },
                )

            self.assertEqual(result["result"]["movement_result"]["movement_status"], "waiting_reaction")
            self.assertEqual(result["result"]["attack_result"], None)

    def test_returns_structured_error_when_attack_invalid_after_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            ensure_preview_encounter(context.encounter_repository)

            with patch(
                "runtime.commands.move_and_attack.BeginMoveEncounterEntity.execute_with_state",
                return_value={
                    "encounter_id": "enc_preview_demo",
                    "entity_id": "ent_ally_ranger_001",
                    "movement_status": "completed",
                    "reaction_requests": [],
                    "encounter_state": {"encounter_id": "enc_preview_demo"},
                },
            ):
                with patch(
                    "runtime.commands.move_and_attack.ExecuteAttack.execute",
                    return_value={
                        "status": "invalid_attack",
                        "reason": "target_out_of_range",
                        "message_for_llm": "当前目标不在攻击范围内，请重新选择目标或调整位置。",
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    result = move_and_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_ranger_001",
                            "target_position": {"x": 8, "y": 10},
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "shortbow",
                        },
                    )

            self.assertEqual(result["error_code"], "attack_invalid_after_movement")
            self.assertEqual(result["result"]["movement_result"]["movement_status"], "completed")
            self.assertEqual(result["result"]["attack_result"]["reason"], "target_out_of_range")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_move_and_attack -v`

Expected: FAIL，`move_and_attack` 命令尚不存在

- [ ] **Step 3: Write minimal implementation**

```python
from tools.repositories.entity_definition_repository import EntityDefinitionRepository
from tools.services import AttackRollRequest, AttackRollResult, BeginMoveEncounterEntity, ExecuteAttack, UpdateHp
from tools.services.events.append_event import AppendEvent


def move_and_attack(context, args: dict[str, object]) -> dict[str, object]:
    encounter_id = str(args["encounter_id"])
    actor_id = str(args["actor_id"])
    movement_result = BeginMoveEncounterEntity(
        context.encounter_repository,
        AppendEvent(context.event_repository),
    ).execute_with_state(
        encounter_id=encounter_id,
        entity_id=actor_id,
        target_position=args["target_position"],
        use_dash=bool(args.get("use_dash", False)),
    )

    if movement_result["movement_status"] == "waiting_reaction":
        return {
            "encounter_id": encounter_id,
            "result": {
                "movement_result": movement_result,
                "attack_result": None,
            },
            "encounter_state": movement_result["encounter_state"],
        }

    execute_attack = ExecuteAttack(
        AttackRollRequest(
            context.encounter_repository,
            entity_definition_repository=EntityDefinitionRepository(),
        ),
        AttackRollResult(
            encounter_repository=context.encounter_repository,
            update_hp=UpdateHp(context.encounter_repository, context.event_repository),
            append_event=AppendEvent(context.event_repository),
        ),
    )
    attack_result = execute_attack.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        target_id=str(args["target_id"]),
        weapon_id=str(args["weapon_id"]),
        final_total=int(args["attack_roll"]["final_total"]),
        dice_rolls=dict(args["attack_roll"]["dice_rolls"]),
        damage_rolls=list(args.get("damage_rolls", [])),
        include_encounter_state=True,
    )
    if attack_result.get("status") == "invalid_attack":
        return {
            "encounter_id": encounter_id,
            "error_code": "attack_invalid_after_movement",
            "result": {
                "movement_result": movement_result,
                "attack_result": attack_result,
            },
            "encounter_state": attack_result["encounter_state"],
        }
    return {
        "encounter_id": encounter_id,
        "result": {
            "movement_result": movement_result,
            "attack_result": attack_result,
        },
        "encounter_state": attack_result["encounter_state"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_move_and_attack -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  runtime/commands/__init__.py \
  runtime/commands/move_and_attack.py \
  test/test_runtime_move_and_attack.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add move and attack runtime command"
```

### Task 4: 实现 `end_turn_and_advance` 与 HTTP runtime 服务

**Files:**
- Create: `runtime/commands/end_turn_and_advance.py`
- Modify: `runtime/commands/__init__.py`
- Create: `runtime/http_server.py`
- Create: `scripts/run_battle_runtime.py`
- Create: `test/test_runtime_end_turn_and_advance.py`
- Create: `test/test_runtime_http_server.py`

- [ ] **Step 1: Write the failing tests**

```python
import tempfile
import unittest
from pathlib import Path

from runtime.commands.end_turn_and_advance import end_turn_and_advance
from runtime.context import build_runtime_context
from runtime.http_server import build_runtime_handler_class
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeEndTurnAndAdvanceTests(unittest.TestCase):
    def test_runs_end_advance_start_and_returns_new_current_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            ensure_preview_encounter(context.encounter_repository)

            result = end_turn_and_advance(context, {"encounter_id": "enc_preview_demo"})

            self.assertIn("ended_entity_id", result["result"])
            self.assertIn("current_entity_id", result["result"])
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["id"], result["result"]["current_entity_id"])


class RuntimeHttpServerTests(unittest.TestCase):
    def test_health_endpoint_returns_ok_payload(self) -> None:
        handler_cls = build_runtime_handler_class(runtime_context=None)
        payload = handler_cls.build_health_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("commands", payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_end_turn_and_advance test.test_runtime_http_server -v`

Expected: FAIL，命令与 HTTP server 尚不存在

- [ ] **Step 3: Write minimal implementation**

```python
# runtime/commands/end_turn_and_advance.py
from tools.services.encounter.turns import AdvanceTurn, EndTurn, StartTurn


def end_turn_and_advance(context, args: dict[str, object]) -> dict[str, object]:
    encounter_id = str(args["encounter_id"])
    ended = EndTurn(context.encounter_repository).execute(encounter_id)
    advanced = AdvanceTurn(context.encounter_repository).execute(encounter_id)
    started = StartTurn(context.encounter_repository).execute(encounter_id)
    return {
        "encounter_id": encounter_id,
        "result": {
            "ended_entity_id": ended.current_entity_id,
            "current_entity_id": started.current_entity_id,
            "round": started.round,
            "turn_effect_resolutions": started.encounter_notes[-5:],
        },
        "encounter_state": context.get_encounter_state(encounter_id),
    }
```

```python
# runtime/http_server.py
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from runtime.dispatcher import execute_runtime_command
from runtime.commands import COMMAND_HANDLERS


def build_runtime_handler_class(*, runtime_context):
    class BattleRuntimeHandler(BaseHTTPRequestHandler):
        context = runtime_context

        @staticmethod
        def build_health_payload() -> dict[str, object]:
            return {
                "status": "ok",
                "commands": sorted(COMMAND_HANDLERS.keys()),
            }

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/runtime/health":
                self._write_json(200, self.build_health_payload())
                return
            if parsed.path == "/runtime/encounter-state":
                encounter_id = parse_qs(parsed.query).get("encounter_id", [""])[0]
                self._write_json(200, self.context.get_encounter_state(encounter_id))
                return
            self.send_error(404, "Not Found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/runtime/command":
                self.send_error(404, "Not Found")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
            payload = json.loads(body or b"{}")
            result = execute_runtime_command(
                self.context,
                command=str(payload.get("command", "")),
                args=dict(payload.get("args", {})),
                handlers=COMMAND_HANDLERS,
            )
            self._write_json(200, result)

        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return BattleRuntimeHandler
```

```python
# scripts/run_battle_runtime.py
import argparse

from runtime.context import build_runtime_context
from runtime.http_server import build_runtime_handler_class, ThreadingHTTPServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run persistent battle runtime server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8771, type=int)
    args = parser.parse_args()

    context = build_runtime_context()
    handler_class = build_runtime_handler_class(runtime_context=context)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    try:
        print(f"http://{args.host}:{args.port}")
        server.serve_forever()
    finally:
        context.encounter_repository.close()
        context.event_repository.close()
        server.server_close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_end_turn_and_advance test.test_runtime_http_server -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  runtime/commands/__init__.py \
  runtime/commands/end_turn_and_advance.py \
  runtime/http_server.py \
  scripts/run_battle_runtime.py \
  test/test_runtime_end_turn_and_advance.py \
  test/test_runtime_http_server.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add battle runtime http server"
```

### Task 5: 让 localhost battlemap demo 真正走 runtime

**Files:**
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_run_battlemap_localhost.py`
- Create: `test/test_battlemap_runtime_integration.py`
- Modify: `trpg-battle-system/SKILL.md`

- [ ] **Step 1: Write the failing tests**

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_battlemap_localhost import bootstrap_runtime_encounter, render_localhost_battlemap_page


class BattlemapRuntimeIntegrationTests(unittest.TestCase):
    def test_bootstrap_runtime_encounter_posts_start_random_command(self) -> None:
        with patch("scripts.run_battlemap_localhost.post_runtime_command") as post_runtime_command:
            bootstrap_runtime_encounter(
                runtime_base_url="http://127.0.0.1:8771",
                encounter_id="enc_preview_demo",
                theme="forest_road",
            )
        post_runtime_command.assert_called_once_with(
            "http://127.0.0.1:8771",
            command="start_random_encounter",
            args={"encounter_id": "enc_preview_demo", "theme": "forest_road"},
        )

    def test_render_localhost_page_polls_runtime_backed_api(self) -> None:
        html = render_localhost_battlemap_page(
            encounter_id="enc_preview_demo",
            page_title="Battlemap Localhost",
        )
        self.assertIn("/api/encounter-state?encounter_id=", html)
        self.assertIn("fetchLatestEncounterState", html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_run_battlemap_localhost test.test_battlemap_runtime_integration -v`

Expected: FAIL，当前 localhost 页面仍直接依赖仓储预种 encounter

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/run_battlemap_localhost.py
import urllib.request


def post_runtime_command(runtime_base_url: str, *, command: str, args: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        f"{runtime_base_url.rstrip('/')}/runtime/command",
        data=json.dumps({"command": command, "args": args}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_runtime_encounter_state(runtime_base_url: str, encounter_id: str) -> dict[str, object]:
    with urllib.request.urlopen(
        f"{runtime_base_url.rstrip('/')}/runtime/encounter-state?encounter_id={encounter_id}"
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def bootstrap_runtime_encounter(*, runtime_base_url: str, encounter_id: str, theme: str | None) -> dict[str, object]:
    return post_runtime_command(
        runtime_base_url,
        command="start_random_encounter",
        args={"encounter_id": encounter_id, "theme": theme},
    )
```

```python
def render_localhost_battlemap_page(*, encounter_id: str, page_title: str, dev_reload_path: str | None = None) -> str:
    html = RenderBattlemapPage().execute(build_preview_encounter())
    polling_script = (
        "<script>"
        "(function(){"
        f"document.title={json.dumps(page_title, ensure_ascii=False)};"
        f"var encounterId={json.dumps(encounter_id, ensure_ascii=False)};"
        "var lastSerializedState=null;"
        "async function fetchLatestEncounterState(){"
        "var response=await fetch('/api/encounter-state?encounter_id=' + encodeURIComponent(encounterId),{cache:'no-store'});"
        "if(!response.ok){throw new Error('failed to fetch runtime encounter state');}"
        "var nextState=await response.json();"
        "var serialized=JSON.stringify(nextState);"
        "if(serialized===lastSerializedState){return null;}"
        "lastSerializedState=serialized;"
        "return window.applyEncounterState(nextState);"
        "}"
        "window.__BATTLEMAP_RUNTIME__.fetchLatestEncounterState=fetchLatestEncounterState;"
        "window.__BATTLEMAP_RUNTIME__.pollIntervalMs=1000;"
        "setInterval(fetchLatestEncounterState, window.__BATTLEMAP_RUNTIME__.pollIntervalMs);"
        "})();"
        "</script>"
    )
```

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Run local battlemap preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8769, type=int)
    parser.add_argument("--runtime-base-url", default="http://127.0.0.1:8771")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--dev-reload-path", default=None)
    args = parser.parse_args()

    if args.runtime_base_url:
        bootstrap_runtime_encounter(
            runtime_base_url=args.runtime_base_url,
            encounter_id=PREVIEW_ENCOUNTER_ID,
            theme=args.theme,
        )
```

```markdown
# trpg-battle-system/SKILL.md
- 开发模式推荐先启动 `python3 scripts/run_battle_runtime.py`
- 若要看 battlemap，则再启动 `python3 scripts/run_battlemap_localhost.py --runtime-base-url http://127.0.0.1:8771`
- battlemap localhost 页面只负责展示与轮询，不再直接编排遭遇战
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_run_battlemap_localhost test.test_battlemap_runtime_integration -v`

Expected: PASS

- [ ] **Step 5: Run focused regression**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_runtime_dispatcher test.test_runtime_start_random_encounter test.test_runtime_move_and_attack test.test_runtime_end_turn_and_advance test.test_runtime_http_server test.test_run_battlemap_localhost test.test_battlemap_runtime_integration -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  scripts/run_battlemap_localhost.py \
  test/test_run_battlemap_localhost.py \
  test/test_battlemap_runtime_integration.py \
  SKILL.md
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: route battlemap localhost through runtime"
```

### Task 6: 完整回归并手动验证 runtime 启动链

**Files:**
- Modify: `runtime/__init__.py`
- Modify: `runtime/commands/__init__.py`
- Modify: `scripts/run_battle_runtime.py`
- Modify: `scripts/run_battlemap_localhost.py`

- [ ] **Step 1: Export final command registry**

```python
# runtime/commands/__init__.py
from runtime.commands.end_turn_and_advance import end_turn_and_advance
from runtime.commands.move_and_attack import move_and_attack
from runtime.commands.start_random_encounter import start_random_encounter

COMMAND_HANDLERS = {
    "start_random_encounter": start_random_encounter,
    "move_and_attack": move_and_attack,
    "end_turn_and_advance": end_turn_and_advance,
}
```

- [ ] **Step 2: Run full regression**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest discover -s test -p 'test_*.py'`

Expected: PASS

- [ ] **Step 3: Manual runtime smoke test**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 scripts/run_battle_runtime.py --port 8771`

Expected: 控制台输出 `http://127.0.0.1:8771`

Run: `curl -s http://127.0.0.1:8771/runtime/health`

Expected:

```json
{"status":"ok","commands":["end_turn_and_advance","move_and_attack","start_random_encounter"]}
```

Run:

```bash
curl -s http://127.0.0.1:8771/runtime/command \
  -H 'Content-Type: application/json' \
  -d '{"command":"start_random_encounter","args":{"encounter_id":"enc_preview_demo","theme":"forest_road"}}'
```

Expected: 返回 `ok: true`，并带有 `initiative_results`、`turn_order`、`encounter_state`

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 scripts/run_battlemap_localhost.py --runtime-base-url http://127.0.0.1:8771 --port 8769`

Expected: 浏览器打开 `http://127.0.0.1:8769/` 后能看到 battlemap、先攻表、当前行动者高亮，且页面轮询拿到 runtime 最新状态

- [ ] **Step 4: Commit**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  runtime/__init__.py \
  runtime/commands/__init__.py \
  scripts/run_battle_runtime.py \
  scripts/run_battlemap_localhost.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: ship first battle runtime http workflow"
```
