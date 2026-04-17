# Help Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the combat `Help` action in two modes so the backend grants and consumes attack-check and ability-check assistance automatically.

**Architecture:** Reuse the existing `turn_effects` runtime state instead of creating a new help subsystem. `use_help_attack` writes a short-lived effect onto the enemy target, `use_help_ability_check` writes a short-lived effect onto the allied beneficiary, `AttackRollRequest` and `ExecuteAbilityCheck` read and consume those effects, and `StartTurn` expires them when the source actor's next turn begins.

**Tech Stack:** Python 3, `unittest`, existing encounter repositories, runtime command dispatcher, `GetEncounterState`, combat action services.

---

## File Map

- Create: `tools/services/combat/actions/help_effects.py`
- Create: `tools/services/combat/actions/use_help_attack.py`
- Create: `tools/services/combat/actions/use_help_ability_check.py`
- Create: `runtime/commands/use_help_attack.py`
- Create: `runtime/commands/use_help_ability_check.py`
- Modify: `tools/services/combat/actions/__init__.py`
- Modify: `tools/services/__init__.py`
- Modify: `runtime/commands/__init__.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/checks/execute_ability_check.py`
- Modify: `tools/services/encounter/turns/start_turn.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `SKILL.md`
- Test: `test/test_use_help_attack.py`
- Test: `test/test_use_help_ability_check.py`
- Test: `test/test_runtime_use_help_attack.py`
- Test: `test/test_runtime_use_help_ability_check.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_runtime_execute_ability_check.py`
- Test: `test/test_start_turn.py`
- Test: `test/test_get_encounter_state.py`

### Task 1: Add shared help-effect helpers

**Files:**
- Create: `tools/services/combat/actions/help_effects.py`
- Modify: `tools/services/combat/actions/__init__.py`
- Test: `test/test_use_help_attack.py`
- Test: `test/test_use_help_ability_check.py`

- [ ] **Step 1: Write the failing helper tests**

```python
class HelpEffectHelpersTests(unittest.TestCase):
    def test_find_help_attack_effect_for_actor_and_target(self) -> None:
        actor = build_actor()
        target = build_enemy()
        target.turn_effects = [
            {
                "effect_id": "help_attack_1",
                "effect_type": "help_attack",
                "source_entity_id": "ent_helper_001",
                "source_side": "ally",
                "remaining_uses": 1,
            }
        ]

        effect = find_help_attack_effect(target=target, attacker=actor)

        self.assertIsNotNone(effect)
        self.assertEqual(effect["effect_id"], "help_attack_1")

    def test_find_help_ability_effect_matches_check_type_and_key(self) -> None:
        actor = build_actor()
        actor.turn_effects = [
            {
                "effect_id": "help_check_1",
                "effect_type": "help_ability_check",
                "remaining_uses": 1,
                "help_check": {"check_type": "skill", "check_key": "investigation"},
            }
        ]

        effect = find_help_ability_check_effect(
            actor=actor,
            check_type="skill",
            check_key="investigation",
        )

        self.assertIsNotNone(effect)
        self.assertEqual(effect["effect_id"], "help_check_1")

    def test_remove_turn_effect_by_id_only_removes_matching_effect(self) -> None:
        actor = build_actor()
        actor.turn_effects = [
            {"effect_id": "keep", "effect_type": "dodge"},
            {"effect_id": "drop", "effect_type": "help_attack"},
        ]

        remove_turn_effect_by_id(actor, "drop")

        self.assertEqual(actor.turn_effects, [{"effect_id": "keep", "effect_type": "dodge"}])
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run: `python3 -m unittest test.test_use_help_attack test.test_use_help_ability_check -v`

Expected: FAIL with import errors for `help_effects` symbols.

- [ ] **Step 3: Write minimal helper implementation**

