import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, ExecuteAbilityCheck
from test.test_ability_check_request import build_encounter


class ExecuteAbilityCheckTests(unittest.TestCase):
    def test_execute_auto_rolls_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            with patch("tools.services.checks.execute_ability_check.random.randint", return_value=11):
                result = ExecuteAbilityCheck(
                    encounter_repository=encounter_repo,
                    append_event=AppendEvent(event_repo),
                ).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="skill",
                    check="察觉",
                    dc=13,
                    include_encounter_state=True,
                )

            self.assertEqual(result["check"], "察觉")
            self.assertEqual(result["normalized_check"], "perception")
            self.assertIn("roll_result", result)
            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_ability_check_test")
            encounter_repo.close()
            event_repo.close()

    def test_execute_tactical_mind_turns_failed_check_into_success_and_spends_second_wind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_sabur_001"]
            actor.class_features["fighter"] = {
                "level": 2,
                "second_wind": {"remaining_uses": 2},
            }
            encounter_repo.save(encounter)

            with patch("tools.services.checks.execute_ability_check.random.randint", return_value=8):
                result = ExecuteAbilityCheck(
                    encounter_repository=encounter_repo,
                    append_event=AppendEvent(event_repo),
                ).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="ability",
                    check="力量",
                    dc=15,
                    class_feature_options={"tactical_mind": True},
                )

            updated = encounter_repo.get("enc_ability_check_test")
            self.assertTrue(result["success"])
            self.assertEqual(result["class_feature_result"]["tactical_mind"]["bonus_roll"], 8)
            self.assertTrue(result["class_feature_result"]["tactical_mind"]["consumed_second_wind"])
            self.assertEqual(updated.entities["ent_ally_sabur_001"].class_features["fighter"]["second_wind"]["remaining_uses"], 1)
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
