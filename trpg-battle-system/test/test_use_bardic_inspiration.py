from __future__ import annotations

"""Bardic Inspiration 服务测试。"""

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
from tools.services.class_features.bard import UseBardicInspiration


def _build_bard() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_bard_001",
        name="诗人",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"cha": 3},
        proficiency_bonus=3,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"bard": {"level": 5}},
    )


def _build_target(*, entity_id: str = "ent_target_001", x: int = 14, y: int = 2) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name="盟友",
        side="ally",
        category="pc",
        controller="player",
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
    )


def _build_encounter(*, target: EncounterEntity | None = None) -> Encounter:
    bard = _build_bard()
    target_entity = target or _build_target()
    return Encounter(
        encounter_id="enc_bardic_inspiration_test",
        name="Bardic Inspiration Test",
        status="active",
        round=1,
        current_entity_id=bard.entity_id,
        turn_order=[bard.entity_id, target_entity.entity_id],
        entities={bard.entity_id: bard, target_entity.entity_id: target_entity},
        map=EncounterMap(
            map_id="map_bardic_inspiration_test",
            name="Bardic Inspiration Test Map",
            description="A small combat room.",
            width=20,
            height=20,
        ),
    )


def test_use_bardic_inspiration_grants_die_and_consumes_bonus_action_and_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseBardicInspiration(repo, append_event).execute(
            encounter_id="enc_bardic_inspiration_test",
            actor_id="ent_bard_001",
            target_id="ent_target_001",
        )

        updated = repo.get("enc_bardic_inspiration_test")
        assert updated is not None
        bard = updated.entities["ent_bard_001"]
        target = updated.entities["ent_target_001"]
        assert bard.action_economy["bonus_action_used"] is True
        assert bard.class_features["bard"]["bardic_inspiration"]["uses_current"] == 2
        assert target.combat_flags["bardic_inspiration"]["die"] == "d8"
        assert target.combat_flags["bardic_inspiration"]["source_entity_id"] == "ent_bard_001"
        assert result["class_feature_result"]["bardic_inspiration"]["granted_die"] == "d8"

        repo.close()
        event_repo.close()


def test_use_bardic_inspiration_rejects_self_target() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter(target=_build_target(entity_id="ent_other_001")))

        with pytest.raises(ValueError, match="bardic_inspiration_cannot_target_self"):
            UseBardicInspiration(repo, append_event).execute(
                encounter_id="enc_bardic_inspiration_test",
                actor_id="ent_bard_001",
                target_id="ent_bard_001",
            )

        repo.close()
        event_repo.close()


def test_use_bardic_inspiration_rejects_target_out_of_range() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter(target=_build_target(x=15, y=2)))

        with pytest.raises(ValueError, match="bardic_inspiration_target_out_of_range"):
            UseBardicInspiration(repo, append_event).execute(
                encounter_id="enc_bardic_inspiration_test",
                actor_id="ent_bard_001",
                target_id="ent_target_001",
            )

        repo.close()
        event_repo.close()
