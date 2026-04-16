import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from runtime.commands.move_and_attack import move_and_attack
from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeMoveAndAttackTests(unittest.TestCase):
    def test_returns_waiting_reaction_without_executing_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)

                move_and_attack_module = import_module("runtime.commands.move_and_attack")

                with patch.object(
                    move_and_attack_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_enemy_brute_001",
                        "movement_status": "waiting_reaction",
                        "reaction_requests": [{"request_id": "react_001"}],
                        "encounter_state": {
                            "encounter_id": "enc_preview_demo",
                            "reaction_requests": [{"request_id": "react_001"}],
                        },
                    },
                ) as mocked_move:
                    with patch.object(move_and_attack_module.ExecuteAttack, "execute") as mocked_execute_attack:
                        result = move_and_attack(
                            context,
                            {
                                "encounter_id": "enc_preview_demo",
                                "actor_id": "ent_enemy_brute_001",
                                "target_position": {"x": 11, "y": 10},
                                "target_id": "ent_ally_ranger_001",
                                "weapon_id": "battleaxe",
                            },
                        )

                self.assertEqual(result["result"]["movement_result"]["movement_status"], "waiting_reaction")
                self.assertEqual(result["result"]["attack_result"], None)
                mocked_move.assert_called_once()
                mocked_execute_attack.assert_not_called()
            finally:
                context.close()

    def test_returns_structured_error_when_attack_invalid_after_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)

                move_and_attack_module = import_module("runtime.commands.move_and_attack")

                with patch.object(
                    move_and_attack_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_ally_ranger_001",
                        "movement_status": "completed",
                        "reaction_requests": [],
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    with patch.object(
                        move_and_attack_module.ExecuteAttack,
                        "execute",
                        return_value={
                            "status": "invalid_attack",
                            "reason": "target_out_of_range",
                            "message_for_llm": "当前目标不在攻击范围内，请重新选择目标或调整位置。",
                            "encounter_state": {"encounter_id": "enc_preview_demo"},
                        },
                    ):
                        result = move_and_attack(
                            context,
                            {
                                "encounter_id": "enc_preview_demo",
                                "actor_id": "ent_ally_ranger_001",
                                "target_position": {"x": 8, "y": 10},
                                "target_id": "ent_enemy_brute_001",
                                "weapon_id": "shortbow",
                                "attack_roll": {
                                    "final_total": 15,
                                    "dice_rolls": {"base_rolls": [12], "modifier": 3},
                                },
                            },
                        )

                self.assertEqual(result["error_code"], "attack_invalid_after_movement")
                self.assertEqual(result["result"]["movement_result"]["movement_status"], "completed")
                self.assertEqual(result["result"]["attack_result"]["reason"], "target_out_of_range")
            finally:
                context.close()

    def test_raises_value_error_when_required_pre_movement_field_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                with self.assertRaisesRegex(ValueError, "encounter_id is required"):
                    move_and_attack(
                        context,
                        {
                            "actor_id": "ent_ally_ranger_001",
                            "target_position": {"x": 8, "y": 10},
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "shortbow",
                        },
                    )
            finally:
                context.close()

    def test_ignores_partial_attack_roll_payload_after_movement_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_and_attack_module = import_module("runtime.commands.move_and_attack")
                with patch.object(
                    move_and_attack_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_ally_ranger_001",
                        "movement_status": "completed",
                        "reaction_requests": [],
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    with patch.object(
                        move_and_attack_module.ExecuteAttack,
                        "execute",
                        return_value={
                            "request": {"encounter_id": "enc_preview_demo"},
                            "roll_result": {
                                "final_total": 15,
                                "dice_rolls": {"base_rolls": [12], "modifier": 3},
                            },
                            "resolution": {"hit": True},
                            "encounter_state": {"encounter_id": "enc_preview_demo"},
                        },
                    ) as mocked_execute:
                        move_and_attack(
                            context,
                            {
                                "encounter_id": "enc_preview_demo",
                                "actor_id": "ent_ally_ranger_001",
                                "target_position": {"x": 8, "y": 10},
                                "target_id": "ent_enemy_brute_001",
                                "weapon_id": "shortbow",
                                "attack_roll": {"dice_rolls": {"base_rolls": [12], "modifier": 3}},
                            },
                        )
                _, kwargs = mocked_execute.call_args
                self.assertNotIn("final_total", kwargs)
                self.assertNotIn("dice_rolls", kwargs)
            finally:
                context.close()

    def test_executes_attack_without_external_attack_roll_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_and_attack_module = import_module("runtime.commands.move_and_attack")
                with patch.object(
                    move_and_attack_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_ally_ranger_001",
                        "movement_status": "completed",
                        "reaction_requests": [],
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    with patch.object(
                        move_and_attack_module.ExecuteAttack,
                        "execute",
                        return_value={
                            "request": {"encounter_id": "enc_preview_demo"},
                            "roll_result": {
                                "final_total": 15,
                                "dice_rolls": {"base_rolls": [12], "modifier": 3},
                            },
                            "resolution": {"hit": True},
                            "encounter_state": {"encounter_id": "enc_preview_demo"},
                        },
                    ) as mocked_execute:
                        result = move_and_attack(
                            context,
                            {
                                "encounter_id": "enc_preview_demo",
                                "actor_id": "ent_ally_ranger_001",
                                "target_position": {"x": 8, "y": 10},
                                "target_id": "ent_enemy_brute_001",
                                "weapon_id": "shortbow",
                            },
                        )

                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
                mocked_execute.assert_called_once()
                _, kwargs = mocked_execute.call_args
                self.assertNotIn("final_total", kwargs)
                self.assertNotIn("dice_rolls", kwargs)
                self.assertNotIn("damage_rolls", kwargs)
            finally:
                context.close()

    def test_ignores_invalid_attack_roll_final_total_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_and_attack_module = import_module("runtime.commands.move_and_attack")
                with patch.object(
                    move_and_attack_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_ally_ranger_001",
                        "movement_status": "completed",
                        "reaction_requests": [],
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    for invalid_total in [True, "15"]:
                        with self.subTest(invalid_total=invalid_total):
                            with patch.object(
                                move_and_attack_module.ExecuteAttack,
                                "execute",
                                return_value={
                                    "request": {"encounter_id": "enc_preview_demo"},
                                    "roll_result": {
                                        "final_total": 15,
                                        "dice_rolls": {"base_rolls": [12], "modifier": 3},
                                    },
                                    "resolution": {"hit": True},
                                    "encounter_state": {"encounter_id": "enc_preview_demo"},
                                },
                            ) as mocked_execute:
                                move_and_attack(
                                    context,
                                    {
                                        "encounter_id": "enc_preview_demo",
                                        "actor_id": "ent_ally_ranger_001",
                                        "target_position": {"x": 8, "y": 10},
                                        "target_id": "ent_enemy_brute_001",
                                        "weapon_id": "shortbow",
                                        "attack_roll": {
                                            "final_total": invalid_total,
                                            "dice_rolls": {"base_rolls": [12], "modifier": 3},
                                        },
                                    },
                                )
                            _, kwargs = mocked_execute.call_args
                            self.assertNotIn("final_total", kwargs)
                            self.assertNotIn("dice_rolls", kwargs)
            finally:
                context.close()
