# Martial Class Feature Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展武力系职业特性模板骨架，把武力系职业统一纳入知识库与 runtime，并让 `rogue.sneak_attack`、`monk.martial_arts` / `flurry_of_blows`、`monk.stunning_strike` 成为最小真实可结算能力。

**Architecture:** 继续沿用现有 `class_feature_definitions` 和 `entity.class_features` 双层结构。知识库只保存职业能力模板，runtime 只保存当前战斗中会变化的次数、资源和标记；攻击链通过一个统一的 `class_feature_options` 入参接住主动宣告型能力，并在命中后应用伤害段或豁免控制效果。

**Tech Stack:** Python 3、unittest、TinyDB、现有 `tools.services` / `tools.repositories` / `GetEncounterState` / `ExecuteAttack` 结构

---

## File Map

### Knowledge Layer

- Modify: `data/knowledge/class_feature_definitions.json`
  - 新增 barbarian / monk / paladin / ranger / rogue 的战斗内特性模板。
- Modify: `tools/repositories/class_feature_definition_repository.py`
  - 无大逻辑变化，主要复用现有仓库读取。
- Test: `test/test_class_feature_definition_repository.py`
  - 增加新职业模板读取断言。

### Shared Runtime Helpers

- Modify: `tools/services/class_features/shared/runtime.py`
  - 从 fighter-only helper 扩成通用职业 bucket helper。
- Modify: `tools/services/class_features/shared/__init__.py`
  - 导出通用 helper。
- Create: `tools/services/class_features/shared/martial_feature_options.py`
  - 统一解析 `class_feature_options`。
- Test: `test/test_class_feature_runtime_helpers.py`
  - 增加 monk / rogue runtime helper 与 options 解析测试。

### Encounter State Projection

- Modify: `tools/services/encounter/get_encounter_state.py`
  - 给 monk / rogue / paladin / barbarian / ranger 增加职业资源摘要。
- Test: `test/test_get_encounter_state.py`
  - 新增 martial class summary projection 测试。

### Rogue Sneak Attack

- Modify: `tools/services/combat/attack/attack_roll_request.py`
  - 校验 Sneak Attack 是否可声明、是否满足武器资格。
- Modify: `tools/services/combat/attack/execute_attack.py`
  - 命中后应用一次偷袭附伤并写入 turn flag。
- Modify: `tools/services/encounter/turns/turn_engine.py`
  - 在回合开始时刷新 `sneak_attack.used_this_turn`。
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_turn_engine.py`

### Monk Martial Arts / Flurry Of Blows

- Modify: `tools/services/combat/attack/weapon_profile_resolver.py`
  - 支持 `unarmed_strike` 虚拟武器解析。
- Modify: `tools/services/combat/attack/attack_roll_request.py`
  - 支持 `attack_mode="martial_arts_bonus"` / `attack_mode="flurry_of_blows"`。
- Modify: `tools/services/combat/attack/execute_attack.py`
  - 对应扣附赠动作 / 功力 / 返回结构化额外攻击信息。
- Modify: `tools/services/encounter/get_encounter_state.py`
  - 暴露 monk 可用能力与功力摘要。
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_get_encounter_state.py`

### Monk Stunning Strike

- Modify: `tools/services/combat/attack/execute_attack.py`
  - 命中后可选结算震慑拳。
- Modify: `tools/services/encounter/turns/turn_effects.py`
  - 复用 turn effect / condition 更新支持“成功减速 + 下一次攻击优势”。
- Test: `test/test_execute_attack.py`

### Documentation / Plan Verification

- Modify: `docs/superpowers/specs/2026-04-17-martial-class-feature-templates-design.md`
  - 如实现中需要微调命名，再同步修正。

---

### Task 1: Expand Martial Class Feature Templates In Knowledge Layer

**Files:**
- Modify: `data/knowledge/class_feature_definitions.json`
- Test: `test/test_class_feature_definition_repository.py`

- [ ] **Step 1: Write the failing tests**

Add repository tests like:

