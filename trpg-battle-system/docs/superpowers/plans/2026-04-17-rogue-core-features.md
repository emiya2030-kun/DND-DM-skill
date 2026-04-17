# Rogue Core Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗系统接入盗贼的核心战斗特性，包括偷袭成长、专精、稳定瞄准、直觉闪避、可靠才能、圆滑心智、飘忽不定以及诡诈打击。

**Architecture:** 继续沿用 `entity.class_features["rogue"]` 作为唯一运行时事实源，把检定类能力挂到属性检定链，把攻击类能力挂到攻击请求 / 结算链，把反应类能力挂到 reaction framework。每个阶段都先写失败测试，再做最小实现，避免一次性把大量盗贼规则硬塞进单个大文件。

**Tech Stack:** Python 3.9, unittest, TinyDB, existing combat / reaction / encounter runtime services

---

### Task 1: 统一盗贼运行时骨架并让偷袭按等级自动成长

**Files:**
- Create: `tools/services/class_features/rogue/__init__.py`
- Create: `tools/services/class_features/rogue/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_rogue_runtime.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_turn_engine.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_ensure_rogue_runtime_refreshes_sneak_attack_damage_by_level(self) -> None:
    entity = EncounterEntity(
        entity_id="ent_rogue_001",
        name="Rogue",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"dex": 4},
        proficiency_bonus=3,
        class_features={"rogue": {"level": 7}},
    )
    runtime = ensure_rogue_runtime(entity)
    self.assertEqual(runtime["sneak_attack"]["damage_dice"], "4d6")
    self.assertFalse(runtime["sneak_attack"]["used_this_turn"])
```

```python
def test_execute_applies_sneak_attack_damage_from_rogue_level_without_manual_damage_dice(self) -> None:
    actor.class_features["rogue"] = {"level": 7}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=18,
        dice_rolls={"base_rolls": [13], "modifier": 5},
        damage_rolls=[
            {"source": "weapon:rapier:part_0", "rolls": [6]},
            {"source": "rogue_sneak_attack", "rolls": [1, 2, 3, 4]},
        ],
        class_feature_options={"sneak_attack": True},
    )
    self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["formula"], "4d6")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest test.test_rogue_runtime test.test_execute_attack test.test_turn_engine test.test_get_encounter_state -v
```

Expected: FAIL because rogue runtime helpers and auto-scaling sneak attack do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `tools/services/class_features/rogue/runtime.py` with helpers like:

```python
from __future__ import annotations

from tools.services.class_features.shared import ensure_class_runtime, get_class_runtime

_SNEAK_ATTACK_BY_LEVEL = {
    1: "1d6", 3: "2d6", 5: "3d6", 7: "4d6", 9: "5d6",
    11: "6d6", 13: "7d6", 15: "8d6", 17: "9d6", 19: "10d6",
}


def resolve_rogue_sneak_attack_dice(level: int) -> str:
    current = "1d6"
    for threshold, dice in sorted(_SNEAK_ATTACK_BY_LEVEL.items()):
        if level >= threshold:
            current = dice
    return current


def ensure_rogue_runtime(entity: object) -> dict:
    rogue = ensure_class_runtime(entity, "rogue")
    level = int(rogue.get("level") or 0)
    rogue.setdefault("expertise", {"skills": []})
    rogue.setdefault("steady_aim", {"enabled": level >= 3, "used_this_turn": False, "grants_advantage_on_next_attack": False})
    rogue.setdefault("cunning_strike", {"enabled": level >= 5, "max_effects_per_hit": 2 if level >= 11 else 1})
    rogue.setdefault("uncanny_dodge", {"enabled": level >= 5})
    rogue.setdefault("reliable_talent", {"enabled": level >= 7})
    rogue.setdefault("slippery_mind", {"enabled": level >= 15})
    rogue.setdefault("elusive", {"enabled": level >= 18})
    sneak_attack = rogue.setdefault("sneak_attack", {})
    sneak_attack["damage_dice"] = resolve_rogue_sneak_attack_dice(level)
    sneak_attack.setdefault("used_this_turn", False)
    return rogue
```