```python
def remove_turn_effect_by_id(entity: Any, effect_id: str) -> None:
    entity.turn_effects = [
        effect
        for effect in getattr(entity, "turn_effects", [])
        if not (isinstance(effect, dict) and effect.get("effect_id") == effect_id)
    ]


def find_help_attack_effect(*, target: Any, attacker: Any) -> dict[str, Any] | None:
    for effect in getattr(target, "turn_effects", []):
        if not isinstance(effect, dict):
            continue
        if effect.get("effect_type") != "help_attack":
            continue
        if int(effect.get("remaining_uses", 0) or 0) <= 0:
            continue
        if effect.get("source_side") != getattr(attacker, "side", None):
            continue
        return effect
    return None


def find_help_ability_check_effect(*, actor: Any, check_type: str, check_key: str) -> dict[str, Any] | None:
    for effect in getattr(actor, "turn_effects", []):
        if not isinstance(effect, dict):
            continue
        if effect.get("effect_type") != "help_ability_check":
            continue
        if int(effect.get("remaining_uses", 0) or 0) <= 0:
            continue
        payload = effect.get("help_check") or {}
        if payload.get("check_type") == check_type and payload.get("check_key") == check_key:
            return effect
    return None
```

- [ ] **Step 4: Export the helpers**

```python
from tools.services.combat.actions.help_effects import (
    find_help_ability_check_effect,
    find_help_attack_effect,
    remove_turn_effect_by_id,
)
```

- [ ] **Step 5: Run helper tests to verify they pass**

Run: `python3 -m unittest test.test_use_help_attack test.test_use_help_ability_check -v`

Expected: helper-focused tests PASS, service tests still FAIL because help action services do not exist yet.

- [ ] **Step 6: Commit**

```bash
git add tools/services/combat/actions/help_effects.py tools/services/combat/actions/__init__.py test/test_use_help_attack.py test/test_use_help_ability_check.py
git commit -m "feat: add help action effect helpers"
```

### Task 2: Implement `use_help_attack` service and runtime command

**Files:**
- Create: `tools/services/combat/actions/use_help_attack.py`
- Create: `runtime/commands/use_help_attack.py`
- Modify: `tools/services/__init__.py`
- Modify: `runtime/commands/__init__.py`
- Test: `test/test_use_help_attack.py`
- Test: `test/test_runtime_use_help_attack.py`

- [ ] **Step 1: Write the failing service and runtime tests**

```python
class UseHelpAttackTests(unittest.TestCase):
    def test_execute_consumes_action_and_adds_help_attack_effect_to_target(self) -> None:
        repo.save(build_help_attack_encounter())

        result = UseHelpAttack(repo).execute(
            encounter_id="enc_help_attack_test",
            actor_id="ent_actor_001",
            target_id="ent_enemy_001",
        )

        updated = repo.get("enc_help_attack_test")
        actor = updated.entities["ent_actor_001"]
        target = updated.entities["ent_enemy_001"]
        self.assertTrue(actor.action_economy["action_used"])
        self.assertTrue(any(effect.get("effect_type") == "help_attack" for effect in target.turn_effects))
        self.assertEqual(result["actor_id"], "ent_actor_001")

    def test_execute_rejects_when_target_not_within_five_feet(self) -> None:
        repo.save(build_help_attack_encounter(target_position={"x": 5, "y": 5}))

        with self.assertRaisesRegex(ValueError, "target_not_within_help_attack_range"):
            UseHelpAttack(repo).execute(
                encounter_id="enc_help_attack_test",
                actor_id="ent_actor_001",
                target_id="ent_enemy_001",
            )

    def test_execute_rejects_when_target_is_not_enemy(self) -> None:
        repo.save(build_help_attack_encounter(target_side="ally"))

        with self.assertRaisesRegex(ValueError, "help_attack_target_must_be_enemy"):
            UseHelpAttack(repo).execute(
                encounter_id="enc_help_attack_test",
                actor_id="ent_actor_001",
                target_id="ent_enemy_001",
            )
```

```python
class RuntimeUseHelpAttackTests(unittest.TestCase):
    def test_command_handlers_include_use_help_attack(self) -> None:
        self.assertIn("use_help_attack", COMMAND_HANDLERS)

    def test_use_help_attack_runs_and_returns_encounter_state(self) -> None:
        result = execute_runtime_command(
            context,
            command="use_help_attack",
            args={
                "encounter_id": "enc_help_attack_test",
                "actor_id": "ent_actor_001",
                "target_id": "ent_enemy_001",
            },
            handlers=COMMAND_HANDLERS,
        )
        self.assertTrue(result["ok"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_use_help_attack test.test_runtime_use_help_attack -v`

