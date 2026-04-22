# Melee Enemy Targeting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-pass melee-enemy tactical briefing layer that projects the top two target candidates for the current GM-controlled melee attacker into `get_encounter_state`.

**Architecture:** Add a focused encounter-side projection helper that inspects the current actor, derives whether the actor qualifies as a melee attacker, scores valid hostile targets using deterministic rules, and emits `current_turn_context.enemy_tactical_brief`. Keep all existing state fields intact and reuse existing encounter/entity projection helpers wherever possible.

**Tech Stack:** Python 3, unittest/pytest, existing encounter state projection services

---

### Task 1: Add failing tests for the new tactical briefing surface

**Files:**
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for presence on a melee GM turn**

Add a new test near the existing `get_encounter_state` projection tests:

```python
    def test_execute_projects_enemy_tactical_brief_for_current_melee_gm_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            enemy = encounter.entities["ent_enemy_goblin_001"]
            enemy.weapons = [
                {
                    "weapon_id": "shortsword",
                    "name": "Shortsword",
                    "attack_bonus": 4,
                    "damage": [{"formula": "1d6+2", "type": "piercing"}],
                    "range": {"normal": 5, "long": 5},
                    "kind": "melee",
                    "category": "martial",
                }
            ]
            encounter.current_entity_id = enemy.entity_id
            encounter.turn_order = [enemy.entity_id, "ent_ally_eric_001", "ent_enemy_archer_001"]
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            brief = state["current_turn_context"]["enemy_tactical_brief"]
            self.assertEqual(brief["role"], "melee_attacker")
            self.assertTrue(brief["can_act"])
            self.assertLessEqual(len(brief["candidate_targets"]), 2)
            repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k enemy_tactical_brief_for_current_melee_gm_actor`

Expected: FAIL because `enemy_tactical_brief` is missing.

- [ ] **Step 3: Write the failing test for absence on non-GM/player turn**

Add a second test:

```python
    def test_execute_omits_enemy_tactical_brief_on_player_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertNotIn("enemy_tactical_brief", state["current_turn_context"])
            repo.close()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k "enemy_tactical_brief_on_player_turn or enemy_tactical_brief_for_current_melee_gm_actor"`