Then call `ensure_rogue_runtime(actor)` before reading sneak attack in `ExecuteAttack`, at turn start in `turn_engine.py`, and when projecting rogue resources in `GetEncounterState`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest test.test_rogue_runtime test.test_execute_attack test.test_turn_engine test.test_get_encounter_state -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/rogue/__init__.py tools/services/class_features/rogue/runtime.py tools/services/class_features/shared/__init__.py tools/services/combat/attack/execute_attack.py tools/services/encounter/turns/turn_engine.py tools/services/encounter/get_encounter_state.py test/test_rogue_runtime.py test/test_execute_attack.py test/test_turn_engine.py test/test_get_encounter_state.py
git commit -m "feat: add rogue runtime and sneak attack scaling"
```

### Task 2: 接入专精、可靠才能与圆滑心智

**Files:**
- Modify: `tools/services/class_features/shared/proficiency_resolver.py`
- Modify: `tools/services/checks/resolve_ability_check.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Test: `test/test_resolve_ability_check.py`
- Test: `test/test_class_feature_runtime_helpers.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_execute_applies_rogue_expertise_to_skill_check(self) -> None:
    encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["stealth"]
    encounter.entities["ent_ally_sabur_001"].class_features["rogue"] = {
        "level": 1,
        "expertise": {"skills": ["stealth"]},
    }
    request = AbilityCheckRequest(repo).execute(
        encounter_id="enc_ability_check_test",
        actor_id="ent_ally_sabur_001",
        check_type="skill",
        check="stealth",
        dc=15,
    )
    result = ResolveAbilityCheck(repo).execute(
        encounter_id="enc_ability_check_test",
        roll_request=request,
        base_roll=10,
    )
    self.assertEqual(result.final_total, 17)
    self.assertEqual(result.metadata["check_bonus_breakdown"]["proficiency_bonus_applied"], 4)
```

```python
def test_execute_reliable_talent_raises_low_skill_roll_to_ten(self) -> None:
    encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["stealth"]
    encounter.entities["ent_ally_sabur_001"].class_features["rogue"] = {
        "level": 7,
        "reliable_talent": {"enabled": True},
    }
    request = AbilityCheckRequest(repo).execute(
        encounter_id="enc_ability_check_test",
        actor_id="ent_ally_sabur_001",
        check_type="skill",
        check="stealth",
        dc=15,
    )
    result = ResolveAbilityCheck(repo).execute(
        encounter_id="enc_ability_check_test",
        roll_request=request,
        base_roll=3,
    )
    self.assertEqual(result.metadata["chosen_roll"], 10)
```

```python
def test_resolve_entity_save_proficiencies_adds_slippery_mind_wis_cha(self) -> None:
    entity.class_features = {"rogue": {"level": 15, "slippery_mind": {"enabled": True}}}
    self.assertIn("wis", resolve_entity_save_proficiencies(entity))
    self.assertIn("cha", resolve_entity_save_proficiencies(entity))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest test.test_resolve_ability_check test.test_class_feature_runtime_helpers -v
```

Expected: FAIL because expertise, reliable talent, and slippery mind are not applied yet.

- [ ] **Step 3: Write minimal implementation**

In `resolve_ability_check.py`, adjust skill fallback logic:

```python
rogue_runtime = get_class_runtime(actor, "rogue")
expertise = rogue_runtime.get("expertise", {})
expertise_skills = set(expertise.get("skills", [])) if isinstance(expertise, dict) else set()
is_proficient = check in resolve_entity_skill_proficiencies(actor)
proficiency_multiplier = 2 if is_proficient and check in expertise_skills else 1
proficiency_bonus = int(actor.proficiency_bonus) * proficiency_multiplier if is_proficient else 0
```

And before final total:

```python
if check_type == "skill" and is_proficient and self._has_reliable_talent(actor) and chosen_roll < 10:
    chosen_roll = 10
```

