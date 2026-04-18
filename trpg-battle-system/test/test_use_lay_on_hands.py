"""Lay on Hands 服务测试。"""

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
from tools.services.class_features.paladin import UseLayOnHands


def _build_paladin() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_paladin_001",
        name="Paladin",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        ability_mods={"cha": 3},
        class_features={"paladin": {"level": 5}},
    )


def _build_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Target",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 4, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        conditions=[],
    )


def _build_encounter() -> Encounter:
    paladin = _build_paladin()
    target = _build_target()
    return Encounter(
        encounter_id="enc_paladin_test",
        name="Paladin Test Encounter",
        status="active",
        round=1,
        current_entity_id=paladin.entity_id,
        turn_order=[paladin.entity_id, target.entity_id],
        entities={paladin.entity_id: paladin, target.entity_id: target},
        map=EncounterMap(
            map_id="map_paladin_test",
            name="Paladin Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def test_use_lay_on_hands_heals_target_and_spends_pool() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseLayOnHands(repo, append_event).execute(
            encounter_id="enc_paladin_test",
            actor_id="ent_paladin_001",
            target_id="ent_target_001",
            heal_amount=6,
        )

        updated = repo.get("enc_paladin_test")
        assert updated is not None
        assert updated.entities["ent_target_001"].hp["current"] == 10
        assert updated.entities["ent_paladin_001"].class_features["paladin"]["lay_on_hands"]["pool_remaining"] == 19
        assert updated.entities["ent_paladin_001"].action_economy["bonus_action_used"] is True
        assert result["pool_spent"] == 6
        assert result["pool_remaining"] == 19
        assert result["hp_restored"] == 6

        repo.close()
        event_repo.close()


def test_use_lay_on_hands_cures_poison_and_spends_five_pool() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_target_001"].conditions = ["poisoned"]
        repo.save(encounter)

        result = UseLayOnHands(repo, append_event).execute(
            encounter_id="enc_paladin_test",
            actor_id="ent_paladin_001",
            target_id="ent_target_001",
            heal_amount=0,
            cure_poison=True,
        )

        updated = repo.get("enc_paladin_test")
        assert updated is not None
        assert "poisoned" not in updated.entities["ent_target_001"].conditions
        assert updated.entities["ent_paladin_001"].class_features["paladin"]["lay_on_hands"]["pool_remaining"] == 20
        assert result["pool_spent"] == 5
        assert result["poison_removed"] is True
        assert result["hp_restored"] == 0

        repo.close()
        event_repo.close()


def test_use_lay_on_hands_rejects_when_bonus_action_already_used() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_paladin_001"].action_economy["bonus_action_used"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="bonus_action_already_used"):
            UseLayOnHands(repo, append_event).execute(
                encounter_id="enc_paladin_test",
                actor_id="ent_paladin_001",
                target_id="ent_target_001",
                heal_amount=4,
            )

        repo.close()
        event_repo.close()


def test_use_lay_on_hands_removes_multiple_supported_conditions_and_heals_in_one_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_paladin_001"].class_features = {"paladin": {"level": 14}}
        encounter.entities["ent_target_001"].conditions = ["poisoned", "paralyzed", "stunned"]
        repo.save(encounter)

        result = UseLayOnHands(repo, append_event).execute(
            encounter_id="enc_paladin_test",
            actor_id="ent_paladin_001",
            target_id="ent_target_001",
            heal_amount=5,
            cure_poison=True,
            remove_conditions=["paralyzed", "stunned"],
        )

        updated = repo.get("enc_paladin_test")
        assert updated is not None
        assert updated.entities["ent_target_001"].hp["current"] == 9
        assert updated.entities["ent_target_001"].conditions == []
        assert result["pool_spent"] == 20
        assert result["poison_removed"] is True
        assert result["conditions_removed"] == ["paralyzed", "stunned"]
        assert result["pool_spent_on_condition_removal"] == 10
        assert updated.entities["ent_paladin_001"].class_features["paladin"]["lay_on_hands"]["pool_remaining"] == 50

        repo.close()
        event_repo.close()


def test_use_lay_on_hands_does_not_charge_for_missing_or_invalid_conditions_but_still_spends_bonus_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_paladin_001"].class_features = {"paladin": {"level": 14}}
        repo.save(encounter)

        result = UseLayOnHands(repo, append_event).execute(
            encounter_id="enc_paladin_test",
            actor_id="ent_paladin_001",
            target_id="ent_target_001",
            remove_conditions=["paralyzed", "frozen"],
        )

        updated = repo.get("enc_paladin_test")
        assert updated is not None
        assert result["pool_spent"] == 0
        assert result["conditions_not_present"] == ["paralyzed"]
        assert result["invalid_requested_conditions"] == ["frozen"]
        assert updated.entities["ent_paladin_001"].action_economy["bonus_action_used"] is True
        assert updated.entities["ent_paladin_001"].class_features["paladin"]["lay_on_hands"]["pool_remaining"] == 70

        repo.close()
        event_repo.close()


def test_use_lay_on_hands_rejects_when_pool_cannot_cover_combined_cost() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_paladin_001"].class_features = {"paladin": {"level": 5}}
        encounter.entities["ent_target_001"].conditions = ["poisoned", "paralyzed"]
        repo.save(encounter)

        with pytest.raises(ValueError, match="lay_on_hands_pool_insufficient"):
            UseLayOnHands(repo, append_event).execute(
                encounter_id="enc_paladin_test",
                actor_id="ent_paladin_001",
                target_id="ent_target_001",
                heal_amount=20,
                cure_poison=True,
                remove_conditions=["paralyzed"],
            )

        repo.close()
        event_repo.close()
