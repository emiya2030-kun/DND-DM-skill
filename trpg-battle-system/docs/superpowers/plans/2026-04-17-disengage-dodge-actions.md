# Disengage And Dodge Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Disengage` and `Dodge` as explicit combat actions with backend-enforced effects across movement, attack rolls, saving throws, runtime commands, and state projection.

**Architecture:** Keep both actions as explicit action services plus runtime commands. Store their temporary state in `EncounterEntity.turn_effects`, let movement and roll-request chains read those effects dynamically, and clear them at the right turn boundary in the existing turn engine. Reuse existing `GetEncounterState`, `BeginMoveEncounterEntity`, `AttackRollRequest`, and `SavingThrowRequest` instead of creating a parallel action framework.

**Tech Stack:** Python 3, `unittest`, existing encounter repositories/services, runtime command dispatcher.

---

## File Map

- Create: `tools/services/combat/actions/__init__.py`
- Create: `tools/services/combat/actions/state_effects.py`
- Create: `tools/services/combat/actions/use_disengage.py`
- Create: `tools/services/combat/actions/use_dodge.py`
- Create: `runtime/commands/use_disengage.py`
- Create: `runtime/commands/use_dodge.py`
- Modify: `tools/services/__init__.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Modify: `tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `runtime/commands/__init__.py`
- Test: `test/test_use_disengage.py`
- Test: `test/test_use_dodge.py`
- Test: `test/test_begin_move_encounter_entity.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_saving_throw_request.py`
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_runtime_dispatcher.py`
- Test: `test/test_runtime_use_disengage.py`
- Test: `test/test_runtime_use_dodge.py`

### Task 1: Add Shared Action State Helpers

**Files:**
- Create: `tools/services/combat/actions/__init__.py`
- Create: `tools/services/combat/actions/state_effects.py`
- Test: `test/test_use_disengage.py`
- Test: `test/test_use_dodge.py`

- [ ] **Step 1: Write the failing helper tests**

```python
import unittest

from tools.models.encounter_entity import EncounterEntity
from tools.services.combat.actions.state_effects import (
    add_or_replace_turn_effect,
    clear_turn_effect_type,
    has_disengage_effect,
    has_dodge_effect,
)


def build_entity() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_test_001",
        name="Test",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        turn_effects=[],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
    )


class ActionStateEffectsTests(unittest.TestCase):
    def test_add_or_replace_turn_effect_replaces_same_type(self) -> None:
        entity = build_entity()
        entity.turn_effects = [{"effect_id": "old", "effect_type": "dodge", "name": "Dodge"}]

        add_or_replace_turn_effect(
            entity,
            {"effect_id": "new", "effect_type": "dodge", "name": "Dodge"},
        )

        self.assertEqual(len(entity.turn_effects), 1)
        self.assertEqual(entity.turn_effects[0]["effect_id"], "new")

    def test_clear_turn_effect_type_removes_matching_effects_only(self) -> None:
        entity = build_entity()
        entity.turn_effects = [
            {"effect_id": "a", "effect_type": "dodge"},
            {"effect_id": "b", "effect_type": "disengage"},
        ]

        clear_turn_effect_type(entity, "dodge")

        self.assertEqual(entity.turn_effects, [{"effect_id": "b", "effect_type": "disengage"}])

    def test_has_disengage_and_dodge_effect_detect_active_effects(self) -> None:
        entity = build_entity()
        entity.turn_effects = [
            {"effect_id": "a", "effect_type": "disengage"},
            {"effect_id": "b", "effect_type": "dodge"},
        ]

        self.assertTrue(has_disengage_effect(entity))
        self.assertTrue(has_dodge_effect(entity))
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_use_disengage test.test_use_dodge -v`

Expected: FAIL with import errors for `tools.services.combat.actions.state_effects` or missing helper symbols.

- [ ] **Step 3: Write minimal helper implementation**

```python
# tools/services/combat/actions/state_effects.py
from __future__ import annotations

from typing import Any


def _ensure_turn_effects(entity: Any) -> list[dict[str, Any]]:
    turn_effects = getattr(entity, "turn_effects", None)
    if not isinstance(turn_effects, list):
        entity.turn_effects = []
    return entity.turn_effects