Expected: FAIL with missing imports / missing command handler.

- [ ] **Step 3: Write minimal `UseHelpAttack` implementation**

```python
class UseHelpAttack:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str, target_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        target = self._get_target_or_raise(encounter, target_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_target_is_enemy(actor, target)
        self._ensure_target_within_help_range(actor, target)

        actor.action_economy["action_used"] = True
        target.turn_effects = [
            effect
            for effect in target.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "help_attack"
                and effect.get("source_entity_id") == actor.entity_id
            )
        ]
        target.turn_effects.append({
            "effect_id": f"effect_help_attack_{uuid4().hex[:12]}",
            "effect_type": "help_attack",
            "name": "Help Attack",
            "source_entity_id": actor.entity_id,
            "source_name": actor.name,
            "source_side": actor.side,
            "trigger": "manual_state",
            "source_ref": "action:help_attack",
            "expires_on": "source_next_turn_start",
            "remaining_uses": 1,
        })
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }
```

- [ ] **Step 4: Add runtime command wiring**

```python
def use_help_attack(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = UseHelpAttack(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
        target_id=str(args["target_id"]),
    )
    return {"result": result, "encounter_state": result.get("encounter_state")}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest test.test_use_help_attack test.test_runtime_use_help_attack -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/services/combat/actions/use_help_attack.py runtime/commands/use_help_attack.py tools/services/__init__.py runtime/commands/__init__.py test/test_use_help_attack.py test/test_runtime_use_help_attack.py
git commit -m "feat: add help attack action"
```

### Task 3: Implement `use_help_ability_check` service and runtime command

**Files:**
- Create: `tools/services/combat/actions/use_help_ability_check.py`
- Create: `runtime/commands/use_help_ability_check.py`
- Modify: `tools/services/__init__.py`
- Modify: `runtime/commands/__init__.py`
- Test: `test/test_use_help_ability_check.py`
- Test: `test/test_runtime_use_help_ability_check.py`

- [ ] **Step 1: Write the failing service and runtime tests**

```python
class UseHelpAbilityCheckTests(unittest.TestCase):
    def test_execute_consumes_action_and_adds_help_check_effect_to_ally(self) -> None:
        repo.save(build_help_check_encounter())

        result = UseHelpAbilityCheck(repo).execute(
            encounter_id="enc_help_check_test",
            actor_id="ent_actor_001",
            ally_id="ent_ally_001",
            check_type="skill",
            check_key="investigation",
        )

        updated = repo.get("enc_help_check_test")
        ally = updated.entities["ent_ally_001"]
        self.assertTrue(any(effect.get("effect_type") == "help_ability_check" for effect in ally.turn_effects))
        self.assertEqual(result["ally_id"], "ent_ally_001")

    def test_execute_rejects_when_ally_is_enemy(self) -> None:
        repo.save(build_help_check_encounter(ally_side="enemy"))

        with self.assertRaisesRegex(ValueError, "help_check_target_must_be_ally"):
            UseHelpAbilityCheck(repo).execute(
                encounter_id="enc_help_check_test",
                actor_id="ent_actor_001",
                ally_id="ent_ally_001",
                check_type="skill",
                check_key="investigation",
            )

    def test_execute_rejects_invalid_check_type(self) -> None:
        repo.save(build_help_check_encounter())

        with self.assertRaisesRegex(ValueError, "invalid_help_check_type"):
            UseHelpAbilityCheck(repo).execute(
                encounter_id="enc_help_check_test",
                actor_id="ent_actor_001",
                ally_id="ent_ally_001",
                check_type="ability",
                check_key="str",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_use_help_ability_check test.test_runtime_use_help_ability_check -v`

Expected: FAIL with missing imports / missing command handler.

- [ ] **Step 3: Write minimal `UseHelpAbilityCheck` implementation**

