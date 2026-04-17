# Class Features Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable combat-time class feature framework and implement the first batch of fighter base features with real runtime effects.

**Architecture:** Add a new `class_features` runtime state block to encounter entities, a static class-feature knowledge repository for LLM-facing definitions, and a small set of feature services/hooks that plug into attack, save, movement, and turn flow. Keep active-use features as dedicated services and passive/triggered features as attack/save/turn hooks.

**Tech Stack:** Python 3, unittest/pytest, existing encounter repositories/services, TinyDB-backed encounter state, HTML battlemap via `get_encounter_state`

---

## File Map

### Runtime model and projection

- Modify: `tools/models/encounter_entity.py`
  - Add `class_features` to runtime encounter entities.
- Modify: `app/models/encounter_entity.py`
  - Mirror the same field in the app-side model.
- Modify: `tools/services/encounter/get_encounter_state.py`
  - Project enough class-feature info for LLM/runtime consumers.

### Knowledge layer

- Create: `data/knowledge/class_feature_definitions.json`
  - Static LLM-facing class feature definitions.
- Create: `tools/repositories/class_feature_definition_repository.py`
  - Read the JSON repository.
- Modify: `tools/repositories/__init__.py`
  - Export the new repository.
- Test: `test/test_class_feature_definition_repository.py`
  - Repository coverage for fighter feature definitions.

### Shared feature runtime helpers

- Create: `tools/services/class_features/shared/__init__.py`
- Create: `tools/services/class_features/shared/runtime.py`
  - Shared getters/setters for `entity.class_features`.
- Create: `tools/services/class_features/shared/extra_attack.py`
  - Shared helpers for attack-action sequence counting and max attack count resolution.
- Create: `tools/services/class_features/shared/studied_attacks.py`
  - Shared helpers for writing/consuming studied-attacks marks.

### Fighter active-use services

- Create: `tools/services/class_features/fighter/__init__.py`
- Create: `tools/services/class_features/fighter/use_second_wind.py`
- Create: `tools/services/class_features/fighter/use_action_surge.py`
- Test: `test/test_use_second_wind.py`
- Test: `test/test_use_action_surge.py`

### Attack-chain hooks

- Modify: `tools/services/combat/attack/attack_roll_request.py`
  - Inject studied-attacks advantage and tactical-master validation context.
- Modify: `tools/services/combat/attack/execute_attack.py`
  - Support `mastery_override`, extra-attack sequence accounting, and studied-attacks mark writes.
- Modify: `tools/services/combat/attack/weapon_mastery_effects.py`
  - Accept tactical-master override when legal.
- Test: `test/test_execute_attack.py`
  - Add focused cases for extra attack, studied attacks, and tactical master.

### Indomitable failure-window integration

- Modify: `tools/services/combat/rules/reactions/reaction_definitions.py`
  - Add `indomitable`.
- Modify: `tools/repositories/reaction_definition_repository.py`
  - No logic change expected, but covered by new reaction definitions.
- Modify: `tools/services/combat/rules/reactions/collect_reaction_candidates.py`
  - Recognize failed-save trigger and eligible fighter actors.
- Modify: `tools/services/combat/rules/reactions/open_reaction_window.py`
  - Support failed-save trigger payload shape.
- Modify: `tools/services/combat/rules/reactions/resolve_reaction_option.py`
  - Route `indomitable`.
- Create: `tools/services/combat/rules/reactions/definitions/indomitable.py`
  - Resolve failed-save reroll plus fighter-level bonus.
- Modify: `tools/services/combat/save_spell/resolve_saving_throw.py`
  - Expose enough failed-save output to open the reaction window.
- Test: `test/test_indomitable_reaction_window.py`
- Test: `test/test_resolve_reaction_option.py`

### Movement integration for Tactical Shift

- Modify: `tools/services/encounter/begin_move_encounter_entity.py`
  - Honor one-shot “ignore opportunity attacks” movement context.