def clear_turn_effect_type(entity: Any, effect_type: str) -> None:
    turn_effects = _ensure_turn_effects(entity)
    entity.turn_effects = [
        effect
        for effect in turn_effects
        if not (isinstance(effect, dict) and effect.get("effect_type") == effect_type)
    ]


def add_or_replace_turn_effect(entity: Any, effect: dict[str, Any]) -> None:
    effect_type = str(effect.get("effect_type") or "").strip()
    if not effect_type:
        raise ValueError("turn_effect.effect_type is required")
    clear_turn_effect_type(entity, effect_type)
    _ensure_turn_effects(entity).append(effect)


def has_disengage_effect(entity: Any) -> bool:
    return any(
        isinstance(effect, dict) and effect.get("effect_type") == "disengage"
        for effect in _ensure_turn_effects(entity)
    )


def has_dodge_effect(entity: Any) -> bool:
    return any(
        isinstance(effect, dict) and effect.get("effect_type") == "dodge"
        for effect in _ensure_turn_effects(entity)
    )
```

- [ ] **Step 4: Export the shared helpers**

```python
# tools/services/combat/actions/__init__.py
from tools.services.combat.actions.state_effects import (
    add_or_replace_turn_effect,
    clear_turn_effect_type,
    has_disengage_effect,
    has_dodge_effect,
)

__all__ = [
    "add_or_replace_turn_effect",
    "clear_turn_effect_type",
    "has_disengage_effect",
    "has_dodge_effect",
]
```

- [ ] **Step 5: Run helper tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_use_disengage test.test_use_dodge -v`

Expected: PASS for the helper-focused tests and remaining tests still FAIL because action services do not exist yet.

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add tools/services/combat/actions/__init__.py tools/services/combat/actions/state_effects.py test/test_use_disengage.py test/test_use_dodge.py
git commit -m "feat: add disengage and dodge state helpers"
```

### Task 2: Implement `use_disengage` and `use_dodge` Services

**Files:**
- Create: `tools/services/combat/actions/use_disengage.py`
- Create: `tools/services/combat/actions/use_dodge.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_use_disengage.py`
- Test: `test/test_use_dodge.py`

- [ ] **Step 1: Write the failing action service tests**

```python
# test/test_use_disengage.py
import tempfile
import unittest
from pathlib import Path

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.combat.actions.use_disengage import UseDisengage


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_actor_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )


def build_encounter(action_used: bool = False) -> Encounter:
    actor = build_actor()
    actor.action_economy["action_used"] = action_used
    return Encounter(
        encounter_id="enc_disengage_test",
        name="Disengage Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id],
        entities={actor.entity_id: actor},
        map=EncounterMap(map_id="map", name="Map", description="Test", width=8, height=8),
    )


class UseDisengageTests(unittest.TestCase):
    def test_execute_consumes_action_and_applies_disengage_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseDisengage(repo).execute(encounter_id="enc_disengage_test", actor_id="ent_actor_001")

            updated = repo.get("enc_disengage_test")
            self.assertTrue(updated.entities["ent_actor_001"].action_economy["action_used"])
            self.assertTrue(any(effect.get("effect_type") == "disengage" for effect in updated.entities["ent_actor_001"].turn_effects))
            self.assertEqual(result["encounter_id"], "enc_disengage_test")

    def test_execute_rejects_when_action_already_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(action_used=True))

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                UseDisengage(repo).execute(encounter_id="enc_disengage_test", actor_id="ent_actor_001")
```

```python
# test/test_use_dodge.py
import tempfile
import unittest
from pathlib import Path

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.combat.actions.use_dodge import UseDodge


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_actor_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )


def build_encounter(action_used: bool = False) -> Encounter:
    actor = build_actor()
    actor.action_economy["action_used"] = action_used
    return Encounter(
        encounter_id="enc_dodge_test",
        name="Dodge Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id],
        entities={actor.entity_id: actor},
        map=EncounterMap(map_id="map", name="Map", description="Test", width=8, height=8),
    )


class UseDodgeTests(unittest.TestCase):
    def test_execute_consumes_action_and_applies_dodge_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseDodge(repo).execute(encounter_id="enc_dodge_test", actor_id="ent_actor_001")

            updated = repo.get("enc_dodge_test")
            self.assertTrue(updated.entities["ent_actor_001"].action_economy["action_used"])
            self.assertTrue(any(effect.get("effect_type") == "dodge" for effect in updated.entities["ent_actor_001"].turn_effects))
            self.assertEqual(result["encounter_id"], "enc_dodge_test")

    def test_execute_rejects_when_action_already_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(action_used=True))

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                UseDodge(repo).execute(encounter_id="enc_dodge_test", actor_id="ent_actor_001")
```

- [ ] **Step 2: Run the action service tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_use_disengage test.test_use_dodge -v`

