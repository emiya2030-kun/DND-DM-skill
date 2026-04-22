from __future__ import annotations

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
from tools.services.class_features.shared import ensure_cleric_runtime
from tools.services.class_features.cleric import UseDivineSpark


def _build_cleric() -> EncounterEntity:
    cleric = EncounterEntity(
        entity_id="ent_cleric_001",
        name="Cleric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=17,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        ability_mods={"wis": 4},
        class_features={"cleric": {"level": 10}},
    )
    ensure_cleric_runtime(cleric)
    return cleric


def _build_ally_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_target_001",
        name="Ally",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 2},
        hp={"current": 4, "max": 14, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def _build_enemy_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_target_001",
        name="Skeleton",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
    )


def _build_encounter() -> Encounter:
    cleric = _build_cleric()
    ally_target = _build_ally_target()
    enemy_target = _build_enemy_target()
    return Encounter(
        encounter_id="enc_cleric_test",
        name="Cleric Test Encounter",
        status="active",
        round=1,
        current_entity_id=cleric.entity_id,
        turn_order=[cleric.entity_id, ally_target.entity_id, enemy_target.entity_id],
        entities={
            cleric.entity_id: cleric,
            ally_target.entity_id: ally_target,
            enemy_target.entity_id: enemy_target,
        },
        map=EncounterMap(
            map_id="map_cleric_test",
            name="Cleric Test Map",
            description="A small shrine.",
            width=8,
            height=8,
        ),
    )


def test_use_divine_spark_heals_target_and_spends_channel_divinity() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseDivineSpark(repo, append_event).execute(
            encounter_id="enc_cleric_test",
            actor_id="ent_cleric_001",
            target_id="ent_ally_target_001",
            mode="heal",
            rolled_value=6,
        )

        updated = repo.get("enc_cleric_test")
        assert updated is not None
        cleric = updated.entities["ent_cleric_001"]
        target = updated.entities["ent_ally_target_001"]
        assert target.hp["current"] == 14
        assert cleric.class_features["cleric"]["channel_divinity"]["remaining_uses"] == 2
        assert cleric.action_economy["action_used"] is True
        assert result["total_points"] == 10
        assert result["mode"] == "heal"

        events = append_event.list_by_encounter("enc_cleric_test")
        assert events[-1].event_type == "class_feature_divine_spark_used"
        assert events[-1].payload["class_feature_id"] == "cleric.divine_spark"

        repo.close()
        event_repo.close()


def test_use_divine_spark_damages_target_and_spends_channel_divinity() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseDivineSpark(repo, append_event).execute(
            encounter_id="enc_cleric_test",
            actor_id="ent_cleric_001",
            target_id="ent_enemy_target_001",
            mode="damage",
            rolled_value=5,
        )

        updated = repo.get("enc_cleric_test")
        assert updated is not None
        cleric = updated.entities["ent_cleric_001"]
        target = updated.entities["ent_enemy_target_001"]
        assert target.hp["current"] == 9
        assert cleric.class_features["cleric"]["channel_divinity"]["remaining_uses"] == 2
        assert cleric.action_economy["action_used"] is True
        assert result["total_points"] == 9
        assert result["mode"] == "damage"

        repo.close()
        event_repo.close()


def test_use_divine_spark_rejects_when_no_channel_divinity_remaining() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_cleric_001"].class_features["cleric"]["channel_divinity"]["remaining_uses"] = 0
        repo.save(encounter)

        with pytest.raises(ValueError, match="divine_spark_no_remaining_uses"):
            UseDivineSpark(repo, append_event).execute(
                encounter_id="enc_cleric_test",
                actor_id="ent_cleric_001",
                target_id="ent_ally_target_001",
                mode="heal",
                rolled_value=4,
            )

        repo.close()
        event_repo.close()
