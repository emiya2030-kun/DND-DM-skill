import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository, EventRepository
from tools.services import AbilityCheckRequest, AbilityCheckResult, AppendEvent, ResolveAbilityCheck
from test.test_ability_check_request import build_encounter


class AbilityCheckResultTests(unittest.TestCase):
    def test_execute_returns_success_comparison_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            request = AbilityCheckRequest(encounter_repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="stealth",
                dc=15,
            )
            roll_result = ResolveAbilityCheck(encounter_repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=12,
            )

            result = AbilityCheckResult(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                roll_result=roll_result,
            )

            self.assertTrue(result["success"])
            self.assertFalse(result["failed"])
            self.assertEqual(result["comparison"]["left_label"], "ability_check_total")
            self.assertEqual(result["comparison"]["right_value"], 15)
            self.assertIsInstance(result["event_id"], str)
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