In `proficiency_resolver.py`, extend `resolve_entity_save_proficiencies`:

```python
rogue = get_class_runtime(entity, "rogue")
slippery_mind = rogue.get("slippery_mind")
if isinstance(slippery_mind, dict) and slippery_mind.get("enabled"):
    resolved.update({"wis", "cha"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest test.test_resolve_ability_check test.test_class_feature_runtime_helpers -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/class_features/shared/proficiency_resolver.py tools/services/checks/resolve_ability_check.py tools/services/class_features/shared/__init__.py test/test_resolve_ability_check.py test/test_class_feature_runtime_helpers.py
git commit -m "feat: add rogue expertise and reliable talent"
```

### Task 3: 接入灵巧动作与稳定瞄准

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/encounter/turns/turn_engine.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_turn_engine.py`
- Test: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_execute_steady_aim_requires_no_prior_movement(self) -> None:
    actor.class_features["rogue"] = {"level": 3}
    actor.combat_flags["movement_spent_feet"] = 5
    with self.assertRaisesRegex(ValueError, "steady_aim_requires_no_movement"):
        service.execute(
            encounter_id="enc_attack_request_test",
            target_id=target.entity_id,
            weapon_id="shortbow",
            class_feature_options={"steady_aim": True},
        )
```

```python
def test_execute_steady_aim_grants_advantage_and_sets_speed_zero(self) -> None:
    actor.class_features["rogue"] = {"level": 3}
    request = service.execute(
        encounter_id="enc_attack_request_test",
        target_id=target.entity_id,
        weapon_id="shortbow",
        class_feature_options={"steady_aim": True},
    )
    self.assertEqual(request.context["vantage"], "advantage")
    updated = repo.get("enc_attack_request_test")
    self.assertEqual(updated.entities[actor.entity_id].speed["remaining"], 0)
    self.assertTrue(updated.entities[actor.entity_id].action_economy["bonus_action_used"])
```

```python
def test_get_encounter_state_projects_rogue_cunning_action_summary(self) -> None:
    current.class_features["rogue"] = {"level": 2}
    state = GetEncounterState(repo, event_repository=event_repo).execute("enc_test")
    rogue = state["current_turn_entity"]["resources"]["class_features"]["rogue"]
    self.assertIn("cunning_action", rogue["available_features"])
    self.assertIn("bonus_dash", rogue["cunning_action"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest test.test_attack_roll_request test.test_turn_engine test.test_get_encounter_state -v
```

Expected: FAIL because steady aim and rogue action summaries are not implemented.

- [ ] **Step 3: Write minimal implementation**

In `attack_roll_request.py`:

```python
if bool(normalized_class_feature_options.get("steady_aim")):
    rogue = ensure_rogue_runtime(actor)
    if not rogue.get("steady_aim", {}).get("enabled"):
        raise ValueError("steady_aim_not_available")
    if int(actor.combat_flags.get("movement_spent_feet", 0) or 0) > 0:
        raise ValueError("steady_aim_requires_no_movement")
    if actor.action_economy.get("bonus_action_used"):
        raise ValueError("steady_aim_requires_bonus_action")
    actor.action_economy["bonus_action_used"] = True
    actor.speed["remaining"] = 0
    rogue["steady_aim"]["used_this_turn"] = True
    rogue["steady_aim"]["grants_advantage_on_next_attack"] = True
    self.encounter_repository.save(encounter)
    final_vantage = "advantage"
```

Also consume the pending steady-aim flag on the next attack request.

In `GetEncounterState`, project rogue summary:

```python
"rogue": {
    "level": rogue.get("level"),
    "sneak_attack": rogue.get("sneak_attack"),
    "cunning_action": {"bonus_dash": True, "bonus_disengage": True, "bonus_hide": True} if level >= 2 else None,
    "steady_aim": rogue.get("steady_aim"),
    "available_features": ["sneak_attack", "cunning_action", "steady_aim"],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest test.test_attack_roll_request test.test_turn_engine test.test_get_encounter_state -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/encounter/turns/turn_engine.py tools/services/encounter/get_encounter_state.py test/test_attack_roll_request.py test/test_turn_engine.py test/test_get_encounter_state.py
git commit -m "feat: add rogue steady aim and cunning action summaries"
```

