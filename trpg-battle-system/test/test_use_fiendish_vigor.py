from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, UseFiendishVigor


def build_warlock(*, include_invocation: bool = True, temp_hp: int = 0) -> EncounterEntity:
    selected = [{"invocation_id": "fiendish_vigor"}] if include_invocation else []
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": temp_hp},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "warlock": {
                "level": 2,
                "eldritch_invocations": {
                    "selected": selected,
                },
            }
        },
    )


def build_encounter(*, include_invocation: bool = True, temp_hp: int = 0) -> Encounter:
    actor = build_warlock(include_invocation=include_invocation, temp_hp=temp_hp)
    target = EncounterEntity(
        entity_id="ent_target_001",
        name="Target",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )
    return Encounter(
        encounter_id="enc_fiendish_vigor_test",
        name="Fiendish Vigor Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_fiendish_vigor_test",
            name="Fiendish Vigor Test Map",
            description="A small test map.",
            width=8,
            height=8,
        ),
    )


def test_execute_grants_false_life_temp_hp_consumes_action_and_no_slots() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        result = UseFiendishVigor(encounter_repo, AppendEvent(event_repo)).execute(
            encounter_id="enc_fiendish_vigor_test",
            actor_id="ent_warlock_001",
        )

        updated = encounter_repo.get("enc_fiendish_vigor_test")
        assert updated is not None
        actor = updated.entities["ent_warlock_001"]
        assert actor.action_economy["action_used"] is True
        assert actor.hp["temp"] == 12
        assert actor.resources["pact_magic_slots"]["remaining"] == actor.resources["pact_magic_slots"]["max"] == 2
        assert result["class_feature_result"]["fiendish_vigor"]["temp_hp_after"] == 12
        assert result["class_feature_result"]["fiendish_vigor"]["temp_hp_decision"] == "replace"

        encounter_repo.close()
        event_repo.close()


def test_execute_keeps_existing_higher_temp_hp() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter(temp_hp=15))

        result = UseFiendishVigor(encounter_repo, AppendEvent(event_repo)).execute(
            encounter_id="enc_fiendish_vigor_test",
            actor_id="ent_warlock_001",
        )

        updated = encounter_repo.get("enc_fiendish_vigor_test")
        assert updated is not None
        actor = updated.entities["ent_warlock_001"]
        assert actor.hp["temp"] == 15
        assert result["class_feature_result"]["fiendish_vigor"]["temp_hp_decision"] == "kept_existing"

        encounter_repo.close()
        event_repo.close()


def test_execute_requires_selected_invocation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter(include_invocation=False))

        try:
            UseFiendishVigor(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_fiendish_vigor_test",
                actor_id="ent_warlock_001",
            )
        except ValueError as exc:
            assert str(exc) == "fiendish_vigor_not_available"
        else:
            raise AssertionError("expected fiendish_vigor_not_available")

        encounter_repo.close()
        event_repo.close()