```python
def test_get_returns_rogue_sneak_attack_definition(self) -> None:
    repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))
    feature = repo.get("rogue.sneak_attack")
    self.assertIsNotNone(feature)
    self.assertEqual(feature["template_type"], "damage_rider_once_per_turn")
    self.assertEqual(feature["activation"], "passive")


def test_get_returns_monk_stunning_strike_definition(self) -> None:
    repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))
    feature = repo.get("monk.stunning_strike")
    self.assertIsNotNone(feature)
    self.assertEqual(feature["template_type"], "save_on_hit_control")
    self.assertEqual(feature["resource_model"]["cost"], {"focus_points": 1})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_class_feature_definition_repository
```

Expected: FAIL because the new feature IDs do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Extend `class_feature_definitions.json` with entries for:

```json
"rogue.sneak_attack": {
  "id": "rogue.sneak_attack",
  "name": "Sneak Attack",
  "class_id": "rogue",
  "level_required": 1,
  "template_type": "damage_rider_once_per_turn",
  "activation": "passive",
  "resource_model": {"recharge": "turn_start"},
  "trigger": {"type": "on_attack_hit"},
  "targeting": {"type": "attack_target"},
  "effect_summary": "Add extra damage once per turn on a qualifying hit.",
  "runtime_support": {"in_encounter": "template_only", "out_of_encounter": "none"}
}
```

```json
"monk.martial_arts": {
  "id": "monk.martial_arts",
  "name": "Martial Arts",
  "class_id": "monk",
  "level_required": 1,
  "template_type": "bonus_attack_grant",
  "activation": "bonus_action",
  "resource_model": {"recharge": "none"},
  "trigger": {"type": "after_attack_action"},
  "targeting": {"type": "self"},
  "effect_summary": "Make one bonus-action unarmed strike while unarmored and unshielded.",
  "runtime_support": {"in_encounter": "template_only", "out_of_encounter": "none"}
}
```

Also add:

- `monk.flurry_of_blows`
- `monk.stunning_strike`
- `monk.patient_defense`
- `monk.step_of_the_wind`
- `monk.deflect_attacks`
- `monk.empowered_strikes`
- `barbarian.rage`
- `paladin.divine_smite`
- `ranger.weapon_mastery_stub`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_class_feature_definition_repository
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/knowledge/class_feature_definitions.json test/test_class_feature_definition_repository.py
git commit -m "feat: add martial class feature templates"
```

### Task 2: Generalize Class Feature Runtime Helpers

**Files:**
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Create: `tools/services/class_features/shared/martial_feature_options.py`
- Test: `test/test_class_feature_runtime_helpers.py`

- [ ] **Step 1: Write the failing tests**

Add helper tests like:

```python
def test_ensure_class_runtime_writes_bucket_under_class_features(self) -> None:
    entity = type("FakeEntity", (), {"class_features": {}})()
    monk = ensure_class_runtime(entity, "monk")
    monk["focus_points"] = {"max": 5, "remaining": 5}
    self.assertEqual(entity.class_features["monk"]["focus_points"]["remaining"], 5)


def test_parse_class_feature_options_normalizes_known_flags(self) -> None:
    options = normalize_class_feature_options(
        {"sneak_attack": True, "stunning_strike": {"enabled": True}}
    )
    self.assertTrue(options["sneak_attack"])
    self.assertTrue(options["stunning_strike"]["enabled"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_class_feature_runtime_helpers
```

Expected: FAIL because `ensure_class_runtime` / `normalize_class_feature_options` do not exist.

- [ ] **Step 3: Write minimal implementation**

In `runtime.py`, add generic helpers:

```python
def get_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _read_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    return bucket if isinstance(bucket, dict) else {}


def ensure_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _ensure_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    if isinstance(bucket, dict):
        return bucket
    class_features[class_id] = {}
    return class_features[class_id]
```

In `martial_feature_options.py`, add:

```python
def normalize_class_feature_options(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip().lower()
        normalized[normalized_key] = value
    return normalized
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_class_feature_runtime_helpers
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/shared/runtime.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/martial_feature_options.py test/test_class_feature_runtime_helpers.py
git commit -m "refactor: generalize class feature runtime helpers"
```

### Task 3: Project Martial Class Resource Summaries To Encounter State

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

Add projection tests like:

```python
def test_execute_projects_monk_class_feature_summary(self) -> None:
    current.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 4},
        "martial_arts_die": "1d8",
        "unarmored_movement_bonus_feet": 10,
    }
    state = GetEncounterState(repo, event_repo).execute("enc_view_test")
    monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]
    self.assertEqual(monk["focus_points"]["remaining"], 4)
    self.assertIn("stunning_strike", monk["available_features"])
