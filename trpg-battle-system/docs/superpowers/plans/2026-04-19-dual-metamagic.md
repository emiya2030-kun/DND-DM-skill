# Dual Metamagic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full 2024 dual-metamagic rules for Sorcerer spells, including known metamagic tracking, `Empowered` / `Seeking` combo exceptions, and `Sorcery Incarnate`-gated two-metamagic casting.

**Architecture:** Extend Sorcerer runtime to carry known metamagic metadata, move metamagic parsing and combo validation into a shared helper, then make `SpellRequest` and `EncounterCastSpell` consume the same structured result. Keep downstream attack/save/damage chains consuming the existing boolean metamagic flags so the change is additive rather than a wholesale rewrite.

**Tech Stack:** Python 3, `unittest`, existing `EncounterRepository` / `EventRepository`, Sorcerer runtime helpers, spell request/cast/save pipelines.

---

### Task 1: Extend Sorcerer Runtime With Known Metamagic State

**Files:**
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_class_feature_runtime_helpers.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing runtime test**

```python
def test_ensure_sorcerer_runtime_initializes_metamagic_state(self) -> None:
    entity = EncounterEntity(
        entity_id="ent_sorcerer_001",
        name="Sorcerer",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        class_features={"sorcerer": {"level": 10}},
    )

    runtime = ensure_sorcerer_runtime(entity)

    self.assertEqual(runtime["metamagic"]["max_known_options"], 4)
    self.assertEqual(runtime["metamagic"]["known_options"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_class_feature_runtime_helpers.ClassFeatureRuntimeHelpersTests.test_ensure_sorcerer_runtime_initializes_metamagic_state -v`
Expected: FAIL because `metamagic` is missing from sorcerer runtime.

- [ ] **Step 3: Add minimal runtime support**

```python
metamagic = sorcerer.setdefault("metamagic", {})
metamagic["max_known_options"] = _resolve_sorcerer_metamagic_known_count(level)
raw_known = metamagic.get("known_options")
if isinstance(raw_known, list):
    normalized_known = []
    for item in raw_known:
        normalized = str(item).strip().lower()
        if normalized and normalized in SUPPORTED_METAMAGIC_OPTIONS and normalized not in normalized_known:
            normalized_known.append(normalized)
    metamagic["known_options"] = normalized_known[: metamagic["max_known_options"]]
else:
    metamagic["known_options"] = []
```

- [ ] **Step 4: Add encounter-state projection test**

```python
def test_execute_projects_sorcerer_metamagic_summary(self) -> None:
    encounter = build_encounter()
    entity = encounter.entities["ent_ally_eric_001"]
    entity.class_features["sorcerer"] = {
        "level": 10,
        "metamagic": {
            "known_options": ["quickened_spell", "heightened_spell", "subtle_spell"],
        },
    }
    self.encounter_repository.save(encounter)

    state = GetEncounterState(self.encounter_repository, self.event_repository).execute("enc_get_state_test")
    sorcerer = state["current_turn_entity"]["resources"]["class_features"]["sorcerer"]

    self.assertEqual(sorcerer["metamagic"]["max_known_options"], 4)
    self.assertEqual(
        sorcerer["metamagic"]["known_options"],
        ["quickened_spell", "heightened_spell", "subtle_spell"],
    )
```

- [ ] **Step 5: Run focused tests and make them pass**

Run: `python3 -m unittest test.test_class_feature_runtime_helpers test.test_get_encounter_state -v`
Expected: PASS for the new Sorcerer metamagic runtime assertions.

- [ ] **Step 6: Commit**

```bash
git add tools/services/class_features/shared/runtime.py tools/services/encounter/get_encounter_state.py test/test_class_feature_runtime_helpers.py test/test_get_encounter_state.py
git commit -m "feat: add sorcerer metamagic runtime state"
```

### Task 2: Add Shared Dual-Metamagic Parsing And Validation

**Files:**
- Modify: `tools/services/spells/metamagic_support.py`
- Test: `test/test_spell_request.py`

- [ ] **Step 1: Write the failing declaration tests**

