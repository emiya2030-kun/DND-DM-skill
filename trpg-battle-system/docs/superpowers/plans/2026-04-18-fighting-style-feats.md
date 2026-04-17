# Fighting Style Feats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全战斗风格专长的战斗期实现，先完成非反应型风格并把现有风格抽到共享解析层。

**Architecture:** 新增共享 fighting style 解析工具，统一从实体职业 runtime 中收集战斗风格。攻击检定、伤害公式、AC 计算与回合开始效果都改为调用这层，从而让 Fighter / Paladin 等后续职业复用同一套规则。

**Tech Stack:** Python, unittest, TinyDB repositories, existing combat runtime services

---

### Task 1: Shared Fighting Style Resolver

**Files:**
- Create: `tools/services/class_features/shared/fighting_styles.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Test: `test/test_attack_roll_request.py`

- [ ] **Step 1: Write the failing test**

```python
def test_execute_archery_style_adds_two_to_ranged_attack_bonus_for_paladin(self) -> None:
    actor.class_features = {"paladin": {"level": 2, "fighting_style": {"style_id": "archery"}}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test/test_attack_roll_request.py::AttackRollRequestTests::test_execute_archery_style_adds_two_to_ranged_attack_bonus_for_paladin -v`
Expected: FAIL because current logic only reads fighter fighting_style

- [ ] **Step 3: Write minimal implementation**

```python
def resolve_fighting_style_ids(entity) -> set[str]:
    styles = set()
    for class_id, bucket in entity.class_features.items():
        fighting_style = bucket.get("fighting_style")
        style_id = str(fighting_style.get("style_id") or "").strip().lower()
        if style_id:
            styles.add(style_id)
    return styles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test/test_attack_roll_request.py::AttackRollRequestTests::test_execute_archery_style_adds_two_to_ranged_attack_bonus_for_paladin -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_attack_roll_request.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/fighting_styles.py
git commit -m "feat: add shared fighting style resolver"
```

### Task 2: Non-Reaction Fighting Styles

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/attack/weapon_profile_resolver.py`
- Modify: `tools/services/combat/defense/armor_profile_resolver.py`
- Modify: `tools/services/encounter/turns/start_turn.py`
- Test: `test/test_attack_roll_request.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_start_turn.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_thrown_weapon_fighting_adds_two_damage_for_thrown_hit(self) -> None: ...
def test_execute_two_weapon_fighting_keeps_ability_modifier_on_light_bonus_attack(self) -> None: ...
def test_execute_great_weapon_fighting_treats_one_and_two_as_three(self) -> None: ...
def test_execute_unarmed_fighting_uses_d8_with_both_hands_free(self) -> None: ...
def test_execute_unarmed_fighting_start_turn_deals_grapple_damage(self) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test/test_execute_attack.py -k "fighting_style or thrown_weapon_fighting or two_weapon_fighting or great_weapon_fighting or unarmed_fighting" -v`
Run: `pytest test/test_start_turn.py -k "unarmed_fighting" -v`
Expected: FAIL because new fighting styles are not implemented

- [ ] **Step 3: Write minimal implementation**

```python
if "thrown_weapon_fighting" in style_ids and attack_mode == "thrown":
    bonus += 2
if "two_weapon_fighting" in style_ids and attack_mode == "light_bonus":
    keep_modifier = True
if "great_weapon_fighting" in style_ids:
    rolls = [max(3, roll) if roll in {1, 2} else roll for roll in rolls]
if "unarmed_fighting" in style_ids:
    formula = "1d8+str" if both_hands_free else "1d6+str"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test/test_attack_roll_request.py test/test_execute_attack.py test/test_start_turn.py -k "archery_style or dueling_style or defense_style or thrown_weapon_fighting or two_weapon_fighting or great_weapon_fighting or unarmed_fighting" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_attack_roll_request.py test/test_execute_attack.py test/test_start_turn.py tools/services/combat/attack/attack_roll_request.py tools/services/combat/attack/execute_attack.py tools/services/combat/attack/weapon_profile_resolver.py tools/services/combat/defense/armor_profile_resolver.py tools/services/encounter/turns/start_turn.py
git commit -m "feat: add non-reaction fighting style feats"
```

### Task 3: Reaction Fighting Styles And Minimal Blind Fighting

**Files:**
- Modify: `tools/services/combat/rules/reactions/reaction_definitions.py`
- Modify: `tools/services/combat/rules/reactions/collect_reaction_candidates.py`
- Modify: `tools/services/combat/rules/reactions/resolve_reaction_option.py`
- Modify: `tools/services/combat/rules/reactions/resume_host_action.py`
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Test: `test/test_attack_reaction_window.py`
- Test: `test/test_resolve_reaction_option.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_interception_reduces_damage_after_hit(self) -> None: ...
def test_protection_rewrites_attack_to_disadvantage(self) -> None: ...
def test_blind_fighting_sets_ten_feet_blindsight_projection(self) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test/test_attack_reaction_window.py test/test_resolve_reaction_option.py -k "interception or protection or blind_fighting" -v`
Expected: FAIL because these styles do not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
host_action_snapshot["pending_flat_damage_reduction"] = "1d10+pb"
host_action_snapshot["vantage_override"] = "disadvantage"
projected["blindsight_feet"] = 10
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test/test_attack_reaction_window.py test/test_resolve_reaction_option.py test/test_attack_roll_request.py -k "interception or protection or blind_fighting" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_attack_reaction_window.py test/test_resolve_reaction_option.py test/test_attack_roll_request.py tools/services/combat/rules/reactions/reaction_definitions.py tools/services/combat/rules/reactions/collect_reaction_candidates.py tools/services/combat/rules/reactions/resolve_reaction_option.py tools/services/combat/rules/reactions/resume_host_action.py tools/services/combat/attack/attack_roll_request.py
git commit -m "feat: add reaction fighting style feats"
```