```

```python
def test_execute_projects_rogue_sneak_attack_summary(self) -> None:
    current.class_features["rogue"] = {
        "level": 5,
        "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False},
    }
    state = GetEncounterState(repo, event_repo).execute("enc_view_test")
    rogue = state["current_turn_entity"]["resources"]["class_features"]["rogue"]
    self.assertEqual(rogue["sneak_attack"]["damage_dice"], "3d6")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_get_encounter_state
```

Expected: FAIL because monk / rogue class feature summaries are not projected.

- [ ] **Step 3: Write minimal implementation**

Extend `_build_resources_view()` or the current class-feature projection path with summaries like:

```python
"monk": {
    "level": monk.get("level"),
    "focus_points": monk.get("focus_points"),
    "martial_arts_die": monk.get("martial_arts_die"),
    "unarmored_movement_bonus_feet": monk.get("unarmored_movement_bonus_feet"),
    "available_features": [
        "martial_arts",
        "flurry_of_blows",
        "patient_defense",
        "step_of_the_wind",
        "stunning_strike",
    ],
}
```

```python
"rogue": {
    "level": rogue.get("level"),
    "sneak_attack": rogue.get("sneak_attack"),
    "available_features": ["sneak_attack", "cunning_action"],
}
```

Also add minimal summaries for:

- `barbarian`
- `paladin`
- `ranger`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_get_encounter_state
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: project martial class feature summaries"
```

