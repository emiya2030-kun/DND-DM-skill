# Melee Enemy Engagement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `enemy_tactical_brief` so GM-controlled melee enemies project not only targets they can already hit, but also targets they can engage this turn using normal movement, Dash, or Disengage, including conservative opportunity-attack risk.

**Architecture:** Keep `candidate_targets` as the “already in melee attack range” list. Add a focused engagement-analysis helper that reuses movement/pathfinding rules and conservative leave-reach semantics to build `reachable_targets` without executing movement. `get_encounter_state` remains the projection entrypoint and only attaches the new field.

**Tech Stack:** Python 3, pytest/unittest, existing encounter state projection services, `movement_rules`, existing leave-reach opportunity semantics

---

### Task 1: Add failing tests for reachable engagement projection

**Files:**
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for move-and-attack reachable target**

Add a focused test near the existing `enemy_tactical_brief` tests:

```python
    def test_execute_enemy_tactical_brief_projects_reachable_target_via_normal_move(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[build_test_weapon(
                weapon_id="mace",
                name="Mace",
                damage_formula="1d6+3",
                damage_type="bludgeoning",
                normal_range=5,
                long_range=5,
                kind="melee",
            )],
        )
        target = EncounterEntity(
            entity_id="ent_ally_target_001",
            name="Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 1},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_reachable_move",
            name="Enemy Brief Reachable Move",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, target.entity_id],
            entities={enemy.entity_id: enemy, target.entity_id: target},
            map=EncounterMap(map_id="map_enemy_brief_reachable_move", name="Reachable Move", description="reachable move test", width=12, height=12),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]

        self.assertEqual(len(reachable), 1)
        self.assertEqual(reachable[0]["entity_id"], target.entity_id)
        self.assertEqual(reachable[0]["engage_mode"], "move_and_attack")
        self.assertTrue(reachable[0]["can_attack_this_turn"])
        self.assertFalse(reachable[0]["requires_action_dash"])
        self.assertFalse(reachable[0]["requires_action_disengage"])
        self.assertFalse(reachable[0]["opportunity_attack_risk"])
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k reachable_target_via_normal_move`

Expected: FAIL because `reachable_targets` does not exist yet.

- [ ] **Step 3: Write the failing test for Dash-only engagement**

Add:

```python
    def test_execute_enemy_tactical_brief_projects_dash_only_target(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="mace",
                name="Mace",
                damage_formula="1d6+3",
                damage_type="bludgeoning",
                normal_range=5,
                long_range=5,
                kind="melee",
            ),
            position={"x": 1, "y": 1},
        )
        encounter.entities["ent_ally_player_001"].position = {"x": 9, "y": 1}

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]

        self.assertEqual(reachable[0]["engage_mode"], "dash_to_engage")
        self.assertFalse(reachable[0]["can_attack_this_turn"])
        self.assertTrue(reachable[0]["requires_action_dash"])
```

- [ ] **Step 4: Run the Dash test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k dash_only_target`

Expected: FAIL because no Dash reachability projection exists yet.

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py
git commit -m "test: cover melee enemy reachable targets"
```

### Task 2: Add failing tests for Disengage and opportunity-attack risk

**Files:**
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for risky engagement without Disengage**

Add:

```python
    def test_execute_enemy_tactical_brief_marks_opportunity_attack_risk_when_leaving_reach(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[build_test_weapon(
                weapon_id="mace",
                name="Mace",
                damage_formula="1d6+3",
                damage_type="bludgeoning",
                normal_range=5,
                long_range=5,
                kind="melee",
            )],
            action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        )
        blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[build_test_weapon(
                weapon_id="rapier",
                name="Rapier",
                damage_formula="1d8+3",
                damage_type="piercing",
                normal_range=5,
                long_range=5,
                kind="melee",
            )],
            action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        )
        caster = EncounterEntity(
            entity_id="ent_ally_caster_001",
            name="Caster",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 9},
            hp={"current": 18, "max": 18, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_oa_risk",
            name="Enemy Brief OA Risk",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, blocker.entity_id, caster.entity_id],
            entities={mover.entity_id: mover, blocker.entity_id: blocker, caster.entity_id: caster},
            map=EncounterMap(map_id="map_enemy_brief_oa_risk", name="OA Risk", description="oa risk test", width=12, height=12),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        by_id = {item["entity_id"]: item for item in reachable}

        self.assertTrue(by_id[caster.entity_id]["opportunity_attack_risk"])
        self.assertEqual(by_id[caster.entity_id]["risk_sources"], [blocker.entity_id])
```

- [ ] **Step 2: Run the risk test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k opportunity_attack_risk_when_leaving_reach`

Expected: FAIL because risk projection does not exist yet.

- [ ] **Step 3: Write the failing test for Disengage-safe engagement**

Add:

```python
    def test_execute_enemy_tactical_brief_projects_disengage_to_engage_option(self) -> None:
        # Reuse the encounter above, but assert a safe fallback option exists.
        ...
        disengage_option = by_id["ent_ally_caster_001"]
        self.assertEqual(disengage_option["engage_mode"], "disengage_to_engage")
        self.assertTrue(disengage_option["requires_action_disengage"])
        self.assertFalse(disengage_option["can_attack_this_turn"])
```

- [ ] **Step 4: Run the Disengage test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k disengage_to_engage_option`

