# Paladin Core Combat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有战斗 runtime 中稳定接入圣武士的 `圣疗 / 守护灵光 / 至圣斩` 三项核心战斗能力。

**Architecture:** 统一把 paladin 运行时挂在 `entity.class_features["paladin"]`，由共享 runtime helper 自动补全等级驱动的默认字段。`圣疗` 走独立 service；`守护灵光` 直接接入豁免链；`至圣斩` 接到命中后结构化伤害链，并复用现有法术位资源结构。

**Tech Stack:** Python, unittest, TinyDB repositories, existing combat runtime services

---

### Task 1: Paladin Runtime And Lay On Hands

**Files:**
- Create: `tools/services/class_features/paladin/__init__.py`
- Create: `tools/services/class_features/paladin/use_lay_on_hands.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Create: `test/test_use_lay_on_hands.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_heals_target_and_spends_pool(self) -> None:
    actor.class_features = {"paladin": {"level": 5}}
    target.hp = {"current": 4, "max": 10, "temp": 0}
    result = UseLayOnHands(repo).execute(
        encounter_id="enc_paladin_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        heal_amount=6,
    )
    self.assertEqual(result["pool_spent"], 6)
    self.assertEqual(result["pool_remaining"], 19)
    self.assertEqual(result["hp_restored"], 6)

def test_execute_cure_poison_spends_five_even_without_hp_restore(self) -> None:
    target.conditions = ["poisoned"]
    result = UseLayOnHands(repo).execute(
        encounter_id="enc_paladin_test",
        actor_id=actor.entity_id,
        target_id=target.entity_id,
        heal_amount=0,
        cure_poison=True,
    )
    self.assertTrue(result["poison_removed"])
    self.assertEqual(result["pool_spent"], 5)