### Task 4: Implement Rogue Sneak Attack As A Once-Per-Turn Damage Rider

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_turn_engine.py`

- [ ] **Step 1: Write the failing tests**

Add request-level validation:

```python
def test_execute_rejects_sneak_attack_with_non_qualifying_weapon(self) -> None:
    actor.class_features["rogue"] = {"level": 5, "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False}}
    actor.weapons = [{"weapon_id": "glaive"}]
    with self.assertRaisesRegex(ValueError, "sneak_attack_requires_finesse_or_ranged_weapon"):
        AttackRollRequest(repo, weapon_definition_repository=weapon_repo).execute(
            encounter_id="enc_attack_request_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="glaive",
            class_feature_options={"sneak_attack": True},
        )
```

Add attack-flow success:

```python
def test_execute_applies_sneak_attack_damage_once_per_turn(self) -> None:
    actor.class_features["rogue"] = {"level": 5, "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False}}
    result = execute_attack.execute(
        encounter_id="enc_execute_attack_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=18,
        damage_rolls=[
            {"source": "weapon_primary", "rolls": [5]},
            {"source": "rogue_sneak_attack", "rolls": [3, 4, 5]},
        ],
        class_feature_options={"sneak_attack": True},
    )
    self.assertEqual(result["damage_resolution"]["total_damage"], 20)
    self.assertTrue(updated.entities[actor.entity_id].class_features["rogue"]["sneak_attack"]["used_this_turn"])
```

Add turn reset:

```python
def test_start_turn_resets_rogue_sneak_attack_flag(self) -> None:
    entity.class_features["rogue"] = {"sneak_attack": {"damage_dice": "3d6", "used_this_turn": True}}
    reset_turn_resources(entity)
    self.assertFalse(entity.class_features["rogue"]["sneak_attack"]["used_this_turn"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_attack_roll_request test.test_execute_attack test.test_turn_engine
```

Expected: FAIL because `class_feature_options` is unsupported and sneak-attack damage source is unknown.

- [ ] **Step 3: Write minimal implementation**

In `AttackRollRequest.execute(...)`, add:

```python
class_feature_options = normalize_class_feature_options(class_feature_options)
if class_feature_options.get("sneak_attack"):
    if not self._weapon_qualifies_for_sneak_attack(request_weapon):
        raise ValueError("sneak_attack_requires_finesse_or_ranged_weapon")
    request_context["class_feature_options"]["sneak_attack"] = True
```

In `ExecuteAttack.execute(...)`, after hit confirmation and before damage resolution:

```python
rogue = get_class_runtime(actor, "rogue")
sneak_attack = rogue.get("sneak_attack")
if request.context.get("class_feature_options", {}).get("sneak_attack"):
    if isinstance(sneak_attack, dict) and not bool(sneak_attack.get("used_this_turn")):
        damage_parts.append(
            {
                "source": "rogue_sneak_attack",
                "formula": str(sneak_attack["damage_dice"]),
                "type": request.context.get("damage_type", "piercing"),
            }
        )
        sneak_attack["used_this_turn"] = True
```

In `turn_engine.reset_turn_resources(...)`, add:

```python
rogue = class_features.get("rogue")
if isinstance(rogue, dict):
    sneak_attack = rogue.get("sneak_attack")
    if isinstance(sneak_attack, dict):
        sneak_attack["used_this_turn"] = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_attack_roll_request test.test_execute_attack test.test_turn_engine
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py tools/services/encounter/turns/turn_engine.py test/test_attack_roll_request.py test/test_execute_attack.py test/test_turn_engine.py
git commit -m "feat: add rogue sneak attack damage rider"
```

### Task 5: Implement Monk Martial Arts Bonus Attack And Flurry Of Blows

**Files:**
- Modify: `tools/services/combat/attack/weapon_profile_resolver.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing tests**

Add request-level tests:

```python
def test_execute_allows_martial_arts_bonus_unarmed_attack(self) -> None:
    actor.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 5},
        "martial_arts_die": "1d8",
    }
    request = AttackRollRequest(repo).execute(
        encounter_id="enc_attack_request_test",
        target_id="ent_enemy_goblin_001",
        weapon_id="unarmed_strike",
        attack_mode="martial_arts_bonus",
    )
    self.assertEqual(request.context["attack_kind"], "melee_weapon")
    self.assertEqual(request.context["damage_formula"], "1d8+3")
```

```python
def test_execute_rejects_flurry_of_blows_when_no_focus_points(self) -> None:
    actor.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 0},
        "martial_arts_die": "1d8",
    }
    with self.assertRaisesRegex(ValueError, "flurry_of_blows_requires_focus_points"):
        AttackRollRequest(repo).execute(
            encounter_id="enc_attack_request_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="unarmed_strike",
            attack_mode="flurry_of_blows",
        )
```

Add attack-flow tests:

```python
def test_execute_flurry_of_blows_spends_focus_and_bonus_action(self) -> None:
    actor.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 5},
        "martial_arts_die": "1d8",
    }
    result = execute_attack.execute(
        encounter_id="enc_execute_attack_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        weapon_id="unarmed_strike",
        attack_mode="flurry_of_blows",
        final_total=18,
        damage_rolls=[{"source": "weapon_primary", "rolls": [6]}],
    )
    self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["focus_points"]["remaining"], 4)
    self.assertTrue(updated.entities[actor.entity_id].action_economy["bonus_action_used"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_attack_roll_request test.test_execute_attack
```

Expected: FAIL because `unarmed_strike` and monk attack modes are unsupported.

- [ ] **Step 3: Write minimal implementation**

In `weapon_profile_resolver.py`, add a virtual weapon path:

```python
if weapon_id == "unarmed_strike":
    return {
        "weapon_id": "unarmed_strike",
        "name": "Unarmed Strike",
        "category": "simple",
        "kind": "melee",
        "properties": [],
        "is_proficient": True,
        "damage": [{"formula": self._resolve_monk_unarmed_formula(actor), "type": "bludgeoning"}],
        "range": {"normal": 5, "long": 5},
        "hands": {"mode": "one_handed"},
    }
```

In `AttackRollRequest.execute(...)`, add monk mode checks:

```python
if attack_mode == "martial_arts_bonus":
    self._ensure_bonus_action_available(actor)
    self._ensure_actor_has_monk_martial_arts(actor)

if attack_mode == "flurry_of_blows":
    self._ensure_bonus_action_available(actor)
    self._ensure_actor_has_focus_points(actor, 1)
```

In `ExecuteAttack.execute(...)`, consume resources:

```python
if normalized_attack_mode == "martial_arts_bonus":
    actor.action_economy["bonus_action_used"] = True

if normalized_attack_mode == "flurry_of_blows":
    actor.action_economy["bonus_action_used"] = True
    monk["focus_points"]["remaining"] -= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_attack_roll_request test.test_execute_attack
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/weapon_profile_resolver.py tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py test/test_attack_roll_request.py test/test_execute_attack.py
git commit -m "feat: add monk martial arts and flurry attacks"
```

### Task 6: Implement Monk Stunning Strike As A Hit-Follow Control Option

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Test: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_execute_stunning_strike_applies_stunned_on_failed_save(self) -> None:
    actor.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 5},
        "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1},
    }
    result = execute_attack.execute(
        encounter_id="enc_execute_attack_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        weapon_id="unarmed_strike",
        final_total=18,
        damage_rolls=[{"source": "weapon_primary", "rolls": [6]}],
        class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 7}},
    )
    self.assertIn("stunned", updated.entities[target.entity_id].conditions)
    self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["focus_points"]["remaining"], 4)