Expected: FAIL because `UseDisengage` and `UseDodge` do not exist yet.

- [ ] **Step 3: Implement the minimal action services**

```python
# tools/services/combat/actions/use_disengage.py
from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseDisengage:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)

        actor.action_economy["action_used"] = True
        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_disengage_{uuid4().hex[:12]}",
                "effect_type": "disengage",
                "name": "Disengage",
                "trigger": "manual_state",
                "source_ref": "action:disengage",
                "expires_at": "end_of_current_turn",
            },
        )
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")
```

```python
# tools/services/combat/actions/use_dodge.py
from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.actions.state_effects import add_or_replace_turn_effect
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseDodge:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)

        actor.action_economy["action_used"] = True
        add_or_replace_turn_effect(
            actor,
            {
                "effect_id": f"effect_dodge_{uuid4().hex[:12]}",
                "effect_type": "dodge",
                "name": "Dodge",
                "trigger": "manual_state",
                "source_ref": "action:dodge",
                "expires_at": "start_of_next_turn",
            },
        )
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")
```

- [ ] **Step 4: Export the new services**

```python
# tools/services/__init__.py
LAZY_IMPORTS.update(
    {
        "UseDisengage": ("tools.services.combat.actions.use_disengage", "UseDisengage"),
        "UseDodge": ("tools.services.combat.actions.use_dodge", "UseDodge"),
    }
)
```

- [ ] **Step 5: Run the action service tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_use_disengage test.test_use_dodge -v`

Expected: PASS for both service test modules.

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add tools/services/combat/actions/use_disengage.py tools/services/combat/actions/use_dodge.py tools/services/__init__.py test/test_use_disengage.py test/test_use_dodge.py
git commit -m "feat: add disengage and dodge action services"
```

### Task 3: Hook `Disengage` Into Movement And Turn Reset

**Files:**
- Modify: `tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Test: `test/test_begin_move_encounter_entity.py`

- [ ] **Step 1: Write the failing movement tests**

```python
def test_execute_ignores_opportunity_attacks_when_mover_has_disengage_effect(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter = build_encounter_with_player_and_moving_enemy()
        encounter.entities["ent_enemy_orc_001"].turn_effects = [
            {"effect_id": "effect_disengage_001", "effect_type": "disengage", "name": "Disengage"}
        ]
        repo.save(encounter)

        service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
        result = service.execute_with_state(
            encounter_id="enc_begin_move_test",
            entity_id="ent_enemy_orc_001",
            target_position={"x": 8, "y": 4},
        )

        updated = repo.get("enc_begin_move_test")
        self.assertEqual(result["movement_status"], "completed")
        self.assertIsNone(updated.pending_movement)
        self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 8, "y": 4})


def test_start_turn_clears_disengage_and_dodge_effects(self) -> None:
    entity = build_entity("ent_turn_test", name="Test", x=1, y=1, side="ally", controller="player", initiative=10)
    entity.turn_effects = [
        {"effect_id": "effect_disengage_001", "effect_type": "disengage"},
        {"effect_id": "effect_dodge_001", "effect_type": "dodge"},
        {"effect_id": "effect_other_001", "effect_type": "knockout_protection"},
    ]

    reset_turn_resources(entity)

    self.assertFalse(any(effect.get("effect_type") == "disengage" for effect in entity.turn_effects))
    self.assertFalse(any(effect.get("effect_type") == "dodge" for effect in entity.turn_effects))
    self.assertTrue(any(effect.get("effect_type") == "knockout_protection" for effect in entity.turn_effects))
```

- [ ] **Step 2: Run the movement tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_begin_move_encounter_entity test.test_start_turn -v`

Expected: FAIL because movement still opens an opportunity attack window and `reset_turn_resources` does not clear the new effect types.

- [ ] **Step 3: Add the `Disengage` movement bypass**

