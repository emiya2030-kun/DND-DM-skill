from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.encounter.turns import StartTurn


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


def build_encounter(*, current_entity_id: str | None = "ent_ally_eric_001") -> Encounter:
    entity_a = build_entity("ent_ally_eric_001", name="Eric", initiative=15)
    entity_a.action_economy = {"action_used": True, "reaction_used": True}
    entity_a.speed["remaining"] = 5
    entity_a.combat_flags["movement_spent_feet"] = 25
    entity_b = build_entity("ent_ally_lia_001", name="Lia", initiative=12)
    return Encounter(
        encounter_id="enc_start_turn_test",
        name="Start Turn Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[entity_a.entity_id, entity_b.entity_id],
        entities={entity_a.entity_id: entity_a, entity_b.entity_id: entity_b},
        map=EncounterMap(
            map_id="map_start_turn_test",
            name="Start Turn Test Map",
            description="A map used by start turn tests.",
            width=10,
            height=10,
        ),
    )


class StartTurnTests(unittest.TestCase):
    def test_execute_keeps_slowed_speed_penalty_on_target_turn_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter(current_entity_id="ent_ally_lia_001")
            encounter.entities["ent_ally_lia_001"].side = "enemy"
            encounter.entities["ent_ally_lia_001"].turn_effects = [
                {
                    "effect_id": "effect_mastery_slow_001",
                    "effect_type": "weapon_mastery",
                    "mastery": "slow",
                    "name": "Slow",
                    "source_entity_id": "ent_ally_eric_001",
                    "target_entity_id": "ent_ally_lia_001",
                    "expires_on": "start_of_source_turn",
                    "speed_penalty_feet": 10,
                }
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.entities["ent_ally_lia_001"].speed["remaining"], 20)
            repo.close()

    def test_execute_removes_expired_mastery_effects_when_source_turn_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter(current_entity_id="ent_ally_eric_001")
            encounter.entities["ent_ally_lia_001"].side = "enemy"
            encounter.entities["ent_ally_lia_001"].turn_effects = [
                {
                    "effect_id": "effect_mastery_slow_001",
                    "effect_type": "weapon_mastery",
                    "mastery": "slow",
                    "name": "Slow",
                    "source_entity_id": "ent_ally_eric_001",
                    "target_entity_id": "ent_ally_lia_001",
                    "expires_on": "start_of_source_turn",
                    "speed_penalty_feet": 10,
                }
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.entities["ent_ally_lia_001"].turn_effects, [])
            repo.close()

    def test_execute_resets_current_entity_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
            self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)
            repo.close()

    def test_execute_also_applies_start_of_turn_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_start_fire_001",
                    "name": "回合开始火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "start_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:start_fire", "formula": "1d4", "damage_type": "fire"}],
                        "apply_conditions": [],
                        "remove_conditions": [],
                    },
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": True,
                }
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 19)
            self.assertEqual(updated.entities["ent_ally_eric_001"].turn_effects, [])
            repo.close()

    def test_execute_removes_shield_ac_bonus_on_target_turn_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].ac = 19
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_shield_001",
                    "effect_type": "shield_ac_bonus",
                    "name": "Shield",
                    "source_entity_id": "ent_ally_eric_001",
                    "target_entity_id": "ent_ally_eric_001",
                    "trigger": "start_of_turn",
                    "ac_bonus": 5,
                    "save": None,
                    "on_trigger": {},
                    "on_save_success": {},
                    "on_save_failure": {},
                    "remove_after_trigger": True,
                }
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.entities["ent_ally_eric_001"].ac, 14)
            self.assertEqual(updated.entities["ent_ally_eric_001"].turn_effects, [])
            repo.close()

    def test_execute_with_state_returns_latest_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                result = StartTurn(repo).execute_with_state("enc_start_turn_test")

            self.assertEqual(result["encounter_id"], "enc_start_turn_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["id"], "ent_ally_eric_001")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["movement_remaining"], "30 feet")
            self.assertFalse(result["encounter_state"]["current_turn_entity"]["actions"]["action_used"])
            repo.close()

    def test_execute_with_state_returns_start_of_turn_effect_resolutions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_start_fire_001",
                    "name": "回合开始火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "start_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:start_fire", "formula": "1d4", "damage_type": "fire"}],
                        "apply_conditions": [],
                        "remove_conditions": [],
                    },
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": True,
                }
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                result = StartTurn(repo).execute_with_state("enc_start_turn_test")

            self.assertEqual(len(result["turn_effect_resolutions"]), 1)
            self.assertEqual(result["turn_effect_resolutions"][0]["trigger"], "start_of_turn")
            repo.close()

    def test_execute_appends_turn_effect_resolved_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_start_fire_001",
                    "name": "回合开始火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "start_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:start_fire", "formula": "1d4", "damage_type": "fire"}],
                        "apply_conditions": [],
                        "remove_conditions": [],
                    },
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": True,
                }
            ]
            encounter_repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                StartTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "turn_effect_resolved")
            self.assertEqual(events[0].actor_entity_id, "ent_ally_lia_001")
            self.assertEqual(events[0].target_entity_id, "ent_ally_eric_001")
            self.assertEqual(events[0].payload["effect_id"], "effect_start_fire_001")
            self.assertEqual(events[0].payload["trigger"], "start_of_turn")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_start_of_turn_zone_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.position = {"x": 3, "y": 3}
            encounter.map.zones = [
                {
                    "zone_id": "zone_frost_001",
                    "type": "hazard_area",
                    "name": "寒霜领域",
                    "cells": [[3, 3]],
                    "note": "回合开始时被冻结。",
                    "runtime": {
                        "source_entity_id": "zone_source_frost",
                        "source_name": "寒霜领域",
                        "triggers": [
                            {
                                "timing": "start_of_turn_inside",
                                "effect": {
                                    "damage_parts": [],
                                    "apply_conditions": ["restrained"],
                                    "remove_conditions": [],
                                },
                            }
                        ],
                    },
                }
            ]
            encounter_repo.save(encounter)

            StartTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            updated = encounter_repo.get("enc_start_turn_test")
            assert updated is not None
            self.assertIn("restrained", updated.entities["ent_ally_eric_001"].conditions)
            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(events[0].event_type, "zone_effect_resolved")
            self.assertEqual(events[0].payload["zone_id"], "zone_frost_001")
            self.assertEqual(events[0].payload["trigger"], "start_of_turn_inside")
            encounter_repo.close()
            event_repo.close()

    def test_execute_rolls_death_save_for_unconscious_zero_hp_pc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.hp["current"] = 0
            actor.conditions = ["unconscious"]
            actor.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
            actor.combat_flags["is_dead"] = False
            repo.save(encounter)

            death_save_module = importlib.import_module(
                "tools.services.combat.rules.death_saves.resolve_death_save"
            )
            with patch.object(death_save_module.random, "randint", return_value=12):
                result = StartTurn(repo).execute_with_state("enc_start_turn_test")

            updated = repo.get("enc_start_turn_test")
            assert updated is not None
            updated_actor = updated.entities["ent_ally_eric_001"]
            self.assertEqual(updated_actor.combat_flags["death_saves"]["successes"], 1)
            self.assertEqual(result["turn_effect_resolutions"][-1]["type"], "death_save")
            self.assertEqual(result["turn_effect_resolutions"][-1]["outcome"], "death_save_success")
            repo.close()

    def test_execute_revives_target_on_third_death_save_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.hp["current"] = 0
            actor.conditions = ["unconscious"]
            actor.combat_flags["death_saves"] = {"successes": 2, "failures": 0}
            actor.combat_flags["is_dead"] = False
            repo.save(encounter)

            death_save_module = importlib.import_module(
                "tools.services.combat.rules.death_saves.resolve_death_save"
            )
            with patch.object(death_save_module.random, "randint", return_value=14):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            updated_actor = updated.entities["ent_ally_eric_001"]
            self.assertEqual(updated_actor.hp["current"], 1)
            self.assertNotIn("unconscious", updated_actor.conditions)
            self.assertEqual(updated_actor.combat_flags["death_saves"], {"successes": 0, "failures": 0})
            self.assertFalse(updated_actor.combat_flags["is_dead"])
            repo.close()

    def test_execute_requires_three_failures_even_with_mixed_death_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.hp["current"] = 0
            actor.conditions = ["unconscious"]
            actor.combat_flags["death_saves"] = {"successes": 1, "failures": 1}
            actor.combat_flags["is_dead"] = False
            repo.save(encounter)

            death_save_module = importlib.import_module(
                "tools.services.combat.rules.death_saves.resolve_death_save"
            )
            with patch.object(death_save_module.random, "randint", return_value=5):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            updated_actor = updated.entities["ent_ally_eric_001"]
            self.assertEqual(updated_actor.combat_flags["death_saves"]["successes"], 1)
            self.assertEqual(updated_actor.combat_flags["death_saves"]["failures"], 2)
            self.assertFalse(updated_actor.combat_flags["is_dead"])
            repo.close()

    def test_execute_marks_dead_on_third_death_save_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.hp["current"] = 0
            actor.conditions = ["unconscious"]
            actor.combat_flags["death_saves"] = {"successes": 0, "failures": 2}
            actor.combat_flags["is_dead"] = False
            repo.save(encounter)

            death_save_module = importlib.import_module(
                "tools.services.combat.rules.death_saves.resolve_death_save"
            )
            with patch.object(death_save_module.random, "randint", return_value=3):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            updated_actor = updated.entities["ent_ally_eric_001"]
            self.assertEqual(updated_actor.combat_flags["death_saves"]["failures"], 3)
            self.assertTrue(updated_actor.combat_flags["is_dead"])
            self.assertEqual(updated_actor.hp["current"], 0)
            repo.close()

    def test_execute_skips_death_save_when_knockout_protection_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.hp["current"] = 0
            actor.conditions = ["unconscious"]
            actor.combat_flags["death_saves"] = {"successes": 1, "failures": 1}
            actor.combat_flags["is_dead"] = False
            actor.turn_effects.append({"effect_type": "knockout_protection"})
            repo.save(encounter)

            death_save_module = importlib.import_module(
                "tools.services.combat.rules.death_saves.resolve_death_save"
            )
            with patch.object(death_save_module.random, "randint", return_value=18):
                result = StartTurn(repo).execute_with_state("enc_start_turn_test")

            updated = repo.get("enc_start_turn_test")
            assert updated is not None
            updated_actor = updated.entities["ent_ally_eric_001"]
            self.assertEqual(updated_actor.combat_flags["death_saves"], {"successes": 1, "failures": 1})
            self.assertEqual(result["turn_effect_resolutions"], [])
            repo.close()

    def test_execute_clears_disengage_and_dodge_effects_on_current_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {"effect_id": "effect_disengage_001", "effect_type": "disengage", "name": "Disengage"},
                {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"},
                {"effect_id": "effect_other_001", "effect_type": "knockout_protection", "name": "Knockout"},
            ]
            repo.save(encounter)

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = StartTurn(repo).execute("enc_start_turn_test")

            effect_types = [effect.get("effect_type") for effect in updated.entities["ent_ally_eric_001"].turn_effects]
            self.assertNotIn("disengage", effect_types)
            self.assertNotIn("dodge", effect_types)
            self.assertIn("knockout_protection", effect_types)
            repo.close()

    def test_execute_expires_help_effects_created_by_current_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            ally = EncounterEntity(
                entity_id="ent_ally_lia_001",
                name="Lia",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 3},
                hp={"current": 18, "max": 18, "temp": 0},
                ac=14,
                speed={"walk": 30, "remaining": 30},
                initiative=9,
                turn_effects=[],
            )
            enemy = EncounterEntity(
                entity_id="ent_enemy_goblin_001",
                name="Goblin",
                side="enemy",
                category="monster",
                controller="gm",
                position={"x": 3, "y": 2},
                hp={"current": 9, "max": 9, "temp": 0},
                ac=13,
                speed={"walk": 30, "remaining": 30},
                initiative=8,
                turn_effects=[],
            )
            ally.turn_effects.append(
                {
                    "effect_id": "help_check_1",
                    "effect_type": "help_ability_check",
                    "source_entity_id": "ent_ally_eric_001",
                    "expires_on": "source_next_turn_start",
                }
            )
            enemy.turn_effects.append(
                {
                    "effect_id": "help_attack_1",
                    "effect_type": "help_attack",
                    "source_entity_id": "ent_ally_eric_001",
                    "expires_on": "source_next_turn_start",
                }
            )
            encounter.entities[ally.entity_id] = ally
            encounter.entities[enemy.entity_id] = enemy
            encounter.turn_order = ["ent_ally_eric_001", ally.entity_id, enemy.entity_id]
            repo.save(encounter)

            updated = StartTurn(repo).execute("enc_start_turn_test")

            self.assertFalse(any(effect.get("effect_id") == "help_check_1" for effect in updated.entities[ally.entity_id].turn_effects))
            self.assertFalse(any(effect.get("effect_id") == "help_attack_1" for effect in updated.entities[enemy.entity_id].turn_effects))
            repo.close()
