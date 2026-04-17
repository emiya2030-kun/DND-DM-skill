# Healing Rules And Healing Word Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `trpg-battle-system` 接入“死亡目标不能接受普通治疗”的通用规则，并新增可在遭遇战中完整结算的 `Healing Word` 法术。

**Architecture:** 底层仍由 `UpdateHp` 统一处理伤害与治疗，新增“已死亡目标禁疗”的结构化返回；法术层通过 `spell_definitions.json` 声明 `healing_word`，并在 `ExecuteSpell` 中新增 `resolution.mode = "heal"` 分支，自动掷治疗骰、计算升环治疗量并调用 `UpdateHp`。整条链路保持与现有攻击 / 伤害 / 豁免法术一致的测试风格与 runtime 返回结构。

**Tech Stack:** Python 3.9, TinyDB repository, unittest, JSON knowledge repository, existing spell / HP services

---

### Task 1: 给 `UpdateHp` 增加死亡目标禁疗规则

**Files:**
- Modify: `tools/services/combat/shared/update_hp.py`
- Test: `test/test_update_hp.py`

- [ ] **Step 1: Write the failing `UpdateHp` tests**

```python
    def test_execute_blocks_healing_for_dead_target(self) -> None:
        """测试已死亡目标不能接受普通治疗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = True
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=-6,
                reason="Healing Word",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 0)
            self.assertEqual(result["event_type"], "hp_unchanged")
            self.assertTrue(result["healing_blocked"])
            self.assertEqual(result["healing_blocked_reason"], "target_is_dead")
            encounter_repo.close()
            event_repo.close()

    def test_execute_allows_healing_for_zero_hp_but_not_dead_target(self) -> None:
        """测试 0 HP 但未死亡的目标仍可接受治疗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = False
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=-4,
                reason="Healing Word",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 4)
            self.assertEqual(result["event_type"], "healing_applied")
            self.assertNotIn("healing_blocked_reason", result)
            encounter_repo.close()
            event_repo.close()
```

- [ ] **Step 2: Run the `UpdateHp` tests to verify they fail**

Run: `python3 -m unittest test.test_update_hp.UpdateHpTests.test_execute_blocks_healing_for_dead_target test.test_update_hp.UpdateHpTests.test_execute_allows_healing_for_zero_hp_but_not_dead_target -v`

Expected: FAIL because `UpdateHp` currently heals any target with `hp_change < 0`.

- [ ] **Step 3: Add the minimal `UpdateHp` blocked-healing branch**

```python
        elif hp_change < 0:
            if bool(target.combat_flags.get("is_dead")):
                result = {
                    "hp_before": hp_before,
                    "hp_after": hp_before,
                    "temp_hp_before": temp_hp_before,
                    "temp_hp_after": temp_hp_before,
                    "applied_change": 0,
                    "temp_hp_absorbed": 0,
                    "original_hp_change": hp_change,
                    "adjusted_hp_change": 0,
                    "damage_adjustment": None,
                    "healing_blocked": True,
                    "healing_blocked_reason": "target_is_dead",
                }
                event_type = "hp_unchanged"
            else:
                result = self._apply_healing(target, abs(hp_change))
                result["original_hp_change"] = hp_change
                result["adjusted_hp_change"] = hp_change
                result["damage_adjustment"] = None
                event_type = "healing_applied"
```

- [ ] **Step 4: Run the `UpdateHp` tests to verify they pass**

Run: `python3 -m unittest test.test_update_hp.UpdateHpTests.test_execute_blocks_healing_for_dead_target test.test_update_hp.UpdateHpTests.test_execute_allows_healing_for_zero_hp_but_not_dead_target -v`

Expected: PASS

- [ ] **Step 5: Commit the `UpdateHp` rule change**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  test/test_update_hp.py \
  tools/services/combat/shared/update_hp.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: block healing for dead targets"
