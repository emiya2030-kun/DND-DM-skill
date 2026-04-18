import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_use_help_attack import build_encounter, build_shared_turn_summon


class RuntimeUseHelpAttackTests(unittest.TestCase):
    def test_command_handlers_include_use_help_attack(self) -> None:
        self.assertIn("use_help_attack", COMMAND_HANDLERS)

    def test_use_help_attack_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.use_help_attack", fromlist=["use_help_attack"])

                with patch.object(
                    module.UseHelpAttack,
                    "execute",
                    return_value={
                        "encounter_id": "enc_help_attack_test",
                        "actor_id": "ent_actor_001",
                        "target_id": "ent_enemy_001",
                        "encounter_state": {"encounter_id": "enc_help_attack_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="use_help_attack",
                        args={
                            "encounter_id": "enc_help_attack_test",
                            "actor_id": "ent_actor_001",
                            "target_id": "ent_enemy_001",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_help_attack_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_help_attack_test")
                self.assertEqual(kwargs["actor_id"], "ent_actor_001")
                self.assertEqual(kwargs["target_id"], "ent_enemy_001")
            finally:
                context.close()

    def test_use_help_attack_executes_for_shared_turn_summon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                encounter = build_encounter()
                summon = build_shared_turn_summon()
                encounter.entities[summon.entity_id] = summon
                context.encounter_repository.save(encounter)

                result = execute_runtime_command(
                    context,
                    command="use_help_attack",
                    args={
                        "encounter_id": "enc_help_attack_test",
                        "actor_id": "ent_summon_001",
                        "target_id": "ent_enemy_001",
                    },
                    handlers=COMMAND_HANDLERS,
                )

                self.assertTrue(result["ok"])
                self.assertEqual(result["result"]["actor_id"], "ent_summon_001")
                target = context.encounter_repository.get("enc_help_attack_test").entities["ent_enemy_001"]
                self.assertTrue(any(effect.get("effect_type") == "help_attack" for effect in target.turn_effects))
            finally:
                context.close()