### Task 4: 接入直觉闪避与飘忽不定

**Files:**
- Modify: `tools/repositories/reaction_definition_repository.py`
- Modify: `tools/services/combat/rules/reactions/definitions/__init__.py`
- Create: `tools/services/combat/rules/reactions/definitions/uncanny_dodge.py`
- Modify: `tools/services/combat/rules/reactions/open_reaction_window.py`
- Modify: `tools/services/combat/rules/reactions/resolve_reaction_option.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Test: `test/test_attack_reaction_window.py`
- Test: `test/test_resolve_reaction_option.py`
- Test: `test/test_attack_roll_request.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_execute_attack_returns_waiting_reaction_when_target_can_uncanny_dodge(self) -> None:
    target.class_features["rogue"] = {"level": 5}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=19,
        dice_rolls={"base_rolls": [14], "modifier": 5},
        damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
    )
    self.assertEqual(result["status"], "waiting_reaction")
```

```python
def test_execute_resolves_uncanny_dodge_and_halves_damage(self) -> None:
    option = {
        "reaction_id": "uncanny_dodge",
        "option_id": "uncanny_dodge_reduce",
        "host_action_type": "attack",
    }
    result = resolver.execute(...)
    self.assertEqual(result["host_action_snapshot"]["pending_damage_multiplier"], 0.5)
```

```python
def test_execute_elusive_removes_advantage_against_target(self) -> None:
    target.class_features["rogue"] = {"level": 18}
    request = service.execute(
        encounter_id="enc_attack_request_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        vantage="advantage",
    )
    self.assertEqual(request.context["vantage"], "normal")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest test.test_attack_reaction_window test.test_resolve_reaction_option test.test_attack_roll_request -v
```

Expected: FAIL because uncanny dodge and elusive do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add reaction definition similar to shield:

```python
{
  "reaction_id": "uncanny_dodge",
  "trigger_type": "attack_hit_confirmed",
  "option_type": "damage_reduction",
  "resource_cost": {"reaction": 1},
}
```

In attack window opening, create the option if:

- target is rogue level 5+
- target can see attacker
- target has reaction

In reaction resolution, set:

```python
host_action_snapshot["pending_damage_multiplier"] = 0.5
```

Then in `ExecuteAttack`, apply this multiplier before HP update.

For `Elusive`, in `attack_roll_request.py`:

```python
target_rogue = ensure_rogue_runtime(target)
if target_rogue.get("elusive", {}).get("enabled") and not self._target_is_incapacitated(target):
    if final_vantage == "advantage":
        final_vantage = "normal"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest test.test_attack_reaction_window test.test_resolve_reaction_option test.test_attack_roll_request -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/repositories/reaction_definition_repository.py tools/services/combat/rules/reactions/definitions/__init__.py tools/services/combat/rules/reactions/definitions/uncanny_dodge.py tools/services/combat/rules/reactions/open_reaction_window.py tools/services/combat/rules/reactions/resolve_reaction_option.py tools/services/combat/attack/attack_roll_request.py test/test_attack_reaction_window.py test/test_resolve_reaction_option.py test/test_attack_roll_request.py
git commit -m "feat: add rogue uncanny dodge and elusive"
```

### Task 5: 接入诡诈打击、进阶诡诈打击与凶狡打击

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/encounter/resolve_forced_movement.py`
- Modify: `tools/services/encounter/turn_effects.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_attack_roll_request.py`

- [ ] **Step 1: Write the failing tests**

Add tests like:

