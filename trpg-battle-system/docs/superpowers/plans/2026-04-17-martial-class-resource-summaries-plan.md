# Martial Class Resource Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project concise martial-class resource summaries for monk, rogue, paladin, barbarian, and ranger without leaking backend-only state while keeping the existing fighter projection intact.

**Architecture:** Add a data-driven projection map keyed by `class_id` that names the whitelisted fields and canonical `available_features` per martial class, then reuse that map inside `_build_class_feature_resource_view` to copy only dialed-in summary fields. Keep the fighter path untouched except for unifying it under the map when helpful.

**Tech Stack:** Python 3, unittest, existing encounter services and tests already covering `GetEncounterState`.

---

### Task 1: Project martial class resource summaries

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py#_build_class_feature_resource_view`
- Modify: `test/test_get_encounter_state.py#GetEncounterStateTests`

- [ ] **Step 1: Write the failing test(s)**

```python
    def test_execute_projects_summaries_for_martial_classes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features.update({
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 4},
                    "martial_arts_die": "1d8",
                    "unarmored_movement_bonus_feet": 10,
                },
                "rogue": {
                    "level": 5,
                    "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False},
                },
                "paladin": {"level": 5, "divine_smite": {"enabled": True}},
                "barbarian": {"level": 4, "rage": {"remaining": 2, "max": 3}},
                "ranger": {"level": 4},
            })
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            resources = state["current_turn_entity"]["resources"]["class_features"]

            monk = resources["monk"]
            self.assertEqual(monk["focus_points"]["remaining"], 4)
            self.assertEqual(monk["martial_arts_die"], "1d8")
            self.assertIn("stunning_strike", monk["available_features"])

            rogue = resources["rogue"]
            self.assertEqual(rogue["level"], 5)
            self.assertEqual(rogue["sneak_attack"]["damage_dice"], "3d6")
            self.assertIn("sneak_attack", rogue["available_features"])

            self.assertEqual(resources["paladin"]["level"], 5)
            self.assertEqual(resources["barbarian"]["rage"]["remaining"], 2)
            self.assertIn("divine_smite", resources["paladin"]["available_features"])
            self.assertEqual(resources["ranger"]["level"], 4)

            repo.close()
            event_repo.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest -v test.test_get_encounter_state:GetEncounterStateTests.test_execute_projects_summaries_for_martial_classes
```

Expected: FAIL because `_build_class_feature_resource_view` currently only returns fighter data.

- [ ] **Step 3: Write minimal implementation**

```python
MARTIAL_CLASS_SUMMARIES = {
    "monk": {
        "fields": [
            "level",
            "focus_points",
            "martial_arts_die",
            "unarmored_movement_bonus_feet",
        ],
        "available_features": [
            "martial_arts",
            "flurry_of_blows",
            "patient_defense",
            "step_of_the_wind",
            "stunning_strike",
        ],
    },
    "rogue": {
        "fields": ["level", "sneak_attack"],
        "available_features": ["sneak_attack", "cunning_action"],
    },
    "paladin": {
        "fields": ["level", "divine_smite"],
        "available_features": ["divine_smite", "lay_on_hands"],
    },
    "barbarian": {
        "fields": ["level", "rage"],
        "available_features": ["rage", "reckless_attack", "danger_sense"],
    },
    "ranger": {
        "fields": ["level"],
        "available_features": ["favored_enemy", "weapon_mastery"],
    },
}

class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
projected: dict[str, Any] = {}
for class_id, summary in MARTIAL_CLASS_SUMMARIES.items():
    bucket = class_features.get(class_id)
    if not isinstance(bucket, dict):
        continue
    projected[class_id] = {field: bucket[field] for field in summary["fields"] if field in bucket}
    projected[class_id]["available_features"] = summary["available_features"]
fighter = class_features.get("fighter")
if isinstance(fighter, dict):
    fighter_view = dict(fighter)
    fighter_view.pop("weapon_proficiencies", None)
    fighter_view.pop("armor_training", None)
    projected["fighter"] = fighter_view
return projected
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest -v test.test_get_encounter_state:GetEncounterStateTests.test_execute_projects_summaries_for_martial_classes
```

Expected: PASS now that summaries and `available_features` are projected.

- [ ] **Step 5: Commit**

```bash
git add tools/services/encounter/get_encounter_state.py test/test_get_encounter_state.py
git commit -m "feat: expose martial class resource summaries"
```