```

### Task 2: 新增 `Healing Word` 法术模板并接入请求层校验

**Files:**
- Modify: `data/knowledge/spell_definitions.json`
- Modify: `test/test_spell_request.py`

- [ ] **Step 1: Write the failing `SpellRequest` tests for `Healing Word`**

```python
    def test_execute_accepts_healing_word_bonus_action_single_target(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "healing_word": {
                        "id": "healing_word",
                        "name": "Healing Word",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 bonus action", "concentration": False},
                        "resolution": {"mode": "heal", "activation": "bonus_action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 60,
                            "requires_line_of_sight": True,
                            "allowed_target_types": ["creature"],
                        },
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter_repo.save(encounter)

        result = SpellRequest(encounter_repo, spell_repo).execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="healing_word",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="bonus_action",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action_cost"], "bonus_action")
        self.assertEqual(result["target_entity_ids"], ["ent_target_humanoid_001"])

    def test_execute_rejects_healing_word_target_point_without_los(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {"spell_definitions": {}}
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter.map.terrain = [{"terrain_id": "wall_01", "type": "wall", "x": 2, "y": 1, "blocks_los": True}]
        encounter_repo.save(encounter)

        with self.assertRaisesRegex(ValueError, "blocked_by_line_of_sight"):
            SpellRequest(encounter_repo).execute(
                encounter_id="enc_spell_request_test",
                actor_id="ent_caster_001",
                spell_id="healing_word",
                cast_level=1,
                target_entity_ids=["ent_target_humanoid_001"],
                declared_action_cost="bonus_action",
            )
```

- [ ] **Step 2: Run the `SpellRequest` tests to verify they fail**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_accepts_healing_word_bonus_action_single_target test.test_spell_request.SpellRequestTests.test_execute_rejects_healing_word_target_point_without_los -v`

Expected: FAIL because the repository does not yet contain `healing_word`.

- [ ] **Step 3: Add the `Healing Word` definition to the spell knowledge base**

```json
    "healing_word": {
      "id": "healing_word",
      "name": "Healing Word",
      "level": 1,
      "save_ability": null,
      "requires_attack_roll": false,
      "localization": {
        "name_zh": "治愈真言",
        "name_en": "Healing Word",
        "rules_text_zh": "你指定施法距离内一个你能看见的生物并恢复其生命值，恢复量等于2d4+你的施法属性调整值。升环施法。使用的法术位每比一环高一环，此法术的治疗量就增加2d4点。",
        "rules_text_en": "A creature of your choice that you can see within range regains hit points equal to 2d4 plus your spellcasting ability modifier. When you cast this spell using a spell slot of 2nd level or higher, the healing increases by 2d4 for each slot level above 1st."
      },
      "usage_contexts": ["combat", "exploration"],
      "runtime_support": {"in_encounter": "implemented", "out_of_encounter": "template_only"},
      "source": {
        "system": "dnd_2024",
        "classes_zh": ["吟游诗人", "牧师", "德鲁伊"],
        "classes_en": ["Bard", "Cleric", "Druid"]
      },
      "base": {
        "level": 1,
        "school": "abjuration",
        "school_zh": "防护",
        "casting_time": "1 bonus action",
        "casting_time_zh": "附赠动作",
        "range": "60 feet",
        "range_zh": "60尺",
        "components": ["V"],
        "components_zh": ["V"],
        "duration": "instantaneous",
        "duration_zh": "立即",
        "concentration": false
      },
      "targeting": {
        "type": "single_target",
        "range_feet": 60,
        "requires_line_of_sight": true,
        "allowed_target_types": ["creature"]
      },
      "resolution": {
        "mode": "heal",
        "activation": "bonus_action",
        "healing_mode": "instant"
      },
      "on_cast": {
        "healing_parts": [
          {
            "source": "spell:healing_word:base",
            "formula": "2d4",
            "include_spellcasting_modifier": true
          }
        ]
      },
      "scaling": {
        "cantrip_by_level": null,
        "slot_level_bonus": {
          "base_slot_level": 1,
          "additional_healing_parts": [
            {
              "source": "spell:healing_word:slot_scaling",
              "formula_per_extra_level": "2d4"
            }
          ]
        }
      }
    }
```

- [ ] **Step 4: Run the `SpellRequest` tests to verify they pass**

Run: `python3 -m unittest test.test_spell_request.SpellRequestTests.test_execute_accepts_healing_word_bonus_action_single_target test.test_spell_request.SpellRequestTests.test_execute_rejects_healing_word_target_point_without_los -v`

Expected: PASS

- [ ] **Step 5: Commit the spell definition update**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  data/knowledge/spell_definitions.json \
  test/test_spell_request.py
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add healing word spell definition"
```

### Task 3: 在 `ExecuteSpell` 中实现 `Healing Word` 治疗分支

**Files:**
- Modify: `tools/services/spells/execute_spell.py`
- Modify: `test/test_execute_spell.py`

- [ ] **Step 1: Write the failing `ExecuteSpell` tests for `Healing Word`**

```python
    def test_execute_healing_word_auto_rolls_and_restores_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            target = encounter.entities["ent_target_humanoid_001"]
            caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
            caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
            caster.source_ref["spellcasting_ability"] = "wis"
            caster.ability_mods["wis"] = 3
            target.hp["current"] = 2
            encounter_repo.save(encounter)

            service = build_execute_spell(encounter_repo, event_repo)
            result = service.execute(
                encounter_id="enc_spell_test",
                actor_id="ent_caster_001",
                spell_id="healing_word",
                cast_level=1,
                target_entity_ids=["ent_target_humanoid_001"],
                declared_action_cost="bonus_action",
            )

            self.assertEqual(result["spell_resolution"]["mode"], "heal")
            self.assertEqual(result["spell_resolution"]["target_id"], "ent_target_humanoid_001")
            self.assertGreaterEqual(result["spell_resolution"]["healing_total"], 5)
            self.assertEqual(result["spell_resolution"]["hp_update"]["event_type"], "healing_applied")

    def test_execute_healing_word_blocks_on_dead_target_but_still_casts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            target = encounter.entities["ent_target_humanoid_001"]
            caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
            caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
            caster.source_ref["spellcasting_ability"] = "wis"
            caster.ability_mods["wis"] = 3
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = True
            encounter_repo.save(encounter)

            service = build_execute_spell(encounter_repo, event_repo)
            result = service.execute(
                encounter_id="enc_spell_test",
                actor_id="ent_caster_001",
                spell_id="healing_word",
                cast_level=1,
                target_entity_ids=["ent_target_humanoid_001"],
                declared_action_cost="bonus_action",
            )

            self.assertEqual(result["resource_update"]["remaining_after"], 1)
            self.assertEqual(result["spell_resolution"]["hp_update"]["event_type"], "hp_unchanged")
            self.assertEqual(
                result["spell_resolution"]["hp_update"]["healing_blocked_reason"],
                "target_is_dead",
            )
```

- [ ] **Step 2: Run the `ExecuteSpell` tests to verify they fail**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_healing_word_auto_rolls_and_restores_hp test.test_execute_spell.ExecuteSpellTests.test_execute_healing_word_blocks_on_dead_target_but_still_casts -v`

Expected: FAIL because `ExecuteSpell` has no `heal` resolution branch.

- [ ] **Step 3: Add the minimal healing branch to `ExecuteSpell`**

```python
        elif self._is_heal_spell(spell_definition):
            prepared_heal_spell = self._prepare_heal_spell_resolution(
                encounter_id=encounter_id,
                actor_id=request_result["actor_id"],
                spell_definition=spell_definition,
                cast_level=request_result["cast_level"],
                target_ids=request_result.get("target_entity_ids"),
                resolved_scaling=request_result.get("resolved_scaling"),
            )
            if not prepared_heal_spell.get("ok"):
                return prepared_heal_spell
```

```python
        if prepared_heal_spell is not None:
            target_id = prepared_heal_spell["target_id"]
            healing_rolls = prepared_heal_spell["healing_rolls"]
            healing_total = prepared_heal_spell["healing_total"]
            hp_update = self.update_hp.execute(
                encounter_id=encounter_id,
                target_id=target_id,
                hp_change=-healing_total,
                reason=cast_result.get("spell_name") or request_result["spell_id"],
            )
            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": {
                    "mode": "heal",
                    "target_id": target_id,
                    "healing_rolls": healing_rolls,
                    "healing_total": healing_total,
                    "hp_update": hp_update,
                },
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }
```

```python
    def _is_heal_spell(self, spell_definition: dict[str, Any] | None) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        resolution = spell_definition.get("resolution")
        return isinstance(resolution, dict) and resolution.get("mode") == "heal"
```

```python
    def _prepare_heal_spell_resolution(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_definition: dict[str, Any],
        cast_level: int,
        target_ids: list[str] | None,
        resolved_scaling: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(target_ids, list) or len(target_ids) != 1:
            raise ValueError("heal_spell_requires_single_target")
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities[actor_id]
        spellcasting_ability = str(actor.source_ref.get("spellcasting_ability") or "").lower()
        spell_mod = actor.ability_mods.get(spellcasting_ability, 0) if spellcasting_ability else 0
        base_rolls = [random.randint(1, 4), random.randint(1, 4)]
        extra_rolls: list[int] = []
        upcast_delta = 0
        if isinstance(resolved_scaling, dict):
            upcast_delta = int(resolved_scaling.get("upcast_delta", 0) or 0)
        for _ in range(upcast_delta * 2):
            extra_rolls.append(random.randint(1, 4))
        all_rolls = base_rolls + extra_rolls
        return {
            "ok": True,
            "target_id": target_ids[0],
            "healing_rolls": {
                "base_rolls": base_rolls,
                "scaling_rolls": extra_rolls,
                "spellcasting_modifier": spell_mod,
            },
            "healing_total": sum(all_rolls) + spell_mod,
        }
```

- [ ] **Step 4: Run the `ExecuteSpell` tests to verify they pass**

Run: `python3 -m unittest test.test_execute_spell.ExecuteSpellTests.test_execute_healing_word_auto_rolls_and_restores_hp test.test_execute_spell.ExecuteSpellTests.test_execute_healing_word_blocks_on_dead_target_but_still_casts -v`

Expected: PASS

- [ ] **Step 5: Run the broader healing / spell regression set**

Run: `python3 -m unittest test.test_update_hp test.test_spell_request test.test_execute_spell -v`

Expected: PASS

- [ ] **Step 6: Commit the healing spell execution work**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system add \
  tools/services/spells/execute_spell.py \
  test/test_execute_spell.py \
  test/test_spell_request.py \
  test/test_update_hp.py \
  data/knowledge/spell_definitions.json
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system commit -m "feat: add healing word spell resolution"
```

### Task 4: Run full verification and prepare integration

**Files:**
- Modify: none
- Test: `test/`

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s /Users/runshi.zhang/DND-DM-skill/trpg-battle-system/test -v`

Expected: `OK`

- [ ] **Step 2: Inspect worktree status**

Run: `git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system status --short`

Expected: no tracked unstaged changes for this feature; do not add `.worktrees/`

- [ ] **Step 3: Push after verification**

```bash
git -C /Users/runshi.zhang/DND-DM-skill/trpg-battle-system push
```

- [ ] **Step 4: Summarize the delivered behavior**

Report:
- `UpdateHp` now blocks ordinary healing on dead targets
- `Healing Word` now works as a bonus-action healing spell with auto-rolled healing and upcasting
- full test suite result
