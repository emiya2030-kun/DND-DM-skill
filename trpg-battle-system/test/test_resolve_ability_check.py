import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EncounterRepository
from tools.services import AbilityCheckRequest, ResolveAbilityCheck
from test.test_ability_check_request import build_encounter


class ResolveAbilityCheckTests(unittest.TestCase):
    def test_execute_uses_skill_modifier_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="隐匿",
                dc=15,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=12,
            )

            self.assertEqual(result.final_total, 17)
            self.assertEqual(result.metadata["check_bonus"], 5)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["source"], "skill_modifier")
            repo.close()

    def test_execute_falls_back_to_ability_plus_proficiency_for_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].skill_modifiers = {}
            encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["perception"]
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="察觉",
                dc=13,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=10,
            )

            self.assertEqual(result.final_total, 14)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["ability_modifier"], 2)
            self.assertTrue(result.metadata["check_bonus_breakdown"]["is_proficient"])
            repo.close()

    def test_execute_supports_advantage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="dex",
                dc=14,
                vantage="advantage",
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_rolls=[4, 17],
                additional_bonus=1,
            )

            self.assertEqual(result.metadata["vantage"], "advantage")
            self.assertEqual(result.metadata["chosen_roll"], 17)
            self.assertEqual(result.final_total, 21)
            repo.close()

    def test_execute_applies_exhaustion_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].conditions = ["exhaustion:2"]
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="wis",
                dc=10,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=14,
            )

            self.assertEqual(result.final_total, 12)
            self.assertEqual(result.metadata["d20_penalty"], 4)
            repo.close()


if __name__ == "__main__":
    unittest.main()