```python
def test_execute_allows_empowered_plus_heightened_without_innate_sorcery(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={
            "selected": ["empowered_spell", "heightened_spell"],
            "heightened_target_id": "ent_target_humanoid_001",
        },
    )
    self.assertTrue(result["ok"])
    self.assertEqual(result["metamagic"]["selected"], ["empowered_spell", "heightened_spell"])
    self.assertEqual(result["metamagic"]["sorcery_point_cost"], 3)

def test_execute_rejects_quickened_plus_heightened_without_innate_sorcery(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={
            "selected": ["quickened_spell", "heightened_spell"],
            "heightened_target_id": "ent_target_humanoid_001",
        },
    )
    self.assertFalse(result["ok"])
    self.assertEqual(result["error_code"], "metamagic_combination_not_allowed")
```

- [ ] **Step 2: Run the declaration tests to verify they fail**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_allows_empowered_plus_heightened_without_innate_sorcery test.test_spell_request.SpellRequestTests.test_execute_rejects_quickened_plus_heightened_without_innate_sorcery -v`
Expected: FAIL because current parsing rejects any `selected` list longer than one item.

- [ ] **Step 3: Add shared metamagic helpers**

```python
SUPPORTED_METAMAGIC_OPTIONS = {
    "subtle_spell": 1,
    "quickened_spell": 2,
    "distant_spell": 1,
    "heightened_spell": 2,
    "careful_spell": 1,
    "empowered_spell": 1,
    "extended_spell": 1,
    "seeking_spell": 1,
    "transmuted_spell": 1,
    "twinned_spell": 1,
}

STACKABLE_METAMAGIC_OPTIONS = {"empowered_spell", "seeking_spell"}

def resolve_metamagic_selection(*, sorcerer: dict[str, Any], metamagic_options: dict[str, Any] | None, known_spell: dict[str, Any], spell_definition: dict[str, Any], action_cost: str | None, encounter_entities: dict[str, Any], target_entity_ids: list[str]) -> dict[str, Any]:
    normalized_selected = normalize_metamagic_selection(metamagic_options)
    validate_known_metamagic_options(sorcerer=sorcerer, normalized_selected=normalized_selected)
    validate_metamagic_combination(sorcerer=sorcerer, normalized_selected=normalized_selected)
    return build_metamagic_payload(...)
```

- [ ] **Step 4: Cover `Sorcery Incarnate` and known-option gating**

```python
def test_execute_allows_quickened_plus_heightened_with_active_innate_sorcery(self) -> None:
    caster.class_features["sorcerer"] = {
        "level": 7,
        "sorcery_points": {"max": 7, "current": 7},
        "innate_sorcery": {"active": True},
        "metamagic": {"known_options": ["quickened_spell", "heightened_spell"]},
    }
    ...
    self.assertTrue(result["ok"])

def test_execute_rejects_unlearned_metamagic(self) -> None:
    caster.class_features["sorcerer"] = {
        "level": 7,
        "sorcery_points": {"max": 7, "current": 7},
        "metamagic": {"known_options": ["subtle_spell", "quickened_spell"]},
    }
    ...
    self.assertEqual(result["error_code"], "metamagic_not_known")
```

- [ ] **Step 5: Run the focused declaration suite**

Run: `python3 -m unittest test.test_spell_request -v`
Expected: PASS including new multi-metamagic, known-option, and Sorcery Incarnate tests.

- [ ] **Step 6: Commit**

```bash
git add tools/services/spells/metamagic_support.py test/test_spell_request.py
git commit -m "feat: add dual metamagic validation helpers"
```

### Task 3: Make SpellRequest Consume Shared Dual-Metamagic Rules

**Files:**
- Modify: `tools/services/spells/spell_request.py`
- Test: `test/test_spell_request.py`

- [ ] **Step 1: Write the failing request-shape tests**

```python
def test_execute_returns_dual_metamagic_payload(self) -> None:
    result = service.execute(
        encounter_id="enc_spell_request_test",
        actor_id="ent_caster_001",
        spell_id="hold_person",
        cast_level=2,
        target_entity_ids=["ent_target_humanoid_001"],
        metamagic_options={
            "selected": ["empowered_spell", "heightened_spell"],
            "heightened_target_id": "ent_target_humanoid_001",
        },
    )
    self.assertEqual(result["metamagic"]["selected"], ["empowered_spell", "heightened_spell"])
    self.assertTrue(result["metamagic"]["empowered_spell"])
    self.assertTrue(result["metamagic"]["heightened_spell"])
    self.assertEqual(result["metamagic"]["sorcery_point_cost"], 3)
