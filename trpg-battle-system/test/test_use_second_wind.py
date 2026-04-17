"""Second Wind 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.class_features.fighter import UseSecondWind


def _build_fighter() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 10, "max": 20, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "fighter": {
                "level": 3,
                "second_wind": {"remaining_uses": 2},
            }
        },
    )


def _build_encounter() -> Encounter:
    fighter = _build_fighter()
    return Encounter(
        encounter_id="enc_fighter_test",
        name="Fighter Test Encounter",
        status="active",
        round=1,
        current_entity_id=fighter.entity_id,
        turn_order=[fighter.entity_id],
        entities={fighter.entity_id: fighter},
        map=EncounterMap(
            map_id="map_fighter_test",
            name="Fighter Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def _build_other_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_other_001",
        name="Other Actor",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def test_use_second_wind_heals_and_consumes_bonus_action_and_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseSecondWind(repo, append_event).execute(
            encounter_id="enc_fighter_test",
            actor_id="ent_fighter_001",
            healing_roll={"rolls": [7]},
        )
        updated = repo.get("enc_fighter_test")
        assert updated is not None
        assert updated.entities["ent_fighter_001"].hp["current"] == 20
        assert updated.entities["ent_fighter_001"].action_economy["bonus_action_used"] is True
        assert updated.entities["ent_fighter_001"].class_features["fighter"]["second_wind"]["remaining_uses"] == 1
        assert result["encounter_state"]["encounter_id"] == "enc_fighter_test"

        repo.close()
        event_repo.close()


def test_use_second_wind_returns_tactical_shift_movement_allowance() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseSecondWind(repo, append_event).execute(
            encounter_id="enc_fighter_test",
            actor_id="ent_fighter_001",
            healing_roll={"rolls": [4]},
        )

        assert result["class_feature_result"]["free_movement_after_second_wind"]["feet"] == 15
        assert result["class_feature_result"]["free_movement_after_second_wind"]["ignore_opportunity_attacks"] is True

        repo.close()
        event_repo.close()


def test_use_second_wind_rejects_when_not_actor_turn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        other = _build_other_actor()
        encounter.current_entity_id = other.entity_id
        encounter.turn_order.append(other.entity_id)
        encounter.entities[other.entity_id] = other
        repo.save(encounter)

        with pytest.raises(ValueError, match="not_actor_turn"):
            UseSecondWind(repo, append_event).execute(
                encounter_id="enc_fighter_test",
                actor_id="ent_fighter_001",
                healing_roll={"rolls": [4]},
            )

        repo.close()
        event_repo.close()


def test_use_second_wind_rejects_when_bonus_action_already_used() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_fighter_001"].action_economy["bonus_action_used"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="bonus_action_already_used"):
            UseSecondWind(repo, append_event).execute(
                encounter_id="enc_fighter_test",
                actor_id="ent_fighter_001",
                healing_roll={"rolls": [4]},
            )

        repo.close()
        event_repo.close()


def test_use_second_wind_rejects_when_no_remaining_uses() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_fighter_001"].class_features["fighter"]["second_wind"]["remaining_uses"] = 0
        repo.save(encounter)

        with pytest.raises(ValueError, match="second_wind_no_remaining_uses"):
            UseSecondWind(repo, append_event).execute(
                encounter_id="enc_fighter_test",
                actor_id="ent_fighter_001",
                healing_roll={"rolls": [4]},
            )

        repo.close()
        event_repo.close()