- Modify: `tools/services/encounter/move_encounter_entity.py`
  - Consume Tactical Shift free movement allowance when provided.
- Test: `test/test_begin_move_encounter_entity.py`
- Test: `test/test_move_encounter_entity.py`

### Encounter initialization / fixtures

- Modify: `tools/services/encounter/initialize_encounter.py` or the existing encounter-creation entrypoint actually used by the repo
  - Accept precomputed `class_features`.
- Modify: test encounter builders that need fighter runtime state.

### Documentation

- Modify: `docs/llm-runtime-tool-guide.md`
  - Add class feature runtime/tool usage notes.

---

### Task 1: Add `class_features` to encounter entities

**Files:**
- Modify: `tools/models/encounter_entity.py`
- Modify: `app/models/encounter_entity.py`
- Test: `test/test_models.py`

- [ ] **Step 1: Write the failing test**

Add a model test like:

```python
def test_encounter_entity_accepts_class_features_runtime_state():
    entity = EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        class_features={
            "fighter": {
                "fighter_level": 5,
                "second_wind": {"max_uses": 3, "remaining_uses": 3},
                "extra_attack_count": 2,
            }
        },
    )

    assert entity.class_features["fighter"]["fighter_level"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_models.py -k class_features_runtime_state`
Expected: FAIL with unexpected keyword argument `class_features` or missing field in serialization.

- [ ] **Step 3: Write minimal implementation**

Update both dataclasses to include:

```python
class_features: dict[str, Any] = field(default_factory=dict)
```

And include it in `to_dict()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_models.py -k class_features_runtime_state`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_models.py tools/models/encounter_entity.py app/models/encounter_entity.py
git commit -m "feat: add class feature runtime state to encounter entities"
```

### Task 2: Add class feature definition repository

**Files:**
- Create: `data/knowledge/class_feature_definitions.json`
- Create: `tools/repositories/class_feature_definition_repository.py`
- Modify: `tools/repositories/__init__.py`
- Test: `test/test_class_feature_definition_repository.py`

- [ ] **Step 1: Write the failing test**

Create:

```python
def test_get_returns_fighter_second_wind_definition():
    repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))
    feature = repo.get("fighter.second_wind")
    assert feature["template_type"] == "activated_heal"
    assert feature["activation"] == "bonus_action"
```

And:

```python
def test_extra_attack_definition_marks_non_stacking_rule():
    repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))
    feature = repo.get("fighter.extra_attack")
    assert feature["special_rules"]["stacking"] == "take_highest_only"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_class_feature_definition_repository.py -v`
Expected: FAIL because repository/file does not exist.

- [ ] **Step 3: Write minimal implementation**

Create repository:

```python
class ClassFeatureDefinitionRepository:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or CLASS_FEATURE_DEFINITIONS_PATH)

    def load_all(self) -> dict[str, dict[str, Any]]:
        ...

    def get(self, feature_id: str) -> dict[str, Any] | None:
        return self.load_all().get(feature_id)
```

Create JSON entries for all 7 fighter features.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_class_feature_definition_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/knowledge/class_feature_definitions.json tools/repositories/class_feature_definition_repository.py tools/repositories/__init__.py test/test_class_feature_definition_repository.py
git commit -m "feat: add class feature definition repository"
```

### Task 3: Add shared fighter runtime helpers

**Files:**
- Create: `tools/services/class_features/shared/runtime.py`
- Create: `tools/services/class_features/shared/extra_attack.py`
- Create: `tools/services/class_features/shared/studied_attacks.py`
- Create: `tools/services/class_features/shared/__init__.py`
- Test: `test/test_class_feature_runtime_helpers.py`

- [ ] **Step 1: Write the failing test**

Add tests like:

```python
def test_resolve_extra_attack_count_takes_highest_source_only():
    fighter_state = {
        "fighter": {
            "extra_attack_count": 2,
            "extra_attack_sources": [
                {"source": "fighter", "attack_count": 2},
                {"source": "other_class", "attack_count": 2},
            ],
        }
    }
    assert resolve_extra_attack_count(fighter_state) == 2
```