```

- [ ] **Step 2: Run the focused request test to verify it fails**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_returns_dual_metamagic_payload -v`
Expected: FAIL because `SpellRequest` still builds a single selected metamagic payload.

- [ ] **Step 3: Replace in-file parsing with the shared helper**

```python
metamagic_result = resolve_metamagic_selection(
    sorcerer=ensure_sorcerer_runtime(actor),
    metamagic_options=metamagic_options,
    known_spell=known_spell,
    spell_definition=spell_definition,
    action_cost=action_cost,
    encounter_entities=encounter.entities,
    target_entity_ids=target_entity_ids,
)
if not metamagic_result["ok"]:
    return metamagic_result

metamagic = metamagic_result["metamagic"]
noticeability = metamagic_result["noticeability"]
```

- [ ] **Step 4: Re-run the full SpellRequest suite**

Run: `python3 -m unittest test.test_spell_request -v`
Expected: PASS with dual-metamagic request output, updated error codes, and existing single-metamagic behavior unchanged.

- [ ] **Step 5: Commit**

```bash
git add tools/services/spells/spell_request.py test/test_spell_request.py
git commit -m "feat: support dual metamagic in spell requests"
```

### Task 4: Make EncounterCastSpell Apply Dual Metamagic Costs And Events

**Files:**
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Test: `test/test_encounter_cast_spell.py`

- [ ] **Step 1: Write the failing cast-execution tests**

```python
def test_execute_quickened_plus_heightened_consumes_total_sorcery_points(self) -> None:
    caster.class_features["sorcerer"] = {
        "level": 7,
        "sorcery_points": {"max": 7, "current": 7},
        "innate_sorcery": {"active": True},
        "metamagic": {"known_options": ["quickened_spell", "heightened_spell"]},
    }
    ...
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="hold_person",
        target_ids=["ent_enemy_iron_duster_001"],
        cast_level=2,
        metamagic_options={
            "selected": ["quickened_spell", "heightened_spell"],
            "heightened_target_id": "ent_enemy_iron_duster_001",
        },
    )
    self.assertEqual(result["metamagic"]["sorcery_point_cost"], 4)
    self.assertEqual(updated.entities["ent_ally_eric_001"].class_features["sorcerer"]["sorcery_points"]["current"], 3)
```

- [ ] **Step 2: Run the execution test to verify it fails**

Run: `python3 -m unittest test.test_encounter_cast_spell.EncounterCastSpellTests.test_execute_quickened_plus_heightened_consumes_total_sorcery_points -v`
Expected: FAIL because current cast parsing rejects multi-select input.

- [ ] **Step 3: Reuse the shared helper and keep rollback centralized**

```python
metamagic = resolve_metamagic_selection(
    sorcerer=ensure_sorcerer_runtime(caster),
    metamagic_options=metamagic_options,
    known_spell=known_spell,
    spell_definition=spell_definition,
    action_cost=action_cost,
    encounter_entities=encounter.entities,
    target_entity_ids=target_ids,
)["metamagic"]

sorcery_points_consumed = self._consume_sorcery_points_if_needed(caster=caster, metamagic=metamagic)
```

- [ ] **Step 4: Add rollback coverage for total-cost restore**

```python
def test_execute_restores_total_sorcery_points_when_dual_metamagic_event_append_fails(self) -> None:
    ...
    with patch.object(service.append_event, "execute", side_effect=RuntimeError("append_failed")):
        with self.assertRaisesRegex(RuntimeError, "append_failed"):
            service.execute(...)
    self.assertEqual(
        updated.entities["ent_ally_eric_001"].class_features["sorcerer"]["sorcery_points"]["current"],
        7,
    )
```