```python
class UseHelpAbilityCheck:
    VALID_CHECK_TYPES = {"skill", "tool"}

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        ally_id: str,
        check_type: str,
        check_key: str,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        ally = self._get_target_or_raise(encounter, ally_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_target_is_ally(actor, ally)
        self._ensure_check_type(check_type)
        self._ensure_check_key(check_key)

        actor.action_economy["action_used"] = True
        ally.turn_effects = [
            effect
            for effect in ally.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "help_ability_check"
                and effect.get("source_entity_id") == actor.entity_id
                and (effect.get("help_check") or {}).get("check_type") == check_type
                and (effect.get("help_check") or {}).get("check_key") == check_key
            )
        ]
        ally.turn_effects.append({
            "effect_id": f"effect_help_check_{uuid4().hex[:12]}",
            "effect_type": "help_ability_check",
            "name": "Help Ability Check",
            "source_entity_id": actor.entity_id,
            "source_name": actor.name,
            "trigger": "manual_state",
            "source_ref": "action:help_ability_check",
            "expires_on": "source_next_turn_start",
            "remaining_uses": 1,
            "help_check": {"check_type": check_type, "check_key": check_key},
        })
```

- [ ] **Step 4: Add runtime command wiring**

```python
def use_help_ability_check(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    result = UseHelpAbilityCheck(context.encounter_repository).execute(
        encounter_id=str(args["encounter_id"]),
        actor_id=str(args["actor_id"]),
        ally_id=str(args["ally_id"]),
        check_type=str(args["check_type"]),
        check_key=str(args["check_key"]),
    )
    return {"result": result, "encounter_state": result.get("encounter_state")}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest test.test_use_help_ability_check test.test_runtime_use_help_ability_check -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/services/combat/actions/use_help_ability_check.py runtime/commands/use_help_ability_check.py tools/services/__init__.py runtime/commands/__init__.py test/test_use_help_ability_check.py test/test_runtime_use_help_ability_check.py
git commit -m "feat: add help ability check action"
```

### Task 4: Apply and consume `help_attack` inside the attack chain

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing request and execution tests**

```python
def test_help_attack_adds_advantage_when_ally_attacks_helped_target(self) -> None:
    target.turn_effects.append({
        "effect_id": "help_attack_1",
        "effect_type": "help_attack",
        "source_entity_id": "ent_helper_001",
        "source_side": "ally",
        "remaining_uses": 1,
    })

    request = AttackRollRequest(repo).execute(
        encounter_id="enc_attack_test",
        actor_id="ent_ally_eric_001",
        target_id="ent_enemy_goblin_001",
        weapon_id="rapier",
    )

    self.assertEqual(request.context["vantage"], "advantage")
    self.assertIn("help_attack", request.context["vantage_sources"]["advantage"])
    self.assertEqual(request.context["consumed_help_attack_effect_id"], "help_attack_1")

def test_execute_attack_consumes_help_attack_effect_after_attack_executes(self) -> None:
    target.turn_effects.append({
        "effect_id": "help_attack_1",
        "effect_type": "help_attack",
        "source_entity_id": "ent_helper_001",
        "source_side": "ally",
        "remaining_uses": 1,
    })

    ExecuteAttack(...).execute(
        encounter_id="enc_attack_test",
        actor_id="ent_ally_eric_001",
        target_id="ent_enemy_goblin_001",
        weapon_id="rapier",
        attack_roll=15,
        damage_rolls=[6],
    )

    updated = repo.get("enc_attack_test")
    self.assertFalse(any(effect.get("effect_id") == "help_attack_1" for effect in updated.entities["ent_enemy_goblin_001"].turn_effects))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_attack_roll_request test.test_execute_attack -v`

Expected: FAIL because request context does not include help-effect metadata and the effect is never consumed.

- [ ] **Step 3: Update `AttackRollRequest` to detect eligible help effects**

```python
help_attack_effect = find_help_attack_effect(target=target, attacker=actor)
if help_attack_effect is not None:
    vantage_sources["advantage"].append("help_attack")
```

Add this context field to the returned `RollRequest`:

```python
"consumed_help_attack_effect_id": help_attack_effect.get("effect_id") if help_attack_effect else None,
```

- [ ] **Step 4: Update `ExecuteAttack` to consume the help effect after real execution**

```python
consumed_help_attack_effect_id = attack_request.context.get("consumed_help_attack_effect_id")
if isinstance(consumed_help_attack_effect_id, str) and consumed_help_attack_effect_id:
    target = encounter.entities.get(target_id)
    if target is not None:
        remove_turn_effect_by_id(target, consumed_help_attack_effect_id)
```