```python
# tools/services/encounter/begin_move_encounter_entity.py
from tools.services.combat.actions import has_disengage_effect

...
        first_trigger = None
        movement_ignores_opportunity_attacks = (
            ignore_opportunity_attacks_for_this_move or has_disengage_effect(mover)
        )
        if not movement_ignores_opportunity_attacks:
            first_trigger = self._find_first_opportunity_trigger(encounter, mover, result)
```

- [ ] **Step 4: Clear `disengage` and `dodge` at turn start**

```python
# tools/services/encounter/turns/turn_engine.py
from tools.services.combat.actions import clear_turn_effect_type

...
def reset_turn_resources(entity: EncounterEntity) -> None:
    ...
    clear_turn_effect_type(entity, "disengage")
    clear_turn_effect_type(entity, "dodge")
```

- [ ] **Step 5: Run the movement and turn reset tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_begin_move_encounter_entity test.test_start_turn -v`

Expected: PASS for the new `Disengage` bypass and turn-start cleanup cases.

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add tools/services/encounter/begin_move_encounter_entity.py tools/services/encounter/turns/turn_engine.py test/test_begin_move_encounter_entity.py test/test_start_turn.py
git commit -m "feat: apply disengage to movement windows"
```

### Task 4: Hook `Dodge` Into Attack Rolls And Dexterity Saves

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/save_spell/saving_throw_request.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_saving_throw_request.py`

- [ ] **Step 1: Write the failing roll-request tests**

```python
def test_target_dodge_adds_disadvantage_against_visible_attacker(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_enemy_goblin_001"].turn_effects = [
            {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"}
        ]
        repo.save(encounter)

        request = AttackRollRequest(repo).execute(
            encounter_id="enc_attack_request_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="rapier",
        )

        self.assertEqual(request.context["vantage"], "disadvantage")
        self.assertIn("dodge", request.context["vantage_sources"]["disadvantage"])


def test_target_dodge_does_not_apply_against_invisible_attacker(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_ally_sabur_001"].conditions.append("invisible")
        encounter.entities["ent_enemy_goblin_001"].turn_effects = [
            {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"}
        ]
        repo.save(encounter)

        request = AttackRollRequest(repo).execute(
            encounter_id="enc_attack_request_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="rapier",
        )

        self.assertNotIn("dodge", request.context["vantage_sources"]["disadvantage"])
```

```python
def test_execute_marks_advantage_for_dodge_dex_save(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_enemy_iron_duster_001"].turn_effects = [
            {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"}
        ]
        repo.save(encounter)

        request = SavingThrowRequest(repo).execute(
            encounter_id="enc_save_request_test",
            target_id="ent_enemy_iron_duster_001",
            spell_id="blindness_deafness",
            force_save_ability="dex",
        )

        self.assertEqual(request.context["vantage"], "advantage")
        self.assertIn("dodge", request.context["vantage_sources"]["advantage"])


def test_execute_dodge_dex_save_ignored_when_target_speed_zero(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_enemy_iron_duster_001"].speed["walk"] = 0
        encounter.entities["ent_enemy_iron_duster_001"].turn_effects = [
            {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"}
        ]
        repo.save(encounter)

        request = SavingThrowRequest(repo).execute(
            encounter_id="enc_save_request_test",
            target_id="ent_enemy_iron_duster_001",
            spell_id="blindness_deafness",
            force_save_ability="dex",
        )

        self.assertNotIn("dodge", request.context["vantage_sources"]["advantage"])
```

- [ ] **Step 2: Run the roll-request tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_attack_roll_request test.test_saving_throw_request -v`

Expected: FAIL because `dodge` is not part of either request context yet.

- [ ] **Step 3: Implement `Dodge` checks in attack requests**

```python
# tools/services/combat/attack/attack_roll_request.py
from tools.services.combat.actions import has_dodge_effect

...
        if self._target_dodge_applies(actor=actor, target=target, target_runtime=target_runtime):
            vantage_sources["disadvantage"].append("dodge")

...
    def _target_dodge_applies(
        self,
        *,
        actor: EncounterEntity,
        target: EncounterEntity,
        target_runtime: ConditionRuntime,
    ) -> bool:
        if not has_dodge_effect(target):
            return False
        if target_runtime.has("incapacitated"):
            return False
        if int(target.speed.get("walk", 0) or 0) <= 0:
            return False
        actor_runtime = ConditionRuntime(actor.conditions)
        if actor_runtime.has("invisible"):
            return False
        return True
```

- [ ] **Step 4: Implement `Dodge` checks in dexterity saves**

```python
# tools/services/combat/save_spell/saving_throw_request.py
from tools.services.combat.actions import has_dodge_effect
from tools.services.combat.rules.conditions import ConditionRuntime

...
        target_runtime = ConditionRuntime(target.conditions)
        if (
            save_ability.strip().lower() == "dex"
            and has_dodge_effect(target)
            and not target_runtime.has("incapacitated")
            and int(target.speed.get("walk", 0) or 0) > 0
        ):
            vantage_sources["advantage"].append("dodge")
```

- [ ] **Step 5: Run the roll-request tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_attack_roll_request test.test_saving_throw_request -v`

Expected: PASS for the new `dodge` attack/save cases.

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/save_spell/saving_throw_request.py test/test_attack_roll_request.py test/test_saving_throw_request.py
git commit -m "feat: apply dodge to attacks and dex saves"
```

### Task 5: Project Effects To State And Expose Runtime Commands

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Create: `runtime/commands/use_disengage.py`
- Create: `runtime/commands/use_dodge.py`
- Modify: `runtime/commands/__init__.py`
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_runtime_dispatcher.py`
- Test: `test/test_runtime_use_disengage.py`
- Test: `test/test_runtime_use_dodge.py`

- [ ] **Step 1: Write the failing projection and runtime tests**

```python
def test_execute_projects_disengage_and_dodge_in_ongoing_effects(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter = build_encounter()
        current = encounter.entities[encounter.current_entity_id]
        current.turn_effects = [
            {"effect_id": "effect_disengage_001", "effect_type": "disengage", "name": "Disengage"},
            {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"},
        ]
        encounter_repo.save(encounter)

        state = GetEncounterState(encounter_repo, event_repository=event_repo).execute(encounter.encounter_id)

        self.assertIn("Disengage", state["current_turn_entity"]["ongoing_effects"])
        self.assertIn("Dodge", state["current_turn_entity"]["ongoing_effects"])
```

```python
class RuntimeUseDisengageTests(unittest.TestCase):
    def test_command_handlers_include_use_disengage(self) -> None:
        self.assertIn("use_disengage", COMMAND_HANDLERS)


class RuntimeUseDodgeTests(unittest.TestCase):
    def test_command_handlers_include_use_dodge(self) -> None:
        self.assertIn("use_dodge", COMMAND_HANDLERS)
```

- [ ] **Step 2: Run the projection and runtime tests to verify they fail**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_get_encounter_state test.test_runtime_dispatcher test.test_runtime_use_disengage test.test_runtime_use_dodge -v`

Expected: FAIL because `GetEncounterState` does not project the new effects and the runtime command handlers do not exist yet.

- [ ] **Step 3: Project the action effects in `GetEncounterState`**

```python
# tools/services/encounter/get_encounter_state.py
    def _build_entity_ongoing_effects(self, encounter: Encounter, entity: EncounterEntity) -> list[str]:
        effect_labels: list[str] = []
        for effect in getattr(entity, "turn_effects", []):
            if not isinstance(effect, dict):
                continue
            effect_type = effect.get("effect_type")
            if effect_type == "disengage":
                effect_labels.append("Disengage")
            elif effect_type == "dodge":
                effect_labels.append("Dodge")
        ...
        return self._dedupe_preserve_order(effect_labels)
```

- [ ] **Step 4: Add runtime commands**

```python
# runtime/commands/use_disengage.py
from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_disengage import UseDisengage


def use_disengage(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(args["encounter_id"])
    actor_id = str(args["actor_id"])
    result = UseDisengage(context.encounter_repository).execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
```

```python
# runtime/commands/use_dodge.py
from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services.combat.actions.use_dodge import UseDodge


def use_dodge(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(args["encounter_id"])
    actor_id = str(args["actor_id"])
    result = UseDodge(context.encounter_repository).execute(
        encounter_id=encounter_id,
        actor_id=actor_id,
    )
    return {
        "result": result,
        "encounter_state": result.get("encounter_state"),
    }
```

```python
# runtime/commands/__init__.py
from runtime.commands.use_disengage import use_disengage
from runtime.commands.use_dodge import use_dodge

COMMAND_HANDLERS = {
    ...
    "use_disengage": use_disengage,
    "use_dodge": use_dodge,
}

__all__ = [
    ...
    "use_disengage",
    "use_dodge",
]
```

- [ ] **Step 5: Run the projection and runtime tests to verify they pass**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest test.test_get_encounter_state test.test_runtime_dispatcher test.test_runtime_use_disengage test.test_runtime_use_dodge -v`

Expected: PASS for `GetEncounterState` and runtime command registration/execution tests.

- [ ] **Step 6: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add tools/services/encounter/get_encounter_state.py runtime/commands/use_disengage.py runtime/commands/use_dodge.py runtime/commands/__init__.py test/test_get_encounter_state.py test/test_runtime_dispatcher.py test/test_runtime_use_disengage.py test/test_runtime_use_dodge.py
git commit -m "feat: expose disengage and dodge through runtime"
```

### Task 6: Full Verification And Skill Update

**Files:**
- Modify: `SKILL.md`
- Test: full targeted suite plus full regression suite

- [ ] **Step 1: Update the combat runtime skill**

```markdown
- `use_disengage`
  - 用途: 执行撤离动作
  - 成功后本回合剩余移动不触发借机攻击
  - 不自动移动

- `use_dodge`
  - 用途: 执行回避动作
  - 成功后直到下个自己回合开始前:
    - 以你为目标的攻击通常具有劣势
    - 你的敏捷豁免具有优势
  - 不自动结束回合
```

- [ ] **Step 2: Run the targeted verification suite**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && \
python3 -m unittest \
  test.test_use_disengage \
  test.test_use_dodge \
  test.test_begin_move_encounter_entity \
  test.test_attack_roll_request \
  test.test_saving_throw_request \
  test.test_get_encounter_state \
  test.test_runtime_dispatcher \
  test.test_runtime_use_disengage \
  test.test_runtime_use_dodge \
  test.test_start_turn -v
```

Expected: PASS.

- [ ] **Step 3: Run the full regression suite**

Run: `cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && python3 -m unittest discover -s test -v`

Expected: PASS with zero failures.

- [ ] **Step 4: Review diff before final commit**

Run:

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system && \
git diff -- \
  SKILL.md \
  tools/services/combat/actions \
  tools/services/encounter/turns/turn_engine.py \
  tools/services/encounter/begin_move_encounter_entity.py \
  tools/services/combat/attack/attack_roll_request.py \
  tools/services/combat/save_spell/saving_throw_request.py \
  tools/services/encounter/get_encounter_state.py \
  runtime/commands \
  test/test_use_disengage.py \
  test/test_use_dodge.py \
  test/test_runtime_use_disengage.py \
  test/test_runtime_use_dodge.py
```

Expected: Only `Disengage` / `Dodge` related changes are present.

- [ ] **Step 5: Commit**

```bash
cd /Users/runshi.zhang/DND-DM-skill/trpg-battle-system
git add SKILL.md tools/services/combat/actions tools/services/encounter/turns/turn_engine.py tools/services/encounter/begin_move_encounter_entity.py tools/services/combat/attack/attack_roll_request.py tools/services/combat/save_spell/saving_throw_request.py tools/services/encounter/get_encounter_state.py runtime/commands test/test_use_disengage.py test/test_use_dodge.py test/test_runtime_use_disengage.py test/test_runtime_use_dodge.py
git commit -m "feat: add disengage and dodge combat actions"
```

## Self-Review

### Spec coverage

- 显式动作 tool：Task 2 与 Task 5 覆盖
- `turn_effects` 运行态：Task 1 与 Task 2 覆盖
- `Disengage` 抑制借机：Task 3 覆盖
- `Dodge` 攻击劣势：Task 4 覆盖
- `Dodge` 敏捷豁免优势：Task 4 覆盖
- `GetEncounterState` 投影：Task 5 覆盖
- skill 调用规则更新：Task 6 覆盖

### Placeholder scan

- 没有 `TODO` / `TBD`
- 每个改动点都有明确文件、测试、命令
- 每个任务都有明确 commit 点

### Type consistency

- service 名统一为 `UseDisengage` / `UseDodge`
- runtime command 名统一为 `use_disengage` / `use_dodge`
- `turn_effect` 类型统一为 `disengage` / `dodge`
