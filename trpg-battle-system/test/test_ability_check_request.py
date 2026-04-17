import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services import AbilityCheckRequest


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_sabur_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 21, "max": 21, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        ability_mods={"str": 1, "dex": 3, "wis": 2},
        proficiency_bonus=2,
        skill_modifiers={"stealth": 5},
        save_proficiencies=["dex"],
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    return Encounter(
        encounter_id="enc_ability_check_test",
        name="Ability Check Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id],
        entities={actor.entity_id: actor},
        map=EncounterMap(
            map_id="map_ability_check_test",
            name="Ability Check Test Map",
            description="Ability check room.",
            width=6,
            height=6,
        ),
    )


class AbilityCheckRequestTests(unittest.TestCase):
    def test_execute_builds_skill_check_request_with_alias_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="skill",
                check="潜行",
                dc=15,
                vantage="advantage",
                reason="Sabur hides behind the wall",
            )

            self.assertEqual(request.roll_type, "ability_check")
            self.assertEqual(request.actor_entity_id, "ent_ally_sabur_001")
            self.assertEqual(request.formula, "1d20+check_modifier")
            self.assertEqual(request.context["check_type"], "skill")
            self.assertEqual(request.context["check"], "stealth")
            self.assertEqual(request.context["dc"], 15)
            self.assertEqual(request.context["vantage"], "advantage")
            repo.close()

    def test_execute_builds_ability_check_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = AbilityCheckRequest(repo).execute(
                encounter_id="enc_ability_check_test",
                actor_id="ent_ally_sabur_001",
                check_type="ability",
                check="力量",
                dc=12,
            )

            self.assertEqual(request.context["check_type"], "ability")
            self.assertEqual(request.context["check"], "str")
            repo.close()

    def test_execute_rejects_unknown_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaisesRegex(ValueError, "unknown_skill_check"):
                AbilityCheckRequest(repo).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="skill",
                    check="潜伏术",
                    dc=15,
                )
            repo.close()

    def test_execute_requires_integer_dc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaisesRegex(ValueError, "dc must be an integer"):
                AbilityCheckRequest(repo).execute(
                    encounter_id="enc_ability_check_test",
                    actor_id="ent_ally_sabur_001",
                    check_type="skill",
                    check="stealth",
                    dc="15",
                )
            repo.close()


if __name__ == "__main__":
    unittest.main()
