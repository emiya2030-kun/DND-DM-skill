from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.encounter.turns.turn_engine import advance_turn, end_turn, start_turn


def build_entity(
    entity_id: str,
    *,
    name: str,
    initiative: int,
    speed_walk: int = 30,
    speed_remaining: int = 30,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": speed_walk, "remaining": speed_remaining},
        initiative=initiative,
    )


def build_encounter_with_two_entities(*, current_entity_id: str | None = "ent_ally_eric_001") -> Encounter:
    entity_a = build_entity("ent_ally_eric_001", name="Eric", initiative=15)
    entity_b = build_entity("ent_ally_lia_001", name="Lia", initiative=12)
    return Encounter(
        encounter_id="enc_turn_engine_test",
        name="Turn Engine Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[entity_a.entity_id, entity_b.entity_id],
        entities={entity_a.entity_id: entity_a, entity_b.entity_id: entity_b},
        map=EncounterMap(
            map_id="map_turn_engine_test",
            name="Turn Engine Test Map",
            description="A map used by turn engine tests.",
            width=10,
            height=10,
        ),
    )


def test_start_turn_resets_fighter_turn_counters() -> None:
    encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
    fighter_entity = encounter.entities["ent_ally_eric_001"]
    fighter_entity.class_features = {
        "fighter": {
            "turn_counters": {"attack_action_attacks_used": 2},
            "action_surge": {"remaining_uses": 1, "used_this_turn": True},
            "temporary_bonuses": {"extra_non_magic_action_available": 1},
        }
    }

    updated = start_turn(encounter)
    fighter = updated.entities["ent_ally_eric_001"].class_features["fighter"]
    assert fighter["turn_counters"]["attack_action_attacks_used"] == 0
    assert fighter["action_surge"]["used_this_turn"] is False
    assert fighter["temporary_bonuses"]["extra_non_magic_action_available"] == 0


def test_start_turn_without_fighter_runtime_does_not_raise() -> None:
    encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
    encounter.entities["ent_ally_eric_001"].class_features = {}

    updated = start_turn(encounter)

    assert updated.entities["ent_ally_eric_001"].class_features == {}


def test_start_turn_still_resets_action_and_movement_when_fighter_runtime_exists() -> None:
    encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
    entity = encounter.entities["ent_ally_eric_001"]
    entity.action_economy = {
        "action_used": True,
        "bonus_action_used": True,
        "reaction_used": True,
        "free_interaction_used": True,
    }
    entity.speed["remaining"] = 5
    entity.combat_flags["movement_spent_feet"] = 25
    entity.class_features = {
        "fighter": {
            "turn_counters": {"attack_action_attacks_used": 3},
            "action_surge": {"remaining_uses": 1, "used_this_turn": True},
            "temporary_bonuses": {"extra_non_magic_action_available": 1},
        }
    }

    updated = start_turn(encounter)

    assert updated.entities["ent_ally_eric_001"].action_economy["action_used"] is False
    assert updated.entities["ent_ally_eric_001"].action_economy["bonus_action_used"] is False
    assert updated.entities["ent_ally_eric_001"].speed["remaining"] == 30
    assert updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"] == 0


def test_start_turn_does_not_create_missing_fighter_turn_reset_buckets() -> None:
    encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
    entity = encounter.entities["ent_ally_eric_001"]
    entity.class_features = {"fighter": {"level": 3}}

    updated = start_turn(encounter)

    fighter = updated.entities["ent_ally_eric_001"].class_features["fighter"]
    assert "turn_counters" not in fighter
    assert "action_surge" not in fighter
    assert "temporary_bonuses" not in fighter


