# Paladin Radiant Strikes And Restoring Touch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有战斗 runtime 中接入圣武士的 `Radiant Strikes / 光耀打击` 与 `Restoring Touch / 复原之触`，并保持 `Lay on Hands / 圣疗`、攻击伤害链与状态投影的一致性。

**Architecture:** `Radiant Strikes` 走现有 `ExecuteAttack` 命中后结构化伤害追加链，不新增独立入口；`Restoring Touch` 直接扩展现有 `UseLayOnHands`，让治疗、解毒、移除多个状态在一次附赠动作中统一结算。paladin runtime 与 `GetEncounterState` 只做最小摘要补充，不引入新的职业资源系统。

**Tech Stack:** Python, pytest, TinyDB repositories, existing combat runtime services

---

### Task 1: Radiant Strikes Damage Rider

**Files:**
- Modify: `test/test_execute_attack.py`
- Modify: `test/test_get_encounter_state.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/encounter/get_encounter_state.py`

- [x] **Step 1: Write the failing tests**

```python
def test_execute_applies_radiant_strikes_on_level_eleven_melee_hit(self) -> None:
    actor = build_paladin_actor()
    actor.class_features = {"paladin": {"level": 11}}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=18,
        dice_rolls={"base_rolls": [13], "chosen_roll": 13, "modifier": 5, "vantage": "normal"},
        damage_rolls=[
            {"source": "weapon:rapier:part_0", "rolls": [4]},
            {"source": "paladin_radiant_strikes", "rolls": [5]},
        ],
    )
    self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["source"], "paladin_radiant_strikes")
    self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["formula"], "1d8")

def test_execute_applies_radiant_strikes_on_level_eleven_unarmed_hit(self) -> None:
    actor = build_actor()
    actor.class_features = {"paladin": {"level": 11}}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="unarmed_strike",
        final_total=17,
        dice_rolls={"base_rolls": [12], "chosen_roll": 12, "modifier": 5, "vantage": "normal"},
        damage_rolls=[
            {"source": "weapon:unarmed_strike:part_0", "rolls": [6]},
            {"source": "paladin_radiant_strikes", "rolls": [4]},
        ],
    )
    self.assertEqual(result["resolution"]["damage_resolution"]["parts"][1]["source"], "paladin_radiant_strikes")

def test_execute_projects_paladin_radiant_strikes_summary_from_level(self) -> None:
    player.class_features["paladin"] = {"level": 11}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertTrue(paladin["radiant_strikes"]["enabled"])
    self.assertIn("radiant_strikes", paladin["available_features"])
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_execute_attack.py test/test_get_encounter_state.py -k "radiant_strikes" -v`
Expected: FAIL because `paladin_radiant_strikes` is not appended yet and paladin projection does not expose the feature.

- [x] **Step 3: Write minimal implementation**

```python
def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)
    radiant_strikes = paladin.setdefault("radiant_strikes", {})
    explicit_enabled = radiant_strikes.get("enabled")
    radiant_strikes["enabled"] = explicit_enabled if isinstance(explicit_enabled, bool) else level >= 11
    return paladin

def _maybe_append_paladin_radiant_strikes_damage_part(
    self,
    *,
    actor: Any,
    attack_context: dict[str, Any],
    damage_parts: list[dict[str, Any]],
) -> bool:
    paladin = ensure_paladin_runtime(actor)
    radiant_strikes = paladin.get("radiant_strikes")
    if not isinstance(radiant_strikes, dict) or not bool(radiant_strikes.get("enabled")):
        return False
    attack_kind = str(attack_context.get("attack_kind") or "").lower()
    if attack_kind not in {"melee_weapon", "unarmed_strike"}:
        return False
    damage_parts.append(
        {
            "source": "paladin_radiant_strikes",
            "formula": "1d8",
            "damage_type": "radiant",
        }
    )
    return True
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_execute_attack.py test/test_get_encounter_state.py -k "radiant_strikes" -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add test/test_execute_attack.py test/test_get_encounter_state.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/runtime.py tools/services/combat/attack/execute_attack.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin radiant strikes"
```

### Task 2: Restoring Touch Through Lay On Hands

**Files:**
- Modify: `test/test_use_lay_on_hands.py`
- Modify: `test/test_get_encounter_state.py`
- Modify: `tools/services/class_features/paladin/use_lay_on_hands.py`
- Modify: `tools/services/encounter/get_encounter_state.py`

- [x] **Step 1: Write the failing tests**