Expected: FAIL because the new field behavior is not implemented.

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py
git commit -m "test: cover melee enemy tactical brief projection"
```

### Task 2: Add failing tests for candidate ranking rules

**Files:**
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for AC, concentration, summon, and range rules**

Add a focused ranking test:

```python
    def test_execute_enemy_tactical_brief_returns_top_two_ranked_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            enemy = EncounterEntity(
                entity_id="ent_enemy_brute_001",
                name="Brute",
                side="enemy",
                category="monster",
                controller="gm",
                position={"x": 5, "y": 5},
                hp={"current": 40, "max": 40, "temp": 0},
                ac=15,
                speed={"walk": 30, "remaining": 30},
                initiative=12,
                weapons=[{
                    "weapon_id": "mace",
                    "name": "Mace",
                    "attack_bonus": 5,
                    "damage": [{"formula": "1d6+3", "type": "bludgeoning"}],
                    "range": {"normal": 5, "long": 5},
                    "kind": "melee",
                }],
            )
            low_ac = EncounterEntity(
                entity_id="ent_ally_low_ac_001",
                name="Low AC",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 6, "y": 5},
                hp={"current": 16, "max": 20, "temp": 0},
                ac=12,
                speed={"walk": 30, "remaining": 30},
                initiative=15,
            )
            concentrating = EncounterEntity(
                entity_id="ent_ally_concentration_001",
                name="Concentration",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 5, "y": 6},
                hp={"current": 22, "max": 22, "temp": 0},
                ac=18,
                speed={"walk": 30, "remaining": 30},
                initiative=14,
                turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hex"}],
            )
            summon = EncounterEntity(
                entity_id="ent_ally_summon_001",
                name="Summon",
                side="ally",
                category="summon",
                controller="player",
                position={"x": 4, "y": 5},
                hp={"current": 10, "max": 10, "temp": 0},
                ac=13,
                speed={"walk": 30, "remaining": 30},
                initiative=13,
            )
            far_target = EncounterEntity(
                entity_id="ent_ally_far_001",
                name="Far",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 10, "y": 5},
                hp={"current": 8, "max": 8, "temp": 0},
                ac=10,
                speed={"walk": 30, "remaining": 30},
                initiative=11,
            )
            encounter = Encounter(
                encounter_id="enc_enemy_brief_rank",
                name="Enemy Brief Rank",
                status="active",
                round=1,
                current_entity_id=enemy.entity_id,
                turn_order=[enemy.entity_id, low_ac.entity_id, concentrating.entity_id, summon.entity_id, far_target.entity_id],
                entities={
                    enemy.entity_id: enemy,
                    low_ac.entity_id: low_ac,
                    concentrating.entity_id: concentrating,
                    summon.entity_id: summon,
                    far_target.entity_id: far_target,
                },
                map=EncounterMap(map_id="map_enemy_brief_rank", name="Rank Map", description="rank test", width=12, height=12),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_enemy_brief_rank")

            candidates = state["current_turn_context"]["enemy_tactical_brief"]["candidate_targets"]
            candidate_ids = [item["entity_id"] for item in candidates]
            self.assertEqual(len(candidates), 2)
            self.assertIn("ent_ally_low_ac_001", candidate_ids)
            self.assertIn("ent_ally_concentration_001", candidate_ids)
            self.assertNotIn("ent_ally_summon_001", candidate_ids)
            self.assertNotIn("ent_ally_far_001", candidate_ids)
            repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k returns_top_two_ranked_targets`

Expected: FAIL because the ranking layer does not exist yet.

- [ ] **Step 3: Write the failing test for empty candidate list when applicable but nothing is in range**

Add:

```python
    def test_execute_enemy_tactical_brief_returns_empty_candidates_when_no_target_in_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            enemy = encounter.entities["ent_enemy_goblin_001"]
            enemy.weapons = [{
                "weapon_id": "club",
                "name": "Club",
                "attack_bonus": 4,
                "damage": [{"formula": "1d4+2", "type": "bludgeoning"}],
                "range": {"normal": 5, "long": 5},
                "kind": "melee",
            }]
            enemy.position = {"x": 9, "y": 9}
            encounter.current_entity_id = enemy.entity_id
            encounter.turn_order = [enemy.entity_id, "ent_ally_eric_001", "ent_enemy_archer_001"]
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            brief = state["current_turn_context"]["enemy_tactical_brief"]
            self.assertEqual(brief["candidate_targets"], [])
            repo.close()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k empty_candidates_when_no_target_in_range`

Expected: FAIL because the empty-brief path is not implemented.

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py
git commit -m "test: cover melee enemy tactical target ranking"
```

### Task 3: Implement a focused melee enemy tactical briefing helper

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`

- [ ] **Step 1: Add a private builder entry point in `GetEncounterState`**

Add a helper call inside `_build_current_turn_context` integration path:

```python
    def _build_enemy_tactical_brief(
        self,
        encounter: Encounter,
        entity: EncounterEntity | None,
    ) -> dict[str, Any] | None:
        if entity is None:
            return None
        if entity.controller != "gm":
            return None
        if not self._entity_is_melee_enemy_attacker(entity):
            return None
        ...
```

- [ ] **Step 2: Implement the minimal “melee attacker” predicate**

Add a helper in the same file:

```python
    def _entity_is_melee_enemy_attacker(self, entity: EncounterEntity) -> bool:
        for weapon in entity.weapons:
            if not isinstance(weapon, dict):
                continue
            weapon_range = weapon.get("range", {})
            normal_range = weapon_range.get("normal")
            if isinstance(normal_range, int) and normal_range <= 10:
                return True
            if str(weapon.get("kind") or "").strip().lower() == "melee":
                return True
        return False
```

- [ ] **Step 3: Implement candidate collection and range filtering**

Add:

```python
    def _collect_melee_enemy_target_candidates(
        self,
        encounter: Encounter,
        actor: EncounterEntity,
    ) -> list[EncounterEntity]:
        max_melee_range = self._max_melee_range(actor)
        if max_melee_range <= 0:
            return []
        items: list[EncounterEntity] = []
        for entity in encounter.entities.values():
            if entity.entity_id == actor.entity_id:
                continue
            if entity.side == actor.side:
                continue
            if self._distance_feet(actor, entity) > max_melee_range:
                continue
            items.append(entity)
        return items
```

- [ ] **Step 4: Implement scoring helpers**

Add helpers that calculate:

```python
    def _score_melee_enemy_target(...): ...
    def _build_melee_enemy_target_score_breakdown(...): ...
    def _target_is_concentrating(...): ...
    def _target_is_summon(...): ...
    def _target_hp_ratio(...): ...
```

Use these first-pass rules:

```python
if target is lowest_ac_tier: +30
elif target is middle_low_ac_tier: +15
if is_concentrating: +30
if attack_has_advantage: +8
if hp_ratio <= 0.5: +10
if max_hp <= max_hp_threshold: +10
if is_summon: -25
if blocked_by_darkness: -35
if hazardous_path_required: -8
```

- [ ] **Step 5: Sort, truncate to top two, and emit readable summaries**

Build the projection shape:

```python
        return {
            "role": "melee_attacker",
            "can_act": not bool(entity.action_economy.get("action_used")),
            "candidate_targets": top_two,
            "llm_decision_note": "...",
        }
```

Each candidate item should include:

```python
{
    "entity_id": target.entity_id,
    "name": target.name,
    "score": score,
    "in_attack_range": True,
    "distance_feet": self._distance_feet(actor, target),
    "ac": target.ac,
    "hp_ratio": hp_ratio,
    "is_concentrating": is_concentrating,
    "is_summon": is_summon,
    "attack_has_advantage": attack_has_advantage,
    "blocked_by_darkness": blocked_by_darkness,
    "terrain_cost_note": terrain_cost_note,
    "score_breakdown": score_breakdown,
    "reason_summary": reason_summary,
}
```

- [ ] **Step 6: Wire the helper into `current_turn_context`**

Inside the current-turn projection builder, only include the new field when non-`None`:

```python
        result = {
            "actor": current_turn_entity,
            "current_turn_group": current_turn_group,
            "actor_options": {...},
            "targeting": current_turn_entity.get("weapon_ranges", {}),
        }
        enemy_tactical_brief = self._build_enemy_tactical_brief(encounter, entity)
        if enemy_tactical_brief is not None:
            result["enemy_tactical_brief"] = enemy_tactical_brief
        return result
```

- [ ] **Step 7: Run the targeted tests to verify they pass**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k "enemy_tactical_brief"`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: project melee enemy tactical brief"
```

### Task 4: Refine tie-break behavior and advantage reuse

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test for concentration tie-break**

Add:

```python
    def test_execute_enemy_tactical_brief_prefers_concentration_on_close_scores(self) -> None:
        ...
        self.assertEqual(candidates[0]["entity_id"], "ent_ally_concentration_001")
```

Craft inputs so the concentration target and low-AC target end up within the configured tie window.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k prefers_concentration_on_close_scores`

Expected: FAIL because the tie-break logic is not applied yet.

- [ ] **Step 3: Implement the tie-break**

Adjust sorting to use:

```python
sorted(
    candidates,
    key=lambda item: (
        item["score"],
        1 if item["is_concentrating"] else 0 if not close_to_top_score else 0,
    ),
    reverse=True,
)
```

If scores differ by `<= 8`, prefer concentrating targets.

- [ ] **Step 4: Reuse a minimal advantage heuristic**

Do not call the full attack execution pipeline. Instead, infer a first-pass `attack_has_advantage` using already projected state:

```python
attack_has_advantage = "restrained" in target.conditions or "paralyzed" in target.conditions
```

Only add more conditions if tests require them.

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k "enemy_tactical_brief or prefers_concentration_on_close_scores"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: refine melee enemy tactical ranking rules"
```

### Task 5: Run broader regression for encounter state consumers

**Files:**
- No code changes expected

- [ ] **Step 1: Run the main encounter state regression**

Run: `python3 -m pytest -q test/test_get_encounter_state.py`

Expected: PASS

- [ ] **Step 2: Run localhost page regression**

Run: `python3 -m pytest -q test/test_run_battlemap_localhost.py`

Expected: PASS

- [ ] **Step 3: Run random encounter/runtime regression**

Run: `python3 -m pytest -q test/test_runtime_start_random_encounter.py`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "chore: verify melee enemy tactical brief regressions"
```

### Task 6: Manual validation with a simulated wight encounter

**Files:**
- No committed code changes expected

- [ ] **Step 1: Build a temporary wight-vs-player encounter and inspect the new field**

Run a one-off script from the repo root that:

- loads `monster_wight` from `data/knowledge/entity_definitions.json`
- makes the wight the current actor
- places two PCs and one summon in melee range
- prints `state["current_turn_context"]["enemy_tactical_brief"]`

Expected: output includes exactly two ranked candidates and excludes or demotes the summon.

- [ ] **Step 2: Record the observed output in the implementation notes**

Summarize:

- which two targets were returned
- whether concentration tie-break worked
- whether the summon stayed out of the top two

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: manually validate melee enemy tactical brief"
```
