"""借机攻击请求构造测试：覆盖玩家确认型与怪物自动型请求。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.services.combat.rules.opportunity_attacks.build_opportunity_request import build_opportunity_request


def build_player_melee() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 4},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )


def build_enemy_mover() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_orc_001",
        name="Orc",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 4},
        hp={"current": 15, "max": 15, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_monster_melee() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 4},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


class BuildOpportunityRequestTests(unittest.TestCase):
    def test_build_request_marks_player_prompt_for_enemy_leaving_reach(self) -> None:
        attacker = build_player_melee()
        target = build_enemy_mover()

        request = build_opportunity_request(
            actor=attacker,
            target=target,
            trigger_position={"x": 5, "y": 4},
            weapon={"weapon_id": "rapier", "name": "Rapier"},
        )

        self.assertEqual(request["reaction_type"], "opportunity_attack")
        self.assertTrue(request["ask_player"])
        self.assertFalse(request["auto_resolve"])
        self.assertEqual(request["payload"]["weapon_id"], "rapier")

    def test_build_request_marks_monster_reaction_as_auto_resolve(self) -> None:
        attacker = build_monster_melee()
        target = build_player_melee()

        request = build_opportunity_request(
            actor=attacker,
            target=target,
            trigger_position={"x": 5, "y": 4},
            weapon={"weapon_id": "scimitar", "name": "Scimitar"},
        )

        self.assertFalse(request["ask_player"])
        self.assertTrue(request["auto_resolve"])
        self.assertEqual(request["payload"]["weapon_name"], "Scimitar")


if __name__ == "__main__":
    unittest.main()
