"""Tests for the open reaction window service."""

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


def build_defender(entity_id: str = "ent_actor_001") -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name="Defender",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 2},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_attack_declared_encounter() -> Encounter:
    defender = build_defender()
    return Encounter(
        encounter_id="enc_reaction_window_test",
        name="Reaction Window Test",
        status="active",
        round=1,
        current_entity_id=defender.entity_id,
        turn_order=[defender.entity_id],
        entities={defender.entity_id: defender},
        map=EncounterMap(
            map_id="map_reaction_window_test",
            name="Reaction Window Map",
            description="Map for reaction window tests.",
            width=6,
            height=6,
        ),
    )


def build_attack_trigger(target_entity_id: str) -> dict[str, object]:
    return {
        "event_id": "evt_attack_declared_001",
        "trigger_type": "attack_declared",
        "host_action_type": "attack",
        "host_action_id": "atk_001",
        "host_action_snapshot": {
            "attack_id": "atk_001",
            "actor_entity_id": "ent_enemy_001",
            "target_entity_id": target_entity_id,
            "attack_total": 17,
            "target_ac_before_reaction": 15,
            "phase": "before_hit_locked",
        },
        "target_entity_id": target_entity_id,
    }


class OpenReactionWindowTests(unittest.TestCase):
    def test_open_reaction_window_groups_multiple_options_by_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_attack_declared_encounter()
            repository.save(encounter)

            service = OpenReactionWindow(
                encounter_repository=repository,
                definition_repository=ReactionDefinitionRepository(),
            )
            result = service.execute(
                encounter_id=encounter.encounter_id,
                trigger_event=build_attack_trigger(encounter.current_entity_id),
            )

            self.assertEqual(result["status"], "waiting_reaction")
            choice_groups = result["pending_reaction_window"]["choice_groups"]
            self.assertEqual(len(choice_groups), 1)
            options = choice_groups[0]["options"]
            self.assertEqual({item["reaction_type"] for item in options}, {"shield", "absorb_elements"})
            self.assertEqual(choice_groups[0]["actor_entity_id"], encounter.current_entity_id)
            repository.close()