```python
def test_add_studied_attack_mark_appends_target_once():
    state = {"fighter": {"studied_attacks": []}}
    add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
    assert state["fighter"]["studied_attacks"][0]["target_entity_id"] == "ent_enemy_001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_class_feature_runtime_helpers.py -v`
Expected: FAIL because helper module does not exist.

- [ ] **Step 3: Write minimal implementation**

Include helpers such as:

```python
def get_fighter_runtime(entity: Any) -> dict[str, Any]:
    ...

def resolve_extra_attack_count(class_features: dict[str, Any]) -> int:
    sources = fighter.get("extra_attack_sources", [])
    counts = [fighter.get("extra_attack_count", 1)]
    counts.extend(item.get("attack_count", 1) for item in sources if isinstance(item, dict))
    return max(1, *[count for count in counts if isinstance(count, int)])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_class_feature_runtime_helpers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/shared/__init__.py tools/services/class_features/shared/runtime.py tools/services/class_features/shared/extra_attack.py tools/services/class_features/shared/studied_attacks.py test/test_class_feature_runtime_helpers.py
git commit -m "feat: add shared class feature runtime helpers"
```

### Task 4: Implement `use_second_wind`

**Files:**
- Create: `tools/services/class_features/fighter/use_second_wind.py`
- Create: `tools/services/class_features/fighter/__init__.py`
- Test: `test/test_use_second_wind.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_use_second_wind_heals_and_consumes_bonus_action_and_use():
    result = UseSecondWind(repo, append_event).execute(
        encounter_id="enc_fighter_test",
        actor_id="ent_fighter_001",
        healing_roll={"rolls": [7]},
    )
    updated = repo.get("enc_fighter_test")
    assert updated.entities["ent_fighter_001"].hp["current"] == 20
    assert updated.entities["ent_fighter_001"].action_economy["bonus_action_used"] is True
    assert updated.entities["ent_fighter_001"].class_features["fighter"]["second_wind"]["remaining_uses"] == 1
```

And:

```python
def test_use_second_wind_returns_tactical_shift_movement_allowance():
    ...
    assert result["class_feature_result"]["free_movement_after_second_wind"]["ignore_opportunity_attacks"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_use_second_wind.py -v`
Expected: FAIL because service does not exist.

- [ ] **Step 3: Write minimal implementation**

Create service skeleton:

```python
class UseSecondWind:
    def execute(self, *, encounter_id: str, actor_id: str, healing_roll: dict[str, Any] | None = None) -> dict[str, Any]:
        encounter = self.repository.get(encounter_id)
        actor = encounter.entities[actor_id]
        fighter = get_fighter_runtime(actor)
        ...
        heal_amount = sum(rolls) + fighter["fighter_level"]
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_use_second_wind.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/fighter/__init__.py tools/services/class_features/fighter/use_second_wind.py test/test_use_second_wind.py
git commit -m "feat: add second wind service"
```

### Task 5: Add Tactical Shift movement hook

**Files:**
- Modify: `tools/services/encounter/begin_move_encounter_entity.py`
- Modify: `tools/services/encounter/move_encounter_entity.py`
- Test: `test/test_begin_move_encounter_entity.py`
- Test: `test/test_move_encounter_entity.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_begin_move_ignores_opportunity_attacks_for_tactical_shift_move():
    result = BeginMoveEncounterEntity(repo).execute(
        encounter_id="enc_fighter_test",
        entity_id="ent_fighter_001",
        target_position={"x": 6, "y": 6},
        ignore_opportunity_attacks_for_this_move=True,
    )
    assert result["status"] != "waiting_reaction"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_begin_move_encounter_entity.py -k tactical_shift -v`
Expected: FAIL because flag unsupported.

- [ ] **Step 3: Write minimal implementation**

Accept and thread a flag:

```python
if ignore_opportunity_attacks_for_this_move:
    candidate_reactors = []
```