def test_execute_projects_paladin_resource_summary(self) -> None:
    player.class_features["paladin"] = {"level": 6}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertEqual(paladin["lay_on_hands"]["pool_max"], 30)
    self.assertTrue(paladin["aura_of_protection"]["enabled"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_use_lay_on_hands.py test/test_get_encounter_state.py -k "lay_on_hands or paladin_resource_summary" -v`
Expected: FAIL because `UseLayOnHands` and paladin runtime defaults do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)
    lay = paladin.setdefault("lay_on_hands", {})
    lay["pool_max"] = level * 5 if level > 0 else int(lay.get("pool_max", 0) or 0)
    remaining = lay.get("pool_remaining")
    lay["pool_remaining"] = remaining if isinstance(remaining, int) else lay["pool_max"]
    paladin.setdefault("divine_smite", {})["enabled"] = level >= 2
    aura = paladin.setdefault("aura_of_protection", {})
    aura["enabled"] = level >= 6
    aura["radius_feet"] = 10
    return paladin

class UseLayOnHands:
    def execute(...):
        total_cost = heal_amount + (5 if cure_poison else 0)
        paladin["lay_on_hands"]["pool_remaining"] -= total_cost
        if heal_amount:
            hp_update = UpdateHp(...).execute(...)
        if cure_poison:
            target.conditions = [c for c in target.conditions if c != "poisoned"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_use_lay_on_hands.py test/test_get_encounter_state.py -k "lay_on_hands or paladin_resource_summary" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_use_lay_on_hands.py test/test_get_encounter_state.py tools/services/class_features/paladin/__init__.py tools/services/class_features/paladin/use_lay_on_hands.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/runtime.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin lay on hands runtime"
```

### Task 2: Aura Of Protection Save Bonus Integration

**Files:**
- Modify: `tools/services/combat/save_spell/resolve_saving_throw.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_resolve_saving_throw.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_applies_aura_of_protection_bonus_from_nearby_paladin(self) -> None:
    paladin.class_features = {"paladin": {"level": 6}}
    paladin.ability_mods["cha"] = 3
    result = ResolveSavingThrow(repo).execute(...)
    self.assertEqual(result.metadata["aura_of_protection_bonus"], 3)
    self.assertEqual(result.final_total, 16)

def test_execute_uses_highest_paladin_aura_bonus(self) -> None:
    self.assertEqual(result.metadata["aura_of_protection_bonus"], 4)
    self.assertEqual(result.metadata["aura_of_protection_source"], "ent_ally_paladin_high_001")

def test_execute_ignores_incapacitated_paladin_aura(self) -> None:
    paladin.conditions = ["incapacitated"]
    self.assertEqual(result.metadata["aura_of_protection_bonus"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_resolve_saving_throw.py test/test_get_encounter_state.py -k "aura_of_protection" -v`
Expected: FAIL because save bonus calculation does not currently inspect nearby paladins.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_aura_of_protection_bonus(...):
    best_bonus = 0
    best_source = None
    for entity in encounter.entities.values():
        paladin = ensure_paladin_runtime(entity)
        aura = paladin.get("aura_of_protection", {})
        if not aura.get("enabled") or runtime.has("incapacitated"):
            continue
        if not self._is_friendly_aura_source(source=entity, target=target):
            continue
        if self._distance_feet(entity, target) > int(aura.get("radius_feet", 10) or 10):
            continue
        bonus = max(1, int(entity.ability_mods.get("cha", 0) or 0))
        if bonus > best_bonus:
            best_bonus = bonus
            best_source = entity.entity_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_resolve_saving_throw.py test/test_get_encounter_state.py -k "aura_of_protection" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_resolve_saving_throw.py test/test_get_encounter_state.py tools/services/combat/save_spell/resolve_saving_throw.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin aura of protection"
```

### Task 3: Divine Smite On Hit Damage Rider

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Modify: `test/test_execute_attack.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_applies_divine_smite_damage_and_consumes_spell_slot(self) -> None:
    actor.class_features = {"paladin": {"level": 5}}
    actor.resources = {"spell_slots": {"1": {"max": 2, "remaining": 2}}}
    result = service.execute(
        encounter_id="enc_execute_attack_test",
        target_id=target.entity_id,
        weapon_id="rapier",
        final_total=18,
        dice_rolls={"base_rolls": [13], "chosen_roll": 13, "modifier": 5, "vantage": "normal"},
        damage_rolls=[{"damage_type": "piercing", "formula": "1d8+3", "rolls": [5], "total": 8}],
        class_feature_options={"divine_smite": {"slot_level": 1}},
    )
    self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 17)
    self.assertEqual(updated_actor.resources["spell_slots"]["1"]["remaining"], 1)

def test_execute_adds_extra_die_against_undead(self) -> None:
    target.source_ref = {"creature_type": "undead"}
    self.assertEqual(smite_part["formula"], "3d8")

def test_execute_does_not_consume_slot_on_miss(self) -> None:
    self.assertEqual(updated_actor.resources["spell_slots"]["1"]["remaining"], 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_execute_attack.py -k "divine_smite" -v`
Expected: FAIL because `ExecuteAttack` does not currently append paladin smite damage or consume spell slots on hit.

- [ ] **Step 3: Write minimal implementation**

```python
def _build_divine_smite_damage_part(...):
    extra_dice = 2 + max(0, slot_level - 1)
    if creature_type in {"fiend", "undead"}:
        extra_dice += 1
    return {"source": "paladin_divine_smite", "formula": f"{extra_dice}d8", "damage_type": "radiant"}

if resolution["hit"] and divine_smite_requested:
    damage_parts.append(self._build_divine_smite_damage_part(...))
    self._consume_spell_slot(actor, slot_level)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_execute_attack.py -k "divine_smite" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_execute_attack.py tools/services/combat/attack/execute_attack.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/runtime.py
git commit -m "feat: add paladin divine smite"
```

### Task 4: Focused Regression Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-paladin-core-combat.md`

- [ ] **Step 1: Run focused regression suite**

Run: `python3 -m pytest test/test_execute_attack.py test/test_resolve_saving_throw.py test/test_get_encounter_state.py test/test_use_lay_on_hands.py -v`
Expected: PASS

- [ ] **Step 2: Run adjacent combat regression suite**

Run: `python3 -m pytest test/test_attack_reaction_window.py test/test_resolve_reaction_option.py test/test_attack_roll_request.py test/test_start_turn.py -v`
Expected: PASS to confirm paladin work did not break existing reaction and attack chains.

- [ ] **Step 3: Mark plan progress**

```markdown
- [x] Task 1
- [x] Task 2
- [x] Task 3
- [x] Task 4
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-18-paladin-core-combat.md
git commit -m "docs: record paladin core combat execution"
```
