from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.encounter.turns import EndTurn
from test.test_start_turn import build_encounter


class EndTurnTests(unittest.TestCase):
    def test_execute_keeps_rage_active_when_extended_by_attack_this_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.class_features = {
                "barbarian": {
                    "level": 5,
                    "rage": {
                        "active": True,
                        "remaining": 2,
                        "ends_at_turn_end_of": actor.entity_id,
                    },
                }
            }
            actor.combat_flags["rage_extended_by_attack_this_turn"] = True
            repo.save(encounter)

            updated = EndTurn(repo).execute("enc_start_turn_test")

            self.assertTrue(updated.entities["ent_ally_eric_001"].class_features["barbarian"]["rage"]["active"])
            repo.close()

    def test_execute_ends_rage_when_no_extension_condition_was_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.class_features = {
                "barbarian": {
                    "level": 5,
                    "rage": {
                        "active": True,
                        "remaining": 2,
                        "ends_at_turn_end_of": actor.entity_id,
                    },
                }
            }
            repo.save(encounter)

            updated = EndTurn(repo).execute("enc_start_turn_test")

            self.assertFalse(updated.entities["ent_ally_eric_001"].class_features["barbarian"]["rage"]["active"])
            repo.close()

    def test_execute_persistent_rage_skips_extension_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.class_features = {
                "barbarian": {
                    "level": 15,
                    "rage": {
                        "active": True,
                        "remaining": 0,
                        "ends_at_turn_end_of": actor.entity_id,
                        "persistent_rage": True,
                    },
                }
            }
            repo.save(encounter)

            updated = EndTurn(repo).execute("enc_start_turn_test")

            self.assertTrue(updated.entities["ent_ally_eric_001"].class_features["barbarian"]["rage"]["active"])
            repo.close()

    def test_execute_keeps_current_entity_state_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                updated = EndTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 5)
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            repo.close()

    def test_execute_also_applies_end_of_turn_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_end_fire_001",
                    "name": "回合结束火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "end_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:end_fire", "formula": "1d4", "damage_type": "fire"}],
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
                updated = EndTurn(repo).execute("enc_start_turn_test")

            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 19)
            self.assertEqual(updated.entities["ent_ally_eric_001"].turn_effects, [])
            repo.close()

    def test_execute_can_append_turn_ended_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            EndTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "turn_ended")
            self.assertEqual(events[0].actor_entity_id, "ent_ally_eric_001")
            encounter_repo.close()
            event_repo.close()

    def test_execute_with_state_returns_latest_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=1):
                result = EndTurn(repo).execute_with_state("enc_start_turn_test")

            self.assertEqual(result["encounter_id"], "enc_start_turn_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["id"], "ent_ally_eric_001")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["movement_remaining"], "5 feet")
            self.assertTrue(result["encounter_state"]["current_turn_entity"]["actions"]["action_used"])
            repo.close()

    def test_execute_with_state_returns_end_of_turn_effect_resolutions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_end_fire_001",
                    "name": "回合结束火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "end_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:end_fire", "formula": "1d4", "damage_type": "fire"}],
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
                result = EndTurn(repo).execute_with_state("enc_start_turn_test")

            self.assertEqual(len(result["turn_effect_resolutions"]), 1)
            self.assertEqual(result["turn_effect_resolutions"][0]["trigger"], "end_of_turn")
            repo.close()

    def test_execute_appends_turn_effect_resolved_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].turn_effects = [
                {
                    "effect_id": "effect_end_fire_001",
                    "name": "回合结束火焰灼烧",
                    "source_entity_id": "ent_ally_lia_001",
                    "trigger": "end_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [{"source": "effect:end_fire", "formula": "1d4", "damage_type": "fire"}],
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
                EndTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].event_type, "turn_effect_resolved")
            self.assertEqual(events[0].actor_entity_id, "ent_ally_lia_001")
            self.assertEqual(events[0].target_entity_id, "ent_ally_eric_001")
            self.assertEqual(events[0].payload["effect_id"], "effect_end_fire_001")
            self.assertEqual(events[0].payload["trigger"], "end_of_turn")
            self.assertEqual(events[1].event_type, "turn_ended")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_end_of_turn_zone_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.position = {"x": 3, "y": 3}
            encounter.map.zones = [
                {
                    "zone_id": "zone_poison_001",
                    "type": "hazard_area",
                    "name": "毒雾区",
                    "cells": [[3, 3]],
                    "note": "回合结束时吸入毒雾。",
                    "runtime": {
                        "source_entity_id": "zone_source_poison",
                        "source_name": "毒雾区",
                        "triggers": [
                            {
                                "timing": "end_of_turn_inside",
                                "effect": {
                                    "damage_parts": [],
                                    "apply_conditions": ["poisoned"],
                                    "remove_conditions": [],
                                },
                            }
                        ],
                    },
                }
            ]
            encounter_repo.save(encounter)

            EndTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            updated = encounter_repo.get("enc_start_turn_test")
            assert updated is not None
            self.assertIn("poisoned", updated.entities["ent_ally_eric_001"].conditions)
            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(events[0].event_type, "zone_effect_resolved")
            self.assertEqual(events[0].payload["zone_id"], "zone_poison_001")
            self.assertEqual(events[0].payload["trigger"], "end_of_turn_inside")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_end_of_turn_zone_save_effect_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.position = {"x": 3, "y": 3}
            actor.ability_mods = {"str": 0, "dex": 2, "con": 0, "int": 0, "wis": 0, "cha": 0}
            encounter.map.zones = [
                {
                    "zone_id": "zone_fire_001",
                    "type": "hazard_area",
                    "name": "火焰灼域",
                    "cells": [[3, 3]],
                    "note": "回合结束时会烧伤。",
                    "runtime": {
                        "source_entity_id": "zone_source_fire",
                        "source_name": "火焰灼域",
                        "triggers": [
                            {
                                "timing": "end_of_turn_inside",
                                "save": {"ability": "dex", "dc": 14},
                                "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                                "on_save_failure": {
                                    "damage_parts": [{"source": "zone:fire:failure", "formula": "1d4", "type": "fire"}],
                                    "apply_conditions": [],
                                    "remove_conditions": [],
                                },
                            }
                        ],
                    },
                }
            ]
            encounter_repo.save(encounter)

            with patch("tools.services.encounter.zones.zone_effects.turn_effect_runtime.random.randint", return_value=1):
                EndTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            updated = encounter_repo.get("enc_start_turn_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 19)
            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertEqual(events[0].event_type, "zone_effect_resolved")
            self.assertFalse(events[0].payload["save"]["success"])
            self.assertEqual(events[0].payload["failure_damage_resolution"]["total_damage"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_end_of_turn_zone_save_effect_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_eric_001"]
            actor.position = {"x": 3, "y": 3}
            actor.ability_mods = {"str": 0, "dex": 2, "con": 0, "int": 0, "wis": 0, "cha": 0}
            encounter.map.zones = [
                {
                    "zone_id": "zone_frost_001",
                    "type": "hazard_area",
                    "name": "寒霜领域",
                    "cells": [[3, 3]],
                    "note": "回合结束时冻结。",
                    "runtime": {
                        "source_entity_id": "zone_source_frost",
                        "source_name": "寒霜领域",
                        "triggers": [
                            {
                                "timing": "end_of_turn_inside",
                                "save": {"ability": "dex", "dc": 12},
                                "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                                "on_save_success": {
                                    "damage_parts": [],
                                    "apply_conditions": ["restrained"],
                                    "remove_conditions": [],
                                },
                                "on_save_failure": {
                                    "damage_parts": [],
                                    "apply_conditions": [],
                                    "remove_conditions": [],
                                },
                            }
                        ],
                    },
                }
            ]
            encounter_repo.save(encounter)

            with patch("tools.services.encounter.zones.zone_effects.turn_effect_runtime.random.randint", return_value=10):
                EndTurn(encounter_repo, AppendEvent(event_repo)).execute("enc_start_turn_test")

            updated = encounter_repo.get("enc_start_turn_test")
            assert updated is not None
            self.assertIn("restrained", updated.entities["ent_ally_eric_001"].conditions)
            events = event_repo.list_by_encounter("enc_start_turn_test")
            self.assertTrue(events[0].payload["save"]["success"])
            self.assertEqual(events[0].payload["condition_updates"][0]["condition"], "restrained")
            encounter_repo.close()
            event_repo.close()
