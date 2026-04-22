# Spellcasting Entity Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将施法相关角色构筑统一到 `EncounterEntity.class_features.<class>` 的标准字段，并在实体初始化时自动迁移旧数据。

**Architecture:** 在模型层增加一个轻量标准化步骤，负责推断主职业、补 class bucket、统一 `prepared_spells` / `always_prepared_spells` / `spell_preparation_mode`。运行时 helper 和施法访问服务统一消费这套 schema，不再各自推断旧结构。

**Tech Stack:** Python dataclasses, unittest, pytest

---

### Task 1: 模型层标准化入口

**Files:**
- Create: `tools/models/entity_class_schema.py`
- Modify: `tools/models/encounter_entity.py`
- Modify: `app/models/encounter_entity.py`
- Test: `test/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
def test_encounter_entity_from_dict_normalizes_spellcasting_class_bucket(self) -> None:
    legacy = build_entity().to_dict()
    legacy["initial_class_name"] = None
    legacy["source_ref"]["class_name"] = "bard"
    legacy["source_ref"]["level"] = 7
    legacy["class_features"] = {}
    legacy["spells"] = [
        {"spell_id": "healing_word", "name": "Healing Word", "level": 1, "casting_class": "bard"},
        {"spell_id": "light", "name": "Light", "level": 0, "casting_class": "bard"},
    ]

    entity = EncounterEntity.from_dict(legacy)

    self.assertEqual(entity.class_features["bard"]["level"], 7)
    self.assertEqual(entity.class_features["bard"]["spell_preparation_mode"], "level_up_one")
    self.assertEqual(entity.class_features["bard"]["prepared_spells"], ["healing_word"])
    self.assertEqual(entity.class_features["bard"]["always_prepared_spells"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_models.py::EncounterModelTests::test_encounter_entity_from_dict_normalizes_spellcasting_class_bucket`
Expected: FAIL because spellcasting bucket is not normalized

- [ ] **Step 3: Write minimal implementation**

```python
def normalize_entity_class_features(...):
    primary_class = resolve_primary_class_name(...)
    bucket = ensure_bucket(...)
    bucket["spell_preparation_mode"] = ...
    bucket["prepared_spells"] = ...
    bucket["always_prepared_spells"] = ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_models.py::EncounterModelTests::test_encounter_entity_from_dict_normalizes_spellcasting_class_bucket`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_models.py tools/models/entity_class_schema.py tools/models/encounter_entity.py app/models/encounter_entity.py
git commit -m "feat: normalize spellcasting entity schema"
```

### Task 2: 运行时 helper 与施法访问统一消费标准字段

**Files:**
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/spells/resolve_spellcasting_access.py`
- Test: `test/test_class_feature_runtime_helpers.py`
- Test: `test/test_resolve_spellcasting_access.py`

- [ ] **Step 1: Write the failing test**

```python
def test_ensure_bard_runtime_sets_standard_spellcasting_fields(self) -> None:
    entity = EncounterEntity(...)
    entity.class_features = {"bard": {"level": 20}}

    bard = ensure_bard_runtime(entity)

    self.assertEqual(bard["spell_preparation_mode"], "level_up_one")
    self.assertEqual(bard["always_prepared_spells"], ["power_word_heal", "power_word_kill"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q test/test_class_feature_runtime_helpers.py::ClassFeatureRuntimeHelperTests::test_ensure_bard_runtime_sets_standard_spellcasting_fields`
Expected: FAIL because runtime helper does not populate the standardized fields

- [ ] **Step 3: Write minimal implementation**

```python
def ensure_bard_runtime(...):
    bard["spell_preparation_mode"] = "level_up_one"
    bard["always_prepared_spells"] = [...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q test/test_class_feature_runtime_helpers.py::ClassFeatureRuntimeHelperTests::test_ensure_bard_runtime_sets_standard_spellcasting_fields`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_class_feature_runtime_helpers.py test/test_resolve_spellcasting_access.py tools/services/class_features/shared/runtime.py tools/services/spells/resolve_spellcasting_access.py
git commit -m "feat: standardize spellcasting runtime fields"
```

### Task 3: 回归验证

**Files:**
- Test: `test/test_models.py`
- Test: `test/test_class_feature_runtime_helpers.py`
- Test: `test/test_resolve_spellcasting_access.py`
- Test: `test/test_spell_request.py`
- Test: `test/test_encounter_cast_spell.py`
- Test: `test/test_execute_spell.py`

- [ ] **Step 1: Run focused regression**

Run: `python3 -m pytest -q test/test_models.py test/test_class_feature_runtime_helpers.py test/test_resolve_spellcasting_access.py test/test_spell_request.py test/test_encounter_cast_spell.py test/test_execute_spell.py`
Expected: PASS

- [ ] **Step 2: Commit**

```bash
git add test/test_models.py test/test_class_feature_runtime_helpers.py test/test_resolve_spellcasting_access.py test/test_spell_request.py test/test_encounter_cast_spell.py test/test_execute_spell.py
git commit -m "test: cover spellcasting entity schema unification"
```