```

```python
def test_execute_stunning_strike_success_applies_speed_half_and_next_attack_advantage_mark(self) -> None:
    actor.class_features["monk"] = {
        "level": 5,
        "focus_points": {"max": 5, "remaining": 5},
        "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1},
    }
    result = execute_attack.execute(
        encounter_id="enc_execute_attack_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        weapon_id="unarmed_strike",
        final_total=18,
        damage_rolls=[{"source": "weapon_primary", "rolls": [6]}],
        class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 18}},
    )
    self.assertTrue(any(effect.get("effect_id") == "monk_stunning_strike_slow" for effect in updated.entities[target.entity_id].turn_effects))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest -v test.test_execute_attack
```

Expected: FAIL because `stunning_strike` option is ignored.

- [ ] **Step 3: Write minimal implementation**

After hit resolution in `execute_attack.py`, add:

```python
stunning_option = request.context.get("class_feature_options", {}).get("stunning_strike")
if resolution["hit"] and isinstance(stunning_option, dict) and stunning_option.get("enabled"):
    monk = get_class_runtime(actor, "monk")
    monk["focus_points"]["remaining"] -= 1
    monk["stunning_strike"]["uses_this_turn"] += 1
    save_total = self._roll_or_resolve_stunning_strike_save(...)
    if save_total < save_dc:
        if "stunned" not in target.conditions:
            target.conditions.append("stunned")
    else:
        target.turn_effects.append(
            {
                "effect_id": "monk_stunning_strike_slow",
                "name": "Stunning Strike Slow",
                "trigger": "start_of_turn",
                "remove_after_trigger": True,
                "effect_type": "speed_modifier",
                "speed_multiplier": 0.5,
            }
        )
```

Also set a request / resolution metadata block so the runtime result clearly says whether `stunning_strike` was applied and whether the target failed or succeeded.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest -v test.test_execute_attack
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/execute_attack.py test/test_execute_attack.py
git commit -m "feat: add monk stunning strike on-hit control"
```

### Task 7: Final Regression And State Projection Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run focused martial regressions**

Run:

```bash
python3 -m unittest -v \
  test.test_class_feature_definition_repository \
  test.test_class_feature_runtime_helpers \
  test.test_get_encounter_state \
  test.test_attack_roll_request \
  test.test_execute_attack \
  test.test_turn_engine
```

Expected: PASS

- [ ] **Step 2: Run full regression**

Run:

```bash
python3 -m unittest discover -s test -v
```

Expected: PASS

- [ ] **Step 3: Check worktree**

Run:

```bash
git status --short
```

Expected: only the planned martial template / runtime / combat files are modified.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: add martial class feature templates and runtime hooks"
```