```python
def test_use_lay_on_hands_removes_multiple_supported_conditions_and_heals_in_one_use() -> None:
    encounter.entities["ent_target_001"].conditions = ["poisoned", "paralyzed", "stunned"]
    result = UseLayOnHands(repo, append_event).execute(
        encounter_id="enc_paladin_test",
        actor_id="ent_paladin_001",
        target_id="ent_target_001",
        heal_amount=5,
        cure_poison=True,
        remove_conditions=["paralyzed", "stunned"],
    )
    assert result["pool_spent"] == 20
    assert result["conditions_removed"] == ["paralyzed", "stunned"]
    assert result["poison_removed"] is True

def test_use_lay_on_hands_does_not_charge_for_missing_or_invalid_conditions_but_still_spends_bonus_action() -> None:
    result = UseLayOnHands(repo, append_event).execute(
        encounter_id="enc_paladin_test",
        actor_id="ent_paladin_001",
        target_id="ent_target_001",
        remove_conditions=["paralyzed", "frozen"],
    )
    assert result["pool_spent"] == 0
    assert result["conditions_not_present"] == ["paralyzed"]
    assert result["invalid_requested_conditions"] == ["frozen"]
    assert updated.entities["ent_paladin_001"].action_economy["bonus_action_used"] is True

def test_use_lay_on_hands_rejects_when_pool_cannot_cover_combined_cost() -> None:
    with pytest.raises(ValueError, match="lay_on_hands_pool_insufficient"):
        UseLayOnHands(repo, append_event).execute(
            encounter_id="enc_paladin_test",
            actor_id="ent_paladin_001",
            target_id="ent_target_001",
            heal_amount=20,
            cure_poison=True,
            remove_conditions=["paralyzed"],
        )

def test_execute_projects_paladin_restoring_touch_feature_at_level_fourteen(self) -> None:
    player.class_features["paladin"] = {"level": 14}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertIn("restoring_touch", paladin["available_features"])
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_use_lay_on_hands.py test/test_get_encounter_state.py -k "restoring_touch or multiple_supported_conditions or invalid_conditions" -v`
Expected: FAIL because `UseLayOnHands` does not yet accept `remove_conditions` and the projection does not expose `restoring_touch`.

- [x] **Step 3: Write minimal implementation**

```python
SUPPORTED_RESTORING_TOUCH_CONDITIONS = {
    "blinded",
    "charmed",
    "deafened",
    "frightened",
    "paralyzed",
    "stunned",
}

def execute(..., remove_conditions: list[str] | None = None, ...):
    requested = self._normalize_requested_conditions(remove_conditions)
    invalid = [name for name in requested if name not in SUPPORTED_RESTORING_TOUCH_CONDITIONS]
    valid = [name for name in requested if name in SUPPORTED_RESTORING_TOUCH_CONDITIONS]
    removable = [name for name in valid if name in target.conditions]
    total_cost = heal_amount + poison_cost + (5 * len(removable))
    if total_cost > pool_remaining:
        raise ValueError("lay_on_hands_pool_insufficient")
    target.conditions = [c for c in target.conditions if c not in removable]
    actor.action_economy["bonus_action_used"] = True
    return {
        "conditions_requested": requested,
        "conditions_removed": removable,
        "conditions_not_present": [name for name in valid if name not in removable],
        "invalid_requested_conditions": invalid,
        "pool_spent_on_condition_removal": 5 * len(removable),
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_use_lay_on_hands.py test/test_get_encounter_state.py -k "restoring_touch or multiple_supported_conditions or invalid_conditions" -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add test/test_use_lay_on_hands.py test/test_get_encounter_state.py tools/services/class_features/paladin/use_lay_on_hands.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin restoring touch"
```

### Task 3: Focused Paladin Regression Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-paladin-radiant-restoring-touch.md`

- [x] **Step 1: Run focused paladin regression**

Run: `python3 -m pytest test/test_execute_attack.py test/test_use_lay_on_hands.py test/test_get_encounter_state.py -k "paladin or radiant_strikes or lay_on_hands or restoring_touch or divine_smite" -v`
Expected: PASS

- [x] **Step 2: Run adjacent combat regression**

Run: `python3 -m pytest test/test_resolve_saving_throw.py test/test_attack_roll_request.py test/test_attack_reaction_window.py test/test_resolve_reaction_option.py -v`
Expected: PASS to confirm new paladin work did not break aura, attack request, or reaction chains.

- [x] **Step 3: Mark plan progress**

```markdown
- [x] Task 1
- [x] Task 2
- [x] Task 3
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-18-paladin-radiant-restoring-touch.md
git commit -m "docs: record paladin radiant strikes plan"
```
