# Runtime Execute Attack Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 battle runtime 新增独立的 `execute_attack` command，让普通攻击、轻型额外攻击、投掷攻击、借机攻击都能通过同一个 runtime 入口调用，并默认由后端自动掷攻击骰与伤害骰。

**Architecture:** 新增一个薄适配层 `runtime/commands/execute_attack.py`，只做参数读取、service 装配与标准 payload 返回；所有规则继续落在现有 `tools.services.combat.attack.ExecuteAttack`。`runtime/commands/__init__.py` 负责注册 command，测试分为 command 单测与 dispatcher/http 集成验证。

**Tech Stack:** Python 3, unittest, battle runtime HTTP server, existing `ExecuteAttack` service, existing encounter/event repositories.

---

## 文件结构

### 新增文件

- `trpg-battle-system/runtime/commands/execute_attack.py`
  - 新的 runtime command 入口
- `trpg-battle-system/test/test_runtime_execute_attack.py`
  - 覆盖普通攻击、借机攻击、轻型额外攻击、投掷攻击、非法攻击与参数缺失

### 修改文件

- `trpg-battle-system/runtime/commands/__init__.py`
  - 注册 `execute_attack`
- `trpg-battle-system/test/test_runtime_http_server.py`
  - 验证 health/command 列表包含 `execute_attack`
- `trpg-battle-system/test/test_runtime_dispatcher.py`
  - 验证 dispatcher 通过 handler 执行新的 command

### 复用但不改动为主的文件

- `trpg-battle-system/tools/services/combat/attack/execute_attack.py`
- `trpg-battle-system/tools/services/combat/attack/attack_roll_request.py`
- `trpg-battle-system/runtime/context.py`

---

### Task 1: 新增 `execute_attack` runtime command

**Files:**
- Create: `trpg-battle-system/runtime/commands/execute_attack.py`
- Test: `trpg-battle-system/test/test_runtime_execute_attack.py`

- [ ] **Step 1: 写普通攻击的失败测试**

```python
def test_execute_attack_runs_normal_attack_and_returns_encounter_state(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        context = build_runtime_context(data_dir=Path(tmp_dir))
        try:
            ensure_preview_encounter(context.encounter_repository)
            execute_attack_module = import_module("runtime.commands.execute_attack")
            with patch.object(
                execute_attack_module.ExecuteAttack,
                "execute",
                return_value={
                    "request": {"encounter_id": "enc_preview_demo"},
                    "roll_result": {"final_total": 16},
                    "resolution": {"hit": True},
                    "encounter_state": {"encounter_id": "enc_preview_demo"},
                },
            ) as mocked_execute:
                result = execute_attack(
                    context,
                    {
                        "encounter_id": "enc_preview_demo",
                        "actor_id": "ent_ally_wizard_001",
                        "target_id": "ent_enemy_brute_001",
                        "weapon_id": "dagger",
                    },
                )

            self.assertEqual(result["encounter_id"], "enc_preview_demo")
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
            _, kwargs = mocked_execute.call_args
            self.assertEqual(kwargs["actor_id"], "ent_ally_wizard_001")
            self.assertEqual(kwargs["target_id"], "ent_enemy_brute_001")
            self.assertEqual(kwargs["weapon_id"], "dagger")
            self.assertTrue(kwargs["include_encounter_state"])
        finally:
            context.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_runtime_execute_attack -v`
Expected: FAIL with `ModuleNotFoundError` or `cannot import name 'execute_attack'`

- [ ] **Step 3: 写最小实现**

```python
from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AttackRollRequest, AttackRollResult, ExecuteAttack, UpdateHp
from tools.services.events.append_event import AppendEvent


def _require_arg(args: dict[str, object], key: str) -> str:
    value = args.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{key} is required")
    return str(value)


def execute_attack(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = _require_arg(args, "encounter_id")
    actor_id = _require_arg(args, "actor_id")
    target_id = _require_arg(args, "target_id")
    weapon_id = _require_arg(args, "weapon_id")

    append_event = AppendEvent(context.event_repository)
    service = ExecuteAttack(
        AttackRollRequest(context.encounter_repository),
        AttackRollResult(
            encounter_repository=context.encounter_repository,
            append_event=append_event,
            update_hp=UpdateHp(context.encounter_repository, append_event),
        ),
    )

    payload = service.execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
        target_id=target_id,
        weapon_id=weapon_id,
        attack_mode=args.get("attack_mode"),
        grip_mode=args.get("grip_mode"),
        vantage=str(args.get("vantage") or "normal"),
        description=args.get("description"),
        zero_hp_intent=args.get("zero_hp_intent"),
        allow_out_of_turn_actor=bool(args.get("allow_out_of_turn_actor", False)),
        consume_action=bool(args.get("consume_action", True)),
        consume_reaction=bool(args.get("consume_reaction", False)),
        damage_rolls=list(args["damage_rolls"]) if "damage_rolls" in args and args.get("damage_rolls") is not None else None,
        include_encounter_state=True,
    )
    return {
        "encounter_id": encounter_id,
        "result": {
            "attack_result": payload,
        },
        "encounter_state": payload["encounter_state"],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest test.test_runtime_execute_attack -v`