Place the removal in the execution flow after the attack request has been accepted and before saving the final encounter.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest test.test_attack_roll_request test.test_execute_attack -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py test/test_attack_roll_request.py test/test_execute_attack.py
git commit -m "feat: consume help attack effects in attack flow"
```

### Task 5: Apply and consume `help_ability_check` in the ability-check flow

**Files:**
- Modify: `tools/services/checks/execute_ability_check.py`
- Test: `test/test_runtime_execute_ability_check.py`

- [ ] **Step 1: Write the failing ability-check test**

```python
def test_execute_ability_check_uses_help_effect_as_advantage_and_consumes_it(self) -> None:
    ally.turn_effects.append({
        "effect_id": "help_check_1",
        "effect_type": "help_ability_check",
        "remaining_uses": 1,
        "help_check": {"check_type": "skill", "check_key": "investigation"},
    })

    with patch("tools.services.checks.execute_ability_check.random.randint", side_effect=[4, 16]):
        result = ExecuteAbilityCheck(repo, append_event).execute(
            encounter_id="enc_check_test",
            actor_id="ent_ally_001",
            check_type="skill",
            check="investigation",
            dc=12,
            include_encounter_state=True,
        )

    self.assertEqual(result["request"]["context"]["vantage"], "advantage")
    self.assertEqual(result["roll_result"]["base_rolls"], [4, 16])
    updated = repo.get("enc_check_test")
    self.assertFalse(any(effect.get("effect_id") == "help_check_1" for effect in updated.entities["ent_ally_001"].turn_effects))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test.test_runtime_execute_ability_check -v`

Expected: FAIL because `ExecuteAbilityCheck` ignores help effects and leaves them on the actor.

- [ ] **Step 3: Update `ExecuteAbilityCheck` to auto-apply help advantage**

```python
normalized_check_type = str(check_type).strip().lower()
normalized_check = str(check).strip().lower()
help_effect = find_help_ability_check_effect(
    actor=self.encounter_repository.get(encounter_id).entities[actor_id],
    check_type=normalized_check_type,
    check_key=normalized_check,
)
effective_vantage = vantage
if help_effect is not None and effective_vantage == "normal":
    effective_vantage = "advantage"
```

Use `effective_vantage` for both request construction and dice generation, then remove the effect after `result_service.execute(...)` completes:

```python
if help_effect is not None:
    updated = self.encounter_repository.get(encounter_id)
    actor = updated.entities.get(actor_id)
    if actor is not None:
        remove_turn_effect_by_id(actor, str(help_effect["effect_id"]))
        self.encounter_repository.save(updated)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest test.test_runtime_execute_ability_check -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/services/checks/execute_ability_check.py test/test_runtime_execute_ability_check.py
git commit -m "feat: apply help effects to ability checks"
```

### Task 6: Expire help effects at source next-turn start and project them in encounter state

**Files:**
- Modify: `tools/services/encounter/turns/start_turn.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `SKILL.md`
- Test: `test/test_start_turn.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing expiration and projection tests**

```python
def test_execute_expires_help_effects_created_by_current_entity(self) -> None:
    enemy.turn_effects.append({
        "effect_id": "help_attack_1",
        "effect_type": "help_attack",
        "source_entity_id": "ent_ally_eric_001",
        "expires_on": "source_next_turn_start",
    })
    ally.turn_effects.append({
        "effect_id": "help_check_1",
        "effect_type": "help_ability_check",
        "source_entity_id": "ent_ally_eric_001",
        "expires_on": "source_next_turn_start",
    })

    updated = StartTurn(repo).execute("enc_turn_test")

    self.assertFalse(any(effect.get("effect_id") == "help_attack_1" for effect in updated.entities["ent_enemy_goblin_001"].turn_effects))
    self.assertFalse(any(effect.get("effect_id") == "help_check_1" for effect in updated.entities["ent_ally_lia_001"].turn_effects))