class TurnEngineTests(unittest.TestCase):
    def test_end_turn_requires_current_entity(self) -> None:
        encounter = build_encounter_with_two_entities(current_entity_id=None)

        with self.assertRaisesRegex(ValueError, "cannot end turn without current_entity_id"):
            end_turn(encounter)

    def test_end_turn_keeps_current_entity_and_resources_unchanged(self) -> None:
        encounter = build_encounter_with_two_entities()
        current = encounter.entities["ent_ally_eric_001"]
        current.action_economy = {"action_used": True, "reaction_used": True}
        current.speed["remaining"] = 5
        current.combat_flags["movement_spent_feet"] = 25

        updated = end_turn(encounter)

        self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
        self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
        self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 5)
        self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 25)

    def test_advance_turn_requires_turn_order(self) -> None:
        encounter = build_encounter_with_two_entities()
        encounter.turn_order = []

        with self.assertRaisesRegex(ValueError, "cannot advance turn without turn_order"):
            advance_turn(encounter)

    def test_advance_turn_switches_to_next_entity_without_resetting_resources(self) -> None:
        encounter = build_encounter_with_two_entities()
        current = encounter.entities["ent_ally_eric_001"]
        current.action_economy = {
            "action_used": True,
            "bonus_action_used": True,
            "reaction_used": True,
            "free_interaction_used": True,
        }
        current.speed["remaining"] = 5
        current.combat_flags["movement_spent_feet"] = 25

        next_entity = encounter.entities["ent_ally_lia_001"]
        next_entity.action_economy = {
            "action_used": True,
            "bonus_action_used": True,
            "reaction_used": True,
            "free_interaction_used": True,
        }
        next_entity.speed["remaining"] = 0
        next_entity.combat_flags["movement_spent_feet"] = 30

        updated = advance_turn(encounter)

        self.assertEqual(updated.current_entity_id, "ent_ally_lia_001")
        self.assertEqual(updated.round, 1)
        self.assertTrue(updated.entities["ent_ally_lia_001"].action_economy["action_used"])
        self.assertEqual(updated.entities["ent_ally_lia_001"].speed["remaining"], 0)
        self.assertEqual(updated.entities["ent_ally_lia_001"].combat_flags["movement_spent_feet"], 30)

    def test_advance_turn_wraps_to_first_entity_and_increments_round(self) -> None:
        encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_lia_001")

        updated = advance_turn(encounter)

        self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
        self.assertEqual(updated.round, 2)

    def test_start_turn_with_no_current_entity_selects_first_and_resets_it(self) -> None:
        encounter = build_encounter_with_two_entities(current_entity_id=None)
        encounter.entities["ent_ally_eric_001"].action_economy = {"action_used": True}
        encounter.entities["ent_ally_eric_001"].speed["remaining"] = 0
        encounter.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"] = 30

        updated = start_turn(encounter)

        self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
        self.assertEqual(updated.round, 1)
        self.assertEqual(updated.entities["ent_ally_eric_001"].action_economy["action_used"], False)
        self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
        self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)

    def test_start_turn_resets_current_entity_resources(self) -> None:
        encounter = build_encounter_with_two_entities()
        entity = encounter.entities["ent_ally_eric_001"]
        entity.action_economy = {"action_used": True, "reaction_used": True}
        entity.speed["remaining"] = 10
        entity.combat_flags["movement_spent_feet"] = 20

        updated = start_turn(encounter)

        self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
        self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy["reaction_used"])
        self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
        self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)

    def test_start_turn_tolerates_dirty_combat_flags(self) -> None:
        encounter = build_encounter_with_two_entities()
        entity = encounter.entities["ent_ally_eric_001"]
        entity.combat_flags = None

        updated = start_turn(encounter)

        self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)

    def test_start_turn_clears_light_bonus_trigger(self) -> None:
        encounter = build_encounter_with_two_entities()
        entity = encounter.entities["ent_ally_eric_001"]
        entity.combat_flags = {
            "movement_spent_feet": 15,
            "light_bonus_trigger": {"weapon_id": "shortsword", "slot": "main_hand"},
        }

        updated = start_turn(encounter)

        self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)
        self.assertNotIn("light_bonus_trigger", updated.entities["ent_ally_eric_001"].combat_flags)

    def test_start_turn_resets_rogue_sneak_attack_flag(self) -> None:
        encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
        entity = encounter.entities["ent_ally_eric_001"]
        entity.class_features = {
            "rogue": {
                "level": 5,
                "sneak_attack": {"damage_dice": "3d6", "used_this_turn": True},
            }
        }

        updated = start_turn(encounter)

        rogue = updated.entities["ent_ally_eric_001"].class_features["rogue"]
        self.assertFalse(rogue["sneak_attack"]["used_this_turn"])

    def test_start_turn_resets_monk_stunning_strike_uses_this_turn(self) -> None:
        encounter = build_encounter_with_two_entities(current_entity_id="ent_ally_eric_001")
        entity = encounter.entities["ent_ally_eric_001"]
        entity.class_features = {
            "monk": {
                "level": 5,
                "focus_points": {"max": 5, "remaining": 4},
                "stunning_strike": {"uses_this_turn": 1, "max_per_turn": 1},
            }
        }

        updated = start_turn(encounter)

        monk = updated.entities["ent_ally_eric_001"].class_features["monk"]
        self.assertEqual(monk["stunning_strike"]["uses_this_turn"], 0)
