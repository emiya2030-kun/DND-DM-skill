import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.commands.start_random_encounter import start_random_encounter
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command


class RuntimeCastSpellTests(unittest.TestCase):
    def test_cast_spell_command_executes_hold_person_without_external_rolls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                with patch(
                    "tools.services.encounter.roll_initiative_and_start_encounter.randint",
                    side_effect=[17, 4],
                ):
                    with patch(
                        "tools.services.encounter.roll_initiative_and_start_encounter.random",
                        side_effect=[0.21, 0.08],
                    ):
                        start_random_encounter(
                            context,
                            {"encounter_id": "enc_runtime_spell_demo", "theme": "forest_road"},
                        )

                with patch(
                    "tools.services.spells.execute_spell.random.randint",
                    return_value=3,
                ):
                    result = execute_runtime_command(
                        context,
                        command="cast_spell",
                        args={
                            "encounter_id": "enc_runtime_spell_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "spell_id": "hold_person",
                            "cast_level": 2,
                            "target_entity_ids": ["ent_enemy_brute_001"],
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["command"], "cast_spell")
                self.assertEqual(result["result"]["spell_id"], "hold_person")
                self.assertEqual(result["result"]["spell_resolution"]["mode"], "save_condition")

                updated = context.encounter_repository.get("enc_runtime_spell_demo")
                self.assertIsNotNone(updated)
                self.assertIn("paralyzed", updated.entities["ent_enemy_brute_001"].conditions)
                self.assertEqual(
                    result["result"]["spell_resolution"]["targets"][0]["save"]["final_total"],
                    3,
                )

                recent_activity = result["encounter_state"]["recent_activity"]
                self.assertTrue(
                    any(item["event_type"] == "spell_declared" for item in recent_activity),
                    recent_activity,
                )
                self.assertTrue(
                    any(item["event_type"] == "saving_throw_resolved" for item in recent_activity),
                    recent_activity,
                )
            finally:
                context.close()

    def test_cast_spell_command_executes_fireball_without_external_rolls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                with patch(
                    "tools.services.encounter.roll_initiative_and_start_encounter.randint",
                    side_effect=[17, 4],
                ):
                    with patch(
                        "tools.services.encounter.roll_initiative_and_start_encounter.random",
                        side_effect=[0.21, 0.08],
                    ):
                        start_random_encounter(
                            context,
                            {"encounter_id": "enc_runtime_spell_demo", "theme": "forest_road"},
                        )

                with patch(
                    "tools.services.spells.execute_spell.random.randint",
                    side_effect=[6, 5, 4, 3, 2, 1, 6, 5, 7],
                ):
                    result = execute_runtime_command(
                        context,
                        command="cast_spell",
                        args={
                            "encounter_id": "enc_runtime_spell_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "spell_id": "fireball",
                            "cast_level": 3,
                            "target_point": {"x": 11, "y": 9},
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["result"]["spell_id"], "fireball")
                self.assertEqual(result["result"]["spell_resolution"]["mode"], "save_damage")

                updated = context.encounter_repository.get("enc_runtime_spell_demo")
                self.assertIsNotNone(updated)
                self.assertEqual(updated.entities["ent_enemy_brute_001"].hp["current"], 13)

                target_resolution = result["result"]["spell_resolution"]["targets"][0]
                self.assertEqual(target_resolution["save"]["final_total"], 8)
                self.assertEqual(target_resolution["damage_resolution"]["total_damage"], 32)

                recent_activity = result["encounter_state"]["recent_activity"]
                self.assertTrue(
                    any(item["event_type"] == "spell_declared" for item in recent_activity),
                    recent_activity,
                )
                self.assertTrue(
                    any(item["event_type"] == "saving_throw_resolved" for item in recent_activity),
                    recent_activity,
                )
            finally:
                context.close()