Expected: PASS for the normal attack test

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/runtime/commands/execute_attack.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_execute_attack.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "Add runtime execute_attack command"
```

### Task 2: 补 command 场景覆盖

**Files:**
- Modify: `trpg-battle-system/test/test_runtime_execute_attack.py`
- Modify: `trpg-battle-system/runtime/commands/execute_attack.py`

- [ ] **Step 1: 写借机攻击、轻型额外攻击、投掷攻击、非法攻击的失败测试**

```python
def test_execute_attack_passes_opportunity_attack_flags(self) -> None:
    ...
    self.assertTrue(kwargs["allow_out_of_turn_actor"])
    self.assertFalse(kwargs["consume_action"])
    self.assertTrue(kwargs["consume_reaction"])


def test_execute_attack_passes_light_bonus_mode(self) -> None:
    ...
    self.assertEqual(kwargs["attack_mode"], "light_bonus")


def test_execute_attack_passes_thrown_mode(self) -> None:
    ...
    self.assertEqual(kwargs["attack_mode"], "thrown")


def test_execute_attack_returns_invalid_attack_payload_without_transport_error(self) -> None:
    ...
    self.assertEqual(result["result"]["attack_result"]["status"], "invalid_attack")
    self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_runtime_execute_attack -v`
Expected: FAIL because new assertions are not yet covered or parameters not yet forwarded

- [ ] **Step 3: 用最小改动补齐参数透传与返回稳定性**

```python
payload = service.execute(
    ...,
    attack_mode=args.get("attack_mode"),
    grip_mode=args.get("grip_mode"),
    allow_out_of_turn_actor=bool(args.get("allow_out_of_turn_actor", False)),
    consume_action=bool(args.get("consume_action", True)),
    consume_reaction=bool(args.get("consume_reaction", False)),
    ...
)

return {
    "encounter_id": encounter_id,
    "result": {"attack_result": payload},
    "encounter_state": payload.get("encounter_state"),
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest test.test_runtime_execute_attack -v`
Expected: PASS for normal/light bonus/thrown/opportunity/invalid attack cases

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/runtime/commands/execute_attack.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_execute_attack.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "Cover runtime execute_attack scenarios"
```

### Task 3: 注册 command 并补 dispatcher/http 验证

**Files:**
- Modify: `trpg-battle-system/runtime/commands/__init__.py`
- Modify: `trpg-battle-system/test/test_runtime_dispatcher.py`
- Modify: `trpg-battle-system/test/test_runtime_http_server.py`
- Test: `trpg-battle-system/test/test_runtime_execute_attack.py`

- [ ] **Step 1: 写注册与公开面的失败测试**

```python
def test_command_handlers_include_execute_attack(self) -> None:
    from runtime.commands import COMMAND_HANDLERS
    self.assertIn("execute_attack", COMMAND_HANDLERS)


def test_health_endpoint_lists_execute_attack(self) -> None:
    payload = handler_class.build_health_payload()
    self.assertIn("execute_attack", payload["commands"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest test.test_runtime_dispatcher test.test_runtime_http_server -v`
Expected: FAIL because `execute_attack` not yet registered

- [ ] **Step 3: 注册 command**

```python
from runtime.commands.execute_attack import execute_attack

COMMAND_HANDLERS = {
    "start_random_encounter": start_random_encounter,
    "move_and_attack": move_and_attack,
    "execute_attack": execute_attack,
    "end_turn_and_advance": end_turn_and_advance,
    "cast_spell": cast_spell,
}

__all__ = [
    "COMMAND_HANDLERS",
    "start_random_encounter",
    "move_and_attack",
    "execute_attack",
    "end_turn_and_advance",
    "cast_spell",
]
```

- [ ] **Step 4: 运行完整相关测试**

Run: `python3 -m unittest test.test_runtime_execute_attack test.test_runtime_dispatcher test.test_runtime_http_server -v`
Expected: PASS

- [ ] **Step 5: 做一次真实 runtime 验证**

Run:

```bash
curl -s -X POST http://127.0.0.1:8771/runtime/command \
  -H 'Content-Type: application/json' \
  -d '{
    "command":"execute_attack",
    "args":{
      "encounter_id":"enc_preview_demo",
      "actor_id":"ent_ally_wizard_001",
      "target_id":"ent_enemy_brute_001",
      "weapon_id":"dagger"
    }
  }'
```

Expected:

- 返回 JSON
- `ok` 为 `true`
- `command` 为 `execute_attack`
- `result.attack_result` 存在
- `encounter_state` 存在

- [ ] **Step 6: 提交**

```bash
git -C /Users/runshi.zhang/DND-DM-skill add \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/runtime/commands/__init__.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/runtime/commands/execute_attack.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_execute_attack.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_dispatcher.py \
  /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test/test_runtime_http_server.py
git -C /Users/runshi.zhang/DND-DM-skill commit -m "Register runtime execute_attack command"
```

---

## Spec 覆盖检查

- 独立 runtime command：Task 1
- 覆盖普通攻击、轻型额外攻击、投掷攻击、借机攻击：Task 2
- 注册到 runtime handler：Task 3
- 非法攻击走结构化结果而非 transport error：Task 2
- 默认后端自动掷骰：Task 1 与 Task 3 的真实验证

## Placeholder 检查

已检查，无 `TODO`、`TBD`、`implement later`、`similar to task N` 之类占位语句。

## 类型一致性检查

- runtime command 名统一为 `execute_attack`
- 参数名统一使用 `encounter_id`、`actor_id`、`target_id`、`weapon_id`
- 特殊攻击参数统一使用 `attack_mode`、`allow_out_of_turn_actor`、`consume_action`、`consume_reaction`

