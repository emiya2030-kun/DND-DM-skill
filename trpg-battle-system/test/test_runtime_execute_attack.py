import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeExecuteAttackTests(unittest.TestCase):
    def test_execute_attack_runs_normal_attack_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "request": {"encounter_id": "enc_preview_demo"},
                        "roll_result": {"final_total": 16},
                        "resolution": {"hit": True},
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ) as mocked_execute:
                    result = execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "dagger",
                        },
                    )

                self.assertEqual(result["encounter_id"], "enc_preview_demo")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["actor_id"], "ent_ally_wizard_001")
                self.assertEqual(kwargs["target_id"], "ent_enemy_brute_001")
                self.assertEqual(kwargs["weapon_id"], "dagger")
                self.assertTrue(kwargs["include_encounter_state"])
            finally:
                context.close()

    def test_execute_attack_passes_opportunity_attack_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "request": {"encounter_id": "enc_preview_demo"},
                        "roll_result": {"final_total": 16},
                        "resolution": {"hit": True},
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ) as mocked_execute:
                    execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_enemy_brute_001",
                            "target_id": "ent_ally_wizard_001",
                            "weapon_id": "dagger",
                            "allow_out_of_turn_actor": True,
                            "consume_action": False,
                            "consume_reaction": True,
                        },
                    )

                _, kwargs = mocked_execute.call_args
                self.assertTrue(kwargs["allow_out_of_turn_actor"])
                self.assertFalse(kwargs["consume_action"])
                self.assertTrue(kwargs["consume_reaction"])
            finally:
                context.close()

    def test_execute_attack_passes_light_bonus_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "request": {"encounter_id": "enc_preview_demo"},
                        "roll_result": {"final_total": 16},
                        "resolution": {"hit": True},
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ) as mocked_execute:
                    execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "dagger",
                            "attack_mode": "light_bonus",
                        },
                    )

                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["attack_mode"], "light_bonus")
            finally:
                context.close()

    def test_execute_attack_passes_thrown_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "request": {"encounter_id": "enc_preview_demo"},
                        "roll_result": {"final_total": 16},
                        "resolution": {"hit": True},
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ) as mocked_execute:
                    execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "dagger",
                            "attack_mode": "thrown",
                        },
                    )

                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["attack_mode"], "thrown")
            finally:
                context.close()

    def test_execute_attack_returns_invalid_attack_payload_without_transport_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "status": "invalid_attack",
                        "reason": "target_out_of_range",
                        "message_for_llm": "当前目标不在攻击范围内，请重新选择目标。",
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    result = execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "dagger",
                        },
                    )

                self.assertEqual(result["result"]["attack_result"]["status"], "invalid_attack")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
            finally:
                context.close()


if __name__ == "__main__":
    unittest.main()
