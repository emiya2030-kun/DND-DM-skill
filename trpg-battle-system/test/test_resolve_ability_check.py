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

    def test_execute_applies_rogue_expertise_to_skill_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].skill_modifiers = {}
            encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["stealth"]
            encounter.entities["ent_ally_sabur_001"].class_features["rogue"] = {
                "level": 1,
                "expertise": {"skills": ["stealth"]},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="stealth",
                dc=15,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=10,
            )

            self.assertEqual(result.final_total, 17)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["proficiency_bonus_applied"], 4)
            repo.close()

    def test_execute_applies_ranger_expertise_to_skill_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].skill_modifiers = {}
            encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["survival"]
            encounter.entities["ent_ally_sabur_001"].class_features["ranger"] = {
                "level": 2,
                "expertise": {"skills": ["survival"]},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="survival",
                dc=15,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=10,
            )

            self.assertEqual(result.final_total, 16)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["proficiency_bonus_applied"], 4)
            repo.close()

    def test_execute_reliable_talent_raises_low_skill_roll_to_ten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].skill_modifiers = {}
            encounter.entities["ent_ally_sabur_001"].source_ref["skill_proficiencies"] = ["stealth"]
            encounter.entities["ent_ally_sabur_001"].class_features["rogue"] = {
                "level": 7,
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="stealth",
                dc=15,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=3,
            )

            self.assertEqual(result.metadata["chosen_roll"], 10)
            self.assertEqual(result.final_total, 15)
            repo.close()

    def test_execute_tactical_mind_keeps_second_wind_when_bonus_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_sabur_001"]
            actor.class_features["fighter"] = {
                "level": 2,
                "second_wind": {"remaining_uses": 2},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="str",
                dc=20,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=6,
                metadata={"class_feature_options": {"tactical_mind": True}, "tactical_mind_bonus_roll": 3},
            )

            updated = repo.get("enc_ability_check_test")
            self.assertEqual(result.final_total, 10)
            self.assertEqual(result.metadata["tactical_mind"]["bonus_roll"], 3)
            self.assertFalse(result.metadata["tactical_mind"]["consumed_second_wind"])
            self.assertEqual(updated.entities["ent_ally_sabur_001"].class_features["fighter"]["second_wind"]["remaining_uses"], 2)
            repo.close()

    def test_execute_primal_knowledge_allows_strength_for_stealth_while_raging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_sabur_001"]
            actor.skill_modifiers = {}
            actor.ability_mods["str"] = 4
            actor.ability_mods["dex"] = 1
            actor.source_ref["skill_proficiencies"] = ["stealth"]
            actor.class_features["barbarian"] = {
                "level": 3,
                "rage": {"active": True},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="stealth",
                dc=14,
                class_feature_options={"primal_knowledge": True},
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_rolls=[6, 12],
            )

            self.assertEqual(result.metadata["vantage"], "advantage")
            self.assertEqual(result.metadata["chosen_roll"], 12)
            self.assertEqual(result.metadata["check_bonus_breakdown"]["ability"], "str")
            self.assertEqual(result.metadata["check_bonus_breakdown"]["ability_modifier"], 4)
            repo.close()

    def test_execute_rage_grants_advantage_on_strength_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_sabur_001"].class_features["barbarian"] = {
                "level": 1,
                "rage": {"active": True},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="str",
                dc=14,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_rolls=[4, 16],
            )

            self.assertEqual(result.metadata["vantage"], "advantage")
            self.assertEqual(result.metadata["chosen_roll"], 16)
            self.assertEqual(result.final_total, 17)
            repo.close()

    def test_execute_indomitable_might_raises_strength_check_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            actor = encounter.entities["ent_ally_sabur_001"]
            actor.ability_scores = {"str": 20, "dex": 16, "wis": 14}
            actor.ability_mods["str"] = 5
            actor.class_features["barbarian"] = {
                "level": 18,
                "indomitable_might": {"enabled": True},
            }
            repo.save(encounter)
            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="str",
                dc=21,
            )

            result = ResolveAbilityCheck(repo).execute(
                encounter_id="enc_ability_check_test",
                roll_request=request,
                base_roll=2,
            )

            self.assertEqual(result.final_total, 20)
            repo.close()


if __name__ == "__main__":
    unittest.main()