And ensure the allowance is only honored for that move call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_begin_move_encounter_entity.py -k tactical_shift -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/begin_move_encounter_entity.py tools/services/encounter/move_encounter_entity.py test/test_begin_move_encounter_entity.py test/test_move_encounter_entity.py
git commit -m "feat: support tactical shift movement flag"
```

### Task 6: Implement `use_action_surge`

**Files:**
- Create: `tools/services/class_features/fighter/use_action_surge.py`
- Test: `test/test_use_action_surge.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_use_action_surge_grants_extra_non_magic_action():
    result = UseActionSurge(repo).execute(encounter_id="enc_fighter_test", actor_id="ent_fighter_001")
    updated = repo.get("enc_fighter_test")
    fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
    assert fighter["temporary_bonuses"]["extra_non_magic_action_available"] == 1
    assert fighter["action_surge"]["remaining_uses"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_use_action_surge.py -v`
Expected: FAIL because service does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
class UseActionSurge:
    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        ...
        fighter["temporary_bonuses"]["extra_non_magic_action_available"] += 1
        fighter["action_surge"]["used_this_turn"] = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_use_action_surge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/fighter/use_action_surge.py test/test_use_action_surge.py
git commit -m "feat: add action surge service"
```

### Task 7: Reset per-turn fighter counters at start turn

**Files:**
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Test: `test/test_turn_engine.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_start_turn_resets_fighter_turn_counters():
    updated = start_turn(encounter)
    fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
    assert fighter["turn_counters"]["attack_action_attacks_used"] == 0
    assert fighter["action_surge"]["used_this_turn"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_turn_engine.py -k fighter_turn_counters -v`
Expected: FAIL because counters are not reset.

- [ ] **Step 3: Write minimal implementation**

Reset fighter turn-local counters inside turn start:

```python
fighter["turn_counters"]["attack_action_attacks_used"] = 0
fighter["action_surge"]["used_this_turn"] = False
fighter["temporary_bonuses"]["extra_non_magic_action_available"] = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_turn_engine.py -k fighter_turn_counters -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/turns/turn_engine.py test/test_turn_engine.py
git commit -m "feat: reset fighter turn counters on turn start"
```

### Task 8: Implement Extra Attack sequence accounting

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_execute_attack_consumes_one_attack_from_attack_action_sequence():
    result = service.execute(...)
    updated = repo.get("enc_fighter_test")
    fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
    assert fighter["turn_counters"]["attack_action_attacks_used"] == 1
    assert updated.entities["ent_fighter_001"].action_economy["action_used"] is False
```

And:

```python
def test_execute_attack_marks_action_used_after_last_extra_attack_is_spent():
    ...
    assert updated.entities["ent_fighter_001"].action_economy["action_used"] is True
```

And:

```python
def test_resolve_extra_attack_count_takes_highest_source_only_in_attack_flow():
    ...
    assert fighter["turn_counters"]["attack_action_attacks_used"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_execute_attack.py -k extra_attack -v`
Expected: FAIL because attack still consumes full action immediately.

- [ ] **Step 3: Write minimal implementation**

Implement helper-driven counting:

```python
max_attacks = resolve_extra_attack_count(actor.class_features)
used = fighter["turn_counters"].get("attack_action_attacks_used", 0) + 1
fighter["turn_counters"]["attack_action_attacks_used"] = used
if used >= max_attacks:
    actor.action_economy["action_used"] = True
```

And make attack request skip “action already used” rejection while the same attack-action sequence still has remaining attacks.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_execute_attack.py -k extra_attack -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/execute_attack.py tools/services/combat/attack/attack_roll_request.py test/test_execute_attack.py
git commit -m "feat: support extra attack action sequences"
```

### Task 9: Implement Studied Attacks mark write and consumption

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_missed_attack_adds_studied_attacks_mark_for_target():
    result = service.execute(...)
    updated = repo.get("enc_fighter_test")
    marks = updated.entities["ent_fighter_001"].class_features["fighter"]["studied_attacks"]
    assert marks[0]["target_entity_id"] == "ent_enemy_001"
```

And:

```python
def test_next_attack_against_marked_target_gets_advantage_and_consumes_mark():
    request = attack_roll_request.execute(...)
    assert request.context["vantage"] == "advantage"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_execute_attack.py -k studied_attacks -v`
Expected: FAIL because no mark is written/read.

- [ ] **Step 3: Write minimal implementation**

On miss:

```python
if not resolution["hit"]:
    add_or_refresh_studied_attack_mark(actor.class_features, target_id)
```

On request build:

```python
if has_unconsumed_studied_attack_mark(actor.class_features, target_id):
    context["vantage"] = "advantage"
```

After attack resolves against that target, consume the mark.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_execute_attack.py -k studied_attacks -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py test/test_execute_attack.py
git commit -m "feat: add studied attacks runtime marks"
```

### Task 10: Implement Tactical Master mastery override

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/attack/weapon_mastery_effects.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_tactical_master_allows_push_override_on_valid_weapon_attack():
    result = service.execute(..., mastery_override="push")
    assert result["mastery_updates"][0]["mastery"] == "push"
```

And:

```python
def test_tactical_master_rejects_invalid_override_when_feature_missing():
    with pytest.raises(ValueError, match="invalid_mastery_override"):
        service.execute(..., mastery_override="push")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_execute_attack.py -k tactical_master -v`
Expected: FAIL because override unsupported.

- [ ] **Step 3: Write minimal implementation**

Add optional param handling:

```python
if mastery_override is not None:
    validate_tactical_master_override(actor, request.context, mastery_override)
```

And thread override into mastery effect resolution.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_execute_attack.py -k tactical_master -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/execute_attack.py tools/services/combat/attack/weapon_mastery_effects.py test/test_execute_attack.py
git commit -m "feat: add tactical master mastery override"
```

### Task 11: Add failed-save reaction window for Indomitable

**Files:**
- Create: `tools/services/combat/rules/reactions/definitions/indomitable.py`
- Modify: `tools/services/combat/rules/reactions/reaction_definitions.py`
- Modify: `tools/services/combat/rules/reactions/collect_reaction_candidates.py`
- Modify: `tools/services/combat/rules/reactions/open_reaction_window.py`
- Modify: `tools/services/combat/rules/reactions/resolve_reaction_option.py`
- Test: `test/test_indomitable_reaction_window.py`
- Test: `test/test_resolve_reaction_option.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_failed_save_opens_indomitable_window_for_fighter():
    window = open_reaction_window.execute(...)
    assert window["status"] == "waiting_reaction"
    assert window["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"] == "indomitable"
```

And:

```python
def test_resolve_indomitable_rerolls_save_and_adds_fighter_level():
    result = resolve_reaction_option.execute(...)
    assert result["reaction_result"]["status"] == "rerolled"
    assert result["reaction_result"]["save"]["fighter_level_bonus"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_indomitable_reaction_window.py test/test_resolve_reaction_option.py -k indomitable -v`
Expected: FAIL because definition/service does not exist.

- [ ] **Step 3: Write minimal implementation**

Resolver shape:

```python
class ResolveIndomitableReaction:
    def execute(...):
        base_roll = random.randint(1, 20)
        final_total = base_roll + original_save_modifier + fighter_level
        ...
```

Use `resolution_mode = "rewrite_host_action"` only if save host flow is resumable; otherwise return a dedicated save rewrite result and keep it self-contained.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_indomitable_reaction_window.py test/test_resolve_reaction_option.py -k indomitable -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/rules/reactions/definitions/indomitable.py tools/services/combat/rules/reactions/reaction_definitions.py tools/services/combat/rules/reactions/collect_reaction_candidates.py tools/services/combat/rules/reactions/open_reaction_window.py tools/services/combat/rules/reactions/resolve_reaction_option.py test/test_indomitable_reaction_window.py test/test_resolve_reaction_option.py
git commit -m "feat: add indomitable failed-save reaction flow"
```

### Task 12: Project class feature state through `get_encounter_state`

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing test**

Add:

```python
def test_get_encounter_state_includes_fighter_runtime_resources():
    state = GetEncounterState(repo).execute("enc_fighter_test")
    assert state["current_turn_entity"]["resources"]["class_features"]["fighter"]["second_wind"]["remaining_uses"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k fighter_runtime_resources -v`
Expected: FAIL because projection absent.

- [ ] **Step 3: Write minimal implementation**

Project only runtime-useful details:

```python
"class_features": {
    "fighter": {
        "second_wind": fighter.get("second_wind"),
        "action_surge": fighter.get("action_surge"),
        "indomitable": fighter.get("indomitable"),
        "extra_attack_count": fighter.get("extra_attack_count"),
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_get_encounter_state.py -k fighter_runtime_resources -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: project class feature runtime state in encounter view"
```

### Task 13: Add tool-guide documentation for fighter class features

**Files:**
- Modify: `docs/llm-runtime-tool-guide.md`

- [ ] **Step 1: Write the documentation update**

Add a short section covering:

```md
## Fighter Class Feature Runtime

- `use_second_wind(...)` heals and may grant `free_movement_after_second_wind`
- `use_action_surge(...)` grants one extra non-magic action this turn
- `Extra Attack` is automatic and never stacks across classes; runtime takes the highest attack count only
- `Indomitable` appears as a failed-save reaction window, not a normal action
- `Tactical Master` is passed through attack requests as `mastery_override`
```

- [ ] **Step 2: Verify docs diff**

Run: `git diff -- docs/llm-runtime-tool-guide.md`
Expected: Shows only the new section.

- [ ] **Step 3: Commit**

```bash
git add docs/llm-runtime-tool-guide.md
git commit -m "docs: add fighter class feature runtime guide"
```

### Task 14: Run final focused regression suite

**Files:**
- No new files

- [ ] **Step 1: Run class feature unit tests**

Run:

```bash
python3 -m pytest -q \
  test/test_class_feature_definition_repository.py \
  test/test_class_feature_runtime_helpers.py \
  test/test_use_second_wind.py \
  test/test_use_action_surge.py \
  test/test_indomitable_reaction_window.py
```

Expected: All pass.

- [ ] **Step 2: Run attack/save/turn regressions**

Run:

```bash
python3 -m pytest -q \
  test/test_execute_attack.py \
  test/test_resolve_reaction_option.py \
  test/test_get_encounter_state.py \
  test/test_turn_engine.py
```

Expected: All pass.

- [ ] **Step 3: Run spell/reaction regression to catch cross-feature breakage**

Run:

```bash
python3 -m unittest \
  test.test_attack_reaction_window \
  test.test_spell_reaction_window \
  test.test_start_turn -v
```

Expected: OK with 0 failures.

- [ ] **Step 4: Commit final integration state**

```bash
git add .
git commit -m "feat: add fighter combat class feature framework"
```

---

## Self-Review

### Spec coverage

- `class_features` runtime state: Task 1
- static knowledge definitions: Task 2
- reusable helper layer: Task 3
- `Second Wind`: Task 4
- `Tactical Shift`: Task 5
- `Action Surge`: Task 6
- turn-local resets: Task 7
- `Extra Attack` highest-only non-stacking rule: Tasks 3 and 8
- `Studied Attacks`: Task 9
- `Tactical Master`: Task 10
- `Indomitable`: Task 11
- runtime projection for LLM/frontend: Task 12
- usage docs: Task 13
- regression evidence: Task 14

### Placeholder scan

- No `TODO` / `TBD`
- Every code-changing task includes a concrete test, command, and implementation sketch

### Type consistency

- Runtime state key is consistently `class_features`
- Fighter subtree is consistently `class_features["fighter"]`
- Extra attack count is consistently `extra_attack_count`
- Non-stacking rule is consistently “take highest only”

