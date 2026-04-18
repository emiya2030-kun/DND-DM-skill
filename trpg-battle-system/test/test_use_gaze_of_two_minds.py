from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.class_features.warlock import UseGazeOfTwoMinds


def build_warlock() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Watcher",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        class_features={
            "warlock": {
                "level": 5,
                "eldritch_invocations": {
                    "selected": [
                        {"invocation_id": "gaze_of_two_minds"},
                    ]
                },
            }
        },
    )


def build_ally() -> EncounterEntity:
    ally = EncounterEntity(
        entity_id="ent_ally_001",
        name="Scout",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        source_ref={"special_senses": {"darkvision": 60}},
    )
    return ally


def build_encounter() -> Encounter:
    warlock = build_warlock()
    ally = build_ally()
    return Encounter(
        encounter_id="enc_gaze_test",
        name="Gaze Test",
        status="active",
        round=1,
        current_entity_id=warlock.entity_id,
        turn_order=[warlock.entity_id, ally.entity_id],
        entities={warlock.entity_id: warlock, ally.entity_id: ally},
        map=EncounterMap(
            map_id="map_gaze_test",
            name="Gaze Test Map",
            description="A minimal map for gaze tests.",
            width=10,
            height=10,
        ),
    )


def test_execute_establishes_gaze_of_two_minds_link_and_consumes_bonus_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        result = UseGazeOfTwoMinds(encounter_repo, AppendEvent(event_repo)).execute(
            encounter_id="enc_gaze_test",
            actor_id="ent_warlock_001",
            target_id="ent_ally_001",
        )

        updated = encounter_repo.get("enc_gaze_test")
        assert updated is not None
        warlock = updated.entities["ent_warlock_001"].class_features["warlock"]
        gaze = warlock["gaze_of_two_minds"]
        assert gaze["linked_entity_id"] == "ent_ally_001"
        assert gaze["linked_entity_name"] == "Scout"
        assert gaze["remaining_source_turn_ends"] == 2
        assert gaze["special_senses"] == {"darkvision": 60}
        assert updated.entities["ent_warlock_001"].action_economy["bonus_action_used"] is True
        assert result["class_feature_result"]["gaze_of_two_minds"]["can_cast_via_link"] is True

        encounter_repo.close()
        event_repo.close()