def test_execute_projects_help_effect_labels_into_ongoing_effects(self) -> None:
    target.turn_effects.append({
        "effect_id": "help_attack_1",
        "effect_type": "help_attack",
        "source_entity_id": "ent_ally_eric_001",
        "source_name": "Eric",
    })
    ally.turn_effects.append({
        "effect_id": "help_check_1",
        "effect_type": "help_ability_check",
        "source_entity_id": "ent_ally_eric_001",
        "source_name": "Eric",
        "help_check": {"check_type": "skill", "check_key": "investigation"},
    })

    state = GetEncounterState(repo).execute("enc_view_test")
    self.assertIn("受到Eric的 Help（攻击）", state["turn_order"][1]["ongoing_effects"])
    self.assertIn("受到Eric的 Help（investigation）", state["turn_order"][2]["ongoing_effects"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest test.test_start_turn test.test_get_encounter_state -v`

Expected: FAIL because `StartTurn` only clears current-entity local effects and `GetEncounterState` does not project help summaries.

- [ ] **Step 3: Add help-effect expiration in `StartTurn`**

```python
def _expire_source_turn_help_effects(encounter: Encounter, source_entity_id: str | None) -> None:
    if not isinstance(source_entity_id, str) or not source_entity_id:
        return
    for entity in encounter.entities.values():
        entity.turn_effects = [
            effect
            for effect in entity.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") in {"help_attack", "help_ability_check"}
                and effect.get("source_entity_id") == source_entity_id
                and effect.get("expires_on") == "source_next_turn_start"
            )
        ]
```

Call it in `_execute_internal(...)` immediately after `start_turn(encounter)`.

- [ ] **Step 4: Add help-effect labels in `GetEncounterState` and LLM protocol notes**

```python
elif effect_type == "help_attack":
    source_name = effect.get("source_name") or "未知角色"
    effect_labels.append(f"受到{source_name}的 Help（攻击）")
elif effect_type == "help_ability_check":
    source_name = effect.get("source_name") or "未知角色"
    help_check = effect.get("help_check") or {}
    check_key = help_check.get("check_key") or "未知检定"
    effect_labels.append(f"受到{source_name}的 Help（{check_key}）")
```

Also add two short command sections to `SKILL.md`:

```md
- `use_help_attack`
  - 用途: 对 5 尺内敌人执行 `Help(attack)`
- `use_help_ability_check`
  - 用途: 对盟友执行 `Help(ability)`，并指定 `check_type/check_key`
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest test.test_start_turn test.test_get_encounter_state -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/services/encounter/turns/start_turn.py tools/services/encounter/get_encounter_state.py SKILL.md test/test_start_turn.py test/test_get_encounter_state.py
git commit -m "feat: expire and project help action effects"
```

### Task 7: Final verification

**Files:**
- Modify: none
- Test: `test/test_use_help_attack.py`
- Test: `test/test_use_help_ability_check.py`
- Test: `test/test_runtime_use_help_attack.py`
- Test: `test/test_runtime_use_help_ability_check.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_runtime_execute_ability_check.py`
- Test: `test/test_start_turn.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
python3 -m unittest \
  test.test_use_help_attack \
  test.test_use_help_ability_check \
  test.test_runtime_use_help_attack \
  test.test_runtime_use_help_ability_check \
  test.test_attack_roll_request \
  test.test_execute_attack \
  test.test_runtime_execute_ability_check \
  test.test_start_turn \
  test.test_get_encounter_state \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run the broader regression suite if the focused suite is green**

Run: `python3 -m unittest discover -s test -v`

Expected: PASS, or report the exact pre-existing failures if unrelated tests are already red.

- [ ] **Step 3: Commit**

```bash
git status --short
git commit -am "test: verify help action integration"
```

## Self-Review

- Spec coverage:
  - Explicit `Help(attack)` action: Task 2
  - Explicit `Help(ability)` action: Task 3
  - Attack-chain auto-read + consume: Task 4
  - Ability-check auto-read + consume: Task 5
  - Source-next-turn expiration: Task 6
  - State projection + skill update: Task 6
- Placeholder scan:
  - No `TODO` / `TBD`
  - Every task contains concrete files, tests, and commands
- Type consistency:
  - `help_attack`, `help_ability_check`, `source_next_turn_start`, `check_type`, `check_key` are used consistently throughout
