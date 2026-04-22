from __future__ import annotations

"""Font of Inspiration 服务测试。"""

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
from tools.services.class_features.bard import UseFontOfInspiration


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
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        resources={"spell_slots": {"1": {"max": 4, "remaining": 2}}},
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"bard": {"level": 5, "bardic_inspiration": {"uses_current": 1}}},
    )


def _build_encounter() -> Encounter:
    bard = _build_bard()
    return Encounter(
        encounter_id="enc_font_of_inspiration_test",
        name="Font of Inspiration Test",
        status="active",
        round=1,
        current_entity_id=bard.entity_id,
        turn_order=[bard.entity_id],
        entities={bard.entity_id: bard},
        map=EncounterMap(
            map_id="map_font_of_inspiration_test",
            name="Font of Inspiration Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def test_use_font_of_inspiration_consumes_spell_slot_and_restores_one_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseFontOfInspiration(repo, append_event).execute(
            encounter_id="enc_font_of_inspiration_test",
            actor_id="ent_bard_001",
        )

        updated = repo.get("enc_font_of_inspiration_test")
        assert updated is not None
        bard = updated.entities["ent_bard_001"]
        assert bard.resources["spell_slots"]["1"]["remaining"] == 1
        assert bard.class_features["bard"]["bardic_inspiration"]["uses_current"] == 2
        assert result["class_feature_result"]["font_of_inspiration"]["slot_level"] == 1

        repo.close()
        event_repo.close()


def test_use_font_of_inspiration_rejects_when_no_use_is_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_bard_001"].class_features["bard"]["bardic_inspiration"]["uses_current"] = 4
        repo.save(encounter)

        with pytest.raises(ValueError, match="bardic_inspiration_already_full"):
            UseFontOfInspiration(repo, append_event).execute(
                encounter_id="enc_font_of_inspiration_test",
                actor_id="ent_bard_001",
            )

        repo.close()
        event_repo.close()
