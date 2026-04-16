import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands.start_random_encounter import start_random_encounter
from runtime.context import build_runtime_context
from tools.models.event import Event


class RuntimeStartRandomEncounterTests(unittest.TestCase):
    def test_start_random_encounter_initializes_map_rolls_initiative_and_returns_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                with patch(
                    "runtime.presets.random_encounters.choose_random_encounter_setup",
                    return_value={
                        "encounter_name": "林间伏击",
                        "map_setup": {
                            "map_id": "map_forest",
                            "name": "林地小径",
                            "description": "树林中的狭窄道路",
                            "width": 20,
                            "height": 20,
                            "grid_size_feet": 5,
                            "terrain": [],
                            "zones": [],
                            "auras": [],
                            "remains": [],
                            "battlemap_details": [{"title": "树林", "summary": "树木遮挡视线"}],
                        },
                        "entity_setups": [
                            {
                                "entity_instance_id": "ent_ally_wizard_001",
                                "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                                "runtime_overrides": {"name": "米伦", "position": {"x": 4, "y": 4}},
                            },
                            {
                                "entity_instance_id": "ent_enemy_brute_001",
                                "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                                "runtime_overrides": {"name": "荒林掠夺者", "position": {"x": 11, "y": 9}},
                            },
                        ],
                    },
                ) as choose_setup:
                    with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[14, 8]):
                        with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.12, 0.03]):
                            result = start_random_encounter(
                                context,
                                {"encounter_id": "enc_runtime_demo", "theme": "forest_road"},
                            )

                choose_setup.assert_called_once_with(theme="forest_road")
                self.assertEqual(result["result"]["encounter_name"], "林间伏击")
                self.assertEqual(result["result"]["map_name"], "林地小径")
                self.assertEqual(result["result"]["current_entity_id"], "ent_ally_wizard_001")
                self.assertEqual(len(result["result"]["initiative_results"]), 2)
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_runtime_demo")
                self.assertEqual(result["encounter_state"]["battlemap_details"]["name"], "林地小径")
                self.assertEqual(
                    result["encounter_state"]["battlemap_details"]["description"],
                    "树林中的狭窄道路",
                )
                self.assertEqual(len(result["encounter_state"]["turn_order"]), 2)
                self.assertEqual(
                    {item["id"] for item in result["encounter_state"]["turn_order"]},
                    {"ent_ally_wizard_001", "ent_enemy_brute_001"},
                )
                self.assertEqual(result["encounter_state"]["current_turn_entity"]["name"], "米伦")
                self.assertEqual(result["encounter_state"]["current_turn_entity"]["position"], "(4, 4)")
                self.assertEqual(result["encounter_state"]["turn_order"][1]["name"], "荒林掠夺者")
                self.assertEqual(result["encounter_state"]["turn_order"][1]["position"], "(11, 9)")
            finally:
                context.close()

    def test_start_random_encounter_clears_stale_events_for_same_encounter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.event_repository.append(
                    Event(
                        event_id="evt_stale_attack",
                        encounter_id="enc_runtime_demo",
                        round=99,
                        event_type="attack_resolved",
                        actor_entity_id="ent_old_actor",
                        target_entity_id="ent_old_target",
                        payload={"summary": "旧日志，不该残留"},
                        created_at="2026-04-16T00:00:00",
                    )
                )

                with patch(
                    "runtime.presets.random_encounters.choose_random_encounter_setup",
                    return_value={
                        "encounter_name": "林间伏击",
                        "map_setup": {
                            "map_id": "map_forest",
                            "name": "林地小径",
                            "description": "树林中的狭窄道路",
                            "width": 20,
                            "height": 20,
                            "grid_size_feet": 5,
                            "terrain": [],
                            "zones": [],
                            "auras": [],
                            "remains": [],
                            "battlemap_details": [{"title": "树林", "summary": "树木遮挡视线"}],
                        },
                        "entity_setups": [
                            {
                                "entity_instance_id": "ent_ally_wizard_001",
                                "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                                "runtime_overrides": {"name": "米伦", "position": {"x": 4, "y": 4}},
                            },
                            {
                                "entity_instance_id": "ent_enemy_brute_001",
                                "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                                "runtime_overrides": {"name": "荒林掠夺者", "position": {"x": 11, "y": 9}},
                            },
                        ],
                    },
                ):
                    with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[14, 8]):
                        with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.12, 0.03]):
                            start_random_encounter(
                                context,
                                {"encounter_id": "enc_runtime_demo", "theme": "forest_road"},
                            )

                remaining_events = context.event_repository.list_by_encounter("enc_runtime_demo")
                self.assertEqual(remaining_events, [])
            finally:
                context.close()
