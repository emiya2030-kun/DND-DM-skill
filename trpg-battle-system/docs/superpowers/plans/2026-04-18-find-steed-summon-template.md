# Find Steed And Summon Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `Find Steed / 寻获坐骑` 建立第一版可复用召唤模板，让施法后真实生成 summon entity，加入 encounter、turn order 和地图，并接上 `Faithful Steed` 免费施放资源。

**Architecture:** 以 `EncounterCastSpell` 现有施法声明链为入口，新增一层 `summons` 内部模板服务：负责创建 summon entity、spell instance 运行时绑定、注入 encounter。`Find Steed` 只实现第一张专用 builder 卡，`UpdateHp` 负责 summon 消失与施法者死亡联动清理，`GetEncounterState` 投影 `faithful_steed` 资源与 summon 实体。

**Tech Stack:** Python, pytest, TinyDB repositories, existing `EncounterCastSpell` / `ExecuteSpell` / `UpdateHp` / `GetEncounterState` services

---

### Task 1: Paladin Faithful Steed Runtime And Projection

**Files:**
- Modify: `tools/services/class_features/shared/runtime.py`
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_projects_paladin_faithful_steed_summary_at_level_five(self) -> None:
    player.class_features["paladin"] = {"level": 5}
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertTrue(paladin["faithful_steed"]["enabled"])
    self.assertTrue(paladin["faithful_steed"]["free_cast_available"])
    self.assertIn("faithful_steed", paladin["available_features"])