```python
def test_execute_cunning_strike_trip_consumes_one_sneak_die_and_applies_prone(self) -> None:
    actor.class_features["rogue"] = {"level": 5}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=18,
        dice_rolls={"base_rolls": [13], "modifier": 5},
        damage_rolls=[
            {"source": "weapon:rapier:part_0", "rolls": [6]},
            {"source": "rogue_sneak_attack", "rolls": [2, 3]},
        ],
        class_feature_options={
            "sneak_attack": True,
            "cunning_strike": {"effects": ["trip"]},
        },
    )
    self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["formula"], "2d6")
    self.assertIn("prone", repo.get("enc_execute_attack_test").entities[target.entity_id].conditions)
```

```python
def test_execute_improved_cunning_strike_allows_two_effects_at_level_eleven(self) -> None:
    actor.class_features["rogue"] = {"level": 11}
    request = service.execute(
        encounter_id="enc_attack_request_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        class_feature_options={
            "sneak_attack": True,
            "cunning_strike": {"effects": ["trip", "withdraw"]},
        },
    )
    self.assertEqual(request.context["class_feature_options"]["cunning_strike"]["effects"], ["trip", "withdraw"])
```

```python
def test_execute_rejects_two_cunning_strikes_below_level_eleven(self) -> None:
    actor.class_features["rogue"] = {"level": 5}
    with self.assertRaisesRegex(ValueError, "cunning_strike_allows_only_one_effect"):
        service.execute(
            encounter_id="enc_attack_request_test",
            target_id=target.entity_id,
            weapon_id="rapier",
            class_feature_options={
                "sneak_attack": True,
                "cunning_strike": {"effects": ["trip", "withdraw"]},
            },
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest test.test_execute_attack test.test_attack_roll_request -v
```

Expected: FAIL because cunning strike is not validated or resolved yet.

- [ ] **Step 3: Write minimal implementation**

In `attack_roll_request.py`, validate:

```python
rogue = ensure_rogue_runtime(actor)
cunning = normalized_class_feature_options.get("cunning_strike")
if cunning:
    effects = list(cunning.get("effects") or [])
    max_effects = rogue.get("cunning_strike", {}).get("max_effects_per_hit", 0)
    if len(effects) > max_effects:
        raise ValueError("cunning_strike_allows_only_one_effect" if max_effects == 1 else "too_many_cunning_strike_effects")
    if not request_class_feature_options.get("sneak_attack"):
        raise ValueError("cunning_strike_requires_sneak_attack")
```

In `execute_attack.py`, before appending sneak attack damage:

```python
remaining_dice = original_sneak_dice_count - spent_dice
damage_formula = f"{remaining_dice}d6" if remaining_dice > 0 else None
```

Then after damage resolution, apply:

- `trip` -> dex save or `prone`
- `withdraw` -> add free movement payload with no OA
- `poison` -> condition + end-of-turn save turn effect
- `daze` -> add turn effect marker
- `knock_out` -> `unconscious` plus save-to-end effect
- `obscure` -> `blinded` until next turn end

- [ ] **Step 4: Run focused tests and full suite**

Run:

```bash
python3 -m unittest test.test_execute_attack test.test_attack_roll_request -v
```

Expected: PASS

Run:

```bash
python3 -m unittest discover -s test -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py tools/services/encounter/resolve_forced_movement.py tools/services/encounter/turn_effects.py test/test_execute_attack.py test/test_attack_roll_request.py
git commit -m "feat: add rogue cunning strike effects"
```

## Self-Review

- Spec coverage:
  - 偷袭自动成长：Task 1
  - 专精 / 可靠才能 / 圆滑心智：Task 2
  - 灵巧动作 / 稳定瞄准：Task 3
  - 直觉闪避 / 飘忽不定：Task 4
  - 诡诈打击 / 进阶诡诈打击 / 凶狡打击：Task 5
- Placeholder scan:
  - 每个 task 都有具体文件、测试、命令和代码骨架
- Type consistency:
  - 统一使用 `class_features["rogue"]`
  - 攻击链通过 `class_feature_options`
  - 反应走现有 reaction framework
