"""Tests for opening an Indomitable failed-save reaction window."""

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


def build_fighter() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=17,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        ability_scores={"str": 18, "dex": 10, "con": 14, "int": 10, "wis": 12, "cha": 8},
        ability_mods={"str": 4, "dex": 0, "con": 2, "int": 0, "wis": 1, "cha": -1},
        proficiency_bonus=4,
        save_proficiencies=["str", "con"],
        action_economy={"reaction_used": True},
        class_features={
            "fighter": {
                "fighter_level": 9,
                "indomitable": {"remaining_uses": 1, "max_uses": 1},
            }
        },
    )


def build_encounter() -> Encounter:
    fighter = build_fighter()
    return Encounter(
        encounter_id="enc_indomitable_window_test",
        name="Indomitable Window Test",
        status="active",
        round=1,
        current_entity_id=fighter.entity_id,
        turn_order=[fighter.entity_id],
        entities={fighter.entity_id: fighter},
        map=EncounterMap(
            map_id="map_indomitable_window_test",
            name="Indomitable Window Map",
            description="Map for indomitable reaction window tests.",
            width=6,
            height=6,
        ),
    )


def build_failed_save_trigger(target_entity_id: str) -> dict[str, object]:
    return {
        "event_id": "evt_failed_save_001",
        "trigger_type": "failed_save",
        "host_action_type": "save",
        "host_action_id": "save_001",
        "host_action_snapshot": {
            "phase": "after_failed_save",
            "target_entity_id": target_entity_id,
            "save_ability": "wis",
            "save_dc": 15,
        },
        "target_entity_id": target_entity_id,
        "request_payloads": {
            target_entity_id: {
                "save_ability": "wis",
                "save_dc": 15,
                "vantage": "normal",
            }
        },
    }


class IndomitableReactionWindowTests(unittest.TestCase):
    def test_failed_save_opens_indomitable_window_for_fighter(self) -> None:
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
                trigger_event=build_failed_save_trigger(encounter.current_entity_id),
            )

            self.assertEqual(result["status"], "waiting_reaction")
            choice_groups = result["pending_reaction_window"]["choice_groups"]
            self.assertEqual(len(choice_groups), 1)
            self.assertEqual(choice_groups[0]["actor_entity_id"], encounter.current_entity_id)
            self.assertEqual(choice_groups[0]["options"][0]["reaction_type"], "indomitable")
            repository.close()
