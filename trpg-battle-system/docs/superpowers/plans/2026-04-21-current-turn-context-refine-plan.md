# Current Turn Context Refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine `current_turn_context` so it behaves like a compact monster turn decision interface without changing the top-level encounter payload shape.

**Architecture:** Keep `current_turn_context` split into `actor / current_turn_group / actor_options / targeting / enemy_tactical_brief`, but shrink each block to only the data needed for current-turn decision making. Preserve `current_turn_entity` as the compatibility/full-detail payload so existing consumers do not break.

**Tech Stack:** Python, `pytest`, existing encounter projection services in `tools/services/encounter/get_encounter_state.py`

---

### Task 1: Lock `current_turn_context` field boundaries with tests

**Files:**
- Modify: `test/test_get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Add failing tests for compact `current_turn_context` blocks**

```python
def test_execute_projects_compact_current_turn_context_actor(self) -> None:
    state = GetEncounterState(repo).execute("enc_view_test")
    actor = state["current_turn_context"]["actor"]
    assert "available_actions" not in actor

def test_execute_projects_compact_current_turn_context_group(self) -> None:
    state = GetEncounterState(repo).execute("enc_view_test")
    group = state["current_turn_context"]["current_turn_group"]
    assert set(group["controlled_members"][0].keys()) == {"entity_id", "name", "relation"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: FAIL on the new `current_turn_context` boundary assertions.

- [ ] **Step 3: Implement the minimal projection changes**

```python
current_turn_context = {
    "actor": self._build_current_turn_context_actor(current_turn_entity),
    "current_turn_group": self._build_current_turn_context_group(current_turn_group),
    ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py tools/services/encounter/get_encounter_state.py
git commit -m "refactor: compact current turn context payload"
```

### Task 2: Compact `actor_options` without losing execution metadata

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Add failing tests for `actor_options` shape**

```python
def test_execute_projects_compact_current_turn_context_actor_options(self) -> None:
    actor_options = state["current_turn_context"]["actor_options"]
    assert "execution" in actor_options["actions"][0]
    assert "summary" in actor_options["traits"][0]
```

- [ ] **Step 2: Run test to verify it fails or protects against regressions**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: FAIL if extra unstructured fields still leak in, otherwise PASS and protect the boundary.

- [ ] **Step 3: Keep only decision-useful action metadata**

```python
"actor_options": {
    "weapon_attacks": ...,
    "spells": ...,
    "spell_slots_available": ...,
    "traits": self._build_entity_traits_metadata(entity),
    "actions": self._build_entity_action_metadata(...),
    "bonus_actions": self._build_entity_action_metadata(...),
    "reactions": self._build_entity_action_metadata(...),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py tools/services/encounter/get_encounter_state.py
git commit -m "refactor: keep current turn action options decision-focused"
```

### Task 3: Compact `targeting` and `enemy_tactical_brief` only where safe

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Add failing tests for tactical payload minimum shape**

```python
def test_execute_projects_enemy_tactical_brief_minimum_shape(self) -> None:
    brief = state["current_turn_context"]["enemy_tactical_brief"]
    assert set(brief.keys()) == {"candidate_targets", "reachable_targets"}
```

- [ ] **Step 2: Run test to verify it fails or guards the shape**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: PASS/FAIL depending on current payload, but the test becomes the guardrail.

- [ ] **Step 3: Leave battlemap-derived information out of `current_turn_context`**

```python
return {
    "candidate_targets": top_candidates,
    "reachable_targets": reachable_targets,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py tools/services/encounter/get_encounter_state.py
git commit -m "test: lock tactical brief boundary"
```

### Task 4: Verify encounter-state compatibility

**Files:**
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_run_battlemap_localhost.py`

- [ ] **Step 1: Run encounter-state tests**

Run: `python3 -m pytest test/test_get_encounter_state.py -q`
Expected: PASS

- [ ] **Step 2: Run localhost projection tests**

Run: `python3 -m pytest test/test_run_battlemap_localhost.py -q`
Expected: PASS outside restricted sandboxes; in restricted sandboxes, only socket bind related failures are acceptable.

- [ ] **Step 3: Summarize any environment-only failures**

```text
If localhost tests fail only on ThreadingHTTPServer bind PermissionError, record it as a sandbox limitation rather than a projection regression.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-21-current-turn-context-refine-plan.md
git commit -m "docs: add current turn context refine plan"
```
