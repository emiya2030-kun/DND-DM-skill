# Fighter Weapon Proficiency Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fighter entities automatically count as proficient with simple and martial weapons when weapon runtime data does not explicitly override proficiency.

**Architecture:** Keep the change local to the weapon-resolution layer so attack flow and other combat systems consume a single resolved `is_proficient` value. Treat explicit runtime `is_proficient` as highest priority, then derive from fighter runtime + weapon category, and finally fall back to `False` for uncategorized or unbound weapons.

**Tech Stack:** Python 3, unittest/pytest, existing `WeaponProfileResolver`, `AttackRollRequest`, encounter runtime models

---

### Task 1: Lock the desired proficiency behavior with tests

**Files:**
- Modify: `test/test_attack_roll_request.py`
- Modify: `test/test_execute_attack.py`

- [ ] **Step 1: Write the failing tests**

Add one request-level test proving fighter auto proficiency:

```python
def test_execute_fighter_auto_applies_martial_weapon_proficiency_from_class_binding(self) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "weapon_definitions": {
                        "rapier": {
                            "id": "rapier",
                            "name": "刺剑",
                            "category": "martial",
                            "kind": "melee",
                            "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                            "properties": ["finesse"],
                            "mastery": "vex",
                            "range": {"normal": 5, "long": 5},
                            "hands": {"mode": "one_handed"},
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        actor = build_actor()
        actor.weapons = [{"weapon_id": "rapier"}]
        actor.class_features = {"fighter": {"fighter_level": 1}}
        repo.save(build_encounter(actor=actor))

        request = AttackRollRequest(
            repo,
            weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
        ).execute(
            encounter_id="enc_attack_request_test",
            target_id="ent_enemy_goblin_001",
            weapon_id="rapier",
        )

        self.assertEqual(request.context["proficiency_bonus"], 2)
        self.assertTrue(request.context["weapon_is_proficient"])
        repo.close()
```

Add one negative test proving non-fighter no longer gets automatic proficiency:

```python
def test_execute_non_fighter_without_explicit_proficiency_does_not_add_martial_weapon_proficiency(self) -> None:
    ...
    actor = build_actor()
    actor.weapons = [{"weapon_id": "rapier"}]
    actor.class_features = {}
    ...
    self.assertEqual(request.context["proficiency_bonus"], 0)
    self.assertFalse(request.context["weapon_is_proficient"])
```

Add one compatibility test proving explicit override still wins:

```python
def test_execute_runtime_weapon_proficiency_override_beats_class_binding(self) -> None:
    ...
    actor.class_features = {"fighter": {"fighter_level": 1}}
    actor.weapons = [{"weapon_id": "rapier", "is_proficient": False}]
    ...
    self.assertEqual(request.context["proficiency_bonus"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest -q \
  test/test_attack_roll_request.py -k "fighter_auto_applies_martial_weapon_proficiency or non_fighter_without_explicit_proficiency or runtime_weapon_proficiency_override"
```

Expected: FAIL because `WeaponProfileResolver` currently defaults missing `is_proficient` to `True`.

### Task 2: Implement automatic fighter weapon proficiency binding

**Files:**
- Modify: `tools/services/combat/attack/weapon_profile_resolver.py`

- [ ] **Step 1: Write the minimal implementation**

Update resolver logic so `resolved["is_proficient"]` comes from:

```python
resolved["is_proficient"] = self._resolve_weapon_proficiency(
    actor=actor,
    runtime_weapon=runtime_weapon,
    resolved_weapon=resolved,
)
```

Add helpers:

```python
def _resolve_weapon_proficiency(
    self,
    *,
    actor: EncounterEntity,
    runtime_weapon: dict[str, Any],
    resolved_weapon: dict[str, Any],
) -> bool:
    explicit = runtime_weapon.get("is_proficient")
    if isinstance(explicit, bool):
        return explicit

    category = str(resolved_weapon.get("category") or "").strip().lower()
    if not category:
        return False

    actor_proficiencies = self._resolve_actor_weapon_proficiencies(actor)
    return category in actor_proficiencies

def _resolve_actor_weapon_proficiencies(self, actor: EncounterEntity) -> set[str]:
    proficiencies: set[str] = set()
    class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
    fighter = class_features.get("fighter")
    if isinstance(fighter, dict):
        proficiencies.update({"simple", "martial"})
        configured = fighter.get("weapon_proficiencies")
        if isinstance(configured, list):
            for item in configured:
                if isinstance(item, str) and item.strip():
                    proficiencies.add(item.strip().lower())
    return proficiencies
```

- [ ] **Step 2: Run the focused tests**

Run:

```bash
python3 -m pytest -q \
  test/test_attack_roll_request.py -k "fighter_auto_applies_martial_weapon_proficiency or non_fighter_without_explicit_proficiency or runtime_weapon_proficiency_override"
```

Expected: PASS

### Task 3: Project fighter weapon proficiencies in encounter state

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`

- [ ] **Step 1: Write the failing projection test**

Add:

```python
def test_execute_projects_fighter_weapon_proficiencies(self) -> None:
    ...
    player.class_features["fighter"]["weapon_proficiencies"] = ["simple", "martial"]
    state = GetEncounterState(repo, event_repo).execute("enc_view_test")
    fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]
    self.assertEqual(fighter["weapon_proficiencies"], ["simple", "martial"])
```

- [ ] **Step 2: Run the projection test to verify it fails**

Run:

```bash
python3 -m pytest -q test/test_get_encounter_state.py -k fighter_weapon_proficiencies -v
```

Expected: FAIL because projection does not include `weapon_proficiencies`.

- [ ] **Step 3: Implement minimal projection**

Extend fighter projection:

```python
"weapon_proficiencies": fighter.get("weapon_proficiencies", ["simple", "martial"]),
```

- [ ] **Step 4: Run focused projection tests**

Run:

```bash
python3 -m pytest -q \
  test/test_get_encounter_state.py -k "fighter_runtime_resources or fighter_weapon_proficiencies"
```

Expected: PASS

### Task 4: Run targeted regression

**Files:**
- No new files

- [ ] **Step 1: Run targeted regressions**

Run:

```bash
python3 -m pytest -q \
  test/test_attack_roll_request.py \
  test/test_execute_attack.py \
  test/test_get_encounter_state.py
```

Expected: PASS