Expected: FAIL because safe re-engagement mode does not exist yet.

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py
git commit -m "test: cover melee enemy engagement risk modes"
```

### Task 3: Implement focused engagement analysis helper

**Files:**
- Create: `tools/services/encounter/enemy_tactical_engagement.py`
- Modify: `tools/services/encounter/get_encounter_state.py`

- [ ] **Step 1: Create the helper module with the projected item shape**

Add:

```python
from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.services.encounter.movement_rules import validate_movement_path


def build_reachable_enemy_tactical_targets(
    *,
    encounter: Encounter,
    actor: EncounterEntity,
    max_melee_range_feet: int,
    base_score_resolver,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for target in encounter.entities.values():
        if target.entity_id == actor.entity_id or target.side == actor.side:
            continue
        projected = _build_single_reachable_target(
            encounter=encounter,
            actor=actor,
            target=target,
            max_melee_range_feet=max_melee_range_feet,
            base_score_resolver=base_score_resolver,
        )
        if projected is not None:
            targets.append(projected)
    return targets
```

- [ ] **Step 2: Implement minimal “adjacent anchor” search and movement-mode evaluation**

Add:

```python
def _build_single_reachable_target(...):
    move_projection = _project_engagement_mode(
        encounter=encounter,
        actor=actor,
        target=target,
        max_melee_range_feet=max_melee_range_feet,
        use_dash=False,
    )
    dash_projection = _project_engagement_mode(
        encounter=encounter,
        actor=actor,
        target=target,
        max_melee_range_feet=max_melee_range_feet,
        use_dash=True,
    )
    # Prefer move-and-attack; fall back to Dash if only Dash reaches.
    ...
```

- [ ] **Step 3: Add conservative opportunity-risk projection**

Use the same leave-reach semantics as `BeginMoveEncounterEntity`:

```python
def _collect_opportunity_risk_sources(encounter: Encounter, actor: EncounterEntity) -> list[str]:
    risk_sources: list[str] = []
    for candidate in encounter.entities.values():
        if candidate.entity_id == actor.entity_id or candidate.side == actor.side:
            continue
        if bool(candidate.action_economy.get("reaction_used")):
            continue
        if not _has_melee_weapon(candidate):
            continue
        if _distance_feet(candidate.position, actor.position) <= 5:
            risk_sources.append(candidate.entity_id)
    return risk_sources
```

- [ ] **Step 4: Add score adjustment for engagement mode**

Use the current score as the high reference, then apply only light penalties:

```python
ENGAGE_MODE_SCORE_ADJUSTMENTS = {
    "move_and_attack": 0.0,
    "dash_to_engage": -1.5,
    "disengage_to_engage": -2.5,
}
OPPORTUNITY_ATTACK_RISK_PENALTY = 2.0
```

- [ ] **Step 5: Wire the helper into `get_encounter_state`**

Extend `_build_enemy_tactical_brief`:

```python
from tools.services.encounter.enemy_tactical_engagement import build_reachable_enemy_tactical_targets

reachable_targets = build_reachable_enemy_tactical_targets(
    encounter=encounter,
    actor=actor,
    max_melee_range_feet=max_melee_range,
    base_score_resolver=self._score_enemy_tactical_target,
)
...
return {
    "candidate_targets": top_candidates,
    "reachable_targets": reachable_targets[:2],
}
```

- [ ] **Step 6: Run the targeted tests to verify they pass**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k "reachable_target_via_normal_move or dash_only_target or opportunity_attack_risk_when_leaving_reach or disengage_to_engage_option"`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tools/services/encounter/enemy_tactical_engagement.py tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: project melee enemy reachable engagement targets"
```

### Task 4: Refine ordering and keep current score as the high reference

**Files:**
- Modify: `tools/services/encounter/enemy_tactical_engagement.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for score-first reachable ordering**

Add:

```python
    def test_execute_enemy_tactical_brief_reachable_targets_keep_score_as_primary_signal(self) -> None:
        ...
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        self.assertEqual([item["entity_id"] for item in reachable], [
            "ent_ally_concentration_001",
            "ent_ally_low_ac_001",
        ])
```

This test should use one “higher-value but needs Dash/has risk” target and one “lower-value but easier to reach” target; the higher-value target should still stay ahead if the score gap is big enough.

- [ ] **Step 2: Run the ordering test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k score_as_primary_signal`

Expected: FAIL because the first implementation will likely over-penalize movement mode.

- [ ] **Step 3: Implement stable reachable target ordering**

Sort reachable targets by:

```python
sorted(
    reachable_targets,
    key=lambda item: (
        -float(item["score"]),
        0 if item["can_attack_this_turn"] else 1,
        0 if not item["opportunity_attack_risk"] else 1,
        int(item["movement_cost_feet"]),
        str(item["entity_id"]),
    ),
)
```

- [ ] **Step 4: Run all `enemy_tactical_brief` tests**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k enemy_tactical_brief`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/enemy_tactical_engagement.py test/test_get_encounter_state.py
git commit -m "feat: rank melee enemy reachable engagement targets"
```

### Task 5: Run regressions for encounter-state consumers

**Files:**
- No code changes expected

- [ ] **Step 1: Run the full encounter-state regression**

Run: `python3 -m pytest -q test/test_get_encounter_state.py`

Expected: PASS

- [ ] **Step 2: Run localhost projection regression**

Run: `python3 -m pytest -q test/test_run_battlemap_localhost.py`

Expected: PASS

- [ ] **Step 3: Run movement-related regression**

Run: `python3 -m pytest -q test/test_movement_rules.py test/test_continue_pending_movement.py`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "chore: verify melee enemy engagement projection regressions"
```