- [ ] **Step 5: Run the EncounterCastSpell suite**

Run: `python3 -m unittest test.test_encounter_cast_spell -v`
Expected: PASS with new multi-metamagic cost, rollback, action-economy, and event-payload assertions.

- [ ] **Step 6: Commit**

```bash
git add tools/services/spells/encounter_cast_spell.py test/test_encounter_cast_spell.py
git commit -m "feat: apply dual metamagic during spell casting"
```

### Task 5: Verify Downstream Attack/Save/Damage Chains And Finish Docs

**Files:**
- Modify: `test/test_execute_spell.py`
- Modify: `test/test_execute_save_spell.py`
- Modify: `test/test_saving_throw_request.py`
- Modify: `test/test_saving_throw_result.py`
- Modify: `docs/development-plan.md`
- Modify: `docs/llm-runtime-tool-guide.md`

- [ ] **Step 1: Write downstream dual-metamagic tests**

```python
def test_execute_seeking_plus_transmuted_spell_rerolls_and_rewrites_damage_type(self) -> None:
    result = ExecuteSpell(...).execute(
        encounter_id="enc_execute_spell_test",
        spell_id="chromatic_orb",
        target_ids=["ent_enemy_001"],
        cast_level=1,
        metamagic_options={
            "selected": ["seeking_spell", "transmuted_spell"],
            "transmuted_damage_type": "cold",
        },
    )
    self.assertTrue(result["attack_resolution"]["metamagic_adjustment"]["metamagic_id"], "seeking_spell")
    self.assertEqual(result["damage_resolution"]["metamagic_adjustment"]["replacement_damage_type"], "cold")

def test_execute_empowered_plus_heightened_spell_applies_disadvantage_and_damage_rerolls(self) -> None:
    result = ExecuteSaveSpell(...).execute(
        ...,
        metamagic_options={
            "selected": ["empowered_spell", "heightened_spell"],
            "heightened_target_id": "ent_target_humanoid_001",
        },
    )
    self.assertIn("metamagic_heightened_spell", result["request"]["context"]["vantage_sources"]["disadvantage"])
    self.assertEqual(result["resolution"]["damage_resolution"]["metamagic_adjustment"]["metamagic_id"], "empowered_spell")
```

- [ ] **Step 2: Run focused downstream tests and make them pass**

Run: `python3 -m unittest test.test_execute_spell test.test_execute_save_spell test.test_saving_throw_request test.test_saving_throw_result -v`
Expected: PASS, with existing single-metamagic tests still green and new dual-metamagic scenarios covered.

- [ ] **Step 3: Update runtime docs**

```markdown
- 默认每次施法只能应用一个超魔
- `empowered_spell` 与 `seeking_spell` 可作为例外与其他超魔共存
- 若 `innate_sorcery.active = true` 且术士等级至少 `7`, 一次施法最多可声明两个超魔
- 术士必须在 `class_features.sorcerer.metamagic.known_options` 中已学会对应选项
```

- [ ] **Step 4: Run full regression**

Run: `python3 -m unittest discover -s test -v`
Expected: PASS with no regressions.

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_spell.py test/test_execute_save_spell.py test/test_saving_throw_request.py test/test_saving_throw_result.py docs/development-plan.md docs/llm-runtime-tool-guide.md
git commit -m "feat: complete dual metamagic rule support"
```

### Plan Self-Review

- [ ] **Spec coverage check**

Verify each major spec section maps to a task:
- Known metamagic runtime: Task 1
- Shared parsing and combo validation: Task 2
- SpellRequest integration: Task 3
- EncounterCastSpell integration and rollback: Task 4
- Downstream chains and docs: Task 5

- [ ] **Placeholder scan**

Run: `rg -n "TBD|TODO|implement later|appropriate error handling|similar to Task" docs/superpowers/plans/2026-04-19-dual-metamagic.md`
Expected: no matches

- [ ] **Type consistency check**

Confirm names stay consistent across tasks:
- `known_options`
- `max_known_options`
- `selected`
- `sorcery_point_cost`
- `metamagic_combination_not_allowed`
- `metamagic_not_known`
- `too_many_metamagic_options`
