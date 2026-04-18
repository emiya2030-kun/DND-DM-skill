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

### Task 5: Channel Divinity Runtime Projection

**Files:**
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/class_features/shared/__init__.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_projects_paladin_channel_divinity_defaults_at_level_3(self) -> None:
    player.class_features["paladin"] = {"level": 3}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertTrue(paladin["channel_divinity"]["enabled"])
    self.assertEqual(paladin["channel_divinity"]["max_uses"], 2)
    self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 2)
    self.assertIn("channel_divinity", paladin["available_features"])

def test_projects_paladin_channel_divinity_defaults_at_level_11(self) -> None:
    player.class_features["paladin"] = {"level": 11}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertEqual(paladin["channel_divinity"]["max_uses"], 3)
    self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 3)

def test_preserves_explicit_remaining_channel_divinity_uses(self) -> None:
    player.class_features["paladin"] = {
        "level": 9,
        "channel_divinity": {"remaining_uses": 1},
    }
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertEqual(paladin["channel_divinity"]["max_uses"], 2)
    self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_get_encounter_state.py -k "channel_divinity" -v`
Expected: FAIL because paladin runtime and encounter projection do not expose `channel_divinity` yet.

- [ ] **Step 3: Write minimal implementation**

```python
def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)

    channel_divinity = paladin.setdefault("channel_divinity", {})
    explicit_enabled = channel_divinity.get("enabled")
    channel_divinity["enabled"] = explicit_enabled if isinstance(explicit_enabled, bool) else level >= 3
    channel_divinity["max_uses"] = 3 if level >= 11 else 2 if level >= 3 else 0
    remaining_uses = channel_divinity.get("remaining_uses")
    channel_divinity["remaining_uses"] = (
        remaining_uses if isinstance(remaining_uses, int) else channel_divinity["max_uses"]
    )

    aura_of_courage = paladin.setdefault("aura_of_courage", {})
    explicit_courage_enabled = aura_of_courage.get("enabled")
    aura_of_courage["enabled"] = explicit_courage_enabled if isinstance(explicit_courage_enabled, bool) else level >= 10
    radius_feet = aura_of_courage.get("radius_feet")
    aura_of_courage["radius_feet"] = radius_feet if isinstance(radius_feet, int) else 10
    return paladin

