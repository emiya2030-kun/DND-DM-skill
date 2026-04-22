"""Countercharm 失败豁免反应窗口测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, ReactionDefinitionRepository
from tools.services.combat.rules.reactions import OpenReactionWindow


def build_bard() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_bard_001",
        name="Bard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 2},
        hp={"current": 22, "max": 22, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        action_economy={"reaction_used": False},
        class_features={"bard": {"level": 7}},
    )


def build_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Target",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 7, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        ability_mods={"wis": 1},
        proficiency_bonus=3,
        save_proficiencies=["wis"],
        action_economy={"reaction_used": True},
    )


def build_encounter() -> Encounter:
    bard = build_bard()
    target = build_target()
    enemy = EncounterEntity(
        entity_id="ent_enemy_001",
        name="Enemy",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=18,
    )
    return Encounter(
        encounter_id="enc_countercharm_window_test",
        name="Countercharm Window Test",
        status="active",
        round=1,
        current_entity_id="ent_enemy_001",
        turn_order=["ent_enemy_001", bard.entity_id, target.entity_id],
        entities={enemy.entity_id: enemy, bard.entity_id: bard, target.entity_id: target},
        map=EncounterMap(
            map_id="map_countercharm_window_test",
            name="Countercharm Window Map",
            description="Map for countercharm reaction window tests.",
            width=10,
            height=10,
        ),
    )


class CountercharmReactionWindowTests(unittest.TestCase):
    def test_failed_save_opens_countercharm_window_for_nearby_bard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            repository.save(encounter)

            service = OpenReactionWindow(
                encounter_repository=repository,
                definition_repository=ReactionDefinitionRepository(),
            )
            result = service.execute(
                encounter_id=encounter.encounter_id,
                trigger_event={
                    "event_id": "evt_failed_save_001",
                    "trigger_type": "failed_save",
                    "host_action_type": "save",
                    "host_action_id": "save_001",
                    "host_action_snapshot": {
                        "phase": "after_failed_save",
                        "target_entity_id": "ent_target_001",
                        "save_ability": "wis",
                        "save_dc": 15,
                        "countercharm_trigger_conditions": ["frightened"],
                    },
                    "target_entity_id": "ent_target_001",
                    "request_payloads": {
                        "ent_bard_001": {
                            "countercharm": {
                                "target_entity_id": "ent_target_001",
                                "save_ability": "wis",
                                "save_dc": 15,
                                "vantage": "normal",
                            }
                        }
                    },
                },
            )

            self.assertEqual(result["status"], "waiting_reaction")
            choice_groups = result["pending_reaction_window"]["choice_groups"]
            self.assertEqual(len(choice_groups), 1)
            self.assertEqual(choice_groups[0]["actor_entity_id"], "ent_bard_001")
            self.assertEqual(choice_groups[0]["options"][0]["reaction_type"], "countercharm")
            repository.close()