def test_execute_preserves_explicit_faithful_steed_free_cast_state(self) -> None:
    player.class_features["paladin"] = {
        "level": 5,
        "faithful_steed": {"free_cast_available": False},
    }
    paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]
    self.assertFalse(paladin["faithful_steed"]["free_cast_available"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_get_encounter_state.py -k "faithful_steed" -v`
Expected: FAIL because paladin runtime does not expose `faithful_steed` yet.

- [ ] **Step 3: Write minimal implementation**

```python
def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)

    faithful_steed = paladin.setdefault("faithful_steed", {})
    explicit_enabled = faithful_steed.get("enabled")
    faithful_steed["enabled"] = explicit_enabled if isinstance(explicit_enabled, bool) else level >= 5
    free_cast_available = faithful_steed.get("free_cast_available")
    faithful_steed["free_cast_available"] = (
        free_cast_available if isinstance(free_cast_available, bool) else level >= 5
    )
    return paladin

MARTIAL_CLASS_SUMMARIES["paladin"]["fields"].append("faithful_steed")

if class_id == "paladin" and level >= 5:
    available_features.append("faithful_steed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_get_encounter_state.py -k "faithful_steed" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_get_encounter_state.py tools/services/class_features/shared/runtime.py tools/services/encounter/get_encounter_state.py
git commit -m "feat: add paladin faithful steed runtime"
```

### Task 2: Summon Template And Find Steed Builder

**Files:**
- Create: `tools/services/spells/summons/create_summoned_entity.py`
- Create: `tools/services/spells/summons/find_steed_builder.py`
- Create: `test/test_find_steed.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_find_steed_entity_uses_level_two_stats() -> None:
    caster = build_paladin_caster()
    summon = build_find_steed_entity(
        caster=caster,
        cast_level=2,
        summon_position={"x": 5, "y": 5},
        steed_type="celestial",
        appearance="warhorse",
        source_spell_instance_id="spell_find_steed_001",
    )
    assert summon.category == "summon"
    assert summon.size == "large"
    assert summon.ac == 12
    assert summon.hp == {"current": 25, "max": 25, "temp": 0}
    assert summon.speed["walk"] == 60
    assert "fly" not in summon.speed
    assert summon.source_ref["steed_type"] == "celestial"

def test_build_find_steed_entity_adds_flight_at_cast_level_four() -> None:
    summon = build_find_steed_entity(..., cast_level=4, steed_type="fey", appearance="elk")
    assert summon.speed["fly"] == 60
    assert summon.weapons[0]["damage"]["damage_type"] == "psychic"

def test_create_summoned_entity_inserts_entity_after_caster_in_turn_order() -> None:
    encounter = build_find_steed_encounter()
    summon = build_find_steed_entity(...)
    result = create_summoned_entity(
        encounter=encounter,
        summon=summon,
        insert_after_entity_id="ent_paladin_001",
    )
    assert encounter.turn_order == ["ent_paladin_001", summon.entity_id, "ent_enemy_001"]
    assert encounter.entities[summon.entity_id].initiative == encounter.entities["ent_paladin_001"].initiative
    assert result["inserted_after"] == "ent_paladin_001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_find_steed.py -k "build_find_steed_entity or create_summoned_entity" -v`
Expected: FAIL because summon builder and summon insertion helper do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_find_steed_entity(
    *,
    caster: EncounterEntity,
    cast_level: int,
    summon_position: dict[str, int],
    steed_type: str,
    appearance: str,
    source_spell_instance_id: str,
) -> EncounterEntity:
    damage_type = {"celestial": "radiant", "fey": "psychic", "fiend": "necrotic"}[steed_type]
    speed = {"walk": 60, "remaining": 60}
    if cast_level >= 4:
        speed["fly"] = 60
    hp_max = 5 + cast_level * 10
    return EncounterEntity(
        entity_id=f"ent_steed_{uuid4().hex[:12]}",
        name="Otherworldly Steed",
        side=caster.side,
        category="summon",
        controller=caster.controller,
        position=dict(summon_position),
        hp={"current": hp_max, "max": hp_max, "temp": 0},
        ac=10 + cast_level,
        speed=speed,
        initiative=caster.initiative,
        size="large",
        proficiency_bonus=int(caster.proficiency_bonus or 0),
        ability_scores={"str": 18, "dex": 12, "con": 14, "int": 6, "wis": 12, "cha": 8},
        ability_mods={"str": 4, "dex": 1, "con": 2, "int": -2, "wis": 1, "cha": -1},
        weapons=[
            {
                "id": "otherworldly_slam",
                "name": "Otherworldly Slam",
                "attack_type": "melee_weapon",
                "range": {"reach": 5},
                "damage": {"formula": f"1d8+{cast_level}", "damage_type": damage_type},
            }
        ],
        source_ref={
            "summoner_entity_id": caster.entity_id,
            "source_spell_id": "find_steed",
            "source_spell_instance_id": source_spell_instance_id,
            "summon_template": "otherworldly_steed",
            "steed_type": steed_type,
            "appearance": appearance,
        },
        combat_flags={
            "dismiss_on_zero_hp": True,
            "dismiss_on_summoner_death": True,
            "shares_initiative_with_summoner": True,
            "controlled_mount": True,
        },
    )

def create_summoned_entity(
    *,
    encounter: Encounter,
    summon: EncounterEntity,
    insert_after_entity_id: str,
) -> dict[str, Any]:
    encounter.entities[summon.entity_id] = summon
    insert_index = encounter.turn_order.index(insert_after_entity_id) + 1
    encounter.turn_order.insert(insert_index, summon.entity_id)
    return {"entity_id": summon.entity_id, "inserted_after": insert_after_entity_id}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_find_steed.py -k "build_find_steed_entity or create_summoned_entity" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_find_steed.py tools/services/spells/summons/create_summoned_entity.py tools/services/spells/summons/find_steed_builder.py
git commit -m "feat: add summon template for find steed"
```

### Task 3: EncounterCastSpell Integration For Find Steed

**Files:**
- Modify: `tools/services/spells/build_spell_instance.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `test/test_build_spell_instance.py`
- Modify: `test/test_encounter_cast_spell.py`
- Modify: `test/test_find_steed.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_spell_instance_for_find_steed_tracks_summon_runtime(self) -> None:
    instance = build_spell_instance(
        spell_definition={"id": "find_steed", "name": "Find Steed", "level": 2},
        caster=caster,
        cast_level=2,
        targets=[],
        started_round=1,
    )
    self.assertEqual(instance["special_runtime"]["summon_mode"], "persistent_entity")
    self.assertEqual(instance["special_runtime"]["summon_entity_ids"], [])
    self.assertTrue(instance["special_runtime"]["replace_previous_from_same_caster"])

def test_execute_find_steed_creates_spell_instance_and_summon_entity(self) -> None:
    result = service.execute(
        encounter_id="enc_cast_spell_test",
        spell_id="find_steed",
        cast_level=2,
        target_point={"x": 5, "y": 5},
        reason="Summon steed",
    )
    updated = encounter_repo.get("enc_cast_spell_test")
    summon_id = result["spell_instance"]["special_runtime"]["summon_entity_ids"][0]
    self.assertIn(summon_id, updated.entities)
    self.assertIn(summon_id, updated.turn_order)
    self.assertEqual(updated.entities[summon_id].position, {"x": 5, "y": 5})

def test_execute_find_steed_consumes_free_cast_before_spell_slot(self) -> None:
    caster.class_features["paladin"] = {"level": 5}
    caster.resources["spell_slots"]["2"] = {"max": 1, "remaining": 1}
    result = service.execute(...)
    updated = encounter_repo.get("enc_cast_spell_test")
    self.assertIsNone(result["slot_consumed"])
    self.assertFalse(updated.entities["ent_ally_eric_001"].class_features["paladin"]["faithful_steed"]["free_cast_available"])
    self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["2"]["remaining"], 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_build_spell_instance.py test/test_encounter_cast_spell.py test/test_find_steed.py -k "find_steed" -v`
Expected: FAIL because `Find Steed` is not wired into `build_spell_instance` or `EncounterCastSpell`.

- [ ] **Step 3: Write minimal implementation**

```python
def _build_special_runtime(...):
    runtime = {"linked_zone_ids": []}
    spell_id = str(spell_definition.get("id") or spell_definition.get("spell_id") or "")
    if spell_id == "find_steed":
        runtime.update(
            {
                "summon_mode": "persistent_entity",
                "summon_entity_ids": [],
                "replace_previous_from_same_caster": True,
            }
        )
        return runtime

def execute(...):
    spell_definition = self._get_spell_definition_or_raise(...)
    if self._is_find_steed_spell(spell_definition):
        normalized_target_point = self._normalize_target_point(target_point)
        if normalized_target_point is None:
            raise ValueError("find_steed_requires_target_point")
        spell_instance = build_spell_instance(...)
        encounter.spell_instances.append(spell_instance)
        self._replace_previous_find_steed_if_needed(encounter=encounter, caster=caster)
        summon = build_find_steed_entity(
            caster=caster,
            cast_level=resolved_cast_level,
            summon_position={"x": normalized_target_point["x"], "y": normalized_target_point["y"]},
            steed_type=self._resolve_find_steed_type(caster),
            appearance=self._resolve_find_steed_appearance(caster),
            source_spell_instance_id=spell_instance["instance_id"],
        )
        create_summoned_entity(encounter=encounter, summon=summon, insert_after_entity_id=caster.entity_id)
        spell_instance["special_runtime"]["summon_entity_ids"] = [summon.entity_id]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_build_spell_instance.py test/test_encounter_cast_spell.py test/test_find_steed.py -k "find_steed" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_build_spell_instance.py test/test_encounter_cast_spell.py test/test_find_steed.py tools/services/spells/build_spell_instance.py tools/services/spells/encounter_cast_spell.py
git commit -m "feat: integrate find steed summon casting"
```

### Task 4: Replacement, Zero-HP Removal, And Summoner-Death Cleanup

**Files:**
- Modify: `tools/services/combat/shared/update_hp.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `test/test_update_hp.py`
- Modify: `test/test_find_steed.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_find_steed_replaces_previous_steed_from_same_caster() -> None:
    service.execute(..., target_point={"x": 5, "y": 5})
    first_updated = encounter_repo.get("enc_cast_spell_test")
    first_summon_id = first_updated.spell_instances[0]["special_runtime"]["summon_entity_ids"][0]

    service.execute(..., target_point={"x": 7, "y": 7})
    updated = encounter_repo.get("enc_cast_spell_test")
    active_summon_ids = [entity_id for entity_id, entity in updated.entities.items() if entity.category == "summon"]
    self.assertEqual(len(active_summon_ids), 1)
    self.assertNotIn(first_summon_id, active_summon_ids)

def test_execute_removes_find_steed_summon_at_zero_hp_and_clears_spell_runtime(self) -> None:
    result = UpdateHp(encounter_repo, AppendEvent(event_repo)).execute(
        encounter_id="enc_cast_spell_test",
        target_id=summon_id,
        hp_change=99,
        reason="Steed destroyed",
    )
    updated = encounter_repo.get("enc_cast_spell_test")
    self.assertEqual(result["zero_hp_outcome"]["outcome"], "summon_removed")
    self.assertNotIn(summon_id, updated.entities)
    self.assertEqual(updated.spell_instances[0]["special_runtime"]["summon_entity_ids"], [])

def test_execute_removes_find_steed_summon_when_summoner_dies(self) -> None:
    result = UpdateHp(encounter_repo, AppendEvent(event_repo)).execute(
        encounter_id="enc_cast_spell_test",
        target_id="ent_ally_eric_001",
        hp_change=99,
        reason="Paladin dropped",
    )
    updated = encounter_repo.get("enc_cast_spell_test")
    self.assertNotIn(summon_id, updated.entities)
    self.assertEqual(updated.spell_instances[0]["special_runtime"]["summon_entity_ids"], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test/test_update_hp.py test/test_find_steed.py -k "find_steed or steed" -v`
Expected: FAIL because replacement and summon cleanup are not implemented.

- [ ] **Step 3: Write minimal implementation**

```python
def _replace_previous_find_steed_if_needed(self, *, encounter: Encounter, caster: EncounterEntity) -> None:
    for instance in encounter.spell_instances:
        if instance.get("caster_entity_id") != caster.entity_id:
            continue
        if instance.get("spell_id") != "find_steed":
            continue
        special_runtime = instance.get("special_runtime", {})
        summon_entity_ids = special_runtime.get("summon_entity_ids", [])
        for summon_id in list(summon_entity_ids):
            encounter.entities.pop(summon_id, None)
            encounter.turn_order = [entity_id for entity_id in encounter.turn_order if entity_id != summon_id]
        special_runtime["summon_entity_ids"] = []

def _clear_find_steed_runtime_for_summon(self, encounter: Encounter, summon_id: str) -> None:
    for instance in encounter.spell_instances:
        special_runtime = instance.get("special_runtime")
        if not isinstance(special_runtime, dict):
            continue
        summon_entity_ids = special_runtime.get("summon_entity_ids")
        if isinstance(summon_entity_ids, list) and summon_id in summon_entity_ids:
            special_runtime["summon_entity_ids"] = [entity_id for entity_id in summon_entity_ids if entity_id != summon_id]

def _remove_summons_for_dead_summoner(self, encounter: Encounter, summoner_entity_id: str) -> None:
    summon_ids = [
        entity_id
        for entity_id, entity in encounter.entities.items()
        if entity.category == "summon" and entity.source_ref.get("summoner_entity_id") == summoner_entity_id
    ]
    for summon_id in summon_ids:
        self._clear_find_steed_runtime_for_summon(encounter, summon_id)
        self._remove_entity_from_encounter(encounter, summon_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/test_update_hp.py test/test_find_steed.py -k "find_steed or steed" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_update_hp.py test/test_find_steed.py tools/services/combat/shared/update_hp.py tools/services/spells/encounter_cast_spell.py
git commit -m "feat: add find steed summon lifecycle"
```

### Task 5: Focused Regression Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-find-steed-summon-template.md`

- [ ] **Step 1: Run focused summon and paladin regression suite**

Run: `python3 -m pytest test/test_find_steed.py test/test_build_spell_instance.py test/test_encounter_cast_spell.py test/test_update_hp.py test/test_get_encounter_state.py -k "find_steed or faithful_steed or summon_removed" -v`
Expected: PASS

- [ ] **Step 2: Run adjacent spell and combat regression suite**

Run: `python3 -m pytest test/test_execute_spell.py test/test_execute_save_spell.py test/test_attack_roll_request.py test/test_resolve_saving_throw.py -v`
Expected: PASS to confirm summon template work did not break the existing spell resolution or combat request chains.

- [ ] **Step 3: Mark plan progress**

```markdown
- [x] Task 1
- [x] Task 2
- [x] Task 3
- [x] Task 4
- [x] Task 5
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-18-find-steed-summon-template.md
git commit -m "docs: record find steed execution plan"
```