MARTIAL_CLASS_SUMMARIES["paladin"] = {
    "fields": [
        "level",
        "divine_smite",
        "lay_on_hands",
        "channel_divinity",
        "aura_of_protection",
        "aura_of_courage",
        "radiant_strikes",
    ],
    "available_features": [
        "divine_smite",
        "lay_on_hands",
        "channel_divinity",
        "abjure_foes",
        "aura_of_protection",
        "aura_of_courage",
    ],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_get_encounter_state.py -k "channel_divinity" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py tools/services/class_features/shared/__init__.py tools/services/class_features/shared/runtime.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin channel divinity runtime"
```

### Task 6: Abjure Foes Action Service

**Files:**
- Create: `tools/services/class_features/paladin/use_abjure_foes.py`
- Modify: `tools/services/class_features/paladin/__init__.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Create: `test/test_use_abjure_foes.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_spends_action_and_channel_divinity_and_applies_effects(self) -> None:
    actor.class_features = {"paladin": {"level": 10, "channel_divinity": {"remaining_uses": 2}}}
    actor.ability_mods["cha"] = 3
    result = service.execute(
        encounter_id="enc_abjure_test",
        actor_id=actor.entity_id,
        target_ids=[enemy.entity_id],
        save_rolls={enemy.entity_id: 5},
    )
    updated_actor = repo.get("enc_abjure_test").entities[actor.entity_id]
    updated_enemy = repo.get("enc_abjure_test").entities[enemy.entity_id]
    self.assertEqual(result["channel_divinity_remaining"], 1)
    self.assertTrue(result["action_consumed"])
    self.assertIn(f"frightened:{actor.entity_id}", updated_enemy.conditions)
    self.assertTrue(any(effect["effect_type"] == "abjure_foes_restriction" for effect in updated_enemy.turn_effects))

def test_execute_rejects_when_target_count_exceeds_charisma_limit(self) -> None:
    actor.ability_mods["cha"] = 1
    with self.assertRaisesRegex(ValueError, "too_many_targets"):
        service.execute(
            encounter_id="enc_abjure_test",
            actor_id=actor.entity_id,
            target_ids=[enemy_a.entity_id, enemy_b.entity_id],
            save_rolls={enemy_a.entity_id: 4, enemy_b.entity_id: 4},
        )

def test_execute_successful_save_leaves_target_unchanged(self) -> None:
    result = service.execute(
        encounter_id="enc_abjure_test",
        actor_id=actor.entity_id,
        target_ids=[enemy.entity_id],
        save_rolls={enemy.entity_id: 19},
    )
    self.assertEqual(result["targets"][0]["outcome"], "saved")
    self.assertFalse(repo.get("enc_abjure_test").entities[enemy.entity_id].conditions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_use_abjure_foes.py -v`
Expected: FAIL because `UseAbjureFoes` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
class UseAbjureFoes:
    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_ids: list[str],
        save_rolls: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        actor = encounter.entities[actor_id]
        paladin = ensure_paladin_runtime(actor)
        if int(paladin.get("level", 0) or 0) < 9:
            raise ValueError("abjure_foes_unavailable")
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_current_turn_actor")
        if actor.action_economy.get("action_used"):
            raise ValueError("action_already_used")

        channel_divinity = paladin["channel_divinity"]
        if int(channel_divinity.get("remaining_uses", 0) or 0) <= 0:
            raise ValueError("channel_divinity_depleted")

        max_targets = max(1, int(actor.ability_mods.get("cha", 0) or 0))
        if len(target_ids) > max_targets:
            raise ValueError("too_many_targets")

        save_dc = 8 + int(actor.proficiency_bonus or 0) + int(actor.ability_mods.get("cha", 0) or 0)
        results = []
        for target_id in target_ids:
            target = encounter.entities[target_id]
            self._validate_target(encounter=encounter, actor=actor, target=target)
            roll = self._resolve_save_roll(target_id=target_id, save_rolls=save_rolls)
            total = roll + int(target.ability_mods.get("wis", 0) or 0)
            if total < save_dc:
                target.conditions.append(f"frightened:{actor.entity_id}")
                target.turn_effects.append(
                    {
                        "effect_id": f"abjure_foes:{actor.entity_id}:{target.entity_id}",
                        "effect_type": "abjure_foes_restriction",
                        "source_entity_id": actor.entity_id,
                        "source_ref": "paladin:abjure_foes",
                        "ends_on_damage": True,
                        "duration_rounds": 10,
                    }
                )
                results.append({"target_id": target_id, "outcome": "failed_save", "save_total": total})
            else:
                results.append({"target_id": target_id, "outcome": "saved", "save_total": total})

        actor.action_economy["action_used"] = True
        channel_divinity["remaining_uses"] -= 1
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "action_consumed": True,
            "channel_divinity_remaining": channel_divinity["remaining_uses"],
            "save_dc": save_dc,
            "targets": results,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_use_abjure_foes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_use_abjure_foes.py tools/services/class_features/paladin/__init__.py tools/services/class_features/paladin/use_abjure_foes.py tools/services/class_features/shared/runtime.py
git commit -m "feat: add paladin abjure foes"
```

### Task 7: Damage Cleanup And Aura Of Courage Suppression

**Files:**
- Modify: `tools/services/combat/shared/update_hp.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/combat/save_spell/resolve_saving_throw.py`
- Modify: `test/test_update_hp.py`
- Modify: `test/test_use_abjure_foes.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_damage_removes_abjure_foes_effect_and_condition(self) -> None:
    target.conditions = [f"frightened:{paladin.entity_id}"]
    target.turn_effects = [
        {
            "effect_id": f"abjure_foes:{paladin.entity_id}:{target.entity_id}",
            "effect_type": "abjure_foes_restriction",
            "source_entity_id": paladin.entity_id,
            "source_ref": "paladin:abjure_foes",
            "ends_on_damage": True,
            "duration_rounds": 10,
        }
    ]
    result = UpdateHp(repo, append_event).execute(
        encounter_id="enc_update_hp_test",
        target_id=target.entity_id,
        hp_change=4,
        reason="test_hit",
        damage_type="slashing",
        source_entity_id=enemy.entity_id,
    )
    updated_target = repo.get("enc_update_hp_test").entities[target.entity_id]
    self.assertNotIn(f"frightened:{paladin.entity_id}", updated_target.conditions)
    self.assertFalse(updated_target.turn_effects)
    self.assertEqual(result["class_feature_resolution"]["abjure_foes"]["removed_effects"], 1)

def test_abjure_foes_does_not_apply_inside_aura_of_courage(self) -> None:
    actor.class_features = {"paladin": {"level": 10, "channel_divinity": {"remaining_uses": 2}}}
    ally_paladin.class_features = {"paladin": {"level": 10}}
    result = service.execute(
        encounter_id="enc_abjure_test",
        actor_id=actor.entity_id,
        target_ids=[covered_target.entity_id],
        save_rolls={covered_target.entity_id: 3},
    )
    self.assertEqual(result["targets"][0]["outcome"], "suppressed_by_aura_of_courage")
    self.assertFalse(repo.get("enc_abjure_test").entities[covered_target.entity_id].conditions)

def test_projects_aura_of_courage_for_level_10_paladin(self) -> None:
    player.class_features["paladin"] = {"level": 10}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertTrue(paladin["aura_of_courage"]["enabled"])
    self.assertEqual(paladin["aura_of_courage"]["radius_feet"], 10)
    self.assertIn("aura_of_courage", paladin["available_features"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_update_hp.py test/test_use_abjure_foes.py test/test_get_encounter_state.py -k "abjure_foes or aura_of_courage" -v`
Expected: FAIL because damage cleanup and `Aura of Courage` suppression are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _clear_abjure_foes_on_damage(self, target: EncounterEntity) -> dict[str, Any] | None:
    remaining_effects = []
    removed_sources = set()
    for effect in target.turn_effects:
        if effect.get("effect_type") == "abjure_foes_restriction" and bool(effect.get("ends_on_damage")):
            removed_sources.add(str(effect.get("source_entity_id") or ""))
            continue
        remaining_effects.append(effect)
    if not removed_sources:
        return None

    target.turn_effects = remaining_effects
    target.conditions = [
        condition
        for condition in target.conditions
        if not any(condition == f"frightened:{source_id}" for source_id in removed_sources)
    ]
    return {"removed_effects": len(removed_sources), "removed_sources": sorted(removed_sources)}

if hp_change > 0:
    abjure_cleanup = self._clear_abjure_foes_on_damage(target)
    if abjure_cleanup is not None:
        class_feature_resolution["abjure_foes"] = abjure_cleanup

def _is_covered_by_aura_of_courage(self, encounter: Encounter, target: EncounterEntity) -> bool:
    for entity in encounter.entities.values():
        paladin = ensure_paladin_runtime(entity)
        aura = paladin.get("aura_of_courage", {})
        if not bool(aura.get("enabled")):
            continue
        if "incapacitated" in entity.conditions:
            continue
        if entity.faction != target.faction:
            continue
        if self._distance_feet(entity, target) <= int(aura.get("radius_feet", 10) or 10):
            return True
    return False

if self._is_covered_by_aura_of_courage(encounter, target):
    results.append({"target_id": target_id, "outcome": "suppressed_by_aura_of_courage"})
    continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_update_hp.py test/test_use_abjure_foes.py test/test_get_encounter_state.py -k "abjure_foes or aura_of_courage" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_update_hp.py test/test_use_abjure_foes.py test/test_get_encounter_state.py tools/services/class_features/shared/runtime.py tools/services/combat/save_spell/resolve_saving_throw.py tools/services/combat/shared/update_hp.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin aura of courage handling"
```

### Task 8: Paladin Phase Two Regression Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-paladin-core-combat.md`

- [ ] **Step 1: Run focused paladin regression suite**

Run: `python3 -m pytest test/test_use_abjure_foes.py test/test_update_hp.py test/test_get_encounter_state.py test/test_execute_attack.py test/test_use_lay_on_hands.py -k "paladin or abjure_foes or aura_of_courage or channel_divinity or divine_smite or radiant_strikes or restoring_touch" -v`
Expected: PASS

- [ ] **Step 2: Run adjacent combat regression suite**

Run: `python3 -m pytest test/test_resolve_saving_throw.py test/test_attack_reaction_window.py test/test_resolve_reaction_option.py test/test_attack_roll_request.py -v`
Expected: PASS to confirm the new paladin phase did not break saving throws, reactions, or attack execution.

- [ ] **Step 3: Mark appended phase progress**

```markdown
- [x] Task 5
- [x] Task 6
- [x] Task 7
- [x] Task 8
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-18-paladin-core-combat.md
git commit -m "docs: record paladin channel divinity execution plan"
```
